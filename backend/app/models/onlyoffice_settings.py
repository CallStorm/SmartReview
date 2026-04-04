from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OnlyofficeSettings(Base):
    """单行：OnlyOffice 对接配置（管理员在系统设置中维护）。"""

    __tablename__ = "onlyoffice_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    docs_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    jwt_secret: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    callback_base_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    editor_lang: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
