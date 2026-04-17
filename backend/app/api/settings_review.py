from __future__ import annotations

import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models.user import User
from app.schemas.review_settings import (
    ReviewBrandingPublic,
    ReviewSettingsPublic,
    ReviewSettingsUpdate,
)
from app.services import minio_storage
from app.services.review_settings import (
    DEFAULT_SYSTEM_NAME,
    get_or_create_review_settings,
    get_compilation_basis_concurrency,
    get_content_concurrency,
    get_context_consistency_concurrency,
    get_system_name,
    get_worker_parallel_tasks,
)

router = APIRouter(prefix="/settings", tags=["settings"])

MAX_BRAND_IMAGE_BYTES = 2 * 1024 * 1024
LOGO_ALLOWED_TYPES = {
    "image/png",
    "image/jpeg",
    "image/svg+xml",
    "image/webp",
}
LOGO_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
FAVICON_ALLOWED_TYPES = LOGO_ALLOWED_TYPES | {
    "image/x-icon",
    "image/vnd.microsoft.icon",
}
FAVICON_ALLOWED_EXTENSIONS = LOGO_ALLOWED_EXTENSIONS | {".ico"}


def _asset_url(request: Request, kind: str, updated_at: datetime | None) -> str:
    base = request.url_for(f"get_brand_{kind}_asset")
    version = int(updated_at.timestamp()) if updated_at else 0
    return str(base.include_query_params(v=version))


def _review_settings_public(request: Request, db: Session, row) -> ReviewSettingsPublic:
    return ReviewSettingsPublic(
        review_timeout_seconds=int(row.review_timeout_seconds),
        prompt_debug_enabled=bool(row.prompt_debug_enabled),
        worker_parallel_tasks=get_worker_parallel_tasks(db),
        compilation_basis_concurrency=get_compilation_basis_concurrency(db),
        context_consistency_concurrency=get_context_consistency_concurrency(db),
        content_concurrency=get_content_concurrency(db),
        system_name=get_system_name(db),
        logo_url=_asset_url(request, "logo", row.updated_at) if row.brand_logo_object_key else None,
        favicon_url=_asset_url(request, "favicon", row.updated_at) if row.favicon_object_key else None,
        logo_configured=bool(row.brand_logo_object_key),
        favicon_configured=bool(row.favicon_object_key),
    )


def _review_branding_public(request: Request, db: Session, row) -> ReviewBrandingPublic:
    return ReviewBrandingPublic(
        system_name=get_system_name(db),
        logo_url=_asset_url(request, "logo", row.updated_at) if row.brand_logo_object_key else None,
        favicon_url=_asset_url(request, "favicon", row.updated_at) if row.favicon_object_key else None,
        logo_configured=bool(row.brand_logo_object_key),
        favicon_configured=bool(row.favicon_object_key),
    )


def _validate_brand_image(file: UploadFile, *, kind: str) -> str:
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail=f"请上传{kind}文件")
    ext = os.path.splitext(filename)[1].lower()
    allowed_types = LOGO_ALLOWED_TYPES if kind == "logo" else FAVICON_ALLOWED_TYPES
    allowed_extensions = LOGO_ALLOWED_EXTENSIONS if kind == "logo" else FAVICON_ALLOWED_EXTENSIONS
    content_type = (file.content_type or "").strip().lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"{kind} 文件格式不支持")
    if content_type and content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"{kind} 文件类型不支持")
    if not content_type:
        if ext == ".svg":
            content_type = "image/svg+xml"
        elif ext == ".png":
            content_type = "image/png"
        elif ext in {".jpg", ".jpeg"}:
            content_type = "image/jpeg"
        elif ext == ".webp":
            content_type = "image/webp"
        else:
            content_type = "image/x-icon"
    return content_type


