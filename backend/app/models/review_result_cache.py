from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReviewResultCache(Base):
    """节点级审核结果缓存。

    同一（文档内容 + 检查项清单 + 全局规则 + 模板版本 + 模型）组合直接复用
    上次的 LLM 判定结果，保证多次审核结果逐条一致；任一要素变化即失效。
    缓存键 fingerprint 见 app/services/review_cache.py。
    """

    __tablename__ = "review_result_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    step_id: Mapped[str] = mapped_column(String(32), nullable=False)
    template_node_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
