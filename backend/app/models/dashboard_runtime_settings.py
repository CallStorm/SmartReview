from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DashboardRuntimeSettings(Base):
    """单行：看板统计调度设置。"""

    __tablename__ = "dashboard_runtime_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    refresh_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    prompt_debug_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
