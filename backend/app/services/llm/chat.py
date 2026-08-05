"""LLM chat for review steps (JSON output)."""

from __future__ import annotations

import json
import re
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from app.services.llm.adapters.anthropic import chat_anthropic_messages
from app.services.llm.adapters.openai_compatible import chat_openai_compatible
from app.services.llm.registry import provider_protocol
from app.services.llm.resolve import (
    effective_deepseek,
    effective_default_provider,
    effective_minimax,
    effective_volcengine,
)


class TokenUsage(TypedDict):
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class ChatResult(TypedDict):
    text: str
    usage: TokenUsage


EMPTY_USAGE: TokenUsage = {
    "input_tokens": None,
    "output_tokens": None,
    "total_tokens": None,
}


def _strip_code_fence(s: str) -> str:
    """剥掉单层 ```...``` 或 ```json ... ``` 包裹。"""
    m = re.search(r"^```(?:json)?\s*([\s\S]*?)\s*```\s*$", s, re.I)
    if m:
        return m.group(1).strip()
    return s


def _find_top_level_json_slice(s: str) -> str | None:
    """在 s 中找到第一个 { 或 [ 并匹配到对应的最外层结束位置，返回切片。

    处理字符串内的转义与嵌套括号/方括号。失败返回 None。
    """
    s = s.strip()
    start = -1
    open_ch = ""
    for i, ch in enumerate(s):
        if ch in "{[":
            start = i
            open_ch = ch
            break
    if start == -1:
        return None
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    escape = False
    for j in range(start, len(s)):
        ch = s[j]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return s[start : j + 1]
    return None


def extract_json_object(text: str) -> dict[str, Any]:
    """从 LLM 输出中宽容地抽出一个 JSON 对象。

    容错策略（按顺序尝试，任一成功即返回）：
    1. 整体去 ```json``` fence 后直接 json.loads
    2. 字符串里有最外层 {...} / [...] → 取切片后再 json.loads
    3. 切片再剥一次 fence 后 json.loads（应对 fences 嵌套的情况）
    全部失败抛 ValueError，附带原始文本摘要便于排查。
    """
    t = (text or "").strip()
    if not t:
        raise ValueError("LLM 返回内容为空")

    # 策略 1：剥掉整段外层 fence 直接 parse
    candidate = _strip_code_fence(t)
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # 策略 2 / 3：找最外层 { ... } 切片；切片内再尝试剥 fence 再 parse
    slice_text = _find_top_level_json_slice(t)
    if slice_text:
        inner = _strip_code_fence(slice_text.strip())
        obj = json.loads(inner)
        if isinstance(obj, dict):
            return obj
        # LLM 返回了顶层数组，按 list 走；调用方只接受 dict，这里抛错
        raise ValueError(
            f"LLM 返回了 JSON {type(obj).__name__}，但调用方要求 JSON object"
        )

    # 全部失败：抛错带摘要
    snippet = t if len(t) <= 200 else t[:200] + "…"
    raise ValueError(f"无法从 LLM 输出中抽取 JSON 对象。原始内容: {snippet!r}")


def complete_chat(
    db: Session,
    *,
    user_message: str,
    system: str,
    max_tokens: int = 8192,
    timeout: float = 120.0,
) -> str:
    return complete_chat_with_usage(
        db,
        user_message=user_message,
        system=system,
        max_tokens=max_tokens,
        timeout=timeout,
    )["text"]


def complete_chat_with_usage(
    db: Session,
    *,
    user_message: str,
    system: str,
    max_tokens: int = 8192,
    timeout: float = 120.0,
) -> ChatResult:
    provider = effective_default_provider(db)
    if not provider:
        raise ValueError("未配置默认模型提供方，请在系统设置中选择火山引擎、MiniMax 或 Deepseek")
    proto = provider_protocol(provider)
    if proto == "openai_compatible":
        if provider == "volcengine":
            url, key, model_or_endpoint = effective_volcengine(db)
            if not url or not key or not model_or_endpoint:
                raise ValueError("火山引擎接口未配置完整（base_url、密钥、endpoint_id）")
        else:
            url, key, model_or_endpoint = effective_deepseek(db)
            if not url or not key or not model_or_endpoint:
                raise ValueError("Deepseek 接口未配置完整（base_url、密钥、model）")
        text, usage = chat_openai_compatible(
            base_url=url,
            api_key=key,
            model=model_or_endpoint,
            user_message=user_message,
            system=system,
            max_tokens=max_tokens,
            timeout=timeout,
            include_usage=True,
        )
        return {"text": text, "usage": usage}
    url, key, model = effective_minimax(db)
    if not url or not key or not model:
        raise ValueError("MiniMax 接口未配置完整（base_url、密钥、模型）")
    text, usage = chat_anthropic_messages(
        base_url=url,
        api_key=key,
        model=model,
        user_message=user_message,
        system=system,
        max_tokens=max_tokens,
        timeout=timeout,
        include_usage=True,
    )
    return {"text": text, "usage": usage}


def chat_json(
    db: Session,
    *,
    user_message: str,
    system: str,
    max_tokens: int = 8192,
) -> dict[str, Any]:
    raw = complete_chat(db, user_message=user_message, system=system, max_tokens=max_tokens)
    return extract_json_object(raw)


def chat_json_with_usage(
    db: Session,
    *,
    user_message: str,
    system: str,
    max_tokens: int = 8192,
    timeout: float = 120.0,
) -> tuple[dict[str, Any], TokenUsage]:
    result = complete_chat_with_usage(
        db,
        user_message=user_message,
        system=system,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    usage = result.get("usage") or EMPTY_USAGE
    return extract_json_object(result["text"]), usage
