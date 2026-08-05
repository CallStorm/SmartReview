from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models.user import User
from app.schemas.upload_settings import UploadSettingsPublic, UploadSettingsUpdate
from app.services.upload_settings import get_or_create_upload_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/upload", response_model=UploadSettingsPublic)
def get_upload_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> UploadSettingsPublic:
    row = get_or_create_upload_settings(db)
    return UploadSettingsPublic(max_upload_mb=int(row.max_upload_mb))


@router.put("/upload", response_model=UploadSettingsPublic)
def update_upload_settings(
    body: UploadSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> UploadSettingsPublic:
    row = get_or_create_upload_settings(db)
    row.max_upload_mb = int(body.max_upload_mb)
    db.commit()
    db.refresh(row)
    return UploadSettingsPublic(max_upload_mb=int(row.max_upload_mb))
