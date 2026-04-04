from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models.model_provider_settings import ModelProviderSettings
from app.models.user import User
from app.schemas.model_provider import (
    ModelProviderPublic,
    ModelProviderUpdate,
    ModelTestRequest,
    ModelTestResult,
)
from app.services.llm.client import chat_once_test
from app.services.llm.registry import PROVIDER_REGISTRY
from app.services.llm.resolve import build_model_provider_public, resolve_for_test

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_or_create_settings_row(db: Session) -> ModelProviderSettings:
    row = db.query(ModelProviderSettings).order_by(ModelProviderSettings.id).first()
    if row is None:
        row = ModelProviderSettings()
        db.add(row)
        db.flush()
    return row


@router.get("/model-providers", response_model=ModelProviderPublic)
def get_model_providers(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ModelProviderPublic:
    return build_model_provider_public(db)


@router.put("/model-providers", response_model=ModelProviderPublic)
def update_model_providers(
    body: ModelProviderUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ModelProviderPublic:
    row = _get_or_create_settings_row(db)
    patch = body.model_dump(exclude_unset=True)

    if "default_provider" in patch:
        row.default_provider = patch["default_provider"]

    if "volcengine_base_url" in patch and patch["volcengine_base_url"] is not None:
        row.volcengine_base_url = patch["volcengine_base_url"].strip()
    key_v = patch.get("volcengine_api_key")
    if key_v is not None and str(key_v).strip():
        row.volcengine_api_key = str(key_v).strip()
    if "volcengine_endpoint_id" in patch and patch["volcengine_endpoint_id"] is not None:
        row.volcengine_endpoint_id = patch["volcengine_endpoint_id"].strip()

    if "minimax_base_url" in patch and patch["minimax_base_url"] is not None:
        row.minimax_base_url = patch["minimax_base_url"].strip()
    key_m = patch.get("minimax_api_key")
    if key_m is not None and str(key_m).strip():
        row.minimax_api_key = str(key_m).strip()
    if "minimax_model" in patch and patch["minimax_model"] is not None:
        row.minimax_model = patch["minimax_model"].strip()

    db.commit()
    db.refresh(row)
    return build_model_provider_public(db)


@router.post("/model-providers/test", response_model=ModelTestResult)
def test_model_provider(
    body: ModelTestRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ModelTestResult:
    _ = PROVIDER_REGISTRY[body.provider]
    cfg = resolve_for_test(db, body.provider)
    if not cfg.api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未配置 API Key",
        )
    if not cfg.base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未配置接入地址",
        )
    if not cfg.model_or_endpoint:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未配置模型/推理接入点",
        )

    try:
        text, latency_ms = chat_once_test(
            provider_id=body.provider,
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            model_or_endpoint=cfg.model_or_endpoint,
        )
    except ValueError as e:
        return ModelTestResult(ok=False, error=str(e)[:500])
    except Exception as e:
        return ModelTestResult(ok=False, error=str(e)[:500])

    preview = text[:120] if len(text) > 120 else text
    return ModelTestResult(ok=True, preview=preview or "（空回复）", latency_ms=latency_ms)
