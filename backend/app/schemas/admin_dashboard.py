from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TaskCountByDayItem(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD（按北京时间日历日聚合）")
    count: int


class TokenCountByDayItem(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD（北京时间）")
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class TaskCountByStatusItem(BaseModel):
    status: str
    count: int


class TaskCountBySchemeTypeItem(BaseModel):
    scheme_type_id: int
    scheme_name: str
    scheme_category: str
    count: int


class DifyDatasetItem(BaseModel):
    id: str
    name: str
    segment_count: int
    truncated: bool = False


class DifyDashboardBlock(BaseModel):
    configured: bool
    dataset_count: int = 0
    segment_total: int = 0
    datasets: list[DifyDatasetItem] = Field(default_factory=list)
    error: str | None = None
    truncated: bool = False


class DashboardSummary(BaseModel):
    refreshed_at: datetime | None = Field(None, description="快照最近刷新时间（存 UTC，前端按北京时间展示）")
    users_total: int
    users_admin: int
    users_regular: int
    scheme_types_total: int
    templates_total: int
    basis_items_total: int
    review_tasks_total: int
    review_tasks_today: int
    active_submitters_7d: int
    completion_rate: float | None = Field(
        None, description="succeeded / (succeeded + failed)，分母为 0 时为 null"
    )
    tokens_total_all: int = Field(0, description="全库累计 total_tokens 之和")
    input_tokens_total: int = Field(0, description="全库累计 input_tokens 之和")
    output_tokens_total: int = Field(0, description="全库累计 output_tokens 之和")
    tokens_today_total: int = Field(0, description="北京时间「今日」内创建任务的 total_tokens 之和")
    input_tokens_today: int = Field(0, description="北京时间「今日」内创建任务的 input_tokens 之和")
    output_tokens_today: int = Field(0, description="北京时间「今日」内创建任务的 output_tokens 之和")
    tokens_window_total: int = Field(0, description="所选时间窗内 total_tokens 之和（北京时间日历日）")
    input_tokens_window: int = Field(0, description="所选时间窗内 input_tokens 之和")
    output_tokens_window: int = Field(0, description="所选时间窗内 output_tokens 之和")
    tasks_per_day: list[TaskCountByDayItem]
    tokens_per_day: list[TokenCountByDayItem] = Field(default_factory=list)
    tasks_by_status: list[TaskCountByStatusItem]
    tasks_by_scheme_type: list[TaskCountBySchemeTypeItem]
    dify: DifyDashboardBlock
