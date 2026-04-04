"""Scheme review: workflow steps, structure fail-fast, LLM steps, Word output."""

from __future__ import annotations

import json
import traceback
import uuid
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.database import SessionLocal
from app.models.basis_item import BasisItem
from app.models.scheme_review_task import ReviewTaskStatus, SchemeReviewTask
from app.models.scheme_template import SchemeTemplate
from app.models.scheme_type import SchemeType
from app.schemas.review_report import ReportIssue, ReportStep, ReviewReportV1
from app.schemas.template import ReviewWorkflowData
from app.services import minio_storage
from app.services.doc_tree_utils import (
    collect_subtree_text,
    iter_nodes,
    resolve_user_node,
    title_path_for_node,
)
from app.services.docx_comments import inject_comments_at_paragraphs
from app.services.dify_client import retrieve_dataset_chunks
from app.services.dify_settings import get_dify_url_and_key
from app.services.llm.chat import chat_json
from app.services.llm.resolve import effective_default_provider
from app.services.tree_align import align_template_user_trees, title_path_str
from app.services.word_parser import parse_docx_to_tree

JSON_SYSTEM = """你是工程文档审核助手。你必须只输出一个 JSON 对象，不要用 markdown 代码块包裹。
格式严格如下：
{
  "passed": true 或 false,
  "summary": "一句话摘要",
  "issues": [
    {
      "severity": "error",
      "message": "问题说明",
      "evidence": "文档中的依据摘录",
      "related": { }
    }
  ]
}
severity 取值仅为 error、warning、info。若无问题，issues 为 [] 且 passed 为 true。related 可为空对象。"""


def _append_log(db: Session, task: SchemeReviewTask, level: str, message: str) -> None:
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    task.review_log = (task.review_log or "") + f"[{ts}] {level.upper()} {message}\n"


def _structure_issues_to_report(structure_raw: list[dict[str, Any]]) -> ReportStep:
    issues: list[ReportIssue] = []
    for raw in structure_raw:
        tp = raw.get("title_path") or []
        hpi = raw.get("heading_para_index")
        anchor: dict[str, Any] = {"title_path": tp, "template_node_id": raw.get("template_node_id")}
        if isinstance(hpi, int):
            anchor["heading_para_index"] = hpi
        issues.append(
            ReportIssue(
                severity="error",
                message=str(raw.get("message") or ""),
                evidence="",
                anchor=anchor,
                related={"kind": str(raw.get("kind") or "")},
            )
        )
    return ReportStep(
        step_id="structure",
        passed=len(issues) == 0,
        summary="结构审核通过" if not issues else "文档章节结构与模版不一致",
        issues=issues,
    )


def _normalize_llm_step(
    step_id: str,
    data: dict[str, Any],
    anchor_base: dict[str, Any],
) -> ReportStep:
    raw_issues = data.get("issues")
    if not isinstance(raw_issues, list):
        raw_issues = []
    issues: list[ReportIssue] = []
    for it in raw_issues:
        if not isinstance(it, dict):
            continue
        sev = str(it.get("severity") or "error")
        if sev not in ("error", "warning", "info"):
            sev = "error"
        rel = it.get("related")
        if not isinstance(rel, dict):
            rel = {}
        extra_anchor = it.get("anchor")
        anchor = {**anchor_base}
        if isinstance(extra_anchor, dict):
            anchor.update(extra_anchor)
        issues.append(
            ReportIssue(
                severity=sev,  # type: ignore[arg-type]
                message=str(it.get("message") or ""),
                evidence=str(it.get("evidence") or ""),
                anchor=anchor,
                related=rel,
            )
        )
    passed = bool(data.get("passed")) if "passed" in data else len(issues) == 0
    if issues:
        passed = False
    return ReportStep(
        step_id=step_id,
        passed=passed,
        summary=str(data.get("summary") or ""),
        issues=issues,
    )


