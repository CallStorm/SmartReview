from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.scheme_type import SchemeType


class SchemeTemplate(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scheme_type_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("scheme_types.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    minio_bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    parsed_structure: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_workflow: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_document_review_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_review_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 模板级「图审核全局规则」：注入到每个图审核节点的视觉模型 prompt
    image_review_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    structure_match_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="exact", default="exact"
    )
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    scheme_type: Mapped[SchemeType] = relationship("SchemeType", back_populates="template")
