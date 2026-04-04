from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OnlyofficeEditorConfigResponse(BaseModel):
    docs_url: str
    config: dict[str, Any]
    token: str


class OnlyofficeCallbackPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    status: int
    url: str | None = None
    users: list[str] = Field(default_factory=list)
    history: dict[str, Any] | None = None