def _llm_review(
    db: Session,
    task: SchemeReviewTask,
    *,
    step_id: str,
    user_prompt: str,
    anchor_base: dict[str, Any],
) -> ReportStep:
    try:
        data = chat_json(db, user_message=user_prompt, system=JSON_SYSTEM, max_tokens=8192)
    except Exception as first:
        _append_log(db, task, "warning", f"{step_id} LLM 首次解析失败，重试: {first!s}")
        try:
            data = chat_json(
                db,
                user_message=user_prompt + "\n\n上一输出不是合法 JSON。请只输出一个 JSON 对象，键为 passed, summary, issues。",
                system=JSON_SYSTEM,
                max_tokens=8192,
            )
        except Exception as second:
            _append_log(db, task, "error", f"{step_id} LLM 失败: {second!s}")
            return ReportStep(
                step_id=step_id,
                passed=False,
                summary="模型调用或 JSON 解析失败",
                issues=[
                    ReportIssue(
                        severity="error",
                        message=str(second),
                        anchor=anchor_base,
                    )
                ],
            )
    return _normalize_llm_step(step_id, data, anchor_base)


def _basis_prompt(full_content: str, rows: list[BasisItem]) -> str:
    lines = []
    for r in rows:
        lines.append(
            f"- 文献类型: {r.doc_type} | 标准号: {r.standard_no} | 名称: {r.doc_name} | 效力: {r.effect_status}"
        )
    catalog = "\n".join(lines) if lines else "(编制依据库中暂无记录)"
    return (
        "以下为待审文档中与编制依据相关的章节全文：\n\n---\n"
        f"{full_content[:24000]}\n---\n\n"
        "以下为该方案类型在系统中登记的编制依据条目（规范列表），请对照检查文档中引用是否正确、是否遗漏应引用规范、效力状态是否合理：\n"
        f"{catalog}\n\n"
        "请输出 JSON：若某条规范在文档中存在问题，在 issues 中说明标准号或文献名称、问题原因；related 中可含 standard_no、doc_name。"
    )


def _context_prompt(current_title: str, current_text: str, ref_blocks: list[tuple[str, str]]) -> str:
    parts = [f"当前章节：{current_title}\n---\n{current_text[:12000]}\n"]
    for title, text in ref_blocks:
        parts.append(f"对照章节：{title}\n---\n{text[:12000]}\n")
    return (
        "\n".join(parts)
        + "\n请检查上述章节在数据、结论、术语、前后要求等方面是否一致。输出 JSON，"
        "issues 中说明哪两章不一致及原因，related 含 chapter_a、chapter_b。"
    )


def _content_prompt(
    current_text: str,
    ref_text: str,
    kb_text: str,
    review_prompt: str,
) -> str:
    return (
        "【当前章节及子节正文】\n"
        f"{current_text[:16000]}\n\n"
        "【引用章节正文】\n"
        f"{ref_text[:12000] or '(无)'}\n\n"
        "【知识库检索片段】\n"
        f"{kb_text[:12000] or '(无)'}\n\n"
        "【审核提示词】\n"
        f"{review_prompt}\n\n"
        "请按审核提示词完成检查，输出 JSON；issues 说明问题与参考依据。"
    )


