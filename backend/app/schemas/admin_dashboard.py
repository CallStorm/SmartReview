from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TaskCountByDayItem(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD (UTC)")
    count: int


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
    refreshed_at: datetime | None = Field(None, description="快照最近刷新时间（UTC）")
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
    tasks_per_day: list[TaskCountByDayItem]
    tasks_by_status: list[TaskCountByStatusItem]
    tasks_by_scheme_type: list[TaskCountBySchemeTypeItem]
    dify: DifyDashboardBlock
