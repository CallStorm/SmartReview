from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ModelProviderSettings(Base):
    """单行：多厂商大模型对接与默认供应商（管理员在设置中维护）。"""

    __tablename__ = "model_provider_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    default_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)

    volcengine_base_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    volcengine_api_key: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    volcengine_endpoint_id: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    minimax_base_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    minimax_api_key: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    minimax_model: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    deepseek_base_url: Mapped[str] = mapped_column(
        String(512), nullable=False, default="https://api.deepseek.com"
    )
    deepseek_api_key: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    deepseek_model: Mapped[str] = mapped_column(String(256), nullable=False, default="deepseek-v4-flash")

    # 图审核（视觉模型，走 MiniMax Anthropic 兼容协议，复用 minimax 凭据）
    image_review_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    image_review_model: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    # 护栏：送审前内部压缩到长边不超过该像素；单节点逐图送审数量上限，超限标记未审核
    image_review_max_side: Mapped[int] = mapped_column(Integer, nullable=False, default=1536)
    image_review_max_per_node: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
