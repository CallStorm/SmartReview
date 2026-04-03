from datetime import datetime

from pydantic import BaseModel, Field


class BasisCreate(BaseModel):
    doc_type: str = Field(default="", description="文献类型")
    standard_no: str = Field(default="", description="标准号")
    doc_name: str = Field(default="", description="文献名称")
    effect_status: str = Field(default="", description="效力状态")
    is_mandatory: bool = Field(default=False, description="是否必引")
    scheme_category: str = Field(default="", description="方案大类")
    scheme_name: str = Field(default="", description="方案名称")
    remark: str | None = None


class BasisUpdate(BaseModel):
    doc_type: str | None = None
    standard_no: str | None = None
    doc_name: str | None = None
    effect_status: str | None = None
    is_mandatory: bool | None = None
    scheme_category: str | None = None
    scheme_name: str | None = None
    remark: str | None = None


class BasisRead(BaseModel):
    id: int
    basis_id: str
    doc_type: str
    standard_no: str
    doc_name: str
    effect_status: str
    is_mandatory: bool
    scheme_category: str
    scheme_name: str
    remark: str | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}
