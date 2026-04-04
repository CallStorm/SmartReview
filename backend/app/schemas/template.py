from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ReviewWorkflowData(BaseModel):
    """审核工作流：有序步骤，自起点经结构审核与可选步骤至结束。"""

    steps: list[str] = Field(..., min_length=3)

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, steps: list[str]) -> list[str]:
        allowed = {
            "start",
            "structure",
            "compilation_basis",
            "context_consistency",
            "content",
            "end",
        }
        optional_mid = {"compilation_basis", "context_consistency", "content"}
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
        if any(m not in optional_mid for m in middle):
            raise ValueError("中间仅可为编制依据、上下文一致性或内容审核")
        if middle.count("compilation_basis") > 1:
            raise ValueError("步骤不可重复")
        if "compilation_basis" in middle and middle[0] != "compilation_basis":
            raise ValueError("编制依据须紧随结构审核之后")
        rest = [m for m in middle if m != "compilation_basis"]
        if len(rest) == 2 and set(rest) != {"context_consistency", "content"}:
            raise ValueError("中间步骤顺序无效")
        if len(rest) == 1 and rest[0] not in ("context_consistency", "content"):
            raise ValueError("中间步骤顺序无效")
        return steps


class ReviewWorkflowUpdate(BaseModel):
    review_workflow: ReviewWorkflowData


class TemplateStructureUpdate(BaseModel):
    """更新已保存的解析结构 JSON（含节点上的引用/知识库/审核提示/编制依据开关/上下文一致性比对等配置）。"""

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
