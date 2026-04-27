from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.model_provider_settings import ModelProviderSettings
from app.schemas.model_provider import DeepseekPublic, ModelProviderPublic, MinimaxPublic, VolcenginePublic
from app.services.llm.registry import ProviderId


def _strip_pair(row_val: str | None, env_val: str) -> str:
    r = (row_val or "").strip()
    if r:
        return r
    return (env_val or "").strip()


def _get_row(db: Session) -> ModelProviderSettings | None:
    return db.query(ModelProviderSettings).order_by(ModelProviderSettings.id).first()


def effective_volcengine(db: Session, settings: Settings | None = None) -> tuple[str, str, str]:
    settings = settings or get_settings()
    row = _get_row(db)
    url = _strip_pair(row.volcengine_base_url if row else None, settings.volcengine_base_url)
    key = _strip_pair(row.volcengine_api_key if row else None, settings.volcengine_api_key)
    eid = _strip_pair(row.volcengine_endpoint_id if row else None, settings.volcengine_endpoint_id)
    return url, key, eid


def effective_minimax(db: Session, settings: Settings | None = None) -> tuple[str, str, str]:
    settings = settings or get_settings()
    row = _get_row(db)
    url = _strip_pair(row.minimax_base_url if row else None, settings.minimax_base_url)
    key = _strip_pair(row.minimax_api_key if row else None, settings.minimax_api_key)
    model = _strip_pair(row.minimax_model if row else None, settings.minimax_model)
    return url, key, model


def effective_deepseek(db: Session, settings: Settings | None = None) -> tuple[str, str, str]:
    settings = settings or get_settings()
    row = _get_row(db)
    url = _strip_pair(row.deepseek_base_url if row else None, settings.deepseek_base_url)
    key = _strip_pair(row.deepseek_api_key if row else None, settings.deepseek_api_key)
    model = _strip_pair(row.deepseek_model if row else None, settings.deepseek_model)
    return url, key, model


def effective_default_provider(db: Session, settings: Settings | None = None) -> ProviderId | None:
    settings = settings or get_settings()
    row = _get_row(db)
    if row and row.default_provider:
        p = row.default_provider.strip()
        if p in ("volcengine", "minimax", "deepseek"):
            return p  # type: ignore[return-value]
    env_p = (settings.default_llm_provider or "").strip()
    if env_p in ("volcengine", "minimax", "deepseek"):
        return env_p  # type: ignore[return-value]
    return None


def build_model_provider_public(db: Session) -> ModelProviderPublic:
    settings = get_settings()
    row = _get_row(db)
    v_url, v_key, v_eid = effective_volcengine(db, settings)
    m_url, m_key, m_model = effective_minimax(db, settings)
    d_url, d_key, d_model = effective_deepseek(db, settings)
    default_p = effective_default_provider(db, settings)
    return ModelProviderPublic(
        default_provider=default_p,
        volcengine=VolcenginePublic(
            base_url=v_url,
            endpoint_id=v_eid,
            api_key_configured=bool(v_key),
        ),
        minimax=MinimaxPublic(
            base_url=m_url,
            model=m_model,
            api_key_configured=bool(m_key),
        ),
        deepseek=DeepseekPublic(
            base_url=d_url,
            model=d_model,
            api_key_configured=bool(d_key),
        ),
    )


@dataclass
class ResolvedForTest:
    base_url: str
    api_key: str
    model_or_endpoint: str


def resolve_for_test(db: Session, provider_id: ProviderId) -> ResolvedForTest:
    settings = get_settings()
    if provider_id == "volcengine":
        url, key, eid = effective_volcengine(db, settings)
        return ResolvedForTest(base_url=url, api_key=key, model_or_endpoint=eid)
    if provider_id == "deepseek":
        url, key, model = effective_deepseek(db, settings)
        return ResolvedForTest(base_url=url, api_key=key, model_or_endpoint=model)
    url, key, model = effective_minimax(db, settings)
    return ResolvedForTest(base_url=url, api_key=key, model_or_endpoint=model)
