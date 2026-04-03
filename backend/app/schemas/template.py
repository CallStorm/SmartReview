from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TemplatePublic(BaseModel):
    id: int
    scheme_type_id: int
    minio_bucket: str
    object_key: str
    original_filename: str
    parsed_structure: Any | None = None
    parsed_at: datetime | None
    updated_at: datetime | None


class TemplateUploadResponse(BaseModel):
    template: TemplatePublic
    message: str = "uploaded"


class DownloadUrlResponse(BaseModel):
    url: str
    expires_seconds: int
