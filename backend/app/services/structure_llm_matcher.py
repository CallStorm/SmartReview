"""LLM-based semantic matcher for fuzzy structure alignment.

Provides a per-level batch matcher that asks the LLM to pair template
section titles with user section titles (1:1). Used by review_pipeline
when structure_match_mode == "fuzzy".
"""

from __future__ import annotations

import json
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.llm.chat import chat_json_with_usage

_SYSTEM = (
    "你是工程文档结构对齐助手。给定模板章节标题列表与用户文档同级章节标题列表，"
    "为每个模板标题在用户标题中找语义对应的那一个（1:1，每个用户标题最多被匹配一次）。"
    "仅当二者确属同一章节内容时 matched=true。返回一个 JSON 对象："
    '{"pairs":[{"template_title":string,"user_title":string|null,"confidence":0.0~1.0,"matched":boolean}]}。'
    "不要输出 markdown 代码块或多余解释。"
)


def _build_prompt(template_titles: list[str], user_titles: list[str]) -> str:
    return (
        "模板章节标题列表：\n"
        + json.dumps(template_titles, ensure_ascii=False)
        + "\n\n用户文档同级章节标题列表：\n"
        + json.dumps(user_titles, ensure_ascii=False)
        + "\n\n请输出 JSON。"
    )


def _clamp01(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


def _parse_llm_pairs(
    raw: Any,
    template_titles: list[str],
    user_titles: list[str],
) -> list[dict[str, Any]]:
    """Normalize LLM output into a per-template-title dict list."""
    user_set = set(user_titles)
    pairs: list[dict[str, Any]] = []
    raw_pairs: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        p = raw.get("pairs")
        if isinstance(p, list):
            raw_pairs = [x for x in p if isinstance(x, dict)]
    elif isinstance(raw, list):
        raw_pairs = [x for x in raw if isinstance(x, dict)]

    by_t: dict[str, dict[str, Any]] = {}
    for item in raw_pairs:
        t = str(item.get("template_title") or "").strip()
        u = item.get("user_title")
        matched = bool(item.get("matched"))
        u_str = u.strip() if isinstance(u, str) else None
        if not t or t not in template_titles:
            continue
        if matched and (not u_str or u_str not in user_set):
            matched = False
            u_str = None
        entry = {
            "template_title": t,
            "user_title": u_str,
            "confidence": _clamp01(item.get("confidence")),
            "matched": matched,
        }
        by_t.setdefault(t, entry)

    for t in template_titles:
        pairs.append(
            by_t.get(
                t,
                {"template_title": t, "user_title": None, "confidence": 0.0, "matched": False},
            )
        )
    return pairs


def build_llm_matcher(
    db: Session,
    *,
    timeout_seconds: float = 60.0,
    log_sink: Callable[[str, str], None] | None = None,
) -> Callable[[list[str], list[str]], list[dict[str, Any]]]:
    """Return a matcher(template_titles, user_titles) -> list[dict].

    Uses a fresh SessionLocal per call. On any failure returns all unmatched
    (so align treats them as missing) and logs a warning via log_sink.
    """
    _ = db  # pipeline passes task db for API symmetry; matcher uses fresh session

    def matcher(template_titles: list[str], user_titles: list[str]) -> list[dict[str, Any]]:
        if not template_titles or not user_titles:
            return [
                {"template_title": t, "user_title": None, "confidence": 0.0, "matched": False}
                for t in template_titles
            ]
        ldb = SessionLocal()
        try:
            data, _usage = chat_json_with_usage(
                ldb,
                user_message=_build_prompt(template_titles, user_titles),
                system=_SYSTEM,
                max_tokens=4096,
                timeout=timeout_seconds,
            )
            return _parse_llm_pairs(data, template_titles, user_titles)
        except Exception as e:
            if log_sink is not None:
                log_sink("warning", f"结构语义匹配 LLM 失败，按缺失处理: {e!s}")
            return [
                {"template_title": t, "user_title": None, "confidence": 0.0, "matched": False}
                for t in template_titles
            ]
        finally:
            ldb.close()

    return matcher
