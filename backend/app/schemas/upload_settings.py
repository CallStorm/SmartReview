from pydantic import BaseModel, Field

from app.services.upload_settings import MAX_UPLOAD_MB, MIN_UPLOAD_MB


class UploadSettingsPublic(BaseModel):
    max_upload_mb: int = Field(
        ...,
        ge=MIN_UPLOAD_MB,
        le=MAX_UPLOAD_MB,
    )


class UploadSettingsUpdate(BaseModel):
    max_upload_mb: int = Field(
        ...,
        ge=MIN_UPLOAD_MB,
        le=MAX_UPLOAD_MB,
    )
