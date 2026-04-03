from __future__ import annotations

import io
from datetime import timedelta

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


def presigned_get_url(object_key: str, expires_seconds: int = 3600) -> str:
    s = get_settings()
    c = get_client()
    return c.presigned_get_object(
        s.minio_bucket,
        object_key,
        expires=timedelta(seconds=expires_seconds),
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
