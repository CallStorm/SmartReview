from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.scheme_review_task import SchemeReviewTask
    from app.models.scheme_template import SchemeTemplate


class SchemeType(Base):
    __tablename__ = "scheme_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    template: Mapped[SchemeTemplate | None] = relationship(
        "SchemeTemplate",
        back_populates="scheme_type",
        uselist=False,
        cascade="all, delete-orphan",
    )
    review_tasks: Mapped[list[SchemeReviewTask]] = relationship(
        "SchemeReviewTask", back_populates="scheme_type"
    )

    @property
    def template_configured(self) -> bool:
        """已上传模版、完成解析且标题树非空。"""
        t = self.template
        if t is None or t.parsed_at is None:
            return False
        raw = t.parsed_structure
        if not raw or not str(raw).strip():
            return False
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return False
        nodes = data.get("nodes") if isinstance(data, dict) else None
        return isinstance(nodes, list) and len(nodes) > 0

    @property
    def workflow_configured(self) -> bool:
        """已保存有效的审核工作流（起点→结构审核→…→结束）。"""
        t = self.template
        if t is None or not t.review_workflow or not str(t.review_workflow).strip():
            return False
        try:
            data = json.loads(t.review_workflow)
        except json.JSONDecodeError:
            return False
        steps = data.get("steps") if isinstance(data, dict) else None
        if not isinstance(steps, list) or len(steps) < 3:
            return False
        return (
            steps[0] == "start"
            and steps[1] == "structure"
            and steps[-1] == "end"
        )
