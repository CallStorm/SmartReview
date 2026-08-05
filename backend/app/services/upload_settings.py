from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.upload_runtime_settings import UploadRuntimeSettings

MIN_UPLOAD_MB = 1
MAX_UPLOAD_MB = 300
DEFAULT_UPLOAD_MB = 100


def get_or_create_upload_settings(db: Session) -> UploadRuntimeSettings:
    row = db.query(UploadRuntimeSettings).order_by(UploadRuntimeSettings.id.asc()).first()
    if row is None:
        row = UploadRuntimeSettings(max_upload_mb=DEFAULT_UPLOAD_MB)
        db.add(row)
        db.flush()
    return row


def get_max_upload_mb(db: Session) -> int:
    """读取方案上传大小上限（MB），自动 clamp 到合法范围。"""
    row = get_or_create_upload_settings(db)
    value = int(row.max_upload_mb or DEFAULT_UPLOAD_MB)
    if value < MIN_UPLOAD_MB:
        return MIN_UPLOAD_MB
    if value > MAX_UPLOAD_MB:
        return MAX_UPLOAD_MB
    return value
