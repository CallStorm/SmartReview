from datetime import datetime
from typing import Any, Literal

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
            "image_review",
            "full_document",
            "end",
        }
        optional_mid = {
            "compilation_basis",
            "context_consistency",
            "content",
            "image_review",
            "full_document",
        }
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
            raise ValueError("中间仅可为编制依据、上下文一致性、内容审核、图审核或通篇审核")
        if len(middle) != len(set(middle)):
            raise ValueError("步骤不可重复")
        if "compilation_basis" in middle and middle[0] != "compilation_basis":
            raise ValueError("编制依据须紧随结构审核之后")
        if "full_document" in middle and middle[-1] != "full_document":
            raise ValueError("通篇审核须为中间步骤的最后一步")
        if (
            "image_review" in middle
            and "full_document" in middle
            and middle.index("image_review") + 1 != middle.index("full_document")
        ):
            raise ValueError("图审核须紧随通篇审核之前")
        core = [m for m in middle if m not in ("compilation_basis", "full_document", "image_review")]
        if len(core) == 2 and set(core) != {"context_consistency", "content"}:
            raise ValueError("中间步骤顺序无效")
        if len(core) == 1 and core[0] not in ("context_consistency", "content"):
            raise ValueError("中间步骤顺序无效")
        if len(core) > 2:
            raise ValueError("中间步骤顺序无效")
        return steps


class FullDocumentReviewConfig(BaseModel):
    review_prompt: str = ""
    dify_dataset_id: str | None = None
    knowledge_keywords: list[str] = Field(default_factory=list)


class FullDocumentReviewConfigUpdate(BaseModel):
    full_document_review_config: FullDocumentReviewConfig


class ReviewWorkflowUpdate(BaseModel):
    review_workflow: ReviewWorkflowData


class StructureMatchModeUpdate(BaseModel):
    mode: Literal["exact", "fuzzy"]


class ContentReviewRulesUpdate(BaseModel):
    """模板级「内容审核全局规则」。保存后会作为每个节点「审核提示词」的补充
    追加到内容审核（per-node）LLM 的 prompt 里；不影响通篇审核、上下文一致性、
    编制依据三步。空字符串表示未设置。"""

    content_review_rules: str = ""


class ImageReviewRulesUpdate(BaseModel):
    """模板级「图审核全局规则」：注入到每个图审核节点的视觉模型 prompt。
    空字符串表示未设置。"""

    image_review_rules: str = ""


class ImageReviewMissingTextUpdate(BaseModel):
    """模板级「缺图提示文案」：节点配置了图审核（图种/内容要素）但未检出附图时，
    在问题列表中展示的说明文字。空字符串表示未设置（用默认「无图审核」）。"""

    image_review_missing_text: str = ""


class TemplateStructureUpdate(BaseModel):
    """更新已保存的解析结构 JSON（含节点上的引用/知识库/审核提示/编制依据开关/上下文一致性比对与一致性提示词等配置）。"""

    parsed_structure: dict[str, Any] = Field(..., description='须包含 nodes 数组，与上传 Word 解析结果 Schema 一致')


class TemplatePublic(BaseModel):
    id: int
    scheme_type_id: int
    minio_bucket: str
    object_key: str
    original_filename: str
    parsed_structure: Any | None = None
    review_workflow: dict[str, Any] | None = None
    full_document_review_config: dict[str, Any] | None = None
    content_review_rules: str | None = None
    image_review_rules: str | None = None
    image_review_missing_text: str | None = None
    structure_match_mode: str = "exact"
    parsed_at: datetime | None
    updated_at: datetime | None


class TemplateUploadResponse(BaseModel):
    template: TemplatePublic
    message: str = "uploaded"


class DownloadUrlResponse(BaseModel):
    url: str
    expires_seconds: int


class PromptHistoryEntry(BaseModel):
    id: int
    node_id: str
    field: str
    node_title: str
    old_value: str
    new_value: str
    source: str
    changed_by: str
    changed_at: datetime


class PromptHistoryListResponse(BaseModel):
    items: list[PromptHistoryEntry]


class SplitPreviewRequest(BaseModel):
    node_id: str = ""
    review_prompt: str = ""


class SplitPreviewItem(BaseModel):
    id: str
    text: str


class SplitPreviewResponse(BaseModel):
    items: list[SplitPreviewItem]
    notes: list[str]


class OptimizePromptRequest(BaseModel):
    kind: Literal["review_prompt", "context_consistency_prompt"] = "review_prompt"
    node_title: str = ""
    scheme_name: str = ""
    current_text: str = ""


class OptimizePromptResponse(BaseModel):
    optimized_text: str
    changes: list[str] = Field(default_factory=list)
