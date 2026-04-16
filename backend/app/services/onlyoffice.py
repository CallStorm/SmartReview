from __future__ import annotations

import hashlib
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.scheme_review_task import SchemeReviewTask
from app.models.user import User
from app.services.onlyoffice_settings import EffectiveOnlyoffice, get_effective_onlyoffice

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _is_loopback_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    return hostname.lower() in LOOPBACK_HOSTS


def _replace_url_host(base_url: str, new_host: str) -> str:
    parts = urlsplit(base_url)
    if not parts.hostname:
        return base_url.rstrip("/")
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{new_host}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment)).rstrip("/")


def _detect_local_lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            outbound_ip = sock.getsockname()[0]
            if outbound_ip and not _is_loopback_host(outbound_ip):
                return outbound_ip
    except OSError:
        pass
    try:
        hostname_ip = socket.gethostbyname(socket.gethostname())
        if hostname_ip and not _is_loopback_host(hostname_ip):
            return hostname_ip
    except OSError:
        return None
    return None


def resolve_onlyoffice_public_base_url(callback_base_url: str) -> str:
    base_url = callback_base_url.rstrip("/")
    base_host = urlsplit(base_url).hostname
    if _is_loopback_host(base_host):
        lan_ip = _detect_local_lan_ip()
        if lan_ip:
            return _replace_url_host(base_url, lan_ip)
    return base_url


def build_doc_key(task: SchemeReviewTask) -> str:
    ua = task.updated_at.isoformat() if task.updated_at else ""
    raw = f"{task.id}:{task.output_object_key or ''}:{ua}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_file_access_token(task_id: int) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(hours=1)
    payload = {
        "purpose": "onlyoffice_file",
        "tid": task_id,
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_file_access_token(token: str) -> int | None:
    settings = get_settings()
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if data.get("purpose") != "onlyoffice_file":
        return None
    tid = data.get("tid")
    if not isinstance(tid, int):
        return None
    return tid


def make_editor_token(config: dict[str, Any], oo_jwt_secret: str) -> str:
    return jwt.encode(config, oo_jwt_secret, algorithm="HS256")


def build_editor_config(
    *,
    task: SchemeReviewTask,
    user: User,
    eff: EffectiveOnlyoffice,
    file_token: str,
    view_only: bool = False,
) -> dict[str, Any]:
    public_base = resolve_onlyoffice_public_base_url(eff.callback_base_url)
    file_url = (
        f"{public_base}/review-tasks/{task.id}/onlyoffice/document"
        f"?token={quote(file_token, safe='')}"
    )
    title = (task.original_filename or "document.docx").strip() or "document.docx"
    editor_cfg: dict[str, Any] = {
        "mode": "view" if view_only else "edit",
        "lang": eff.editor_lang,
        "user": {"id": str(user.id), "name": user.username or f"user-{user.id}"},
        "customization": {
            "compactToolbar": True,
            "compactHeader": True,
            "toolbarHideFileName": True,
            # Ensure users can trigger explicit save, so callback pushes
            # the latest content before export/download.
            "forcesave": True,
        },
    }
    if not view_only:
        editor_cfg["callbackUrl"] = f"{public_base}/onlyoffice/callback?task_id={task.id}"
    return {
        "document": {
            "fileType": "docx",
            "key": build_doc_key(task),
            "title": title,
            "url": file_url,
        },
        "documentType": "word",
        "editorConfig": editor_cfg,
        "permissions": {
            "edit": not view_only,
            "comment": not view_only,
            "review": not view_only,
            "download": True,
            "print": True,
        },
    }


async def pull_callback_file(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def assert_onlyoffice_ready(db: Session) -> EffectiveOnlyoffice:
    eff = get_effective_onlyoffice(db)
    if not eff.docs_url or not eff.jwt_secret or not eff.callback_base_url:
        raise ValueError("OnlyOffice 未配置完整：请在「设置」或环境变量中填写 Docs 地址、JWT 密钥与回调基址")
    return eff
