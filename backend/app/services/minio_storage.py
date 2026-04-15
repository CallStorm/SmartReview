from __future__ import annotations

import io
from multiprocessing import Process, Queue
from datetime import timedelta
from urllib.parse import quote

from minio import Minio
from urllib3 import PoolManager, Timeout

from app.config import get_settings


def _build_http_client(timeout_seconds: float) -> PoolManager:
    t = max(1.0, float(timeout_seconds))
    return PoolManager(
        timeout=Timeout(total=t, connect=min(10.0, t), read=t),
        retries=False,
    )


def _looks_like_timeout(exc: Exception) -> bool:
    text = str(exc).lower()
    return ("timeout" in text) or ("timed out" in text) or ("read timed out" in text)


def get_client(timeout_seconds: float | None = None) -> Minio:
    s = get_settings()
    http_client = _build_http_client(timeout_seconds) if timeout_seconds is not None else None
    return Minio(
        s.minio_endpoint,
        access_key=s.minio_access_key,
        secret_key=s.minio_secret_key,
        secure=s.minio_secure,
        http_client=http_client,
    )


def ensure_bucket(timeout_seconds: float | None = None) -> None:
    s = get_settings()
    c = get_client(timeout_seconds=timeout_seconds)
    if not c.bucket_exists(s.minio_bucket):
        c.make_bucket(s.minio_bucket)


def put_object(
    object_key: str,
    data: bytes,
    length: int,
    content_type: str,
    *,
    timeout_seconds: float | None = None,
) -> None:
    try:
        ensure_bucket(timeout_seconds=timeout_seconds)
        s = get_settings()
        c = get_client(timeout_seconds=timeout_seconds)
        c.put_object(
            s.minio_bucket,
            object_key,
            io.BytesIO(data),
            length,
            content_type=content_type,
        )
    except Exception as e:
        if _looks_like_timeout(e):
            t = timeout_seconds if timeout_seconds is not None else "default"
            raise TimeoutError(f"MinIO 上传超时（timeout={t}s, object_key={object_key}）") from e
        raise


def _put_object_worker(
    q: Queue,
    object_key: str,
    data: bytes,
    length: int,
    content_type: str,
    timeout_seconds: float | None,
) -> None:
    try:
        put_object(
            object_key=object_key,
            data=data,
            length=length,
            content_type=content_type,
            timeout_seconds=timeout_seconds,
        )
        q.put(("ok", ""))
    except Exception as e:
        q.put(("err", f"{type(e).__name__}: {e!s}"))


def put_object_with_hard_timeout(
    object_key: str,
    data: bytes,
    length: int,
    content_type: str,
    *,
    timeout_seconds: float,
    hard_timeout_seconds: float | None = None,
) -> None:
    deadline = hard_timeout_seconds if hard_timeout_seconds is not None else (float(timeout_seconds) + 5.0)
    q: Queue = Queue(maxsize=1)
    p = Process(
        target=_put_object_worker,
        args=(q, object_key, data, length, content_type, timeout_seconds),
        daemon=True,
    )
    p.start()
    p.join(max(1.0, float(deadline)))
    if p.is_alive():
        p.terminate()
        p.join(2.0)
        raise TimeoutError(
            f"MinIO 上传硬超时（hard_timeout={deadline}s, timeout={timeout_seconds}s, object_key={object_key}）"
        )
    if not q.empty():
        status, payload = q.get()
        if status == "ok":
            return
        raise RuntimeError(f"MinIO 上传失败: {payload}")
    if p.exitcode not in (0, None):
        raise RuntimeError(f"MinIO 上传子进程异常退出（exitcode={p.exitcode}）")


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
