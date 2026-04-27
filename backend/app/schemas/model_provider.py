from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

ProviderId = Literal["volcengine", "minimax", "deepseek"]
LlmApiProtocol = Literal["openai_compatible", "anthropic"]


class VolcenginePublic(BaseModel):
    api_protocol: Literal["openai_compatible"] = "openai_compatible"
    base_url: str
    endpoint_id: str
    api_key_configured: bool


class MinimaxPublic(BaseModel):
    api_protocol: Literal["anthropic"] = "anthropic"
    base_url: str
    model: str
    api_key_configured: bool


class DeepseekPublic(BaseModel):
    api_protocol: Literal["openai_compatible"] = "openai_compatible"
    base_url: str
    model: str
    api_key_configured: bool


class ModelProviderPublic(BaseModel):
    default_provider: ProviderId | None
    volcengine: VolcenginePublic
    minimax: MinimaxPublic
    deepseek: DeepseekPublic


class ModelProviderUpdate(BaseModel):
    default_provider: ProviderId | None = None

    volcengine_base_url: str | None = None
    volcengine_api_key: str | None = Field(
        default=None,
        description="新密钥；不传或空字符串表示不修改",
    )
    volcengine_endpoint_id: str | None = None

    minimax_base_url: str | None = None
    minimax_api_key: str | None = Field(default=None, description="新密钥；不传或空表示不修改")
    minimax_model: str | None = None
    deepseek_base_url: str | None = None
    deepseek_api_key: str | None = Field(default=None, description="新密钥；不传或空表示不修改")
    deepseek_model: str | None = None

    @field_validator(
        "volcengine_base_url",
        "volcengine_endpoint_id",
        "minimax_base_url",
        "minimax_model",
        "deepseek_base_url",
        "deepseek_model",
        mode="before",
    )
    @classmethod
    def strip_opt(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip()
        return v


class ModelTestRequest(BaseModel):
    provider: ProviderId


class ModelTestResult(BaseModel):
    ok: bool
    preview: str | None = None
    error: str | None = None
    latency_ms: int | None = None
