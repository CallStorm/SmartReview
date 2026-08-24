from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.review_runtime_settings import ReviewRuntimeSettings

MIN_REVIEW_TIMEOUT_SECONDS = 30
MAX_REVIEW_TIMEOUT_SECONDS = 600
DEFAULT_REVIEW_TIMEOUT_SECONDS = 120

# LLM 输出上限（max_tokens）：过低会被长输出截断，过高受网关上限约束
MIN_LLM_MAX_OUTPUT_TOKENS = 4096
MAX_LLM_MAX_OUTPUT_TOKENS = 65536
DEFAULT_LLM_MAX_OUTPUT_TOKENS = 32768

# 内容审核「当前章节正文」截断长度（字符）
MIN_CONTENT_TEXT_CAP_CHARS = 4000
MAX_CONTENT_TEXT_CAP_CHARS = 80000
DEFAULT_CONTENT_TEXT_CAP_CHARS = 16000

MIN_PARALLELISM = 1
MAX_PARALLELISM = 8
DEFAULT_WORKER_PARALLEL_TASKS = 1
DEFAULT_COMPILATION_BASIS_CONCURRENCY = 2
DEFAULT_CONTEXT_CONSISTENCY_CONCURRENCY = 2
DEFAULT_CONTENT_CONCURRENCY = 4
DEFAULT_SYSTEM_NAME = "智能方案审核"


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
            disable_reasoning=True,
            llm_max_output_tokens=DEFAULT_LLM_MAX_OUTPUT_TOKENS,
            content_text_cap_chars=DEFAULT_CONTENT_TEXT_CAP_CHARS,
            worker_parallel_tasks=DEFAULT_WORKER_PARALLEL_TASKS,
            compilation_basis_concurrency=DEFAULT_COMPILATION_BASIS_CONCURRENCY,
            context_consistency_concurrency=DEFAULT_CONTEXT_CONSISTENCY_CONCURRENCY,
            content_concurrency=DEFAULT_CONTENT_CONCURRENCY,
            system_name=DEFAULT_SYSTEM_NAME,
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


def get_disable_reasoning(db: Session) -> bool:
    row = get_or_create_review_settings(db)
    return bool(row.disable_reasoning)


def get_llm_max_output_tokens(db: Session) -> int:
    row = get_or_create_review_settings(db)
    value = int(row.llm_max_output_tokens or DEFAULT_LLM_MAX_OUTPUT_TOKENS)
    if value < MIN_LLM_MAX_OUTPUT_TOKENS:
        return MIN_LLM_MAX_OUTPUT_TOKENS
    if value > MAX_LLM_MAX_OUTPUT_TOKENS:
        return MAX_LLM_MAX_OUTPUT_TOKENS
    return value


def get_content_text_cap_chars(db: Session) -> int:
    row = get_or_create_review_settings(db)
    value = int(row.content_text_cap_chars or DEFAULT_CONTENT_TEXT_CAP_CHARS)
    if value < MIN_CONTENT_TEXT_CAP_CHARS:
        return MIN_CONTENT_TEXT_CAP_CHARS
    if value > MAX_CONTENT_TEXT_CAP_CHARS:
        return MAX_CONTENT_TEXT_CAP_CHARS
    return value


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


def get_system_name(db: Session) -> str:
    row = get_or_create_review_settings(db)
    value = (row.system_name or "").strip()
    return value or DEFAULT_SYSTEM_NAME
