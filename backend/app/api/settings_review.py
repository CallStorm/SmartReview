from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models.user import User
from app.schemas.review_settings import ReviewSettingsPublic, ReviewSettingsUpdate
from app.services.review_settings import get_or_create_review_settings

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
    db.commit()
    db.refresh(row)
    return ReviewSettingsPublic(
        review_timeout_seconds=int(row.review_timeout_seconds),
        prompt_debug_enabled=bool(row.prompt_debug_enabled),
    )
