from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import require_admin
from app.models.knowledge_base_settings import KnowledgeBaseSettings
from app.models.user import User
from app.schemas.knowledge_base import KnowledgeBasePublic, KnowledgeBaseUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


def _effective_config(db: Session) -> tuple[str, bool]:
    settings = get_settings()
    row = db.query(KnowledgeBaseSettings).order_by(KnowledgeBaseSettings.id).first()
    url = ""
    key_plain = ""
    if row:
        url = (row.dify_base_url or "").strip()
        key_plain = (row.dify_api_key or "").strip()
    if not url:
        url = (settings.dify_base_url or "").strip()
    if not key_plain:
        key_plain = (settings.dify_api_key or "").strip()
    configured = bool(key_plain)
    return url, configured


@router.get("/knowledge-base", response_model=KnowledgeBasePublic)
def get_knowledge_base_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> KnowledgeBasePublic:
    url, configured = _effective_config(db)
    return KnowledgeBasePublic(dify_base_url=url, api_key_configured=configured)


@router.put("/knowledge-base", response_model=KnowledgeBasePublic)
def update_knowledge_base_settings(
    body: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> KnowledgeBasePublic:
    row = db.query(KnowledgeBaseSettings).order_by(KnowledgeBaseSettings.id).first()
    if row is None:
        row = KnowledgeBaseSettings(dify_base_url="", dify_api_key="")
        db.add(row)
        db.flush()

    row.dify_base_url = body.dify_base_url
    if body.dify_api_key is not None and body.dify_api_key.strip():
        row.dify_api_key = body.dify_api_key.strip()
    db.commit()
    db.refresh(row)

    settings = get_settings()
    url = (row.dify_base_url or "").strip() or (settings.dify_base_url or "").strip()
    key_db = (row.dify_api_key or "").strip()
    key_env = (settings.dify_api_key or "").strip()
    configured = bool(key_db or key_env)
    return KnowledgeBasePublic(dify_base_url=url, api_key_configured=configured)
