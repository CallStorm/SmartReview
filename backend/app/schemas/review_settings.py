from pydantic import BaseModel, Field

from app.services.review_settings import (
    MAX_PARALLELISM,
    MAX_REVIEW_TIMEOUT_SECONDS,
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
    worker_parallel_tasks: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)
    compilation_basis_concurrency: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)
    context_consistency_concurrency: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)
    content_concurrency: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)


class ReviewSettingsUpdate(BaseModel):
    review_timeout_seconds: int = Field(
        ...,
        ge=MIN_REVIEW_TIMEOUT_SECONDS,
        le=MAX_REVIEW_TIMEOUT_SECONDS,
    )
    prompt_debug_enabled: bool = False
    worker_parallel_tasks: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)
    compilation_basis_concurrency: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)
    context_consistency_concurrency: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)
    content_concurrency: int = Field(..., ge=MIN_PARALLELISM, le=MAX_PARALLELISM)
