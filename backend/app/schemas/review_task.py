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
    review_stage: str | None = Field(default=None, description="处理中时的当前审核阶段 id")
    review_result_json: str | None = Field(
        default=None,
        description="统一审核报告 JSON；列表接口可为空以减负",
    )
    output_object_key: str | None = Field(default=None, description="带批注的 docx 对象键")
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
