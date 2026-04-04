"""LLM chat for review steps (JSON output)."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.llm.adapters.anthropic import chat_anthropic_messages
from app.services.llm.adapters.openai_compatible import chat_openai_compatible
from app.services.llm.registry import provider_protocol
from app.services.llm.resolve import effective_default_provider, effective_minimax, effective_volcengine


def extract_json_object(text: str) -> dict[str, Any]:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.I)
    if m:
        t = m.group(1).strip()
    return json.loads(t)


def complete_chat(
    db: Session,
    *,
    user_message: str,
    system: str,
    max_tokens: int = 8192,
    timeout: float = 120.0,
) -> str:
    provider = effective_default_provider(db)
    if not provider:
        raise ValueError("未配置默认模型提供方，请在系统设置中选择火山引擎或 MiniMax")
    proto = provider_protocol(provider)
    if proto == "openai_compatible":
        url, key, eid = effective_volcengine(db)
        if not url or not key or not eid:
            raise ValueError("火山引擎接口未配置完整（base_url、密钥、endpoint_id）")
        return chat_openai_compatible(
            base_url=url,
            api_key=key,
            model=eid,
            user_message=user_message,
            system=system,
            max_tokens=max_tokens,
            timeout=timeout,
        )
    url, key, model = effective_minimax(db)
    if not url or not key or not model:
        raise ValueError("MiniMax 接口未配置完整（base_url、密钥、模型）")
    return chat_anthropic_messages(
        base_url=url,
        api_key=key,
        model=model,
        user_message=user_message,
        system=system,
        max_tokens=max_tokens,
        timeout=timeout,
    )


def chat_json(
    db: Session,
    *,
    user_message: str,
    system: str,
    max_tokens: int = 8192,
) -> dict[str, Any]:
    raw = complete_chat(db, user_message=user_message, system=system, max_tokens=max_tokens)
    return extract_json_object(raw)
