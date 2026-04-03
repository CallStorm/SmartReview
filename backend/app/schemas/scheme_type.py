from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SchemeTypeCreate(BaseModel):
    category: str = Field(..., description="方案大类")
    name: str = Field(..., description="方案名称")
    remark: str | None = None

    @field_validator("category")
    @classmethod
    def category_non_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("方案大类不能为空")
        return s


class SchemeTypeUpdate(BaseModel):
    category: str | None = None
    name: str | None = None
    remark: str | None = None

    @field_validator("category")
    @classmethod
    def category_if_set(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            raise ValueError("方案大类不能为空")
        return s


class SchemeTypeRead(BaseModel):
    id: int
    category: str
    name: str
    remark: str | None
    created_at: datetime | None
    updated_at: datetime | None
    template_configured: bool = False

    model_config = {"from_attributes": True}