def run_review_pipeline(task_id: int) -> None:
    db = SessionLocal()
    try:
        task = (
            db.query(SchemeReviewTask)
            .options(joinedload(SchemeReviewTask.scheme_type))
            .filter(SchemeReviewTask.id == task_id)
            .first()
        )
        if task is None:
            return

        task.status = ReviewTaskStatus.processing
        task.error_message = None
        task.review_stage = None
        task.output_object_key = None
        _append_log(db, task, "info", "任务开始处理")
        db.commit()

        scheme = task.scheme_type
        if scheme is None:
            raise RuntimeError("方案类型不存在")

        tmpl = db.query(SchemeTemplate).filter(SchemeTemplate.scheme_type_id == task.scheme_type_id).first()
        if tmpl is None:
            raise RuntimeError("模版不存在")

        if not tmpl.review_workflow or not tmpl.review_workflow.strip():
            raise RuntimeError("模版未配置审核工作流")
        wf = ReviewWorkflowData.model_validate(json.loads(tmpl.review_workflow))
        active = [s for s in wf.steps if s not in ("start", "end")]

        if not tmpl.parsed_structure or not tmpl.parsed_structure.strip():
            raise RuntimeError("模版无解析结构")
        tpl_tree = json.loads(tmpl.parsed_structure)
        template_nodes = tpl_tree.get("nodes") or []
        if not template_nodes:
            raise RuntimeError("模版结构为空")

        _append_log(db, task, "info", "从对象存储读取审核文件…")
        db.commit()
        raw = minio_storage.get_object_bytes(task.object_key)
        user_tree = parse_docx_to_tree(BytesIO(raw))
        user_nodes = user_tree.get("nodes") or []

        mapping, struct_raw = align_template_user_trees(template_nodes, user_nodes)
        structure_step = _structure_issues_to_report(struct_raw)

        provider = effective_default_provider(db)
        report = ReviewReportV1(
            steps=[structure_step],
            model_provider=provider,
        )

        if "structure" in active and not structure_step.passed:
            task.review_result_json = report.to_json_str()
            task.status = ReviewTaskStatus.failed
            task.review_stage = None
            task.error_message = "文档结构与模版不一致"
            task.result_text = structure_step.summary
            _append_log(db, task, "error", "结构审核未通过，已终止后续步骤")
            db.commit()
            return

        category = scheme.category
        name = scheme.name
        basis_rows = (
            db.query(BasisItem)
            .filter(BasisItem.scheme_category == category, BasisItem.scheme_name == name)
            .order_by(BasisItem.id)
            .all()
        )

        dify_url, dify_key = get_dify_url_and_key(db)

        for step_id in active:
            if step_id == "structure":
                continue

            task.review_stage = step_id
            _append_log(db, task, "info", f"开始步骤: {step_id}")
            db.commit()

            if step_id == "compilation_basis":
                merged = ReportStep(step_id=step_id, passed=True, summary="", issues=[])
                for tn in iter_nodes(template_nodes):
                    if not tn.get("compilation_basis_audit_enabled"):
                        continue
                    tid = str(tn.get("id") or "")
                    un = resolve_user_node(mapping, tid)
                    if un is None:
                        continue
                    full = collect_subtree_text(un)
                    if not full.strip():
                        continue
                    tp = title_path_for_node(template_nodes, tid)
                    hpi = un.get("heading_para_index")
                    anchor = {
                        "template_node_id": tid,
                        "title_path": tp,
                        "heading_para_index": hpi,
                    }
                    prompt = _basis_prompt(full, basis_rows)
                    sub = _llm_review(db, task, step_id=step_id, user_prompt=prompt, anchor_base=anchor)
                    merged.issues.extend(sub.issues)
                    if not sub.passed:
                        merged.passed = False
                merged.summary = (
                    "编制依据审核通过" if merged.passed else f"发现 {len(merged.issues)} 条编制依据相关问题"
                )
                report.steps.append(merged)

            elif step_id == "context_consistency":
                merged = ReportStep(step_id=step_id, passed=True, summary="", issues=[])
                for tn in iter_nodes(template_nodes):
                    refs = tn.get("context_consistency_ref_node_ids") or []
                    if not isinstance(refs, list) or not refs:
                        continue
                    tid = str(tn.get("id") or "")
                    un = resolve_user_node(mapping, tid)
                    if un is None:
                        continue
                    cur_title = str(tn.get("title") or "")
                    cur_text = collect_subtree_text(un)
                    ref_blocks: list[tuple[str, str]] = []
                    for rid in refs:
                        rid_s = str(rid)
                        ru = resolve_user_node(mapping, rid_s)
                        if ru is None:
                            continue
                        rt = title_path_for_node(template_nodes, rid_s)
                        ref_blocks.append((title_path_str(rt), collect_subtree_text(ru)))
                    if not ref_blocks:
                        continue
                    tp = title_path_for_node(template_nodes, tid)
                    hpi = un.get("heading_para_index")
                    anchor = {
                        "template_node_id": tid,
                        "title_path": tp,
                        "heading_para_index": hpi,
                    }
                    prompt = _context_prompt(cur_title, cur_text, ref_blocks)
                    sub = _llm_review(db, task, step_id=step_id, user_prompt=prompt, anchor_base=anchor)
                    merged.issues.extend(sub.issues)
                    if not sub.passed:
                        merged.passed = False
                merged.summary = (
                    "上下文一致性审核通过" if merged.passed else f"发现 {len(merged.issues)} 条一致性问题"
                )
                report.steps.append(merged)

            elif step_id == "content":
                merged = ReportStep(step_id=step_id, passed=True, summary="", issues=[])
                for tn in iter_nodes(template_nodes):
                    rp = (tn.get("review_prompt") or "").strip() if isinstance(tn.get("review_prompt"), str) else ""
                    if not rp:
                        continue
                    tid = str(tn.get("id") or "")
                    un = resolve_user_node(mapping, tid)
                    if un is None:
                        continue
                    current_text = collect_subtree_text(un)
                    ref_ids = tn.get("ref_node_ids") or []
                    ref_chunks: list[str] = []
                    if isinstance(ref_ids, list):
                        for rid in ref_ids:
                            ru = resolve_user_node(mapping, str(rid))
                            if ru is not None:
                                ref_chunks.append(collect_subtree_text(ru))
                    ref_text = "\n\n---\n\n".join(ref_chunks)
                    kb_text = ""
                    ds = tn.get("dify_dataset_id")
                    if ds and dify_url and dify_key:
                        kws = tn.get("knowledge_keywords") or []
                        qparts: list[str] = []
                        if isinstance(kws, list):
                            qparts.extend(str(x).strip() for x in kws if str(x).strip())
                        if not qparts:
                            qparts.append(str(tn.get("title") or "").strip())
                        query = " ".join(qparts)[:250]
                        try:
                            kb_text = retrieve_dataset_chunks(dify_url, dify_key, str(ds), query)
                        except Exception as e:
                            _append_log(db, task, "warning", f"知识库检索跳过: {e!s}")
                    tp = title_path_for_node(template_nodes, tid)
                    hpi = un.get("heading_para_index")
                    anchor = {
                        "template_node_id": tid,
                        "title_path": tp,
                        "heading_para_index": hpi,
                    }
                    prompt = _content_prompt(current_text, ref_text, kb_text, rp)
                    sub = _llm_review(db, task, step_id=step_id, user_prompt=prompt, anchor_base=anchor)
                    merged.issues.extend(sub.issues)
                    if not sub.passed:
                        merged.passed = False
                merged.summary = (
                    "内容审核完成" if merged.passed else f"发现 {len(merged.issues)} 条内容问题"
                )
                report.steps.append(merged)

        task.review_stage = None
        task.review_result_json = report.to_json_str()

        annotations: list[tuple[int, str]] = []
        for st in report.steps:
            for iss in st.issues:
                hpi = (iss.anchor or {}).get("heading_para_index")
                if isinstance(hpi, int):
                    txt = f"[{st.step_id}] {iss.message}"
                    if iss.evidence:
                        txt += f"\n{iss.evidence[:800]}"
                    annotations.append((hpi, txt[:2000]))

        out_bytes = raw
        if annotations:
            try:
                out_bytes = inject_comments_at_paragraphs(raw, annotations)
            except Exception as e:
                _append_log(db, task, "warning", f"写入 Word 批注失败，已保留原文: {e!s}")

        out_key = f"reviews/{task.scheme_type_id}/{uuid.uuid4().hex}_annotated.docx"
        minio_storage.put_object(
            out_key,
            out_bytes,
            length=len(out_bytes),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        task.output_object_key = out_key

        task.status = ReviewTaskStatus.succeeded
        ok = all(s.passed for s in report.steps)
        task.result_text = "审核已完成，批注已写入 Word。" if ok else "审核已完成，存在待处理问题，请查看报告与批注。"
        _append_log(db, task, "info", "任务处理成功")
        db.commit()
    except Exception as e:
        db.rollback()
        try:
            task = db.get(SchemeReviewTask, task_id)
            if task is not None:
                err_text = str(e)
                tb = traceback.format_exc()
                _append_log(db, task, "error", f"处理失败: {err_text}")
                _append_log(db, task, "error", f"异常堆栈:\n{tb}")
                task.status = ReviewTaskStatus.failed
                task.error_message = err_text
                task.review_stage = None
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
