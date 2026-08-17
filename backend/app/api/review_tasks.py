import json
import re
import uuid
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, defer, joinedload

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models.scheme_review_task import ReviewTaskStatus, SchemeReviewTask
from app.models.scheme_template import SchemeTemplate
from app.models.scheme_type import SchemeType
from app.models.user import User, UserRole
from app.schemas.onlyoffice_editor import OnlyofficeEditorConfigResponse
from app.schemas.review_task import DebugPromptPublic, ReviewTaskCreateResponse, ReviewTaskPublic
from app.schemas.template import DownloadUrlResponse
from app.services import minio_storage
from app.schemas.review_report import ReviewReportV1
from app.services.onlyoffice import (
    assert_onlyoffice_ready,
    build_editor_config,
    make_editor_token,
    make_file_access_token,
    verify_file_access_token,
)
from app.services.review_report_docx import build_audit_report_docx
from app.services.review_report_pdf import build_audit_report_pdf
from app.services.review_adversarial import generate_prompt_suggestions, run_adversarial_audit
from app.services.review_selfcheck import run_selfcheck
from app.services.review_settings import DEFAULT_SYSTEM_NAME, get_or_create_review_settings
from app.services.upload_settings import get_max_upload_mb

router = APIRouter(prefix="/review-tasks", tags=["review-tasks"])


def _audit_report_filename(original_filename: str) -> str:
    raw = (original_filename or "").strip() or "document"
    base = re.sub(r"\.docx$", "", raw, flags=re.IGNORECASE).strip() or "document"
    safe = re.sub(r'[\\/:*?"<>|]', "_", base).strip() or "document"
    return f"{safe}_审核报告.pdf"


def _audit_report_docx_filename(original_filename: str) -> str:
    raw = (original_filename or "").strip() or "document"
    base = re.sub(r"\.docx$", "", raw, flags=re.IGNORECASE).strip() or "document"
    safe = re.sub(r'[\\/:*?"<>|]', "_", base).strip() or "document"
    return f"{safe}_审核报告.docx"


def _parse_review_report_json(raw: str | None) -> ReviewReportV1 | None:
    if not (raw or "").strip():
        return None
    try:
        return ReviewReportV1.model_validate(json.loads(raw))
    except Exception:
        return None


