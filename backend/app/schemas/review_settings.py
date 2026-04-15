from pydantic import BaseModel, Field

from app.services.review_settings import MAX_REVIEW_TIMEOUT_SECONDS, MIN_REVIEW_TIMEOUT_SECONDS


class ReviewSettingsPublic(BaseModel):
    review_timeout_seconds: int = Field(
        ...,
        ge=MIN_REVIEW_TIMEOUT_SECONDS,
        le=MAX_REVIEW_TIMEOUT_SECONDS,
    )
    prompt_debug_enabled: bool = False


class ReviewSettingsUpdate(BaseModel):
    review_timeout_seconds: int = Field(
        ...,
        ge=MIN_REVIEW_TIMEOUT_SECONDS,
        le=MAX_REVIEW_TIMEOUT_SECONDS,
    )
    prompt_debug_enabled: bool = False
