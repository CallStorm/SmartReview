from __future__ import annotations

import io
from datetime import timedelta
from urllib.parse import quote

from minio import Minio

from app.config import get_settings


def get_client() -> Minio:
    s = get_settings()
    return Minio(
        s.minio_endpoint,
        access_key=s.minio_access_key,
        secret_key=s.minio_secret_key,
        secure=s.minio_secure,
    )


def ensure_bucket() -> None:
    s = get_settings()
    c = get_client()
    if not c.bucket_exists(s.minio_bucket):
        c.make_bucket(s.minio_bucket)


def put_object(object_key: str, data: bytes, length: int, content_type: str) -> None:
    ensure_bucket()
    s = get_settings()
    c = get_client()
    c.put_object(
        s.minio_bucket,
        object_key,
        io.BytesIO(data),
        length,
        content_type=content_type,
    )


def _content_disposition_attachment(filename: str) -> str:
    """RFC 5987: filename* for UTF-8 names; ASCII fallback for legacy clients."""
    name = (filename or "").strip() or "download.docx"
    if not name.lower().endswith(".docx"):
        name = f"{name}.docx"
    ascii_safe = "".join(
        c if 32 <= ord(c) < 127 and c not in '\\/:*?"<>|' else "_"
        for c in name
    ).strip("._")
    if not ascii_safe:
        ascii_safe = "template.docx"
    if len(ascii_safe) > 200:
        ascii_safe = ascii_safe[:200]
    quoted = quote(name, safe="")
    return f'attachment; filename="{ascii_safe}"; filename*=UTF-8\'\'{quoted}'


def presigned_get_url(
    object_key: str,
    expires_seconds: int = 3600,
    *,
    download_filename: str | None = None,
) -> str:
    s = get_settings()
    c = get_client()
    response_headers = None
    if download_filename:
        response_headers = {
            "response-content-disposition": _content_disposition_attachment(download_filename),
        }
    return c.presigned_get_object(
        s.minio_bucket,
        object_key,
        expires=timedelta(seconds=expires_seconds),
        response_headers=response_headers,
    )


def get_object_bytes(object_key: str) -> bytes:
    s = get_settings()
    c = get_client()
    r = c.get_object(s.minio_bucket, object_key)
    try:
        return r.read()
    finally:
        r.close()
        r.release_conn()


def remove_object_if_exists(object_key: str) -> None:
    """Best-effort delete; ignores missing object or errors."""
    key = (object_key or "").strip()
    if not key:
        return
    try:
        s = get_settings()
        c = get_client()
        c.remove_object(s.minio_bucket, key)
    except Exception:
        pass
