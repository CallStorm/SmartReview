from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DashboardSummarySnapshot(Base):
    """按时间窗口保存看板聚合快照（7/30/90 天）。"""

    __tablename__ = "dashboard_summary_snapshots"
    __table_args__ = (UniqueConstraint("window_days", name="uq_dashboard_summary_window_days"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