def _task_public(
    t: SchemeReviewTask,
    *,
    include_review_log: bool = True,
    include_result_json: bool = True,
    include_debug_prompts: bool = True,
    owner_username: str | None = None,
) -> ReviewTaskPublic:
    debug_prompts: list[DebugPromptPublic] | None = None
    if include_debug_prompts and include_result_json and (t.review_result_json or "").strip():
        try:
            parsed = json.loads(t.review_result_json or "{}")
            raw_prompts = parsed.get("debug_prompts")
            if isinstance(raw_prompts, list):
                rows: list[DebugPromptPublic] = []
                for it in raw_prompts:
                    if not isinstance(it, dict):
                        continue
                    mp = it.get("model_passed")
                    rows.append(
                        DebugPromptPublic(
                            step_id=str(it.get("step_id") or ""),
                            template_node_id=str(it.get("template_node_id") or ""),
                            title_path=[str(x) for x in (it.get("title_path") or []) if str(x)],
                            prompt_text=str(it.get("prompt_text") or ""),
                            prompt_length=int(it.get("prompt_length") or 0),
                            created_at=str(it.get("created_at") or ""),
                            image_object_key=str(it.get("image_object_key") or ""),
                            image_caption=str(it.get("image_caption") or ""),
                            model_passed=(mp if isinstance(mp, bool) else None),
                            model_summary=str(it.get("model_summary") or ""),
                        )
                    )
                debug_prompts = rows or None
        except Exception:
            debug_prompts = None

    st = t.scheme_type
    return ReviewTaskPublic(
        id=t.id,
        scheme_type_id=t.scheme_type_id,
        scheme_category=st.category if st else "",
        scheme_name=st.name if st else "",
        owner_username=owner_username,
        status=t.status,
        result_text=t.result_text,
        error_message=t.error_message,
        review_stage=t.review_stage,
        review_result_json=(t.review_result_json if include_result_json else None),
        output_object_key=t.output_object_key,
        started_at=t.started_at,
        finished_at=t.finished_at,
        duration_ms=t.duration_ms,
        input_tokens=t.input_tokens,
        output_tokens=t.output_tokens,
        total_tokens=t.total_tokens,
        review_log=(t.review_log if include_review_log else None),
        debug_prompts=debug_prompts if include_debug_prompts else None,
        original_filename=t.original_filename,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.get("", response_model=list[ReviewTaskPublic])
def list_my_tasks(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ReviewTaskPublic]:
    """列出当前用户可见的全部审核任务：管理员看所有用户的任务，普通用户仅看自己的。

    注意：返回全量（无分页/无 limit）。前端 ReviewPage 的统计卡依赖 tasks.length 与
    数据看板的「审核任务总数」对齐。如果未来数据量过大（万级以上），应改为分页接口
    `{items, total}`，统计卡读 total 即可。
    """
    opts = [
        joinedload(SchemeReviewTask.scheme_type),
        defer(SchemeReviewTask.review_log),
        defer(SchemeReviewTask.review_result_json),
    ]
    if user.role == UserRole.admin:
        opts.append(joinedload(SchemeReviewTask.user))
    q = db.query(SchemeReviewTask).options(*opts)
    if user.role != UserRole.admin:
        q = q.filter(SchemeReviewTask.user_id == user.id)
    q = q.order_by(SchemeReviewTask.id.desc())
    rows = q.all()
    return [
        _task_public(
            r,
            include_review_log=False,
            include_result_json=False,
            include_debug_prompts=False,
            owner_username=(r.user.username if user.role == UserRole.admin else None),
        )
        for r in rows
    ]


@router.get("/image-url", response_model=DownloadUrlResponse)
def get_review_image_url(
    object_key: str = Query(..., min_length=1, max_length=1024),
    expires_seconds: int = Query(1800, ge=60, le=86400),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DownloadUrlResponse:
    """图审核 issue 缩略图：对文档抽取图片对象签发临时访问链接。"""
    # 仅允许访问文档图片命名空间，key 含 UUID 不可枚举
    if "/images/" not in object_key or ".." in object_key or object_key.startswith("/"):
        raise HTTPException(status_code=400, detail="非法图片对象键")
    try:
        url = minio_storage.presigned_get_url(object_key, expires_seconds=expires_seconds)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"无法生成图片链接: {e!s}") from e
    return DownloadUrlResponse(url=url, expires_seconds=expires_seconds)


@router.get("/{task_id}", response_model=ReviewTaskPublic)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReviewTaskPublic:
    t = (
        db.query(SchemeReviewTask)
        .options(joinedload(SchemeReviewTask.scheme_type), joinedload(SchemeReviewTask.user))
        .filter(SchemeReviewTask.id == task_id)
        .first()
    )
    if t is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.user_id != user.id and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="无权查看该任务")
    return _task_public(t, owner_username=t.user.username)


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
    source_key = (t.object_key or "").strip()
    source_prefix = source_key.rsplit(".", maxsplit=1)[0] if "." in source_key else source_key
    if source_prefix:
        minio_storage.remove_objects_with_prefix(f"{source_prefix}/images/")
    minio_storage.remove_object_if_exists(t.object_key)
    if (t.output_object_key or "").strip():
        minio_storage.remove_object_if_exists(t.output_object_key.strip())
    db.delete(t)
    db.commit()


