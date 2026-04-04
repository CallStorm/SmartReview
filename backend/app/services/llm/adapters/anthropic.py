from __future__ import annotations

import json
from typing import Any

import httpx


def _truncate(s: str, n: int = 500) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _messages_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/messages"
    return f"{root}/v1/messages"


def _normalize_block_type(block: dict[str, Any]) -> str:
    t = block.get("type")
    if isinstance(t, str):
        return t.strip().lower()
    return ""


def _text_from_text_block(block: dict[str, Any]) -> str:
    """Anthropic / MiniMax: { type: text, text: str }；兼容嵌套或别名字段。"""
    raw = block.get("text")
    if isinstance(raw, str) and raw.strip():
        return raw
    if isinstance(raw, list):
        return _collect_text_from_blocks(raw)
    alt = block.get("content")
    if isinstance(alt, str) and alt.strip():
        return alt
    if isinstance(alt, list):
        return _collect_text_from_blocks(alt)
    return ""


def _collect_text_from_blocks(blocks: Any) -> str:
    """遍历 content 块列表：跳过 thinking，拼接所有 text 块（与 SDK 遍历 message.content 一致）。"""
    if blocks is None:
        return ""
    if isinstance(blocks, str):
        return blocks.strip()
    if isinstance(blocks, dict):
        bt = _normalize_block_type(blocks)
        if bt == "thinking":
            return ""
        if bt == "text":
            return _text_from_text_block(blocks)
        if bt == "tool_use":
            return ""
        inner = blocks.get("content")
        if inner is not None:
            return _collect_text_from_blocks(inner)
        return ""
    if not isinstance(blocks, list):
        return ""
    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        bt = _normalize_block_type(block)
        if bt == "thinking" or bt == "redacted_thinking":
            continue
        if bt == "text":
            s = _text_from_text_block(block)
            if s:
                parts.append(s)
        elif bt == "tool_use":
            continue
        else:
            inner = block.get("content")
            if inner is not None:
                sub = _collect_text_from_blocks(inner)
                if sub:
                    parts.append(sub)
    return "".join(parts).strip()


def _content_list_from_response(data: dict[str, Any]) -> Any:
    """兼容顶层 content、message.content、以及部分网关的 data/result 包装。"""
    if "content" in data and data["content"] is not None:
        return data["content"]
    for wrap_key in ("message", "data", "result", "response"):
        sub = data.get(wrap_key)
        if isinstance(sub, dict) and sub.get("content") is not None:
            return sub["content"]
    return None


def chat_anthropic_messages(
    *,
    base_url: str,
    api_key: str,
    model: str,
    user_message: str,
    system: str = "You are a helpful assistant.",
    max_tokens: int = 1024,
    timeout: float = 60.0,
) -> str:
    url = _messages_url(base_url)
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": user_message}],
            }
        ],
    }
    if system.strip():
        payload["system"] = system.strip()
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, headers=headers, json=payload)
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = _truncate(e.response.text or "")
        except Exception:
            detail = ""
        raise ValueError(f"HTTP {e.response.status_code}{': ' + detail if detail else ''}") from e

    try:
        data = r.json()
    except json.JSONDecodeError as e:
        raise ValueError("响应不是合法 JSON") from e

    if not isinstance(data, dict):
        raise ValueError("响应根节点不是 JSON 对象")

    raw_content = _content_list_from_response(data)
    text = _collect_text_from_blocks(raw_content)
    if not text:
        raise ValueError(
            "响应中未找到文本内容（可能仅有 thinking 块或网关返回结构与 Anthropic Messages 不一致）"
        )
    return text