async def _store_brand_asset(file: UploadFile, *, folder: str, kind: str) -> tuple[str, str]:
    content_type = _validate_brand_image(file, kind=kind)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail=f"{kind} 文件不能为空")
    if len(data) > MAX_BRAND_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail=f"{kind} 文件过大（上限 2MB）")
    ext = os.path.splitext((file.filename or "").strip())[1].lower()
    object_key = f"branding/{folder}/{uuid.uuid4().hex}{ext}"
    try:
        minio_storage.put_object(
            object_key=object_key,
            data=data,
            length=len(data),
            content_type=content_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{kind} 上传失败: {exc!s}") from exc
    return object_key, content_type


@router.get("/review", response_model=ReviewSettingsPublic)
def get_review_settings(
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ReviewSettingsPublic:
    row = get_or_create_review_settings(db)
    return _review_settings_public(request, db, row)


@router.get("/review/public", response_model=ReviewBrandingPublic)
def get_public_review_settings(
    request: Request,
    db: Session = Depends(get_db),
) -> ReviewBrandingPublic:
    row = get_or_create_review_settings(db)
    return _review_branding_public(request, db, row)


@router.put("/review", response_model=ReviewSettingsPublic)
async def update_review_settings(
    request: Request,
    review_timeout_seconds: int = Form(...),
    prompt_debug_enabled: bool = Form(False),
    worker_parallel_tasks: int = Form(...),
    compilation_basis_concurrency: int = Form(...),
    context_consistency_concurrency: int = Form(...),
    content_concurrency: int = Form(...),
    system_name: str = Form(...),
    logo_file: UploadFile | None = File(None),
    favicon_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ReviewSettingsPublic:
    body = ReviewSettingsUpdate(
        review_timeout_seconds=review_timeout_seconds,
        prompt_debug_enabled=prompt_debug_enabled,
        worker_parallel_tasks=worker_parallel_tasks,
        compilation_basis_concurrency=compilation_basis_concurrency,
        context_consistency_concurrency=context_consistency_concurrency,
        content_concurrency=content_concurrency,
        system_name=system_name.strip() or DEFAULT_SYSTEM_NAME,
    )
    row = get_or_create_review_settings(db)
    row.review_timeout_seconds = int(body.review_timeout_seconds)
    row.prompt_debug_enabled = bool(body.prompt_debug_enabled)
    row.worker_parallel_tasks = int(body.worker_parallel_tasks)
    row.compilation_basis_concurrency = int(body.compilation_basis_concurrency)
    row.context_consistency_concurrency = int(body.context_consistency_concurrency)
    row.content_concurrency = int(body.content_concurrency)
    row.system_name = body.system_name.strip() or DEFAULT_SYSTEM_NAME
    old_logo_key = row.brand_logo_object_key
    old_favicon_key = row.favicon_object_key
    if logo_file is not None:
        object_key, content_type = await _store_brand_asset(logo_file, folder="logo", kind="logo")
        row.brand_logo_object_key = object_key
        row.brand_logo_content_type = content_type
    if favicon_file is not None:
        object_key, content_type = await _store_brand_asset(favicon_file, folder="favicon", kind="favicon")
        row.favicon_object_key = object_key
        row.favicon_content_type = content_type
    db.commit()
    db.refresh(row)
    if logo_file is not None and old_logo_key and old_logo_key != row.brand_logo_object_key:
        minio_storage.remove_object_if_exists(old_logo_key)
    if favicon_file is not None and old_favicon_key and old_favicon_key != row.favicon_object_key:
        minio_storage.remove_object_if_exists(old_favicon_key)
    return _review_settings_public(request, db, row)


@router.get("/review/logo", name="get_brand_logo_asset")
def get_brand_logo_asset(
    db: Session = Depends(get_db),
) -> Response:
    row = get_or_create_review_settings(db)
    if not row.brand_logo_object_key:
        raise HTTPException(status_code=404, detail="未配置 logo")
    try:
        data = minio_storage.get_object_bytes(row.brand_logo_object_key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取 logo 失败: {exc!s}") from exc
    return Response(content=data, media_type=row.brand_logo_content_type or "application/octet-stream")


@router.get("/review/favicon", name="get_brand_favicon_asset")
def get_brand_favicon_asset(
    db: Session = Depends(get_db),
) -> Response:
    row = get_or_create_review_settings(db)
    if not row.favicon_object_key:
        raise HTTPException(status_code=404, detail="未配置 favicon")
    try:
        data = minio_storage.get_object_bytes(row.favicon_object_key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取 favicon 失败: {exc!s}") from exc
    return Response(content=data, media_type=row.favicon_content_type or "application/octet-stream")
