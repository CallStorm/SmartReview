import uuid
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, defer, joinedload

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models.scheme_review_task import ReviewTaskStatus, SchemeReviewTask
from app.models.scheme_template import SchemeTemplate
from app.models.scheme_type import SchemeType
from app.models.user import User, UserRole
from app.schemas.onlyoffice_editor import OnlyofficeEditorConfigResponse
from app.schemas.review_task import ReviewTaskCreateResponse, ReviewTaskPublic
from app.schemas.template import DownloadUrlResponse
from app.services import minio_storage
from app.services.onlyoffice import (
    assert_onlyoffice_ready,
    build_editor_config,
    make_editor_token,
    make_file_access_token,
    verify_file_access_token,
)
from app.services.review_task_worker import process_scheme_review_task

router = APIRouter(prefix="/review-tasks", tags=["review-tasks"])

MAX_UPLOAD_BYTES = 30 * 1024 * 1024


def _task_public(
    t: SchemeReviewTask,
    *,
    include_review_log: bool = True,
    include_result_json: bool = True,
) -> ReviewTaskPublic:
    st = t.scheme_type
    return ReviewTaskPublic(
        id=t.id,
        scheme_type_id=t.scheme_type_id,
        scheme_category=st.category if st else "",
        scheme_name=st.name if st else "",
        status=t.status,
        result_text=t.result_text,
        error_message=t.error_message,
        review_stage=t.review_stage,
        review_result_json=(t.review_result_json if include_result_json else None),
        output_object_key=t.output_object_key,
        review_log=(t.review_log if include_review_log else None),
        original_filename=t.original_filename,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.get("", response_model=list[ReviewTaskPublic])
def list_my_tasks(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = 100,
) -> list[ReviewTaskPublic]:
    q = (
        db.query(SchemeReviewTask)
        .options(
            joinedload(SchemeReviewTask.scheme_type),
            defer(SchemeReviewTask.review_log),
            defer(SchemeReviewTask.review_result_json),
        )
        .filter(SchemeReviewTask.user_id == user.id)
        .order_by(SchemeReviewTask.id.desc())
    )
    rows = q.limit(min(limit, 200)).all()
    return [
        _task_public(r, include_review_log=False, include_result_json=False) for r in rows
    ]


@router.get("/{task_id}", response_model=ReviewTaskPublic)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReviewTaskPublic:
    t = (
        db.query(SchemeReviewTask)
        .options(joinedload(SchemeReviewTask.scheme_type))
        .filter(SchemeReviewTask.id == task_id)
        .first()
    )
    if t is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.user_id != user.id and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="无权查看该任务")
    return _task_public(t)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    t = db.get(SchemeReviewTask, task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.user_id != user.id and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="无权删除该任务")
    minio_storage.remove_object_if_exists(t.object_key)
    if (t.output_object_key or "").strip():
        minio_storage.remove_object_if_exists(t.output_object_key.strip())
    db.delete(t)
    db.commit()


@router.get("/{task_id}/output-download-url", response_model=DownloadUrlResponse)
def get_output_download_url(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DownloadUrlResponse:
    t = (
        db.query(SchemeReviewTask)
        .options(joinedload(SchemeReviewTask.scheme_type))
        .filter(SchemeReviewTask.id == task_id)
        .first()
    )
    if t is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.user_id != user.id and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="无权下载该任务文件")
    if not (t.output_object_key or "").strip():
        raise HTTPException(status_code=404, detail="暂无带批注的文档（任务未完成或结构审核未通过）")
    url = minio_storage.presigned_get_url(t.output_object_key.strip(), expires_seconds=3600)
    return DownloadUrlResponse(url=url, expires_seconds=3600)


@router.get("/{task_id}/onlyoffice/editor-config", response_model=OnlyofficeEditorConfigResponse)
def get_onlyoffice_editor_config(
    task_id: int,
    mode: str = Query("edit", description="edit：可编辑；view：仅预览（人工审阅左侧对照）"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OnlyofficeEditorConfigResponse:
    t = (
        db.query(SchemeReviewTask)
        .options(joinedload(SchemeReviewTask.scheme_type))
        .filter(SchemeReviewTask.id == task_id)
        .first()
    )
    if t is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.user_id != user.id and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="无权编辑该任务文档")
    if not (t.output_object_key or "").strip():
        raise HTTPException(status_code=404, detail="暂无带批注的文档（任务未完成或结构审核未通过）")
    normalized_mode = (mode or "edit").strip().lower()
    if normalized_mode not in ("edit", "view"):
        raise HTTPException(status_code=400, detail="mode 必须为 edit 或 view")
    view_only = normalized_mode == "view"
    try:
        eff = assert_onlyoffice_ready(db)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    file_token = make_file_access_token(t.id)
    config = build_editor_config(
        task=t, user=user, eff=eff, file_token=file_token, view_only=view_only
    )
    oo_token = make_editor_token(config, eff.jwt_secret)
    docs_url = eff.docs_url.rstrip("/")
    return OnlyofficeEditorConfigResponse(docs_url=docs_url, config=config, token=oo_token)


@router.get("/{task_id}/onlyoffice/document")
def download_onlyoffice_document(
    task_id: int,
    db: Session = Depends(get_db),
    token: str = Query(..., min_length=1),
) -> StreamingResponse:
    tid = verify_file_access_token(token)
    if tid is None or tid != task_id:
        raise HTTPException(status_code=403, detail="无效或过期的访问令牌")
    t = db.get(SchemeReviewTask, task_id)
    if t is None or not (t.output_object_key or "").strip():
        raise HTTPException(status_code=404, detail="文档不存在")
    content = minio_storage.get_object_bytes(t.output_object_key.strip())
    title = (t.original_filename or "document.docx").strip() or "document.docx"
    ascii_fallback = "document.docx"
    encoded_name = quote(title, safe="")
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_fallback}"; '
                f"filename*=UTF-8''{encoded_name}"
            )
        },
    )


@router.post("", response_model=ReviewTaskCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    background_tasks: BackgroundTasks,
    scheme_type_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReviewTaskCreateResponse:
    scheme = db.get(SchemeType, scheme_type_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    tmpl = db.query(SchemeTemplate).filter(SchemeTemplate.scheme_type_id == scheme_type_id).first()
    if tmpl is None:
        raise HTTPException(status_code=400, detail="该方案类型尚未上传模版，无法提交审核")

    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="请上传 .docx 文件")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="文件过大")

    s = get_settings()
    object_key = f"reviews/{scheme_type_id}/{uuid.uuid4().hex}.docx"
    try:
        minio_storage.put_object(
            object_key,
            data,
            length=len(data),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"存储失败: {e!s}") from e

    now = datetime.now(UTC)
    ts = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    row = SchemeReviewTask(
        scheme_type_id=scheme_type_id,
        user_id=user.id,
        status=ReviewTaskStatus.pending,
        minio_bucket=s.minio_bucket,
        object_key=object_key,
        original_filename=file.filename or "scheme.docx",
        created_at=now,
        updated_at=now,
        review_log=f"[{ts}] INFO 任务已提交，等待处理\n",
    )
    db.add(row)
    db.commit()
    loaded = (
        db.query(SchemeReviewTask)
        .options(joinedload(SchemeReviewTask.scheme_type))
        .filter(SchemeReviewTask.id == row.id)
        .first()
    )
    if loaded is None:
        raise HTTPException(status_code=500, detail="创建任务失败")

    background_tasks.add_task(process_scheme_review_task, loaded.id)

    return ReviewTaskCreateResponse(task=_task_public(loaded))
