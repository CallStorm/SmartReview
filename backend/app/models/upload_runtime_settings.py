from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UploadRuntimeSettings(Base):
    """单行：方案上传大小限制（MB）。"""

    __tablename__ = "upload_runtime_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    max_upload_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
