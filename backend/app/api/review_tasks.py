import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session, defer, joinedload

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models.scheme_review_task import ReviewTaskStatus, SchemeReviewTask
from app.models.scheme_template import SchemeTemplate
from app.models.scheme_type import SchemeType
from app.models.user import User, UserRole
from app.schemas.review_task import ReviewTaskCreateResponse, ReviewTaskPublic
from app.services import minio_storage
from app.services.review_task_worker import process_scheme_review_task

router = APIRouter(prefix="/review-tasks", tags=["review-tasks"])

MAX_UPLOAD_BYTES = 30 * 1024 * 1024


def _task_public(t: SchemeReviewTask, *, include_review_log: bool = True) -> ReviewTaskPublic:
    st = t.scheme_type
    return ReviewTaskPublic(
        id=t.id,
        scheme_type_id=t.scheme_type_id,
        scheme_category=st.category if st else "",
        scheme_name=st.name if st else "",
        status=t.status,
        result_text=t.result_text,
        error_message=t.error_message,
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
        )
        .filter(SchemeReviewTask.user_id == user.id)
        .order_by(SchemeReviewTask.id.desc())
    )
    rows = q.limit(min(limit, 200)).all()
    return [_task_public(r, include_review_log=False) for r in rows]


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
