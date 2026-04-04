from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models.onlyoffice_settings import OnlyofficeSettings
from app.models.user import User
from app.schemas.onlyoffice_settings import OnlyofficeSettingsPublic, OnlyofficeSettingsUpdate
from app.services.onlyoffice_settings import get_effective_onlyoffice, jwt_configured

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_or_create_row(db: Session) -> OnlyofficeSettings:
    row = db.query(OnlyofficeSettings).order_by(OnlyofficeSettings.id).first()
    if row is None:
        row = OnlyofficeSettings()
        db.add(row)
        db.flush()
    return row


@router.get("/onlyoffice", response_model=OnlyofficeSettingsPublic)
def get_onlyoffice_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> OnlyofficeSettingsPublic:
    eff = get_effective_onlyoffice(db)
    return OnlyofficeSettingsPublic(
        docs_url=eff.docs_url,
        callback_base_url=eff.callback_base_url,
        editor_lang=eff.editor_lang,
        jwt_configured=jwt_configured(eff),
    )


@router.put("/onlyoffice", response_model=OnlyofficeSettingsPublic)
def update_onlyoffice_settings(
    body: OnlyofficeSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> OnlyofficeSettingsPublic:
    row = _get_or_create_row(db)
    patch = body.model_dump(exclude_unset=True)

    if "docs_url" in patch and patch["docs_url"] is not None:
        row.docs_url = str(patch["docs_url"]).strip()
    if "callback_base_url" in patch and patch["callback_base_url"] is not None:
        row.callback_base_url = str(patch["callback_base_url"]).strip()
    if "editor_lang" in patch and patch["editor_lang"] is not None:
        row.editor_lang = str(patch["editor_lang"]).strip()

    js = patch.get("jwt_secret")
    if js is not None and str(js).strip():
        row.jwt_secret = str(js).strip()

    db.commit()
    db.refresh(row)

    eff = get_effective_onlyoffice(db)
    return OnlyofficeSettingsPublic(
        docs_url=eff.docs_url,
        callback_base_url=eff.callback_base_url,
        editor_lang=eff.editor_lang,
        jwt_configured=jwt_configured(eff),
    )
