"""节点级审核结果缓存：指纹计算与读写。

指纹覆盖：checklist 版本、步骤、默认模型提供方与模型名、检查项清单签名
（含全局规则）、模板 updated_at、当前节正文、引用章节正文、知识库
dataset+query（不含检索文本本身--Dify 检索结果有波动，纳入会导致缓存
永远 miss）。

任何一项变化 -> 指纹变化 -> 该节点重新走 LLM。
"""

from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy.orm import Session

from app.models.review_result_cache import ReviewResultCache
from app.schemas.review_report import ReportStep
from app.services.checklist import CHECKLIST_VERSION
from app.services.llm.resolve import (
    effective_deepseek,
    effective_default_provider,
    effective_minimax,
    effective_volcengine,
)
from app.services.review_settings import (
    get_content_text_cap_chars,
    get_disable_reasoning,
    get_llm_max_output_tokens,
)

# 段落附图标记行：`[附图] <object_key>`。object_key 含每次上传生成的
# UUID，同一文档两次解析的 key 不同；指纹需剥离 key 只保留标记本身，
# 否则所有含图节点永远缓存 miss。
_IMAGE_MARKER_RE = re.compile(r"^(\[附图\])[^\n]*$", re.MULTILINE)

_PARSE_FAILURE_SUMMARY_PREFIX = "模型调用或 JSON 解析失败"
_PARSE_FAILURE_MESSAGE_MARKER = "模型输出未能解析为结构化结果"


def is_llm_parse_failure_step(step: ReportStep) -> bool:
    """LLM JSON 解析/调用失败时的占位 ReportStep；不应写入结果缓存。"""
    if _PARSE_FAILURE_SUMMARY_PREFIX in (step.summary or ""):
        return True
    return any(
        _PARSE_FAILURE_MESSAGE_MARKER in (issue.message or "")
        for issue in step.issues
    )


def normalize_text_for_fingerprint(text: str) -> str:
    return _IMAGE_MARKER_RE.sub(r"\1", text or "")


def provider_model_pair(db: Session) -> tuple[str, str]:
    """当前默认提供方与模型名（指纹组成部分；模型换挡后缓存自动失效）。"""
    provider = effective_default_provider(db)
    if provider == "volcengine":
        _, _, model = effective_volcengine(db)
    elif provider == "minimax":
        _, _, model = effective_minimax(db)
    else:
        _, _, model = effective_deepseek(db)
    return provider or "", model or ""


def _llm_settings_sig(db: Session) -> str:
    """运行时 LLM 参数签名：推理开关/输出上限/正文截断任一变化 -> 缓存自动失效。

    参数变化会改变发送给模型的实际请求（thinking 开关、max_tokens、正文截断），
    复用旧参数算出的结果会误导用户，因此纳入指纹。
    """
    return f"{get_disable_reasoning(db)}|{get_llm_max_output_tokens(db)}|{get_content_text_cap_chars(db)}"


def node_fingerprint(
    *,
    step_id: str,
    provider: str,
    model: str,
    checklist_sig: str,
    template_updated_at: str,
    current_text: str,
    ref_text: str,
    dataset_id: str = "",
    query: str = "",
    db: Session | None = None,
) -> str:
    parts: list[str] = [
        CHECKLIST_VERSION,
        step_id,
        provider,
        model,
        checklist_sig,
        template_updated_at or "",
        normalize_text_for_fingerprint(current_text),
        normalize_text_for_fingerprint(ref_text),
        f"{dataset_id or ''}|{query or ''}",
    ]
    if db is not None:
        parts.append(_llm_settings_sig(db))
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def prompt_fingerprint(
    *,
    step_id: str,
    provider: str,
    model: str,
    prompt: str,
    template_updated_at: str,
    db: Session | None = None,
) -> str:
    """以完整 prompt 为输入的通用指纹（用于 prompt 完全决定 LLM 输入的步骤，
    如上下文一致性：当前章节 + 对照章节 + 提示词全部在 prompt 内）。"""
    parts: list[str] = [
        CHECKLIST_VERSION,
        step_id,
        provider,
        model,
        normalize_text_for_fingerprint(prompt),
        template_updated_at or "",
    ]
    if db is not None:
        parts.append(_llm_settings_sig(db))
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def cache_lookup(db: Session, fingerprint: str) -> ReportStep | None:
    row = db.query(ReviewResultCache).filter(ReviewResultCache.fingerprint == fingerprint).first()
    if row is None:
        return None
    try:
        data = json.loads(row.payload_json)
        step = ReportStep.model_validate(data)
    except Exception:
        return None
    if is_llm_parse_failure_step(step):
        # 历史脏数据：解析失败曾被误写入缓存，删除后视为 miss 以便重试 LLM。
        try:
            db.delete(row)
            db.commit()
        except Exception:
            db.rollback()
        return None
    return step


def cache_store(
    db: Session,
    *,
    fingerprint: str,
    step_id: str,
    template_node_id: str,
    step: ReportStep,
) -> None:
    if is_llm_parse_failure_step(step):
        return
    row = db.query(ReviewResultCache).filter(ReviewResultCache.fingerprint == fingerprint).first()
    payload = json.dumps(step.model_dump(mode="json"), ensure_ascii=False)
    if row is not None:
        row.step_id = step_id
        row.template_node_id = template_node_id
        row.payload_json = payload
    else:
        db.add(
            ReviewResultCache(
                fingerprint=fingerprint,
                step_id=step_id,
                template_node_id=template_node_id,
                payload_json=payload,
            )
        )
    db.commit()
