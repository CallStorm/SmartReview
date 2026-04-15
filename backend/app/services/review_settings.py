from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.review_runtime_settings import ReviewRuntimeSettings

MIN_REVIEW_TIMEOUT_SECONDS = 30
MAX_REVIEW_TIMEOUT_SECONDS = 600
DEFAULT_REVIEW_TIMEOUT_SECONDS = 120


def get_or_create_review_settings(db: Session) -> ReviewRuntimeSettings:
    row = db.query(ReviewRuntimeSettings).order_by(ReviewRuntimeSettings.id.asc()).first()
    if row is None:
        row = ReviewRuntimeSettings(
            review_timeout_seconds=DEFAULT_REVIEW_TIMEOUT_SECONDS,
            prompt_debug_enabled=False,
        )
        db.add(row)
        db.flush()
    return row


def get_review_timeout_seconds(db: Session) -> int:
    row = get_or_create_review_settings(db)
    value = int(row.review_timeout_seconds or DEFAULT_REVIEW_TIMEOUT_SECONDS)
    if value < MIN_REVIEW_TIMEOUT_SECONDS:
        return MIN_REVIEW_TIMEOUT_SECONDS
    if value > MAX_REVIEW_TIMEOUT_SECONDS:
        return MAX_REVIEW_TIMEOUT_SECONDS
    return value


def get_review_prompt_debug_enabled(db: Session) -> bool:
    row = get_or_create_review_settings(db)
    return bool(row.prompt_debug_enabled)
