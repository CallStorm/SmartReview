from __future__ import annotations

from typing import Literal

from app.schemas.model_provider import LlmApiProtocol

ProviderId = Literal["volcengine", "minimax", "deepseek"]


class ProviderSpec:
    __slots__ = ("id", "api_protocol", "default_base_url_hint")

    def __init__(
        self,
        id: ProviderId,
        api_protocol: LlmApiProtocol,
        default_base_url_hint: str,
    ) -> None:
        self.id = id
        self.api_protocol = api_protocol
        self.default_base_url_hint = default_base_url_hint


PROVIDER_REGISTRY: dict[ProviderId, ProviderSpec] = {
    "volcengine": ProviderSpec(
        "volcengine",
        "openai_compatible",
        "https://ark.cn-beijing.volces.com/api/v3",
    ),
    "minimax": ProviderSpec(
        "minimax",
        "anthropic",
        "https://api.minimaxi.com/anthropic",
    ),
    "deepseek": ProviderSpec(
        "deepseek",
        "openai_compatible",
        "https://api.deepseek.com",
    ),
}


def provider_protocol(provider_id: ProviderId) -> LlmApiProtocol:
    return PROVIDER_REGISTRY[provider_id].api_protocol
