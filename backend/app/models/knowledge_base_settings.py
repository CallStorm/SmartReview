from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class KnowledgeBaseSettings(Base):
    """单例行：Dify 知识库对接配置（由管理员在系统设置中维护）。"""

    __tablename__ = "knowledge_base_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dify_base_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    dify_api_key: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    dify_dataset_name_prefix: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
