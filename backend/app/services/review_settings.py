from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.review_runtime_settings import ReviewRuntimeSettings

MIN_REVIEW_TIMEOUT_SECONDS = 30
MAX_REVIEW_TIMEOUT_SECONDS = 600
DEFAULT_REVIEW_TIMEOUT_SECONDS = 120

MIN_PARALLELISM = 1
MAX_PARALLELISM = 8
DEFAULT_WORKER_PARALLEL_TASKS = 1
DEFAULT_COMPILATION_BASIS_CONCURRENCY = 2
DEFAULT_CONTEXT_CONSISTENCY_CONCURRENCY = 2
DEFAULT_CONTENT_CONCURRENCY = 4


def _clamp_parallelism(value: int | None, *, default: int) -> int:
    if value is None:
        return default
    v = int(value)
    if v < MIN_PARALLELISM:
        return MIN_PARALLELISM
    if v > MAX_PARALLELISM:
        return MAX_PARALLELISM
    return v


def get_or_create_review_settings(db: Session) -> ReviewRuntimeSettings:
    row = db.query(ReviewRuntimeSettings).order_by(ReviewRuntimeSettings.id.asc()).first()
    if row is None:
        row = ReviewRuntimeSettings(
            review_timeout_seconds=DEFAULT_REVIEW_TIMEOUT_SECONDS,
            prompt_debug_enabled=False,
            worker_parallel_tasks=DEFAULT_WORKER_PARALLEL_TASKS,
            compilation_basis_concurrency=DEFAULT_COMPILATION_BASIS_CONCURRENCY,
            context_consistency_concurrency=DEFAULT_CONTEXT_CONSISTENCY_CONCURRENCY,
            content_concurrency=DEFAULT_CONTENT_CONCURRENCY,
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


def get_worker_parallel_tasks(db: Session) -> int:
    row = get_or_create_review_settings(db)
    return _clamp_parallelism(row.worker_parallel_tasks, default=DEFAULT_WORKER_PARALLEL_TASKS)


def get_compilation_basis_concurrency(db: Session) -> int:
    row = get_or_create_review_settings(db)
    return _clamp_parallelism(row.compilation_basis_concurrency, default=DEFAULT_COMPILATION_BASIS_CONCURRENCY)


def get_context_consistency_concurrency(db: Session) -> int:
    row = get_or_create_review_settings(db)
    return _clamp_parallelism(
        row.context_consistency_concurrency, default=DEFAULT_CONTEXT_CONSISTENCY_CONCURRENCY
    )


def get_content_concurrency(db: Session) -> int:
    row = get_or_create_review_settings(db)
    return _clamp_parallelism(row.content_concurrency, default=DEFAULT_CONTENT_CONCURRENCY)
