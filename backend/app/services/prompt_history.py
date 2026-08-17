"""模板提示词变更历史的记录与查询。

三个保存入口（PUT structure / PUT content-review-rules / PUT full-document）
在写入前调用本模块做自动 diff：值有变化的 (node_id, field) 各记一条
template_prompt_history。回滚通过 restore_prompt_history_entry 写回旧值，
并同样记一条 source=restore 的历史（回滚本身也可再回滚）。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SchemeTemplate, TemplatePromptHistory

# parsed_structure 节点里可追踪的提示词字段
_NODE_PROMPT_FIELDS = ("review_prompt", "context_consistency_prompt", "image_review")


def _field_value(field: str, raw: Any) -> str:
    """节点字段的规范字符串值。image_review 是结构化配置（勾选+说明），
    序列化为紧凑 JSON 便于 diff 与回滚。"""
    if field == "image_review":
        return image_review_to_history_value(raw)
    return _norm(raw)


def image_review_to_history_value(raw: Any) -> str:
    if not isinstance(raw, dict):
        return ""
    return json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _iter_nodes(nodes: list[dict[str, Any]]):
    for n in nodes:
        if isinstance(n, dict):
            yield n
            children = n.get("children")
            if isinstance(children, list):
                yield from _iter_nodes(children)


def _node_index(structure: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(structure, dict):
        return {}
    return {str(n.get("id") or ""): n for n in _iter_nodes(structure.get("nodes") or [])}


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def record_structure_diff(
    db: Session,
    *,
    template: SchemeTemplate,
    old_structure: dict[str, Any] | None,
    new_structure: dict[str, Any] | None,
    changed_by: str,
) -> int:
    """对比新旧 parsed_structure,记录节点提示词字段的变化。返回记录条数。"""
    old_nodes = _node_index(old_structure)
    new_nodes = _node_index(new_structure)
    count = 0
    for tid, new_node in new_nodes.items():
        old_node = old_nodes.get(tid, {})
        title = _norm(new_node.get("title"))
        for field in _NODE_PROMPT_FIELDS:
            old_v = _field_value(field, old_node.get(field))
            new_v = _field_value(field, new_node.get(field))
            if old_v == new_v:
                continue
            db.add(
                TemplatePromptHistory(
                    template_id=template.id,
                    node_id=tid,
                    field=field,
                    node_title=title,
                    old_value=old_v,
                    new_value=new_v,
                    source="manual",
                    changed_by=changed_by,
                )
            )
            count += 1
    return count


def record_full_document_diff(
    db: Session,
    *,
    template: SchemeTemplate,
    old_config: dict[str, Any] | None,
    new_config: dict[str, Any] | None,
    changed_by: str,
) -> int:
    """对比通篇审核配置的 review_prompt（扁平单值结构）。"""
    old_v = _norm((old_config or {}).get("review_prompt"))
    new_v = _norm((new_config or {}).get("review_prompt"))
    if old_v == new_v:
        return 0
    db.add(
        TemplatePromptHistory(
            template_id=template.id,
            node_id="",
            field="full_document_review_prompt",
            node_title="通篇审核",
            old_value=old_v,
            new_value=new_v,
            source="manual",
            changed_by=changed_by,
        )
    )
    return 1


def record_field_change(
    db: Session,
    *,
    template: SchemeTemplate,
    field: str,
    old_value: str,
    new_value: str,
    changed_by: str,
    node_id: str = "",
    node_title: str = "",
    source: str = "manual",
) -> None:
    """记录非节点级字段（如全局规则）的单值变化。"""
    if _norm(old_value) == _norm(new_value):
        return
    db.add(
        TemplatePromptHistory(
            template_id=template.id,
            node_id=node_id,
            field=field,
            node_title=node_title,
            old_value=_norm(old_value),
            new_value=_norm(new_value),
            source=source,
            changed_by=changed_by,
        )
    )


def load_structure(template: SchemeTemplate) -> dict[str, Any] | None:
    raw = getattr(template, "parsed_structure", None)
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None
    return raw if isinstance(raw, dict) else None


def list_history(
    db: Session,
    *,
    template_id: int,
    node_id: str | None = None,
    field: str | None = None,
    limit: int = 50,
) -> list[TemplatePromptHistory]:
    stmt = (
        select(TemplatePromptHistory)
        .where(TemplatePromptHistory.template_id == template_id)
        .order_by(TemplatePromptHistory.changed_at.desc(), TemplatePromptHistory.id.desc())
        .limit(max(1, min(limit, 500)))
    )
    if node_id is not None:
        stmt = stmt.where(TemplatePromptHistory.node_id == node_id)
    if field:
        stmt = stmt.where(TemplatePromptHistory.field == field)
    return list(db.scalars(stmt))


def get_entry(db: Session, entry_id: int) -> TemplatePromptHistory | None:
    return db.get(TemplatePromptHistory, entry_id)
