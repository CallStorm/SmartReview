from pydantic import BaseModel, Field

from app.services.review_settings import (
    MAX_CONTENT_TEXT_CAP_CHARS,
    MAX_LLM_MAX_OUTPUT_TOKENS,
    MAX_PARALLELISM,
    MAX_REVIEW_TIMEOUT_SECONDS,
    MIN_CONTENT_TEXT_CAP_CHARS,
    MIN_LLM_MAX_OUTPUT_TOKENS,
    MIN_PARALLELISM,
    MIN_REVIEW_TIMEOUT_SECONDS,
)


class ReviewSettingsPublic(BaseModel):
    review_timeout_seconds: int = Field(
        ...,
        ge=MIN_REVIEW_TIMEOUT_SECONDS,
        le=MAX_REVIEW_TIMEOUT_SECONDS,
    )
    prompt_debug_enabled: bool = False
    disable_reasoning: bool = True
    llm_max_output_tokens: int = Field(
        ...,
        ge=MIN_LLM_MAX_OUTPUT_TOKENS,
        le=MAX_LLM_MAX_OUTPUT_TOKENS,
    )
    content_text_cap_chars: int = Field(
        ...,
        ge=MIN_CONTENT_TEXT_CAP_CHARS,
        le=MAX_CONTENT_TEXT_CAP_CHARS,
    )
    worker_parallel_tasks: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)
    compilation_basis_concurrency: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)
    context_consistency_concurrency: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)
    content_concurrency: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)
    system_name: str = Field(..., min_length=1, max_length=100)
    logo_url: str | None = None
    favicon_url: str | None = None
    logo_configured: bool = False
    favicon_configured: bool = False


class ReviewBrandingPublic(BaseModel):
    system_name: str = Field(..., min_length=1, max_length=100)
    logo_url: str | None = None
    favicon_url: str | None = None
    logo_configured: bool = False
    favicon_configured: bool = False


class ReviewSettingsUpdate(BaseModel):
    review_timeout_seconds: int = Field(
        ...,
        ge=MIN_REVIEW_TIMEOUT_SECONDS,
        le=MAX_REVIEW_TIMEOUT_SECONDS,
    )
    prompt_debug_enabled: bool = False
    disable_reasoning: bool = True
    llm_max_output_tokens: int = Field(
        ...,
        ge=MIN_LLM_MAX_OUTPUT_TOKENS,
        le=MAX_LLM_MAX_OUTPUT_TOKENS,
    )
    content_text_cap_chars: int = Field(
        ...,
        ge=MIN_CONTENT_TEXT_CAP_CHARS,
        le=MAX_CONTENT_TEXT_CAP_CHARS,
    )
    worker_parallel_tasks: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)
    compilation_basis_concurrency: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)
    context_consistency_concurrency: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)
    content_concurrency: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)
    system_name: str = Field(..., min_length=1, max_length=100)
