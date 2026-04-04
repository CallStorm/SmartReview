from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ReviewWorkflowData(BaseModel):
    """审核工作流：有序步骤，自起点经结构审核与可选步骤至结束。"""

    steps: list[str] = Field(..., min_length=3)

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, steps: list[str]) -> list[str]:
        allowed = {"start", "structure", "context_consistency", "content", "end"}
        optional = {"context_consistency", "content"}
        if steps[0] != "start":
            raise ValueError("第一步须为起点 start")
        if steps[1] != "structure":
            raise ValueError("第二步须为结构审核 structure")
        if steps[-1] != "end":
            raise ValueError("最后一步须为结束 end")
        if any(s not in allowed for s in steps):
            raise ValueError("包含非法步骤 id")
        if len(steps) != len(set(steps)):
            raise ValueError("步骤不可重复")
        middle = steps[2:-1]
        if any(m not in optional for m in middle):
            raise ValueError("中间仅可为上下文一致性或内容审核")
        return steps


class ReviewWorkflowUpdate(BaseModel):
    review_workflow: ReviewWorkflowData


class TemplateStructureUpdate(BaseModel):
    """更新已保存的解析结构 JSON（含节点上的引用/知识库/审核提示/上下文一致性比对等配置）。"""

    parsed_structure: dict[str, Any] = Field(..., description='须包含 nodes 数组，与上传 Word 解析结果 Schema 一致')


class TemplatePublic(BaseModel):
    id: int
    scheme_type_id: int
    minio_bucket: str
    object_key: str
    original_filename: str
    parsed_structure: Any | None = None
    review_workflow: dict[str, Any] | None = None
    parsed_at: datetime | None
    updated_at: datetime | None


class TemplateUploadResponse(BaseModel):
    template: TemplatePublic
    message: str = "uploaded"


class DownloadUrlResponse(BaseModel):
    url: str
    expires_seconds: int
