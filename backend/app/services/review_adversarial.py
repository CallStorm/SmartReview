"""AI 测评（对抗层）：对一次已完成审核做 LLM 独立复核。

按节点批量挑战：
- 上次判 pass 的检查项 -> 漏检嫌疑（missed_suspect）
- 上次判 fail 的问题 -> 误报嫌疑（false_positive_suspect）

产出 ReviewAuditFinding 记录，等管理员裁决（confirmed/rejected/unclear）；
confirmed 的记录再经 generate_prompt_suggestions 生成提示词优化建议。
判定依据（检查项清单、全局规则）取当前模板配置，节点正文取该任务的
文档原文，复用确定性对齐（exact 模式）。
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    ReviewAuditFinding,
    SchemeReviewTask,
    SchemeTemplate,
)
from app.services import minio_storage
from app.services.checklist import split_check_items
from app.services.llm.chat import chat_json
from app.services.tree_align import align_template_user_trees
from app.services.word_parser import parse_docx_to_tree

# 单节点正文送审上限（与内容审核截断一致量级）
_AUDIT_TEXT_CAP = 16_000

_ADVERSARIAL_SYSTEM = """你是建筑施工方案审核系统的独立评审员（第二意见）。给你某章节的检查项清单、上次审核的判定结果和该章节正文，请以怀疑的态度复核：

1. 漏检嫌疑：上次判 pass 的检查项，逐条核对正文是否真的含有该内容、能否引用原文证明；凡是「找不到可引用原文」「只有占位措辞（详见后附/后续补充等）」「证据牵强」的 pass，都标记为 suspect。
2. 误报嫌疑：上次判 fail 的问题，核对正文是否其实已满足该检查项、或问题表述与正文不符；站不住的 fail 标记为 suspect。

要求：只基于给出的正文与检查项判断，不引入新标准；宁可多报嫌疑（后面有人工裁决），不得凭印象放过。每条嫌疑必须给出具体理由（引用正文或指出缺失点）。

输出 JSON：
{"missed_suspects": [{"item_id": "n17-2", "reason": "..."}],
 "false_positive_suspects": [{"item_id": "n32-3", "reason": "..."}]}
没有嫌疑则两个数组都为空。"""

_SUGGESTION_SYSTEM = """你是建筑施工方案审核系统的提示词工程师。根据管理员已裁决确认的测评分歧（确认漏检 / 确认误报），给出对应章节审核提示词的具体优化建议。

要求：
1. 建议必须落到提示词文本层面（怎么改哪一句、拆成哪几行、加什么判定标准），不要泛泛而谈。
2. 不得建议新增超出原审核意图的检查点。
3. 每个受影响章节一条建议。

