"""Shared Dify URL + API key resolution (DB row then env)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.knowledge_base_settings import KnowledgeBaseSettings


def get_dify_url_and_key(db: Session) -> tuple[str, str]:
    row = db.query(KnowledgeBaseSettings).order_by(KnowledgeBaseSettings.id).first()
    settings = get_settings()
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


def get_dify_dataset_name_prefix(db: Session) -> str:
    row = db.query(KnowledgeBaseSettings).order_by(KnowledgeBaseSettings.id).first()
    if row is None:
        return ""
    return (row.dify_dataset_name_prefix or "").strip()
