from __future__ import annotations

import time

from app.services.llm.adapters.anthropic import chat_anthropic_messages
from app.services.llm.adapters.openai_compatible import chat_openai_compatible
from app.services.llm.registry import ProviderId, provider_protocol


def chat_once_test(
    *,
    provider_id: ProviderId,
    base_url: str,
    api_key: str,
    model_or_endpoint: str,
) -> tuple[str, int]:
    """返回 (assistant 文本, 耗时 ms)。"""
    msg = "请只回复一个字：好"
    t0 = time.perf_counter()
    proto = provider_protocol(provider_id)
    if proto == "openai_compatible":
        text = chat_openai_compatible(
            base_url=base_url,
            api_key=api_key,
            model=model_or_endpoint,
            user_message=msg,
            max_tokens=32,
        )
    else:
        # MiniMax 等模型可能先返回较长 thinking 再返回 text，max_tokens 过小会导致无 text 块
        text = chat_anthropic_messages(
            base_url=base_url,
            api_key=api_key,
            model=model_or_endpoint,
            user_message=msg,
            max_tokens=1024,
        )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return text.strip(), elapsed_ms
