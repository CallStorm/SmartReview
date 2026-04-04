"""OnlyOffice 配置：数据库非空优先，否则环境变量。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.onlyoffice_settings import OnlyofficeSettings


def _strip_pair(row_val: str | None, env_val: str) -> str:
    r = (row_val or "").strip()
    if r:
        return r
    return (env_val or "").strip()


@dataclass(frozen=True)
class EffectiveOnlyoffice:
    docs_url: str
    jwt_secret: str
    callback_base_url: str
    editor_lang: str


def get_effective_onlyoffice(db: Session, settings: Settings | None = None) -> EffectiveOnlyoffice:
    settings = settings or get_settings()
    row = db.query(OnlyofficeSettings).order_by(OnlyofficeSettings.id).first()
    docs = _strip_pair(row.docs_url if row else None, settings.onlyoffice_docs_url)
    jwt_s = _strip_pair(row.jwt_secret if row else None, settings.onlyoffice_jwt_secret)
    cb = _strip_pair(row.callback_base_url if row else None, settings.onlyoffice_callback_base_url)
    lang = _strip_pair(row.editor_lang if row else None, settings.onlyoffice_editor_lang)
    if not lang:
        lang = "zh"
    return EffectiveOnlyoffice(
        docs_url=docs,
        jwt_secret=jwt_s,
        callback_base_url=cb,
        editor_lang=lang,
    )


def jwt_configured(eff: EffectiveOnlyoffice) -> bool:
    return bool(eff.jwt_secret)