@router.get("/{task_id}/self-check")
def self_check_task(
    task_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """AI 测评（确定性体检层）：程序化核验一次审核的质量，不调 LLM。"""
    t = db.get(SchemeReviewTask, task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.status == ReviewTaskStatus.pending or t.status == ReviewTaskStatus.processing:
        raise HTTPException(status_code=409, detail="任务尚未完成，暂无法测评")
    if not t.review_result_json:
        raise HTTPException(status_code=404, detail="暂无审核结果数据")
    return run_selfcheck(db, t)


@router.post("/{task_id}/ai-audit")
def start_ai_audit(
    task_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """AI 测评（对抗层）：LLM 独立复核 pass/fail 判定，生成分歧记录。"""
    t = db.get(SchemeReviewTask, task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.status == ReviewTaskStatus.pending or t.status == ReviewTaskStatus.processing:
        raise HTTPException(status_code=409, detail="任务尚未完成，暂无法测评")
    if not t.review_result_json:
        raise HTTPException(status_code=404, detail="暂无审核结果数据")
    try:
        return run_adversarial_audit(db, t)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"测评执行失败: {e!s}") from e


@router.get("/{task_id}/ai-audit/findings")
def list_ai_audit_findings(
    task_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """列出该任务的测评分歧记录（对抗层）。"""
    from app.models.review_audit_finding import ReviewAuditFinding

    rows = (
        db.query(ReviewAuditFinding)
        .filter(ReviewAuditFinding.task_id == task_id)
        .order_by(ReviewAuditFinding.id.desc())
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "node_id": r.node_id,
                "node_title": r.node_title,
                "check_item_id": r.check_item_id,
                "check_item_text": r.check_item_text,
                "finding_type": r.finding_type,
                "description": r.description,
                "status": r.status,
                "adjudicated_by": r.adjudicated_by,
            }
            for r in rows
        ]
    }


@router.patch("/audit-findings/{finding_id}")
def adjudicate_ai_audit_finding(
    finding_id: int,
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict:
    """管理员裁决分歧：status 取 confirmed / rejected / unclear。"""
    from datetime import UTC, datetime as _dt

    from app.models.review_audit_finding import ReviewAuditFinding

    status_val = str((body or {}).get("status") or "").strip()
    if status_val not in ("confirmed", "rejected", "unclear"):
        raise HTTPException(status_code=400, detail="status 须为 confirmed/rejected/unclear")
    r = db.get(ReviewAuditFinding, finding_id)
    if r is None:
        raise HTTPException(status_code=404, detail="分歧记录不存在")
    r.status = status_val
    r.adjudicated_by = user.username
    r.adjudicated_at = _dt.now(UTC)
    db.commit()
    return {"id": r.id, "status": r.status}


@router.post("/{task_id}/ai-audit/suggestions")
def build_ai_audit_suggestions(
    task_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """把已确认的分歧转成提示词优化建议（LLM 生成，供管理员参考）。"""
    t = db.get(SchemeReviewTask, task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        return generate_prompt_suggestions(db, t)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"建议生成失败: {e!s}") from e


@router.get("/{task_id}/audit-report")
def download_audit_report(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    t = (
        db.query(SchemeReviewTask)
        .options(joinedload(SchemeReviewTask.scheme_type))
        .filter(SchemeReviewTask.id == task_id)
        .first()
    )
    if t is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.user_id != user.id and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="无权下载该任务报告")
    if t.status in (ReviewTaskStatus.pending, ReviewTaskStatus.processing):
        raise HTTPException(status_code=409, detail="任务尚未完成，暂无法导出审核报告")
    report = _parse_review_report_json(t.review_result_json)
    if report is None or not report.steps:
        raise HTTPException(status_code=404, detail="暂无审核报告数据")
    settings = get_or_create_review_settings(db)
    system_name = (settings.system_name or "").strip() or DEFAULT_SYSTEM_NAME
    content = build_audit_report_pdf(t, report, system_name=system_name)
    filename = _audit_report_filename(t.original_filename)
    ascii_fallback = "audit-report.pdf"
    encoded_name = quote(filename, safe="")
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_fallback}"; '
                f"filename*=UTF-8''{encoded_name}"
            )
        },
    )


@router.get("/{task_id}/audit-report.docx")
def download_audit_report_docx(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    t = (
        db.query(SchemeReviewTask)
        .options(joinedload(SchemeReviewTask.scheme_type))
        .filter(SchemeReviewTask.id == task_id)
        .first()
    )
    if t is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.user_id != user.id and user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="无权下载该任务报告")
    if t.status in (ReviewTaskStatus.pending, ReviewTaskStatus.processing):
        raise HTTPException(status_code=409, detail="任务尚未完成，暂无法导出审核报告")
    report = _parse_review_report_json(t.review_result_json)
    if report is None or not report.steps:
        raise HTTPException(status_code=404, detail="暂无审核报告数据")
    settings = get_or_create_review_settings(db)
    system_name = (settings.system_name or "").strip() or DEFAULT_SYSTEM_NAME
    payload = build_audit_report_docx(t, report, system_name=system_name)
    filename = _audit_report_docx_filename(t.original_filename)
    ascii_fallback = "audit-report.docx"
    encoded_name = quote(filename, safe="")
    return StreamingResponse(
        iter([payload]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_fallback}"; '
                f"filename*=UTF-8''{encoded_name}"
            )
        },
    )


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
    if t.status in (ReviewTaskStatus.pending, ReviewTaskStatus.processing):
        raise HTTPException(status_code=409, detail="任务尚未完成，暂无法导出")
    object_key = (t.output_object_key or "").strip() or (t.object_key or "").strip()
    if not object_key:
        raise HTTPException(status_code=404, detail="文档不存在")
    url = minio_storage.presigned_get_url(object_key, expires_seconds=3600)
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
    max_mb = get_max_upload_mb(db)
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"文件超过 {max_mb} MB 限制")

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
        .options(joinedload(SchemeReviewTask.scheme_type), joinedload(SchemeReviewTask.user))
        .filter(SchemeReviewTask.id == row.id)
        .first()
    )
    if loaded is None:
        raise HTTPException(status_code=500, detail="创建任务失败")

    return ReviewTaskCreateResponse(task=_task_public(loaded, owner_username=user.username))
