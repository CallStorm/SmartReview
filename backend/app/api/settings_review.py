from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models.user import User
from app.schemas.review_settings import ReviewSettingsPublic, ReviewSettingsUpdate
from app.services.review_settings import (
    get_or_create_review_settings,
    get_compilation_basis_concurrency,
    get_content_concurrency,
    get_context_consistency_concurrency,
    get_worker_parallel_tasks,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/review", response_model=ReviewSettingsPublic)
def get_review_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ReviewSettingsPublic:
    row = get_or_create_review_settings(db)
    return ReviewSettingsPublic(
        review_timeout_seconds=int(row.review_timeout_seconds),
        prompt_debug_enabled=bool(row.prompt_debug_enabled),
        worker_parallel_tasks=get_worker_parallel_tasks(db),
        compilation_basis_concurrency=get_compilation_basis_concurrency(db),
        context_consistency_concurrency=get_context_consistency_concurrency(db),
        content_concurrency=get_content_concurrency(db),
    )


@router.put("/review", response_model=ReviewSettingsPublic)
def update_review_settings(
    body: ReviewSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ReviewSettingsPublic:
    row = get_or_create_review_settings(db)
    row.review_timeout_seconds = int(body.review_timeout_seconds)
    row.prompt_debug_enabled = bool(body.prompt_debug_enabled)
    row.worker_parallel_tasks = int(body.worker_parallel_tasks)
    row.compilation_basis_concurrency = int(body.compilation_basis_concurrency)
    row.context_consistency_concurrency = int(body.context_consistency_concurrency)
    row.content_concurrency = int(body.content_concurrency)
    db.commit()
    db.refresh(row)
    return ReviewSettingsPublic(
        review_timeout_seconds=int(row.review_timeout_seconds),
        prompt_debug_enabled=bool(row.prompt_debug_enabled),
        worker_parallel_tasks=get_worker_parallel_tasks(db),
        compilation_basis_concurrency=get_compilation_basis_concurrency(db),
        context_consistency_concurrency=get_context_consistency_concurrency(db),
        content_concurrency=get_content_concurrency(db),
    )
