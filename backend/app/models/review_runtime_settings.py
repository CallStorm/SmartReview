from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReviewRuntimeSettings(Base):
    """单行：方案审核运行时设置。"""

    __tablename__ = "review_runtime_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    prompt_debug_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # LLM 推理开关：为 True 时 DeepSeek 请求禁用 thinking（max_tokens 全用于输出，
    # 避免推理耗尽预算返回空 content 导致审核节点静默降级失败）
    disable_reasoning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 各审核步骤 LLM 单次输出上限（max_tokens）
    llm_max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=32768)
    # 内容审核「当前章节正文」截断长度（字符）
    content_text_cap_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=16000)
    worker_parallel_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    compilation_basis_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    context_consistency_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    content_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    system_name: Mapped[str] = mapped_column(String(100), nullable=False, default="智能方案审核")
    brand_logo_object_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_logo_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    favicon_object_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    favicon_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
