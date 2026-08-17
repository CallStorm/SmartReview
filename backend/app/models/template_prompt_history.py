from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# 可追踪的提示词字段（写入与回滚都按此白名单校验）
PROMPT_HISTORY_FIELDS = (
    "review_prompt",
    "context_consistency_prompt",
    "content_review_rules",
    "full_document_review_prompt",
)


class TemplatePromptHistory(Base):
    """模板提示词变更历史。

    在模板保存接口里自动 diff 记录（谁、何时、改了哪个节点/字段、前后值），
    供前端「历史」按钮查看与一键回滚。审核提示词直接影响所有后续审核
    结果，变更必须可追溯、可回滚。
    """

    __tablename__ = "template_prompt_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # 节点 id；全局规则/通篇审核等非节点级字段为空串
    node_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    # 见 PROMPT_HISTORY_FIELDS
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    node_title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    old_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    new_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 变更来源：manual（界面编辑）/ restore（历史回滚）
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    changed_by: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
