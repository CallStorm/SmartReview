from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ReviewTaskPublic(BaseModel):
    id: int
    scheme_type_id: int
    scheme_category: str = ""
    scheme_name: str = ""
    status: str
    result_text: str | None = None
    error_message: str | None = None
    original_filename: str
    created_at: datetime
    updated_at: datetime
    review_log: str | None = Field(
        default=None,
        description="审核过程日志；列表接口为减轻负载不返回，仅详情接口返回",
    )


class ReviewTaskCreateResponse(BaseModel):
    task: ReviewTaskPublic
    message: str = Field(default="已提交审核任务")
