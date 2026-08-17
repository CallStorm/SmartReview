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


class ImageReviewPublic(BaseModel):
    """图审核（视觉模型）配置：复用 MiniMax 凭据，单独的模型名与护栏。"""

    enabled: bool
    model: str
    base_url: str
    api_key_configured: bool
    max_side: int
    max_per_node: int


class ModelProviderPublic(BaseModel):
    default_provider: ProviderId | None
    volcengine: VolcenginePublic
    minimax: MinimaxPublic
    deepseek: DeepseekPublic
    image_review: ImageReviewPublic


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

    image_review_enabled: bool | None = None
    image_review_model: str | None = None
    image_review_max_side: int | None = Field(default=None, ge=256, le=8192)
    image_review_max_per_node: int | None = Field(default=None, ge=1, le=100)

    @field_validator(
        "volcengine_base_url",
        "volcengine_endpoint_id",
        "minimax_base_url",
        "minimax_model",
        "deepseek_base_url",
        "deepseek_model",
        "image_review_model",
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
