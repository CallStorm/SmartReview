import json
import re
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
    ContentReviewRulesUpdate,
    DownloadUrlResponse,
    FullDocumentReviewConfigUpdate,
    ImageReviewMissingTextUpdate,
    ImageReviewRulesUpdate,
    OptimizePromptRequest,
    OptimizePromptResponse,
    PromptHistoryEntry,
    PromptHistoryListResponse,
    ReviewWorkflowUpdate,
    SplitPreviewItem,
    SplitPreviewRequest,
    SplitPreviewResponse,
    StructureMatchModeUpdate,
    TemplatePublic,
    TemplateStructureUpdate,
    TemplateUploadResponse,
)
from app.services import minio_storage
from app.services.prompt_history import (
    image_review_to_history_value as _image_review_to_history_value,
    load_structure,
    record_field_change,
    record_full_document_diff,
    record_structure_diff,
)
from app.services.upload_settings import get_max_upload_mb
from app.services.word_parser import parse_docx_to_tree, tree_to_json_str

router = APIRouter(tags=["templates"])


def _download_filename_for_scheme_template(scheme: SchemeType) -> str:
    """Human-readable .docx name: 方案大类 + 方案名称（与前台展示一致）。"""
    def clean(part: str) -> str:
        s = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", (part or "").strip())
        s = re.sub(r"\s+", " ", s).strip()
        return s[:120]

    cat, name = clean(scheme.category), clean(scheme.name)
    if cat and name:
        base = f"{cat}_{name}"
    else:
        base = cat or name or "方案模板"
    if not base.lower().endswith(".docx"):
        base = f"{base}.docx"
    return base


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
    workflow = None
    if t.review_workflow:
        try:
            workflow = json.loads(t.review_workflow)
        except json.JSONDecodeError:
            workflow = None
    full_doc = None
    if t.full_document_review_config:
        try:
            full_doc = json.loads(t.full_document_review_config)
        except json.JSONDecodeError:
            full_doc = None
    return TemplatePublic(
        id=t.id,
        scheme_type_id=t.scheme_type_id,
        minio_bucket=t.minio_bucket,
        object_key=t.object_key,
        original_filename=t.original_filename,
        parsed_structure=structure,
        review_workflow=workflow,
        full_document_review_config=full_doc,
        content_review_rules=t.content_review_rules,
        image_review_rules=t.image_review_rules,
        image_review_missing_text=t.image_review_missing_text,
        structure_match_mode=t.structure_match_mode or "exact",
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
    max_mb = get_max_upload_mb(db)
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"文件超过 {max_mb} MB 限制")
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
    user: User = Depends(require_admin),
) -> TemplatePublic:
    scheme = db.get(SchemeType, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    t = db.query(SchemeTemplate).filter(SchemeTemplate.scheme_type_id == scheme_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="尚未上传模版")
    _validate_parsed_structure_blob(body.parsed_structure)
    old_structure = load_structure(t)
    try:
        t.parsed_structure = json.dumps(body.parsed_structure, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"无法序列化 JSON: {e!s}") from e
    record_structure_diff(
        db,
        template=t,
        old_structure=old_structure,
        new_structure=body.parsed_structure,
        changed_by=user.username,
    )
    db.commit()
    db.refresh(t)
    return _template_public(t)


@router.put("/scheme-types/{scheme_id}/template/review-workflow", response_model=TemplatePublic)
def update_template_review_workflow(
    scheme_id: int,
    body: ReviewWorkflowUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> TemplatePublic:
    scheme = db.get(SchemeType, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    t = db.query(SchemeTemplate).filter(SchemeTemplate.scheme_type_id == scheme_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="尚未上传模版")
    try:
        t.review_workflow = json.dumps(
            body.review_workflow.model_dump(), ensure_ascii=False
        )
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"无法序列化工作流: {e!s}") from e
    db.commit()
    db.refresh(t)
    return _template_public(t)


@router.put(
    "/scheme-types/{scheme_id}/template/full-document-review",
    response_model=TemplatePublic,
)
def update_template_full_document_review(
    scheme_id: int,
    body: FullDocumentReviewConfigUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> TemplatePublic:
    scheme = db.get(SchemeType, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    t = db.query(SchemeTemplate).filter(SchemeTemplate.scheme_type_id == scheme_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="尚未上传模版")
    old_config = None
    if t.full_document_review_config:
        try:
            old_config = json.loads(t.full_document_review_config)
        except (TypeError, ValueError):
            old_config = None
    try:
        t.full_document_review_config = json.dumps(
            body.full_document_review_config.model_dump(),
            ensure_ascii=False,
        )
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"无法序列化配置: {e!s}") from e
    record_full_document_diff(
        db,
        template=t,
        old_config=old_config,
        new_config=body.full_document_review_config.model_dump(),
        changed_by=user.username,
    )
    db.commit()
    db.refresh(t)
    return _template_public(t)


@router.patch(
    "/scheme-types/{scheme_id}/template/structure-match-mode",
    response_model=TemplatePublic,
)
def update_template_structure_match_mode(
    scheme_id: int,
    body: StructureMatchModeUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> TemplatePublic:
    scheme = db.get(SchemeType, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    t = db.query(SchemeTemplate).filter(SchemeTemplate.scheme_type_id == scheme_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="尚未上传模版")
    t.structure_match_mode = body.mode
    db.commit()
    db.refresh(t)
    return _template_public(t)


@router.put(
    "/scheme-types/{scheme_id}/template/content-review-rules",
    response_model=TemplatePublic,
)
def update_template_content_review_rules(
    scheme_id: int,
    body: ContentReviewRulesUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> TemplatePublic:
    scheme = db.get(SchemeType, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    t = db.query(SchemeTemplate).filter(SchemeTemplate.scheme_type_id == scheme_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="尚未上传模版")
    old_rules = t.content_review_rules or ""
    value = (body.content_review_rules or "").strip()
    t.content_review_rules = value or None
    record_field_change(
        db,
        template=t,
        field="content_review_rules",
        old_value=old_rules,
        new_value=value,
        changed_by=user.username,
    )
    db.commit()
    db.refresh(t)
    return _template_public(t)


@router.put(
    "/scheme-types/{scheme_id}/template/image-review-rules",
    response_model=TemplatePublic,
)
def update_template_image_review_rules(
    scheme_id: int,
    body: ImageReviewRulesUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> TemplatePublic:
    scheme = db.get(SchemeType, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    t = db.query(SchemeTemplate).filter(SchemeTemplate.scheme_type_id == scheme_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="尚未上传模版")
    old_rules = t.image_review_rules or ""
    value = (body.image_review_rules or "").strip()
    t.image_review_rules = value or None
    record_field_change(
        db,
        template=t,
        field="image_review_rules",
        old_value=old_rules,
        new_value=value,
        changed_by=user.username,
        node_title="图审核全局规则",
    )
    db.commit()
    db.refresh(t)
    return _template_public(t)


@router.put(
    "/scheme-types/{scheme_id}/template/image-review-missing-text",
    response_model=TemplatePublic,
)
def update_template_image_review_missing_text(
    scheme_id: int,
    body: ImageReviewMissingTextUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> TemplatePublic:
    """模板级「缺图提示文案」：节点配置了图审核但未检出附图时，在问题列表展示的说明文字。"""
    scheme = db.get(SchemeType, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    t = db.query(SchemeTemplate).filter(SchemeTemplate.scheme_type_id == scheme_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="尚未上传模版")
    old_text = t.image_review_missing_text or ""
    value = (body.image_review_missing_text or "").strip()
    t.image_review_missing_text = value or None
    record_field_change(
        db,
        template=t,
        field="image_review_missing_text",
        old_value=old_text,
        new_value=value,
        changed_by=user.username,
        node_title="图审核缺图提示文案",
    )
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
        url = minio_storage.presigned_get_url(
            t.object_key,
            expires_seconds=expires_seconds,
            download_filename=_download_filename_for_scheme_template(scheme),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"无法生成下载链接: {e!s}") from e
    return DownloadUrlResponse(url=url, expires_seconds=expires_seconds)


def _find_node(nodes, node_id: str):
    for n in nodes:
        if isinstance(n, dict) and str(n.get("id") or "") == node_id:
            return n
        found = _find_node(n.get("children") or [], node_id) if isinstance(n, dict) else None
        if found is not None:
            return found
    return None


def _get_template_or_404(db: Session, scheme_id: int) -> tuple[SchemeType, SchemeTemplate]:
    scheme = db.get(SchemeType, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    t = db.query(SchemeTemplate).filter(SchemeTemplate.scheme_type_id == scheme_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="尚未上传模版")
    return scheme, t


@router.get(
    "/scheme-types/{scheme_id}/template/prompt-history",
    response_model=PromptHistoryListResponse,
)
def list_prompt_history(
    scheme_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    node_id: str | None = None,
    field: str | None = None,
    limit: int = 50,
) -> PromptHistoryListResponse:
    _, t = _get_template_or_404(db, scheme_id)
    from app.services.prompt_history import list_history

    rows = list_history(db, template_id=t.id, node_id=node_id, field=field, limit=limit)
    return PromptHistoryListResponse(
        items=[
            PromptHistoryEntry(
                id=r.id,
                node_id=r.node_id,
                field=r.field,
                node_title=r.node_title,
                old_value=r.old_value,
                new_value=r.new_value,
                source=r.source,
                changed_by=r.changed_by,
                changed_at=r.changed_at,
            )
            for r in rows
        ]
    )


@router.post(
    "/scheme-types/{scheme_id}/template/prompt-history/{entry_id}/restore",
    response_model=TemplatePublic,
)
def restore_prompt_history_entry(
    scheme_id: int,
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> TemplatePublic:
    """把某条历史记录的 old_value 写回模板（一键回滚）。"""
    from app.services.prompt_history import get_entry, record_field_change

    _, t = _get_template_or_404(db, scheme_id)
    entry = get_entry(db, entry_id)
    if entry is None or entry.template_id != t.id:
        raise HTTPException(status_code=404, detail="历史记录不存在")

    if entry.field == "content_review_rules":
        current = t.content_review_rules or ""
        t.content_review_rules = entry.old_value or None
        record_field_change(
            db,
            template=t,
            field="content_review_rules",
            old_value=current,
            new_value=entry.old_value or "",
            changed_by=user.username,
            source="restore",
        )
    elif entry.field == "image_review_rules":
        current = t.image_review_rules or ""
        t.image_review_rules = entry.old_value or None
        record_field_change(
            db,
            template=t,
            field="image_review_rules",
            old_value=current,
            new_value=entry.old_value or "",
            changed_by=user.username,
            node_title="图审核全局规则",
            source="restore",
        )
    elif entry.field == "image_review_missing_text":
        current = t.image_review_missing_text or ""
        t.image_review_missing_text = entry.old_value or None
        record_field_change(
            db,
            template=t,
            field="image_review_missing_text",
            old_value=current,
            new_value=entry.old_value or "",
            changed_by=user.username,
            node_title="图审核缺图提示文案",
            source="restore",
        )
    elif entry.field == "full_document_review_prompt":
        config = None
        if t.full_document_review_config:
            try:
                config = json.loads(t.full_document_review_config)
            except (TypeError, ValueError):
                config = None
        config = config if isinstance(config, dict) else {}
        current = str(config.get("review_prompt") or "")
        config["review_prompt"] = entry.old_value
        t.full_document_review_config = json.dumps(config, ensure_ascii=False)
        record_field_change(
            db,
            template=t,
            field="full_document_review_prompt",
            old_value=current,
            new_value=entry.old_value,
            changed_by=user.username,
            node_title="通篇审核",
            source="restore",
        )
    elif entry.field == "image_review":
        structure = load_structure(t) or {"nodes": []}
        node = _find_node(structure.get("nodes") or [], entry.node_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f"节点 {entry.node_id} 已不存在，无法回滚")
        current_raw = node.get("image_review")
        current = _image_review_to_history_value(current_raw)
        if entry.old_value.strip():
            try:
                node["image_review"] = json.loads(entry.old_value)
            except (TypeError, ValueError) as e:
                raise HTTPException(status_code=400, detail=f"历史记录值无法解析: {e!s}") from e
        else:
            node.pop("image_review", None)
        t.parsed_structure = json.dumps(structure, ensure_ascii=False)
        record_field_change(
            db,
            template=t,
            field="image_review",
            old_value=current,
            new_value=entry.old_value,
            changed_by=user.username,
            node_id=entry.node_id,
            node_title=entry.node_title,
            source="restore",
        )
    elif entry.field in ("review_prompt", "context_consistency_prompt"):
        structure = load_structure(t) or {"nodes": []}
        node = _find_node(structure.get("nodes") or [], entry.node_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f"节点 {entry.node_id} 已不存在，无法回滚")
        current = str(node.get(entry.field) or "")
        node[entry.field] = entry.old_value
        t.parsed_structure = json.dumps(structure, ensure_ascii=False)
        record_field_change(
            db,
            template=t,
            field=entry.field,
            old_value=current,
            new_value=entry.old_value,
            changed_by=user.username,
            node_id=entry.node_id,
            node_title=entry.node_title,
            source="restore",
        )
    else:
        raise HTTPException(status_code=400, detail=f"不支持回滚的字段: {entry.field}")

    db.commit()
    db.refresh(t)
    return _template_public(t)


@router.post(
    "/scheme-types/{scheme_id}/template/split-preview",
    response_model=SplitPreviewResponse,
)
def preview_split_check_items(
    scheme_id: int,
    body: SplitPreviewRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> SplitPreviewResponse:
    """预览审核提示词会被确定性拆分成哪些检查项（不调 LLM）。"""
    from app.services.checklist import split_check_items

    items, notes = split_check_items(
        body.node_id or "preview",
        body.review_prompt,
    )
    return SplitPreviewResponse(
        items=[SplitPreviewItem(id=i["id"], text=i["text"]) for i in items],
        notes=notes,
    )


_OPTIMIZE_REVIEW_PRINCIPLES = """你是建筑施工方案审核系统的提示词工程师。请把给定的「审核提示词」改写成更适合逐项判定审核的形式，严格遵守：

1. 一句一行、一行一条检查项：系统会把每行（每句）作为一条独立检查项交给审核模型逐项判定 pass/fail，一行内不得塞多个字段。
2. 枚举字段逐条拆开：原文用顿号列举的内容（如"步距、纵距、横距、连墙件布置方式"）按语义归组拆成多行，每行 2~5 个强相关字段；语义独立的字段（如"连墙件布置方式"）单独一行。
3. 文字取自原文：改写只做拆分与最小限度的通顺化，不得新增、删减或放宽任何审核要求；禁止引入原文没有的新检查点。
4. 判级说明保留：类似"若无X则属于严重缺陷"的句子保留为独立一行。
5. 判定口径说明保留：类似"概念相同即可、不需要完全一致"的说明句保留（系统会自动识别为附注，不占检查项编号）。
6. 不使用带圈序号①②③（系统会当作特殊结构处理）；直接每行一条。

输出 JSON：{"optimized_text": "改写后的多行文本", "changes": ["修改点1", "修改点2", ...]}。changes 用一句话说明每处修改（如"把第2行的15个参数拆成4行"）。"""

_OPTIMIZE_CTX_PRINCIPLES = """你是建筑施工方案审核系统的提示词工程师。请把给定的「上下文一致性比对提示词」改写成字段化、可逐项比对的核对清单，严格遵守：

1. 逐项比对：每行一个比对点，明确两侧的章节与字段（如"技术参数节的材料规格型号须与材料与设备计划完全一致"）。
2. 字段化：把"规格型号、数量"等打包词拆成具体字段行（材料名称、规格型号、数量、工种名称、人数、总数……），只保留原文涉及的字段。
3. 名称一致性优先：凡涉及名称/工种/型号的比对，须写明名称须完全一致，同一事物不得使用不同名称（如同一工种的两个叫法）。
4. 文字取自原文：不得新增原文没有的比对点；只是把模糊的一句话要求变成逐字段清单。
5. 不使用带圈序号①②③；直接每行一条。

输出 JSON：{"optimized_text": "改写后的多行文本", "changes": ["修改点1", ...]}。"""


@router.post(
    "/scheme-types/{scheme_id}/template/optimize-prompt",
    response_model=OptimizePromptResponse,
)
def optimize_template_prompt(
    scheme_id: int,
    body: OptimizePromptRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> OptimizePromptResponse:
    """LLM 辅助优化提示词（按逐项判定/逐字段比对原则改写）。

    只返回优化建议文本与修改说明，不直接写入模板；由管理员在前端
    diff 确认后走正常保存（自动记历史）。
    """
    from app.services.checklist import split_check_items
    from app.services.llm.chat import chat_json

    text = (body.current_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="提示词为空，无法优化")

    system = (
        _OPTIMIZE_REVIEW_PRINCIPLES
        if body.kind == "review_prompt"
        else _OPTIMIZE_CTX_PRINCIPLES
    )
    parts: list[str] = []
    if body.scheme_name:
        parts.append(f"方案类型：{body.scheme_name}")
    if body.node_title:
        parts.append(f"章节：{body.node_title}")
    if body.kind == "review_prompt":
        items, _ = split_check_items("preview", text)
        item_lines = "\n".join(f"- {i['text']}" for i in items)
        parts.append(f"当前提示词会被系统拆成 {len(items)} 条检查项：\n{item_lines}")
    parts.append("待优化提示词：\n" + text)
    try:
        data = chat_json(
            db,
            user_message="\n\n".join(parts),
            system=system,
            max_tokens=8192,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"模型调用失败: {e!s}") from e

    optimized = str(data.get("optimized_text") or "").strip()
    if not optimized:
        raise HTTPException(status_code=502, detail="模型未返回有效的优化文本")
    changes = [str(c) for c in data.get("changes") or [] if str(c).strip()]
    return OptimizePromptResponse(optimized_text=optimized, changes=changes)


@router.post("/scheme-types/{scheme_id}/prompt-regression")
def start_prompt_regression(
    scheme_id: int,
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict:
    """提示词回归测试：把最近 N 份成功任务重新提交（带 [回归] 前缀）。"""
    from app.services.prompt_regression import create_regression_tasks

    _, t = _get_template_or_404(db, scheme_id)
    try:
        task_limit = int((body or {}).get("task_limit") or 5)
    except (TypeError, ValueError):
        task_limit = 5
    try:
        pairs = create_regression_tasks(
            db, scheme_id=scheme_id, admin_user_id=user.id, task_limit=task_limit
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"回归任务创建失败: {e!s}") from e
    return {"pairs": pairs}


@router.post("/scheme-types/{scheme_id}/prompt-regression/compare")
def compare_prompt_regression(
    scheme_id: int,
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """对比回归任务与源任务的问题集差异。"""
    from app.services.prompt_regression import compare_regression_pair

    pairs = (body or {}).get("pairs") or []
    results = []
    errors = []
    for p in pairs:
        if not isinstance(p, dict):
            continue
        try:
            results.append(
                compare_regression_pair(
                    db,
                    original_id=int(p.get("original_task_id")),
                    rerun_id=int(p.get("rerun_task_id")),
                )
            )
        except (TypeError, ValueError) as e:
            errors.append(str(e))
    return {"results": results, "errors": errors}
