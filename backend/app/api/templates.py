import json
import uuid
from datetime import UTC, datetime
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models.scheme_template import SchemeTemplate
from app.models.scheme_type import SchemeType
from app.models.user import User
from app.schemas.template import (
    DownloadUrlResponse,
    TemplatePublic,
    TemplateStructureUpdate,
    TemplateUploadResponse,
)
from app.services import minio_storage
from app.services.word_parser import parse_docx_to_tree, tree_to_json_str

router = APIRouter(tags=["templates"])

MAX_UPLOAD_BYTES = 30 * 1024 * 1024


def _validate_parsed_structure_blob(obj: object) -> None:
    if not isinstance(obj, dict):
        raise HTTPException(status_code=400, detail="parsed_structure 须为 JSON 对象")
    nodes = obj.get("nodes")
    if not isinstance(nodes, list):
        raise HTTPException(status_code=400, detail="parsed_structure 须包含 nodes 数组")


def _template_public(t: SchemeTemplate) -> TemplatePublic:
    structure = None
    if t.parsed_structure:
        try:
            structure = json.loads(t.parsed_structure)
        except json.JSONDecodeError:
            structure = None
    return TemplatePublic(
        id=t.id,
        scheme_type_id=t.scheme_type_id,
        minio_bucket=t.minio_bucket,
        object_key=t.object_key,
        original_filename=t.original_filename,
        parsed_structure=structure,
        parsed_at=t.parsed_at,
        updated_at=t.updated_at,
    )


@router.post(
    "/scheme-types/{scheme_id}/template",
    response_model=TemplateUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_template(
    scheme_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    file: UploadFile = File(...),
) -> TemplateUploadResponse:
    scheme = db.get(SchemeType, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="请上传 .docx 文件")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="文件过大")
    try:
        tree = parse_docx_to_tree(BytesIO(data))
        parsed_json = tree_to_json_str(tree)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法解析 Word: {e!s}") from e

    s = get_settings()
    object_key = f"templates/{scheme_id}/{uuid.uuid4().hex}.docx"
    try:
        minio_storage.put_object(
            object_key,
            data,
            length=len(data),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"存储失败: {e!s}") from e

    existing = db.query(SchemeTemplate).filter(SchemeTemplate.scheme_type_id == scheme_id).first()
    now = datetime.now(UTC)
    if existing:
        existing.object_key = object_key
        existing.minio_bucket = s.minio_bucket
        existing.original_filename = file.filename or "template.docx"
        existing.parsed_structure = parsed_json
        existing.parsed_at = now
        db.commit()
        db.refresh(existing)
        return TemplateUploadResponse(template=_template_public(existing), message="updated")
    row = SchemeTemplate(
        scheme_type_id=scheme_id,
        minio_bucket=s.minio_bucket,
        object_key=object_key,
        original_filename=file.filename or "template.docx",
        parsed_structure=parsed_json,
        parsed_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return TemplateUploadResponse(template=_template_public(row), message="created")


@router.get("/scheme-types/{scheme_id}/template", response_model=TemplatePublic)
def get_template(
    scheme_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TemplatePublic:
    scheme = db.get(SchemeType, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    t = db.query(SchemeTemplate).filter(SchemeTemplate.scheme_type_id == scheme_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="尚未上传模版")
    return _template_public(t)


@router.put("/scheme-types/{scheme_id}/template/structure", response_model=TemplatePublic)
def update_template_structure(
    scheme_id: int,
    body: TemplateStructureUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> TemplatePublic:
    scheme = db.get(SchemeType, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    t = db.query(SchemeTemplate).filter(SchemeTemplate.scheme_type_id == scheme_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="尚未上传模版")
    _validate_parsed_structure_blob(body.parsed_structure)
    try:
        t.parsed_structure = json.dumps(body.parsed_structure, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"无法序列化 JSON: {e!s}") from e
    db.commit()
    db.refresh(t)
    return _template_public(t)


@router.get("/scheme-types/{scheme_id}/template/download-url", response_model=DownloadUrlResponse)
def get_template_download_url(
    scheme_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    expires_seconds: int = 3600,
) -> DownloadUrlResponse:
    scheme = db.get(SchemeType, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    t = db.query(SchemeTemplate).filter(SchemeTemplate.scheme_type_id == scheme_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="尚未上传模版")
    try:
        url = minio_storage.presigned_get_url(t.object_key, expires_seconds=expires_seconds)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"无法生成下载链接: {e!s}") from e
    return DownloadUrlResponse(url=url, expires_seconds=expires_seconds)
