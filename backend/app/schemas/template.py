from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TemplateStructureUpdate(BaseModel):
    """更新已保存的解析结构 JSON（含节点上的引用/知识库/审核提示等配置）。"""

    parsed_structure: dict[str, Any] = Field(..., description='须包含 nodes 数组，与上传 Word 解析结果 Schema 一致')


class TemplatePublic(BaseModel):
    id: int
    scheme_type_id: int
    minio_bucket: str
    object_key: str
    original_filename: str
    parsed_structure: Any | None = None
    parsed_at: datetime | None
    updated_at: datetime | None


class TemplateUploadResponse(BaseModel):
    template: TemplatePublic
    message: str = "uploaded"


class DownloadUrlResponse(BaseModel):
    url: str
    expires_seconds: int
