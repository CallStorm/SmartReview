from pydantic import BaseModel, Field, field_validator


class KnowledgeBasePublic(BaseModel):
    """返回给前端：不暴露完整密钥。"""

    dify_base_url: str
    api_key_configured: bool


class KnowledgeBaseUpdate(BaseModel):
    dify_base_url: str = Field(..., description="Dify API 根路径，如 http://host/v1")
    dify_api_key: str | None = Field(
        default=None,
        description="新密钥；不传或空字符串表示不修改已保存的密钥",
    )

    @field_validator("dify_base_url")
    @classmethod
    def strip_url(cls, v: str) -> str:
        return v.strip()