输出 JSON：{"suggestions": [{"node_id": "n17", "node_title": "技术参数", "suggestion": "..."}]}"""


def _iter_nodes(nodes: list[dict[str, Any]]):
    for n in nodes:
        yield n
        yield from _iter_nodes(n.get("children") or [])


def _collect_subtree_text(node: dict[str, Any]) -> str:
    parts: list[str] = [str(node.get("title") or "")]
    content = node.get("content")
    if isinstance(content, list):
        parts.extend(str(p) for p in content if p)
    for c in node.get("children") or []:
        parts.append(_collect_subtree_text(c))
    return "\n".join(p for p in parts if p)


def _load_report(task: SchemeReviewTask) -> dict[str, Any]:
    raw = task.review_result_json
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def _content_failed_map(report: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    """content 步骤为扁平结构：按 node_id 收集 fail 的 issue（含检查项 id）。"""
    out: dict[str, list[dict[str, str]]] = {}
    for s in report.get("steps") or []:
        if str(s.get("step_id") or "") != "content":
            continue
        for i in s.get("issues") or []:
            anchor = i.get("anchor") or {}
            rel = i.get("related") or {}
            nid = str(anchor.get("template_node_id") or "")
            cid = str(rel.get("check_item_id") or "").strip()
            if not nid or not cid:
                continue
            out.setdefault(nid, []).append(
                {
                    "check_item_id": cid,
                    "message": str(i.get("message") or ""),
                    "evidence": str(i.get("evidence") or ""),
                }
            )
    return out


def run_adversarial_audit(db: Session, task: SchemeReviewTask) -> dict[str, Any]:
    """执行对抗测评：清空该任务旧 pending 记录后重新生成。"""
    tmpl = (
        db.query(SchemeTemplate)
        .filter(SchemeTemplate.scheme_type_id == task.scheme_type_id)
        .first()
    )
    if tmpl is None or not tmpl.parsed_structure:
        raise ValueError("该方案类型尚未配置模板，无法测评")
    structure = json.loads(tmpl.parsed_structure)
    template_nodes = structure.get("nodes") or []
    global_rules = (tmpl.content_review_rules or "").strip()

    report = _load_report(task)
    failed_map = _content_failed_map(report)

    # 解析任务文档并对齐到模板节点（exact 模式，确定性）
    raw = minio_storage.get_object_bytes(task.object_key)
    user_tree = parse_docx_to_tree(BytesIO(raw))
    mapping, _issues, _records = align_template_user_trees(template_nodes, user_tree.get("nodes") or [])

    # 先清掉该任务未裁决的旧记录（重新测评覆盖 pending）
    db.query(ReviewAuditFinding).filter(
        ReviewAuditFinding.task_id == task.id,
        ReviewAuditFinding.status == "pending",
    ).delete()

    audited_nodes = 0
    created = 0
    errors: list[str] = []

    for tn in _iter_nodes(template_nodes):
        tid = str(tn.get("id") or "")
        rp = tn.get("review_prompt") or ""
        if not tid or not rp:
            continue
        un = mapping.get(tid)
        if un is None:
            continue
        items, notes = split_check_items(tid, rp, node=tn)
        if not items:
            continue
        node_failed = failed_map.get(tid) or []
        failed_ids = {f["check_item_id"] for f in node_failed}
        node_text = _collect_subtree_text(un)[:_AUDIT_TEXT_CAP]
        item_lines = []
        for it in items:
            verdict = "fail" if it["id"] in failed_ids else "pass"
            item_lines.append(f"[{it['id']}] ({verdict}) {it['text']}")
        failed_issue_lines = [
            f"- 检查项 {f['check_item_id']}：{f['message']}（证据：{f['evidence']}）"
            for f in node_failed
        ]
        user_msg_parts = [
            f"章节：{tn.get('title')}",
            "【检查项清单与上次判定】",
            "\n".join(item_lines),
        ]
        if failed_issue_lines:
            user_msg_parts.append("【上次判定 fail 的完整问题】\n" + "\n".join(failed_issue_lines))
        if notes:
            user_msg_parts.append("【判定附注】\n" + "\n".join(f"- {n}" for n in notes))
        if global_rules:
            user_msg_parts.append("【审核总则】\n" + global_rules)
        user_msg_parts.append("【该章节正文】\n" + node_text)
        audited_nodes += 1
        try:
            data = chat_json(
                db,
                user_message="\n\n".join(user_msg_parts),
                system=_ADVERSARIAL_SYSTEM,
                max_tokens=8192,
            )
        except Exception as e:  # 单节点失败不阻断整体
            errors.append(f"{tid}: {e!s}")
            continue
        item_map = {it["id"]: it["text"] for it in items}
        for s in data.get("missed_suspects") or []:
            if not isinstance(s, dict):
                continue
            iid = str(s.get("item_id") or "").strip()
            if iid not in item_map or iid in failed_ids:
                continue
            db.add(
                ReviewAuditFinding(
                    task_id=task.id,
                    node_id=tid,
                    node_title=str(tn.get("title") or ""),
                    check_item_id=iid,
                    check_item_text=item_map[iid],
                    finding_type="missed_suspect",
                    description=str(s.get("reason") or "").strip(),
                )
            )
            created += 1
        for s in data.get("false_positive_suspects") or []:
            if not isinstance(s, dict):
                continue
            iid = str(s.get("item_id") or "").strip()
            if iid not in failed_ids:
                continue
            db.add(
                ReviewAuditFinding(
                    task_id=task.id,
                    node_id=tid,
                    node_title=str(tn.get("title") or ""),
                    check_item_id=iid,
                    check_item_text=item_map.get(iid, ""),
                    finding_type="false_positive_suspect",
                    description=str(s.get("reason") or "").strip(),
                )
            )
            created += 1

    db.commit()
    return {
        "task_id": task.id,
        "audited_nodes": audited_nodes,
        "findings_created": created,
        "errors": errors,
    }


def generate_prompt_suggestions(db: Session, task: SchemeReviewTask) -> dict[str, Any]:
    """把该任务已确认（confirmed）的分歧汇总成提示词优化建议。"""
    findings = (
        db.query(ReviewAuditFinding)
        .filter(
            ReviewAuditFinding.task_id == task.id,
            ReviewAuditFinding.status == "confirmed",
        )
        .all()
    )
    if not findings:
        return {"task_id": task.id, "suggestions": []}
    lines = []
    for f in findings:
        kind = "确认漏检" if f.finding_type == "missed_suspect" else "确认误报"
        lines.append(
            f"- 章节[{f.node_id} {f.node_title}] 检查项[{f.check_item_id} {f.check_item_text}]"
            f"（{kind}）：{f.description}"
        )
    data = chat_json(
        db,
        user_message="以下是管理员裁决确认的测评分歧：\n" + "\n".join(lines),
        system=_SUGGESTION_SYSTEM,
        max_tokens=8192,
    )
    suggestions = [
        {
            "node_id": str(s.get("node_id") or ""),
            "node_title": str(s.get("node_title") or ""),
            "suggestion": str(s.get("suggestion") or ""),
        }
        for s in data.get("suggestions") or []
        if isinstance(s, dict) and str(s.get("suggestion") or "").strip()
    ]
    return {"task_id": task.id, "suggestions": suggestions}
