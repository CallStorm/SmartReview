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
