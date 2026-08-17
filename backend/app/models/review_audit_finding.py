from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReviewAuditFinding(Base):
    """AI 测评（对抗层）产生的分歧记录。

    missed_suspect：上次审核判了 pass，但独立复审判其可疑（漏检嫌疑）。
    false_positive_suspect：上次审核判了 fail，但独立复审判其可疑（误报嫌疑）。
    由管理员裁决（confirmed / rejected / unclear），confirmed 的记录用于
    生成提示词优化建议。
    """

    __tablename__ = "review_audit_finding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    node_title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # 检查项 id（missed_suspect）/ issue 的 message 摘要键（false_positive_suspect）
    check_item_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    check_item_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    finding_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # pending / confirmed / rejected / unclear
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    adjudicated_by: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    adjudicated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
