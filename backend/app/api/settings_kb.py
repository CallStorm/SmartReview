import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import require_admin
from app.models.knowledge_base_settings import KnowledgeBaseSettings
from app.models.user import User
from app.schemas.knowledge_base import DifyDatasetItem, KnowledgeBasePublic, KnowledgeBaseUpdate
from app.services.dify_client import list_dataset_catalog

router = APIRouter(prefix="/settings", tags=["settings"])


def _dify_url_and_key(db: Session) -> tuple[str, str]:
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
    return url, key_plain


def _effective_config(db: Session) -> tuple[str, bool]:
    url, key_plain = _dify_url_and_key(db)
    return url, bool(key_plain)


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


@router.get("/knowledge-base/datasets", response_model=list[DifyDatasetItem])
def list_dify_datasets(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[DifyDatasetItem]:
    """代理 Dify 知识库列表（使用服务端保存的 Dataset API 配置）。"""
    url, key = _dify_url_and_key(db)
    try:
        rows = list_dataset_catalog(url, key)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = (e.response.text or "")[:500]
        except Exception:
            detail = ""
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Dify 请求失败（{e.response.status_code}）{': ' + detail if detail else ''}",
        ) from e
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"无法连接 Dify: {e!s}",
        ) from e
    return [DifyDatasetItem(id=r["id"], name=r.get("name") or "") for r in rows]
