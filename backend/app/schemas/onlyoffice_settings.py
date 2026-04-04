from pydantic import BaseModel, Field


class OnlyofficeSettingsPublic(BaseModel):
    docs_url: str
    callback_base_url: str
    editor_lang: str
    jwt_configured: bool


class OnlyofficeSettingsUpdate(BaseModel):
    docs_url: str | None = None
    callback_base_url: str | None = None
    editor_lang: str | None = None
    jwt_secret: str | None = Field(default=None, description="非空时写入；留空不修改")
