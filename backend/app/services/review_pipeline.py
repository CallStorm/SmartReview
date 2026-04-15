"""Scheme review: workflow steps, structure fail-fast, LLM steps, Word output."""

from __future__ import annotations

import json
import traceback
import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO
from time import perf_counter
from typing import Any, Literal

import httpx
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
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
from app.services.llm.chat import TokenUsage, chat_json_with_usage
from app.services.llm.resolve import effective_default_provider
from app.services.review_settings import get_review_prompt_debug_enabled, get_review_timeout_seconds
from app.services.tree_align import align_template_user_trees, title_path_str
from app.services.word_parser import parse_docx_to_tree

LOCK_WAIT_TIMEOUT_SECONDS = 15

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
    by_kind: dict[str, int] = {"missing_section": 0, "order_mismatch": 0, "extra_section": 0}
    for raw in structure_raw:
        kind = str(raw.get("kind") or "")
        if kind in by_kind:
            by_kind[kind] += 1
        tp = raw.get("title_path") or []
        if not isinstance(tp, list):
            tp = []
        hpi = raw.get("heading_para_index")
        tid = raw.get("template_node_id")
        anchor: dict[str, Any] = {"title_path": tp}
        if tid is not None and str(tid).strip():
            anchor["template_node_id"] = tid
        ut = raw.get("user_title")
        if ut is not None and str(ut).strip():
            anchor["user_title"] = str(ut).strip()
        if isinstance(hpi, int):
            anchor["heading_para_index"] = hpi
        if kind == "missing_section":
            sev: Literal["error", "warning", "info"] = "error"
        elif kind in ("order_mismatch", "extra_section"):
            sev = "warning"
        else:
            sev = "error"
        issues.append(
            ReportIssue(
                severity=sev,
                message=str(raw.get("message") or ""),
                evidence="",
                anchor=anchor,
                related={"kind": kind},
            )
        )
    n_miss = by_kind["missing_section"]
    n_ord = by_kind["order_mismatch"]
    n_extra = by_kind["extra_section"]
    if not issues:
        summary = "结构审核通过"
    else:
        parts = [f"共 {len(issues)} 项结构问题"]
        detail_bits: list[str] = []
        if n_miss:
            detail_bits.append(f"缺失 {n_miss}")
        if n_ord:
            detail_bits.append(f"顺序 {n_ord}")
        if n_extra:
            detail_bits.append(f"多余 {n_extra}")
        if detail_bits:
            parts.append("（" + "，".join(detail_bits) + "）")
        summary = "".join(parts)
    return ReportStep(
        step_id="structure",
        passed=len(issues) == 0,
        summary=summary,
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
    debug_prompts: list[dict[str, Any]] | None = None,
    timeout_seconds: float = 120.0,
    timeout_fail_fast: bool = False,
) -> tuple[ReportStep, TokenUsage]:
    if debug_prompts is not None:
        debug_prompts.append(
            {
                "step_id": step_id,
                "template_node_id": str(anchor_base.get("template_node_id") or ""),
                "title_path": anchor_base.get("title_path") or [],
                "prompt_text": user_prompt,
                "prompt_length": len(user_prompt),
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
    try:
        data, usage = chat_json_with_usage(
            db,
            user_message=user_prompt,
            system=JSON_SYSTEM,
            max_tokens=8192,
            timeout=timeout_seconds,
        )
    except Exception as first:
        _append_log(db, task, "warning", f"{step_id} LLM 首次解析失败，重试: {first!s}")
        try:
            data, usage = chat_json_with_usage(
                db,
                user_message=user_prompt + "\n\n上一输出不是合法 JSON。请只输出一个 JSON 对象，键为 passed, summary, issues。",
                system=JSON_SYSTEM,
                max_tokens=8192,
                timeout=timeout_seconds,
            )
        except Exception as second:
            _append_log(db, task, "error", f"{step_id} LLM 失败: {second!s}")
            if timeout_fail_fast and _is_timeout_error(second):
                raise TimeoutError(f"{step_id} 超时（>{int(timeout_seconds)} 秒）") from second
            return (
                ReportStep(
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
                ),
                {"input_tokens": None, "output_tokens": None, "total_tokens": None},
            )
    return _normalize_llm_step(step_id, data, anchor_base), usage


def _is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    text = str(exc).lower()
    return ("timeout" in text) or ("timed out" in text) or ("超时" in text)


def _merge_usage(total: TokenUsage, delta: TokenUsage) -> None:
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        d = delta.get(key)
        if d is None:
            continue
        existing = total.get(key)
        total[key] = (existing or 0) + d


def _write_usage_snapshot(task: SchemeReviewTask, total: TokenUsage) -> None:
    task.input_tokens = total["input_tokens"] or None
    task.output_tokens = total["output_tokens"] or None
    task.total_tokens = total["total_tokens"] or None


def _as_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _finalize_timing_and_tokens(task: SchemeReviewTask) -> None:
    finished = datetime.now(UTC)
    task.finished_at = finished
    if task.started_at is not None:
        started = _as_utc_aware(task.started_at)
        duration = finished - started
        task.duration_ms = max(0, int(duration.total_seconds() * 1000))


def _recover_stale_processing_tasks(db: Session, *, current_task_id: int, stale_minutes: int = 5) -> int:
    cutoff = datetime.now(UTC) - timedelta(minutes=stale_minutes)
    rows = (
        db.query(SchemeReviewTask)
        .filter(
            SchemeReviewTask.status == ReviewTaskStatus.processing,
            SchemeReviewTask.updated_at < cutoff,
            SchemeReviewTask.id != current_task_id,
        )
        .all()
    )
    if not rows:
        return 0
    for row in rows:
        _append_log(
            db,
            row,
            "error",
            "检测到任务长时间处于 processing，已自动回收为失败（疑似进程中断或提交阶段未完成）",
        )
        row.status = ReviewTaskStatus.failed
        row.review_stage = None
        row.error_message = "Auto recovered: stale processing task"
        _finalize_timing_and_tokens(row)
    db.commit()
    return len(rows)


def _review_result_to_json(
    report: ReviewReportV1,
    *,
    debug_prompts: list[dict[str, Any]] | None = None,
) -> str:
    payload: dict[str, Any] = report.model_dump(mode="json")
    if debug_prompts:
        payload["debug_prompts"] = debug_prompts
    return json.dumps(payload, ensure_ascii=False)


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
        "说明：若章节中存在表格，系统会按“[表格第N行] 单元格1 | 单元格2 ...”形式展开。\n\n"
        "以下为该方案类型在系统中登记的编制依据条目（规范列表），请对照检查文档中引用是否正确、是否遗漏应引用规范、效力状态是否合理：\n"
        f"{catalog}\n\n"
        "审核要求：必须同时检查正文与表格中的规范编号/名称，不得遗漏仅出现在表格单元格里的引用。\n"
        "请输出 JSON：若某条规范在文档中存在问题，在 issues 中说明标准号或文献名称、问题原因；"
        "并在 related 中给出可执行整改建议（suggestions: string[]，可选 suggestion: string）。"
        "related 中还可含 standard_no、doc_name。"
    )


def _context_prompt(current_title: str, current_text: str, ref_blocks: list[tuple[str, str]]) -> str:
    parts = [f"当前章节：{current_title}\n---\n{current_text[:12000]}\n"]
    for title, text in ref_blocks:
        parts.append(f"对照章节：{title}\n---\n{text[:12000]}\n")
    return (
        "\n".join(parts)
        + "\n请检查上述章节在数据、结论、术语、前后要求等方面是否一致。输出 JSON，"
        "issues 中说明哪两章不一致及原因，"
        "related 含 chapter_a、chapter_b，并补充可执行整改建议（suggestions: string[]，可选 suggestion: string）。"
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
        "【审核逻辑】\n"
        "1. 严格依据【审核提示词】提取核查项，不得自行新增无关检查项。\n"
        "2. 逐项核查【当前章节及子节正文】；若缺失关键信息，明确指出缺失项。\n"
        "3. 使用【引用章节正文】与【知识库检索片段】做交叉验证与依据补充。\n"
        "4. 对值为“(无)”的输入块，不得臆测内容；如影响判断，请在 issues 中说明“证据不足/无法交叉验证”。\n"
        "5. 仅输出 JSON 对象；issues 需同时说明问题、证据来源（当前章节/引用章节/知识库）及参考依据。\n"
        "6. 每条 issue 的 related 中必须给出可执行整改建议（suggestions: string[]，可选 suggestion: string）。"
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

        recovered = _recover_stale_processing_tasks(db, current_task_id=task_id, stale_minutes=5)
        if recovered > 0:
            task = db.get(SchemeReviewTask, task_id)
            if task is None:
                return
            _append_log(db, task, "warning", f"已自动回收 {recovered} 个僵尸 processing 任务")
            db.commit()

        try:
            db.execute(text(f"SET SESSION innodb_lock_wait_timeout = {LOCK_WAIT_TIMEOUT_SECONDS}"))
        except Exception:
            # Best-effort safety setting; ignore if backend does not support it.
            pass

        task.status = ReviewTaskStatus.processing
        task.error_message = None
        task.review_stage = None
        task.output_object_key = None
        task.started_at = datetime.now(UTC)
        task.finished_at = None
        task.duration_ms = None
        task.input_tokens = None
        task.output_tokens = None
        task.total_tokens = None
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
        prompt_debug_enabled = get_review_prompt_debug_enabled(db)
        review_timeout_seconds = get_review_timeout_seconds(db)
        debug_prompts: list[dict[str, Any]] = []
        report = ReviewReportV1(
            steps=[structure_step],
            model_provider=provider,
        )
        token_usage_total: TokenUsage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

        if "structure" in active and not structure_step.passed:
            task.review_result_json = _review_result_to_json(
                report,
                debug_prompts=debug_prompts if prompt_debug_enabled else None,
            )
            task.status = ReviewTaskStatus.failed
            task.review_stage = None
            task.error_message = "文档结构与模版不一致"
            task.result_text = structure_step.summary
            _finalize_timing_and_tokens(task)
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
                    sub, usage = _llm_review(
                        db,
                        task,
                        step_id=step_id,
                        user_prompt=prompt,
                        anchor_base=anchor,
                        debug_prompts=debug_prompts if prompt_debug_enabled else None,
                    )
                    _merge_usage(token_usage_total, usage)
                    _write_usage_snapshot(task, token_usage_total)
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
                    sub, usage = _llm_review(
                        db,
                        task,
                        step_id=step_id,
                        user_prompt=prompt,
                        anchor_base=anchor,
                        debug_prompts=debug_prompts if prompt_debug_enabled else None,
                    )
                    _merge_usage(token_usage_total, usage)
                    _write_usage_snapshot(task, token_usage_total)
                    merged.issues.extend(sub.issues)
                    if not sub.passed:
                        merged.passed = False
                merged.summary = (
                    "上下文一致性审核通过" if merged.passed else f"发现 {len(merged.issues)} 条一致性问题"
                )
                report.steps.append(merged)

            elif step_id == "content":
                merged = ReportStep(step_id=step_id, passed=True, summary="", issues=[])
                content_nodes: list[dict[str, Any]] = []
                for tn in iter_nodes(template_nodes):
                    rp = (tn.get("review_prompt") or "").strip() if isinstance(tn.get("review_prompt"), str) else ""
                    if not rp:
                        continue
                    tid = str(tn.get("id") or "")
                    un = resolve_user_node(mapping, tid)
                    if un is None:
                        continue
                    content_nodes.append(tn)

                _append_log(
                    db,
                    task,
                    "info",
                    f"内容审核节点数: {len(content_nodes)}，超时阈值: {review_timeout_seconds} 秒",
                )
                db.commit()

                for idx, tn in enumerate(content_nodes, start=1):
                    node_t0 = perf_counter()
                    tid = str(tn.get("id") or "")
                    node_title = title_path_str(title_path_for_node(template_nodes, tid)) or str(
                        tn.get("title") or ""
                    )
                    _append_log(
                        db,
                        task,
                        "info",
                        f"content 节点开始 [{idx}/{len(content_nodes)}] id={tid} 标题={node_title}",
                    )
                    db.commit()

                    un = resolve_user_node(mapping, tid)
                    if un is None:
                        _append_log(db, task, "warning", f"content 节点跳过（未匹配用户节点）id={tid}")
                        db.commit()
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
                        kb_t0 = perf_counter()
                        try:
                            kb_text = retrieve_dataset_chunks(dify_url, dify_key, str(ds), query)
                        except Exception as e:
                            if _is_timeout_error(e):
                                raise TimeoutError(
                                    f"content 节点 [{idx}/{len(content_nodes)}] 知识库检索超时（dataset={ds}）"
                                ) from e
                            _append_log(
                                db,
                                task,
                                "warning",
                                f"content 节点知识库检索跳过 id={tid} dataset={ds}: {e!s}",
                            )
                        finally:
                            kb_elapsed_ms = int((perf_counter() - kb_t0) * 1000)
                            _append_log(
                                db,
                                task,
                                "info",
                                f"content 节点知识库检索完成 id={tid} 用时={kb_elapsed_ms}ms",
                            )
                            db.commit()
                    tp = title_path_for_node(template_nodes, tid)
                    hpi = un.get("heading_para_index")
                    anchor = {
                        "template_node_id": tid,
                        "title_path": tp,
                        "heading_para_index": hpi,
                    }
                    prompt = _content_prompt(current_text, ref_text, kb_text, rp)
                    llm_t0 = perf_counter()
                    try:
                        sub, usage = _llm_review(
                            db,
                            task,
                            step_id=step_id,
                            user_prompt=prompt,
                            anchor_base=anchor,
                            debug_prompts=debug_prompts if prompt_debug_enabled else None,
                            timeout_seconds=float(review_timeout_seconds),
                            timeout_fail_fast=True,
                        )
                    except TimeoutError as e:
                        raise TimeoutError(
                            f"content 节点 [{idx}/{len(content_nodes)}] LLM 调用超时（>{review_timeout_seconds}秒）"
                        ) from e
                    finally:
                        llm_elapsed_ms = int((perf_counter() - llm_t0) * 1000)
                        _append_log(
                            db,
                            task,
                            "info",
                            f"content 节点模型调用完成 id={tid} 用时={llm_elapsed_ms}ms",
                        )
                        db.commit()
                    _merge_usage(token_usage_total, usage)
                    _write_usage_snapshot(task, token_usage_total)
                    merged.issues.extend(sub.issues)
                    if not sub.passed:
                        merged.passed = False
                    node_elapsed_ms = int((perf_counter() - node_t0) * 1000)
                    _append_log(
                        db,
                        task,
                        "info",
                        (
                            f"content 节点完成 [{idx}/{len(content_nodes)}] id={tid} "
                            f"总用时={node_elapsed_ms}ms 累计tokens={task.total_tokens or 0}"
                        ),
                    )
                    db.commit()
                merged.summary = (
                    "内容审核完成" if merged.passed else f"发现 {len(merged.issues)} 条内容问题"
                )
                report.steps.append(merged)

        task.review_stage = None
        _append_log(db, task, "info", "内容审核阶段结束，开始生成审核报告")
        db.commit()
        task.review_result_json = _review_result_to_json(
            report,
            debug_prompts=debug_prompts if prompt_debug_enabled else None,
        )
        _append_log(db, task, "info", "审核报告 JSON 生成完成")
        db.commit()

        annotations: list[tuple[int, str]] = []
        for st in report.steps:
            for iss in st.issues:
                hpi = (iss.anchor or {}).get("heading_para_index")
                if isinstance(hpi, int):
                    txt = f"[{st.step_id}] {iss.message}"
                    if iss.evidence:
                        txt += f"\n{iss.evidence[:800]}"
                    annotations.append((hpi, txt[:2000]))

        _append_log(db, task, "info", f"收集批注完成，待写入批注数: {len(annotations)}")
        db.commit()

        out_bytes = raw
        if annotations:
            _append_log(db, task, "info", "开始写入 Word 批注")
            db.commit()
            comments_t0 = perf_counter()
            try:
                out_bytes = inject_comments_at_paragraphs(raw, annotations)
            except Exception as e:
                _append_log(db, task, "warning", f"写入 Word 批注失败，已保留原文: {e!s}")
            finally:
                comments_elapsed_ms = int((perf_counter() - comments_t0) * 1000)
                _append_log(db, task, "info", f"Word 批注阶段完成，用时={comments_elapsed_ms}ms")
                db.commit()
        else:
            _append_log(db, task, "info", "无可写入批注，跳过 Word 批注阶段")
            db.commit()

        out_key = f"reviews/{task.scheme_type_id}/{uuid.uuid4().hex}_annotated.docx"
        _append_log(
            db,
            task,
            "info",
            f"开始上传审核结果文档（超时阈值: {review_timeout_seconds} 秒）",
        )
        db.commit()
        upload_t0 = perf_counter()
        minio_storage.put_object_with_hard_timeout(
            out_key,
            out_bytes,
            length=len(out_bytes),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            timeout_seconds=float(review_timeout_seconds),
            hard_timeout_seconds=float(review_timeout_seconds) + 8.0,
        )
        upload_elapsed_ms = int((perf_counter() - upload_t0) * 1000)
        task.output_object_key = out_key
        _append_log(db, task, "info", f"上传审核结果文档完成，用时={upload_elapsed_ms}ms")

        _append_log(db, task, "info", "开始写入最终任务状态")
        task.status = ReviewTaskStatus.succeeded
        _write_usage_snapshot(task, token_usage_total)
        _finalize_timing_and_tokens(task)
        ok = all(s.passed for s in report.steps)
        task.result_text = "审核已完成，批注已写入 Word。" if ok else "审核已完成，存在待处理问题，请查看报告与批注。"
        _append_log(db, task, "info", "任务处理成功")
        try:
            db.commit()
        except OperationalError as e:
            db.rollback()
            err_text = f"最终状态提交失败（可能锁等待或连接超时）: {e!s}"
            try:
                recovery = db.get(SchemeReviewTask, task_id)
                if recovery is None:
                    raise TimeoutError(err_text)
                _append_log(db, recovery, "error", err_text)
                recovery.status = ReviewTaskStatus.failed
                recovery.review_stage = None
                recovery.error_message = err_text
                _finalize_timing_and_tokens(recovery)
                db.commit()
            except Exception as recover_exc:
                db.rollback()
                raise TimeoutError(err_text) from recover_exc
            return
    except TimeoutError as e:
        db.rollback()
        try:
            task = db.get(SchemeReviewTask, task_id)
            if task is not None:
                err_text = str(e)
                _append_log(db, task, "error", f"处理超时并已终止: {err_text}")
                task.status = ReviewTaskStatus.failed
                task.error_message = err_text
                task.review_stage = None
                _finalize_timing_and_tokens(task)
                db.commit()
        except Exception:
            db.rollback()
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
                _finalize_timing_and_tokens(task)
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
