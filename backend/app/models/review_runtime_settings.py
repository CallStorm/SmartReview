from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReviewRuntimeSettings(Base):
    """单行：方案审核运行时设置。"""

    __tablename__ = "review_runtime_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    prompt_debug_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    worker_parallel_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    compilation_basis_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    context_consistency_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    content_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
