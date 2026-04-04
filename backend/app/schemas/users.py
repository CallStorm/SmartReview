from datetime import datetime

from pydantic import BaseModel, Field

from app.models.user import UserRole


class UserListItem(BaseModel):
    id: int
    username: str
    phone: str
    role: UserRole
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class AdminUserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    phone: str = Field(..., min_length=1, max_length=20)
    password: str = Field(..., min_length=6, max_length=128)
    role: UserRole = UserRole.user


class AdminUserUpdate(BaseModel):
    username: str | None = Field(None, min_length=1, max_length=64)
    phone: str | None = Field(None, min_length=1, max_length=20)
    password: str | None = Field(None, min_length=6, max_length=128)
    role: UserRole | None = None
