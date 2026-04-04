from __future__ import annotations

import json
from typing import Any

import httpx


def _truncate(s: str, n: int = 500) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def chat_openai_compatible(
    *,
    base_url: str,
    api_key: str,
    model: str,
    user_message: str,
    system: str | None = None,
    max_tokens: int = 32,
    timeout: float = 60.0,
) -> str:
    root = base_url.rstrip("/")
    url = f"{root}/chat/completions"
    messages: list[dict[str, Any]] = []
    if system and system.strip():
        messages.append({"role": "system", "content": system.strip()})
    messages.append({"role": "user", "content": user_message})
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
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
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("响应中缺少 choices")
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = msg.get("content") if isinstance(msg, dict) else None
    if content is None:
        raise ValueError("响应中缺少 message.content")
    if isinstance(content, str):
        return content.strip()
    raise ValueError("不支持的 message.content 格式")
