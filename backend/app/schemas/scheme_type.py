from datetime import datetime

from pydantic import BaseModel, Field


class SchemeTypeCreate(BaseModel):
    business_code: str = Field(..., description="方案业务ID")
    category: str = Field(default="", description="方案大类")
    name: str = Field(..., description="方案名称")
    remark: str | None = None


class SchemeTypeUpdate(BaseModel):
    business_code: str | None = None
    category: str | None = None
    name: str | None = None
    remark: str | None = None


class SchemeTypeRead(BaseModel):
    id: int
    business_code: str
    category: str
    name: str
    remark: str | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}
