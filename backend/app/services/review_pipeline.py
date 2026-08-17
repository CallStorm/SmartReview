"""Scheme review: workflow steps, structure fail-fast, LLM steps, Word output."""

from __future__ import annotations

import json
import re
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from io import BytesIO
from time import perf_counter
from typing import Any, Callable, Literal

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
from app.schemas.template import FullDocumentReviewConfig, ReviewWorkflowData
from app.services import minio_storage
from app.services.checklist import (
    build_checklist_block,
    checklist_signature,
    split_check_items,
)
from app.services.doc_tree_utils import (
    UserHeadingEntry,
    build_user_heading_index,
    collect_full_document_text,
    collect_subtree_text,
    format_heading_catalog,
    iter_nodes,
    parse_title_path_value,
    resolve_heading_from_index,
    resolve_user_node,
    title_path_for_node,
)
from app.services.docx_image_assets import extract_and_store_docx_images
from app.services.docx_comments import inject_comments_at_paragraphs
from app.services.dify_client import retrieve_dataset_chunks
from app.services.dify_settings import get_dify_url_and_key
from app.services.llm.chat import EMPTY_USAGE, TokenUsage, chat_json_with_usage
from app.services.llm.resolve import effective_default_provider, effective_image_review
from app.services.image_review import IMAGE_STEP_ID, parse_node_image_config, review_node_images
from app.services.review_cache import (
    cache_lookup,
    cache_store,
    node_fingerprint,
    prompt_fingerprint,
    provider_model_pair,
)
from app.services.review_settings import (
    get_compilation_basis_concurrency,
    get_content_concurrency,
    get_context_consistency_concurrency,
    get_review_prompt_debug_enabled,
    get_review_timeout_seconds,
)
from app.services.structure_llm_matcher import build_llm_matcher
from app.services.tree_align import align_template_user_trees, title_path_str
from app.services.word_parser import parse_docx_to_tree

LOCK_WAIT_TIMEOUT_SECONDS = 15

# 写入 Word 批注时使用的步骤中文标签（与前端展示用语一致）
WORD_COMMENT_STEP_LABEL_CN: dict[str, str] = {
    "structure": "结构审核",
    "compilation_basis": "编制依据审核",
    "context_consistency": "上下文一致性",
    "content": "内容审核",
    "full_document": "通篇审核",
    "image_review": "图审核",
}

FULL_DOCUMENT_TEXT_CAP = 80_000
FULL_DOCUMENT_KB_CAP = 12_000
FULL_DOCUMENT_HEADING_CATALOG_MAX = 300

# 内容审核 per-node 输入截断上限（超长正文截断并在 prompt 中注明）
CONTENT_TEXT_CAP = 16_000
CONTENT_REF_TEXT_CAP = 12_000
CONTENT_KB_TEXT_CAP = 12_000

# 单次审核 LLM 调用的输出上限。覆盖 content / basis / context /
# full_document 四类节点。节点命中多个问题时，模型需要为每个问题生成
# message + evidence + suggestions，中文 evidence/suggestions 加上
# JSON 转义后容易把字符串撑到 8K 以上、被截断后触发 JSON 解析失败。
# 16K 留足余量，避免半截 JSON。
LLM_JSON_REVIEW_MAX_TOKENS = 16384

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
      "related": {
        "fix": "可粘贴替换的完整句子或短语（≤80字）",
        "suggestions": ["可执行整改建议"]
      }
    }
  ]
}
severity 取值仅为 error、warning、info。若无问题，issues 为 [] 且 passed 为 true。
related 必须包含 fix：审核员可复制贴入文档的具体替换文本（≤80字）。
suggestions 可选，1-3 条 ≤40字的整改路径说明。"""

# 内容审核（per-node）专用系统提示词：逐项清单判定。
# 与 JSON_SYSTEM 的差异：不输出自由 issues，而是对【检查项清单】中的
# 每个 item_id 恰好回填一次判定（pass/fail/na），保证同一文档多次审核
# 的覆盖面一致（不漏检、不越权新增检查项）。
CONTENT_JSON_SYSTEM = """你是工程文档审核助手。你必须只输出一个 JSON 对象，不要用 markdown 代码块包裹。
格式严格如下：
{
  "passed": true 或 false,
  "summary": "一句话摘要",
  "checks": [
    {
      "item_id": "检查项清单中的 item_id",
      "verdict": "pass 或 fail 或 na",
      "severity": "error",
      "message": "问题说明（仅 verdict=fail 时填写）",
      "evidence": "文档中的依据摘录（仅 verdict=fail 时填写）",
      "related": {
        "fix": "可粘贴替换的完整句子或短语（≤80字）",
        "suggestions": ["可执行整改建议"]
      }
    }
  ]
}
规则：
- checks 必须覆盖【检查项清单】中的每一个 item_id，每个恰好出现一次；不得遗漏、不得新增清单之外的 item_id。
- verdict 取值：pass=符合；fail=不符合；na=该项必须依赖引用章节或知识库才能判断、而两者均为“(无)”。
- verdict=pass 时，evidence 必须填写正文中能证明该内容存在的原文引文（≤50 字）——找不到可引用的原文时
  不得判 pass，应按【审核总则】“未给出”处理（verdict=fail）。
- verdict=pass 或 na 时，message、related 留空（severity 填 warning 即可）。
- fail 时 severity 取值仅为 error、warning、info，判定档次遵循【审核总则】。
- 全部通过时 checks 每项 verdict 均为 pass，且 passed 为 true。
- fail 时 related 必须包含 fix：审核员可复制贴入文档的具体替换文本（≤80字）；
  suggestions 可选，1-3 条 ≤40字的整改路径说明。"""

FULL_DOCUMENT_JSON_SYSTEM = """你是工程文档审核助手。你必须只输出一个 JSON 对象，不要用 markdown 代码块包裹。
格式严格如下：
{
  "passed": true 或 false,
  "summary": "一句话摘要",
  "issues": [
    {
      "severity": "error",
      "message": "问题说明",
      "evidence": "文档中的依据摘录",
      "anchor": {
        "heading_para_index": 128,
        "title_path": ["六、施工管理及作业人员配备和分工", "4.其他作业人员"]
      },
      "related": { "suggestions": ["可执行整改建议"] }
    }
  ]
}
规则：
- severity 取值仅为 error、warning、info。
- 每条可定位到具体章节的问题，anchor 必须包含 heading_para_index（整数，取自【文档标题索引】或正文 [hpi=N]，禁止臆造）及 title_path（字符串数组，每级标题一项，须与该 hpi 的完整路径一致）。
- 无法定位到具体章节时，可省略 anchor，但须在 message 中说明。
- related.suggestions 为 string[]，给出可执行整改建议。
- 若无问题，issues 为 [] 且 passed 为 true。"""

_HPI_IN_TEXT_RE = re.compile(r"\[hpi=(\d+)\]|hpi\s*[:=]\s*(\d+)", re.IGNORECASE)

_BASIS_ALLOWED_CATEGORIES = {"现行缺失", "废止误引"}
_BASIS_MISSING_EVIDENCE = "文档全文及表格中未发现该规范的名称或编号。"


def _append_log(db: Session, task: SchemeReviewTask, level: str, message: str) -> None:
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    task.review_log = (task.review_log or "") + f"[{ts}] {level.upper()} {message}\n"


def _structure_issues_to_report(
    structure_raw: list[dict[str, Any]],
    *,
    match_records: list[dict[str, Any]] | None = None,
    match_mode: str = "exact",
) -> ReportStep:
    issues: list[ReportIssue] = []
    by_kind: dict[str, int] = {"missing_section": 0, "extra_section": 0}
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
        elif kind == "extra_section":
            sev = "info"
        elif kind == "order_mismatch":
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

    records = match_records or []
    method_counts: dict[str, int] = {}
    low_count = 0
    for r in records:
        m = str(r.get("match_method") or "")
        method_counts[m] = method_counts.get(m, 0) + 1
        if r.get("low_confidence"):
            low_count += 1

    error_count = by_kind["missing_section"]
    extra_count = by_kind["extra_section"]
    passed = error_count == 0

    if not issues and not records:
        summary = "结构审核通过"
    elif match_mode == "fuzzy":
        parts = [f"共 {len(records)} 项映射"]
        seg: list[str] = []
        for m in ("exact", "normalized", "semantic"):
            if method_counts.get(m):
                seg.append(f"{m} {method_counts[m]}")
        if seg:
            parts.append("（" + " / ".join(seg) + "）")
        if low_count:
            parts.append(f"低信心 {low_count}")
        if error_count:
            parts.append(f"缺失 {error_count}")
        if extra_count:
            parts.append(f"多余 {extra_count}")
        summary = "".join(parts)
    else:
        if not issues:
            summary = "结构审核通过"
        else:
            parts = [f"共 {len(issues)} 项结构问题"]
            if error_count:
                parts.append(f"（缺失 {error_count}）")
            summary = "".join(parts)

    return ReportStep(
        step_id="structure",
        passed=passed,
        summary=summary,
        issues=issues,
        mappings=records,
    )


def _coerce_int_hpi(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == int(value):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _extract_hpi_from_text(text: str) -> int | None:
    for m in _HPI_IN_TEXT_RE.finditer(text or ""):
        g = m.group(1) or m.group(2)
        if g and g.isdigit():
            return int(g)
    return None


def _coerce_raw_issue_anchor(it: dict[str, Any]) -> dict[str, Any]:
    """Normalize LLM issue dict into anchor fields (full-document and legacy shapes)."""
    anchor: dict[str, Any] = {}
    extra = it.get("anchor")
    if isinstance(extra, dict):
        anchor.update(extra)

    for key in ("heading_para_index", "title_path", "user_title", "template_node_id"):
        if key in it and it[key] is not None and key not in anchor:
            anchor[key] = it[key]

    hpi = _coerce_int_hpi(anchor.get("heading_para_index"))
    if hpi is not None:
        anchor["heading_para_index"] = hpi
    elif "heading_para_index" in anchor:
        del anchor["heading_para_index"]

    path = parse_title_path_value(anchor.get("title_path"))
    if path:
        anchor["title_path"] = path

    rel = it.get("related")
    if not isinstance(rel, dict):
        return anchor

    loc = rel.get("location")
    if isinstance(loc, str) and loc.strip():
        loc_path = parse_title_path_value(loc)
        if loc_path and not anchor.get("title_path"):
            anchor["title_path"] = loc_path
    elif isinstance(loc, dict):
        if anchor.get("heading_para_index") is None:
            loc_hpi = _coerce_int_hpi(loc.get("heading_para_index"))
            if loc_hpi is not None:
                anchor["heading_para_index"] = loc_hpi
        if not anchor.get("title_path"):
            loc_path = parse_title_path_value(loc.get("chapter_path")) or parse_title_path_value(
                loc.get("chapter_text")
            )
            if loc_path:
                anchor["title_path"] = loc_path

    if not anchor.get("title_path"):
        for key in ("chapter", "chapter_a", "chapter_text", "title_path"):
            rel_path = parse_title_path_value(rel.get(key))
            if rel_path:
                anchor["title_path"] = rel_path
                break

    return anchor


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
        raw_category = str(it.get("category") or "").strip()
        if raw_category and not str(rel.get("category") or "").strip():
            rel["category"] = raw_category
        coerced_anchor = _coerce_raw_issue_anchor(it)
        anchor = {**anchor_base, **coerced_anchor}
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


def _normalize_content_checks(
    step_id: str,
    data: dict[str, Any],
    anchor_base: dict[str, Any],
    items: list[dict[str, Any]],
) -> tuple[ReportStep | None, list[LogLine]]:
    """把 LLM 的 checks[] 逐项判定归一化为 ReportStep。

    返回 (step, logs)；当模型未按清单格式输出（无 checks 或非 list）时
    step 为 None，调用方降级走 _normalize_llm_step（旧 issues 路径）。

    程序性约束（对应「内容审核全局规则」的硬性落地）：
    - 仅清单内的 item_id 可产生 issue，清单外的一律丢弃并记日志；
    - 每个检查项最多 1 条 issue（重复回填仅保留首条）；
    - issue.related 附 check_item_id / check_item，保证问题可溯源到配置规则。
    """
    logs: list[LogLine] = []
    raw_checks = data.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        logs.append(("warning", f"{step_id} 模型未按检查项清单输出 checks，降级为 issues 解析"))
        return None, logs
    item_map = {str(it.get("id")): it for it in items}
    issues: list[ReportIssue] = []
    seen: set[str] = set()
    pass_without_evidence: list[str] = []
    for c in raw_checks:
        if not isinstance(c, dict):
            continue
        iid = str(c.get("item_id") or "").strip()
        verdict = str(c.get("verdict") or "").strip().lower()
        if iid not in item_map:
            logs.append(("warning", f"{step_id} 输出的检查项 {iid or '(空)'} 不在清单内，已丢弃"))
            continue
        if iid in seen:
            logs.append(("warning", f"{step_id} 检查项 {iid} 重复输出，仅保留首条"))
            continue
        seen.add(iid)
        if verdict != "fail":
            if verdict == "pass" and not str(c.get("evidence") or "").strip():
                pass_without_evidence.append(iid)
            continue
        sev = str(c.get("severity") or "error")
        if sev not in ("error", "warning", "info"):
            sev = "error"
        rel = c.get("related")
        rel = dict(rel) if isinstance(rel, dict) else {}
        rel["check_item_id"] = iid
        rel["check_item"] = str(item_map[iid].get("text") or "")
        message = str(c.get("message") or "").strip()
        issues.append(
            ReportIssue(
                severity=sev,  # type: ignore[arg-type]
                message=message or f"检查项 {iid} 不符合：{rel['check_item']}",
                evidence=str(c.get("evidence") or ""),
                anchor=dict(anchor_base),
                related=rel,
            )
        )
    missing = [str(it.get("id")) for it in items if str(it.get("id")) not in seen]
    if missing:
        logs.append(
            ("warning", f"{step_id} 模型漏判 {len(missing)} 个检查项: {', '.join(missing)}")
        )
    if pass_without_evidence:
        logs.append(
            (
                "warning",
                f"{step_id} {len(pass_without_evidence)} 个检查项判 pass 但未附原文引文"
                f"（存在凭印象通过的风险）: {', '.join(pass_without_evidence)}",
            )
        )
    passed = not issues
    return (
        ReportStep(
            step_id=step_id,
            passed=passed,
            summary=str(data.get("summary") or ""),
            issues=issues,
        ),
        logs,
    )


LogLine = tuple[str, str]


def _llm_review_execute(
    db: Session,
    *,
    step_id: str,
    user_prompt: str,
    anchor_base: dict[str, Any],
    collect_debug: bool,
    timeout_seconds: float = 120.0,
    timeout_fail_fast: bool = False,
    system: str | None = None,
    max_tokens: int = 8192,
    normalize_fn: Callable[[dict[str, Any], dict[str, Any]], tuple[ReportStep | None, list[LogLine]]] | None = None,
) -> tuple[ReportStep, TokenUsage, list[LogLine], dict[str, Any] | None]:
    """LLM JSON 审核（不写入 task.review_log）；日志行由调用方在主线程写入。

    `normalize_fn`：自定义 (data, anchor_base) -> (ReportStep | None, logs)。
    返回 None 时降级用默认 _normalize_llm_step（如模型未按 checks 格式输出）。
    """
    log_lines: list[LogLine] = []
    debug_entry: dict[str, Any] | None = None
    system_prompt = system or JSON_SYSTEM
    if collect_debug:
        debug_entry = {
            "step_id": step_id,
            "template_node_id": str(anchor_base.get("template_node_id") or ""),
            "title_path": anchor_base.get("title_path") or [],
            "prompt_text": user_prompt,
            "prompt_length": len(user_prompt),
            "created_at": datetime.now(UTC).isoformat(),
        }
    try:
        data, usage = chat_json_with_usage(
            db,
            user_message=user_prompt,
            system=system_prompt,
            max_tokens=max_tokens,
            timeout=timeout_seconds,
        )
    except Exception as first:
        log_lines.append(("warning", f"{step_id} LLM 首次解析失败，重试: {first!s}"))
        try:
            data, usage = chat_json_with_usage(
                db,
                user_message=user_prompt + "\n\n上一输出不是合法 JSON。请只输出一个 JSON 对象，键为 passed, summary, "
                + ("checks。" if normalize_fn is not None else "issues。"),
                system=system_prompt,
                max_tokens=max_tokens,
                timeout=timeout_seconds,
            )
        except Exception as second:
            # 用户可见文案：只说结论，原始异常保留在 review_log 供排查
            log_lines.append(
                (
                    "error",
                    f"{step_id} LLM 失败（{type(second).__name__}）: {second!s}",
                )
            )
            if timeout_fail_fast and _is_timeout_error(second):
                raise TimeoutError(f"{step_id} 超时（>{int(timeout_seconds)} 秒）") from second
            friendly = (
                "模型输出未能解析为结构化结果，请稍后重试或联系管理员。"
                "（详细原因已写入审核日志。）"
            )
            return (
                ReportStep(
                    step_id=step_id,
                    passed=False,
                    summary=f"模型调用或 JSON 解析失败（{type(second).__name__}）",
                    issues=[
                        ReportIssue(
                            severity="error",
                            message=friendly,
                            anchor=anchor_base,
                        )
                    ],
                ),
                {"input_tokens": None, "output_tokens": None, "total_tokens": None},
                log_lines,
                debug_entry,
            )
    if normalize_fn is not None:
        step, extra_logs = normalize_fn(data, anchor_base)
        log_lines.extend(extra_logs)
        if step is not None:
            return step, usage, log_lines, debug_entry
    return _normalize_llm_step(step_id, data, anchor_base), usage, log_lines, debug_entry


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
    max_tokens: int = 8192,
) -> tuple[ReportStep, TokenUsage]:
    sub, usage, log_lines, dbg = _llm_review_execute(
        db,
        step_id=step_id,
        user_prompt=user_prompt,
        anchor_base=anchor_base,
        collect_debug=debug_prompts is not None,
        timeout_seconds=timeout_seconds,
        timeout_fail_fast=timeout_fail_fast,
        max_tokens=max_tokens,
    )
    for level, msg in log_lines:
        _append_log(db, task, level, msg)
    if dbg is not None and debug_prompts is not None:
        debug_prompts.append(dbg)
    return sub, usage


def _bounded_parallel_map(
    *,
    concurrency: int,
    items: list[tuple[int, Any]],
    worker: Callable[[Any], Any],
) -> list[tuple[int, Any]]:
    """按 work index 并行执行，返回 (idx, result) 列表（顺序不保证，由调用方排序）。"""
    if not items:
        return []
    max_workers = max(1, min(int(concurrency), len(items)))
    out: list[tuple[int, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {pool.submit(worker, payload): idx for idx, payload in items}
        for fut in as_completed(future_map):
            idx = future_map[fut]
            out.append((idx, fut.result()))
    return out


def _content_node_worker(
    payload: tuple[
        int,
        dict[str, Any],
        list[dict[str, Any]],
        dict[str, dict[str, Any]],
        str | None,
        str | None,
        int,
        bool,
        str,
        int,
        str,
        str,
    ],
) -> tuple[int, ReportStep, TokenUsage, list[LogLine], dict[str, Any] | None]:
    """单节点：缓存查询 + 知识库检索 + LLM 逐项判定；不写入主库，日志行返回给主线程按序写入。"""
    (
        work_idx,
        tn,
        template_nodes,
        mapping,
        dify_url,
        dify_key,
        review_timeout_seconds,
        prompt_debug_enabled,
        step_id,
        len_content_nodes,
        global_rules,
        template_updated_at,
    ) = payload
    logs: list[LogLine] = []
    node_t0 = perf_counter()
    tid = str(tn.get("id") or "")
    rp = (tn.get("review_prompt") or "").strip() if isinstance(tn.get("review_prompt"), str) else ""
    node_title = title_path_str(title_path_for_node(template_nodes, tid)) or str(tn.get("title") or "")
    logs.append(
        (
            "info",
            f"content 节点开始 [{work_idx + 1}/{len_content_nodes}] id={tid} 标题={node_title}",
        )
    )

    ldb = SessionLocal()
    try:
        un = resolve_user_node(mapping, tid)
        if un is None:
            logs.append(("warning", f"content 节点跳过（未匹配用户节点）id={tid}"))
            return (
                work_idx,
                ReportStep(step_id=step_id, passed=True, summary="", issues=[]),
                EMPTY_USAGE,
                logs,
                None,
            )

        current_text = collect_subtree_text(un)
        ref_ids = tn.get("ref_node_ids") or []
        ref_chunks: list[str] = []
        if isinstance(ref_ids, list):
            for rid in ref_ids:
                ru = resolve_user_node(mapping, str(rid))
                if ru is not None:
                    ref_chunks.append(collect_subtree_text(ru))
        ref_text = "\n\n---\n\n".join(ref_chunks)

        # 检查项清单（确定性拆分）+ 结果缓存
        items, notes = split_check_items(tid, rp, node=tn)
        if not items and rp:
            # 拆分结果为空（整段均为判定说明）时兜底：整段 prompt 作为唯一检查项
            items = [{"id": f"{tid}-1", "text": rp}]
        checklist_sig = checklist_signature(items, notes, global_rules)
        ds = tn.get("dify_dataset_id")
        kws = tn.get("knowledge_keywords") or []
        qparts: list[str] = []
        if isinstance(kws, list):
            qparts.extend(str(x).strip() for x in kws if str(x).strip())
        if not qparts:
            qparts.append(str(tn.get("title") or "").strip())
        query = " ".join(qparts)[:250]
        fingerprint = ""
        try:
            provider, model = provider_model_pair(ldb)
            fingerprint = node_fingerprint(
                step_id=step_id,
                provider=provider,
                model=model,
                checklist_sig=checklist_sig,
                template_updated_at=template_updated_at,
                current_text=current_text,
                ref_text=ref_text,
                dataset_id=str(ds or ""),
                query=query,
            )
            cached_step = cache_lookup(ldb, fingerprint)
            if cached_step is not None:
                logs.append(
                    (
                        "info",
                        f"content 节点命中结果缓存 id={tid} 检查项={len(items)} "
                        f"问题={len(cached_step.issues)}（文档与规则未变化，复用上次判定）",
                    )
                )
                return (work_idx, cached_step, EMPTY_USAGE, logs, None)
        except Exception as e:
            fingerprint = ""
            logs.append(("warning", f"content 节点结果缓存查询失败 id={tid}: {e!s}"))

        kb_text = ""
        if ds and dify_url and dify_key:
            kb_t0 = perf_counter()
            try:
                kb_text = retrieve_dataset_chunks(dify_url, dify_key, str(ds), query)
            except Exception as e:
                if _is_timeout_error(e):
                    raise TimeoutError(
                        f"content 节点 [{work_idx + 1}/{len_content_nodes}] 知识库检索超时（dataset={ds}）"
                    ) from e
                logs.append(
                    (
                        "warning",
                        f"content 节点知识库检索跳过 id={tid} dataset={ds}: {e!s}",
                    )
                )
            finally:
                kb_elapsed_ms = int((perf_counter() - kb_t0) * 1000)
                logs.append(
                    (
                        "info",
                        f"content 节点知识库检索完成 id={tid} 用时={kb_elapsed_ms}ms",
                    )
                )
        if len(current_text) > CONTENT_TEXT_CAP:
            logs.append(
                (
                    "warning",
                    f"content 节点正文超长截断 id={tid} 原文 {len(current_text)} 字符，"
                    f"截断至 {CONTENT_TEXT_CAP} 字符（截断点之后的内容不参与判定）",
                )
            )
        if len(ref_text) > CONTENT_REF_TEXT_CAP:
            logs.append(
                (
                    "warning",
                    f"content 节点引用章节正文超长截断 id={tid} 原文 {len(ref_text)} 字符，"
                    f"截断至 {CONTENT_REF_TEXT_CAP} 字符",
                )
            )
        tp = title_path_for_node(template_nodes, tid)
        hpi = un.get("heading_para_index")
        anchor = {
            "template_node_id": tid,
            "title_path": tp,
            "heading_para_index": hpi,
        }
        prompt = _content_prompt(
            current_text,
            ref_text,
            kb_text,
            build_checklist_block(items, notes),
            global_rules,
        )
        llm_t0 = perf_counter()
        try:
            sub, usage, ll_logs, dbg = _llm_review_execute(
                ldb,
                step_id=step_id,
                user_prompt=prompt,
                anchor_base=anchor,
                collect_debug=prompt_debug_enabled,
                timeout_seconds=float(review_timeout_seconds),
                timeout_fail_fast=True,
                max_tokens=LLM_JSON_REVIEW_MAX_TOKENS,
                system=CONTENT_JSON_SYSTEM,
                normalize_fn=lambda data, a_base: _normalize_content_checks(
                    step_id, data, a_base, items
                ),
            )
            logs.extend(ll_logs)
        except TimeoutError as e:
            llm_elapsed_ms = int((perf_counter() - llm_t0) * 1000)
            logs.append(
                (
                    "info",
                    f"content 节点模型调用完成 id={tid} 用时={llm_elapsed_ms}ms",
                )
            )
            raise TimeoutError(
                f"content 节点 [{work_idx + 1}/{len_content_nodes}] LLM 调用超时（>{review_timeout_seconds}秒）"
            ) from e
        else:
            llm_elapsed_ms = int((perf_counter() - llm_t0) * 1000)
            logs.append(
                (
                    "info",
                    f"content 节点模型调用完成 id={tid} 用时={llm_elapsed_ms}ms",
                )
            )

        node_elapsed_ms = int((perf_counter() - node_t0) * 1000)
        logs.append(
            (
                "info",
                (
                    f"content 节点完成 [{work_idx + 1}/{len_content_nodes}] id={tid} "
                    f"总用时={node_elapsed_ms}ms 累计tokens={{tokens_placeholder}}"
                ),
            )
        )
        if fingerprint:
            try:
                cache_store(
                    ldb,
                    fingerprint=fingerprint,
                    step_id=step_id,
                    template_node_id=tid,
                    step=sub,
                )
            except Exception as e:
                logs.append(("warning", f"content 节点结果缓存写入失败 id={tid}: {e!s}"))
        return (work_idx, sub, usage, logs, dbg)
    finally:
        ldb.close()


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


def _basis_catalog_from_rows(rows: list[BasisItem]) -> str:
    lines = []
    for r in rows:
        mandatory = "是" if bool(r.is_mandatory) else "否"
        lines.append(
            f"- 文献类型: {r.doc_type} | 标准号: {r.standard_no} | 名称: {r.doc_name} | 效力: {r.effect_status} | 必引: {mandatory}"
        )
    return "\n".join(lines) if lines else "(编制依据库中暂无记录)"


def _basis_prompt(full_content: str, rows: list[BasisItem]) -> str:
    catalog = _basis_catalog_from_rows(rows)
    return (
        "# Role\n"
        "你是一位极其严谨的建筑工程文档合规性审核专家。\n\n"
        "# Task\n"
        "对比【待审文档】与【标准规范列表】，识别“现行必引缺失”与“废止误引”两类合规性问题。\n"
        "说明：输入文本已剔除“精确匹配已命中”的行；仅对剩余文本与剩余条目执行匹配。\n\n"
        "# Process Logic\n"
        "1. 提取待审文档正文和 [表格第N行] 中出现的所有标准号（如 GB50007-2011）和名称（如 建筑地基基础设计规范）。\n"
        "2. 将提取结果与【标准规范列表】逐一比对：\n"
        "   - 规则A（现行缺失）：若列表条目为“效力：现行”且“必引：是”，但其标准号和名称均未出现在文档中，判定为“现行缺失”。\n"
        "   - 规则B（废止误引）：若列表条目为“效力：废止”，但其标准号或名称出现在文档中，判定为“废止误引”。\n"
        "   - 规则C：忽略列表外多余引用；忽略列表内“必引：否”且文档未引用的条目。\n\n"
        "# Constraints\n"
        "- issues 仅允许包含“现行缺失”“废止误引”。\n"
        "- 每条 issue 必须包含 category，且只能是“现行缺失”或“废止误引”。\n"
        "- 禁止输出模糊表述（如“建议核实”“需确认”“可能”“请核查”），必须给出确定性判定。\n"
        f"- 若问题类型为“现行缺失”，evidence 固定填写：{_BASIS_MISSING_EVIDENCE}\n"
        "- 若问题类型为“废止误引”，evidence 必须是文档原文或表格展开内容中的直接摘录。\n"
        "- 若某条废止规范未被引用，不得为其生成 issue。\n"
        "- 每条 issue 的 related.suggestions 必须返回 1~2 条可执行整改动作，使用祈使句，禁止空数组。\n"
        "- 建议语句必须包含明确对象（标准号或规范名称）与动作（补充引用/删除替换/同步修订）。\n"
        "- category=现行缺失 时，suggestions 优先使用“在编制依据中补充引用《规范名》（标准号）”类动作。\n"
        "- category=废止误引 时，suggestions 优先使用“删除废止规范并替换为现行版本”类动作。\n"
        "- 严格按给定 JSON 结构输出，不要新增、改名字段。\n"
        "- 仅输出 JSON 对象本体，不要输出任何额外解释或 Markdown 代码块。\n\n"
        "# Data Source\n"
        "【待审文档】：\n"
        "以下内容为待审文档中与编制依据相关的章节全文（若有表格，已按“[表格第N行] 单元格1 | 单元格2 ...”展开）：\n\n"
        "---\n"
        f"{full_content[:24000]}\n"
        "---\n\n"
        "【标准规范列表】：\n"
        "以下为该方案类型在系统中登记的编制依据条目（审核必须完全依照该列表执行）：\n"
        f"{catalog}\n\n"
        "# Suggestions Template\n"
        "- 现行缺失示例：['在编制依据中补充引用《建筑地基基础设计规范》（GB50007-2011）', '补充后同步检查目录与正文引用名称一致']\n"
        "- 废止误引示例：['从编制依据中删除《建设工程高大模板支撑系统施工安全监督导则》（建办质[2009]254号）', '将该废止规范替换为对应现行标准并同步修订正文引用']\n\n"
        "# Output Format\n"
        "请严格按照以下 JSON 结构输出：\n"
        '{"passed": boolean, "summary": string, "issues": [{"category": "现行缺失|废止误引", "message": string, "evidence": string, "related": {"standard_no": string, "doc_name": string, "suggestions": string[]}}]}'
    )


def _normalize_basis_issue_related(issue: ReportIssue) -> None:
    related = issue.related if isinstance(issue.related, dict) else {}
    anchor = issue.anchor if isinstance(issue.anchor, dict) else {}

    suggestions: list[str] = []
    raw_suggestions = related.get("suggestions")
    if isinstance(raw_suggestions, list):
        suggestions.extend(str(x).strip() for x in raw_suggestions if str(x).strip())
    for key in ("suggestion", "optimize_suggestion", "optimization_suggestion"):
        text = str(related.get(key) or "").strip()
        if text:
            suggestions.append(text)
    deduped_suggestions: list[str] = []
    for item in suggestions:
        if item not in deduped_suggestions:
            deduped_suggestions.append(item)
    standard_no = str(related.get("standard_no") or "").strip()
    doc_name = str(related.get("doc_name") or "").strip()
    raw_category = str(related.get("category") or "").strip()
    category = raw_category if raw_category in _BASIS_ALLOWED_CATEGORIES else ""
    if not category:
        msg = issue.message.strip()
        if "废止" in msg or "失效" in msg:
            category = "废止误引"
        else:
            category = "现行缺失"
    related["category"] = category

    if category == "现行缺失":
        issue.evidence = _BASIS_MISSING_EVIDENCE
    elif not str(issue.evidence or "").strip():
        issue.evidence = str(related.get("original_text") or "").strip()

    if not deduped_suggestions:
        if category == "废止误引":
            subject = f"《{doc_name}》（{standard_no}）" if doc_name or standard_no else "该废止规范"
            deduped_suggestions = [
                f"从编制依据中删除{subject}",
                "将该废止规范替换为对应现行标准并同步修订正文引用",
            ]
        else:
            subject = f"《{doc_name}》（{standard_no}）" if doc_name or standard_no else "相关现行必引规范（标准号待补充）"
            deduped_suggestions = [
                f"在编制依据中补充引用{subject}",
                "补充后同步检查目录与正文引用名称一致",
            ]
    related["suggestions"] = deduped_suggestions[:2]
    related["standard_no"] = standard_no
    related["doc_name"] = doc_name

    related["original_text"] = str(related.get("original_text") or issue.evidence or "").strip()

    chapter_path_raw = anchor.get("title_path")
    chapter_path = [str(x).strip() for x in chapter_path_raw] if isinstance(chapter_path_raw, list) else []
    chapter_path = [x for x in chapter_path if x]
    template_node_id = str(anchor.get("template_node_id") or "").strip()
    user_title = str(anchor.get("user_title") or "").strip()
    heading_para_index_raw = anchor.get("heading_para_index")
    heading_para_index = heading_para_index_raw if isinstance(heading_para_index_raw, int) else None
    related["location"] = {
        "chapter_path": chapter_path,
        "chapter_text": " > ".join(chapter_path),
        "template_node_id": template_node_id,
        "heading_para_index": heading_para_index,
        "user_title": user_title,
    }

    issue.related = related


def _normalize_context_consistency_issue(
    issue: ReportIssue,
    *,
    current_title_path: list[Any],
    ref_full_paths: list[str],
) -> None:
    """将章节展示为完整标题路径（如 一、… > 1.…），并尽量把对照章节解析为模板中的完整路径。"""
    related = issue.related if isinstance(issue.related, dict) else {}
    parts = [str(x).strip() for x in current_title_path if str(x).strip()]
    cur_full = " > ".join(parts)
    if cur_full:
        related["chapter_a"] = cur_full
    raw_b = str(related.get("chapter_b") or "").strip()
    if raw_b and ref_full_paths:
        if raw_b in ref_full_paths:
            related["chapter_b"] = raw_b
        else:
            matched: str | None = None
            for rp in ref_full_paths:
                if not rp:
                    continue
                if raw_b in rp:
                    matched = rp
                    break
                last_seg = rp.split(" > ")[-1].strip()
                if last_seg and (raw_b == last_seg or last_seg.endswith(raw_b) or raw_b in last_seg):
                    matched = rp
                    break
            if matched:
                related["chapter_b"] = matched
    issue.related = related


def _context_prompt(
    current_title: str,
    current_text: str,
    ref_blocks: list[tuple[str, str]],
    consistency_prompt: str | None = None,
    global_rules: str = "",
) -> str:
    parts: list[str] = [
        f"当前章节：{current_title}\n---\n{current_text[:12000]}",
    ]
    for title, text in ref_blocks:
        parts.append(f"对照章节：{title}\n---\n{text[:12000]}")
    cp = (consistency_prompt or "").strip()
    if cp:
        cp = cp[:8000]
        parts.append(f"【一致性校验提示词】\n{cp}")
    else:
        # 无 CP 时回退到通用检查指引

        parts.append(
            "请检查上述章节在数据、结论、术语、前后要求等方面是否一致。"
            "输出 JSON，issues 中说明哪两章不一致及原因，"
            "related 含 chapter_a、chapter_b（均须为完整层级路径，多级用「 > 」连接，与上文章节标题行一致），"
            "并补充可执行整改建议（suggestions: string[]，可选 suggestion: string）。"
        )
    if global_rules and global_rules.strip():
        parts.append("【审核总则】\n" + global_rules.strip())
    parts.append(
        "【审核逻辑】\n"
        "1. 严格依据【一致性校验提示词】界定比对重点与判定标准；不得凭空增设其中未涉及的无关检查项。\n"
        "2. 在当前章节与对照章节之间进行交叉核对。\n"
        "3. 输出 JSON：issues 中说明哪两章不一致及原因；related 含 chapter_a、chapter_b，"
        "chapter_a 与 chapter_b 必须使用与上文「当前章节」「对照章节」标题行一致的完整层级路径，"
        "多级标题用「 > 」连接（例如：一、工程概况 > 1.模板支撑体系工程概况和特点），"
        "并给出可执行整改建议（suggestions: string[]，可选 suggestion: string）。"
    )
    return "\n\n".join(parts) + "\n"


def _content_prompt(
    current_text: str,
    ref_text: str,
    kb_text: str,
    checklist_block: str,
    global_rules: str = "",
) -> str:
    """构造 per-node 内容审核 LLM prompt（逐项清单判定版）。

    `checklist_block` 为由节点 review_prompt 确定性拆分出的
    【检查项清单】+【判定附注】文本块（见 services/checklist.py），
    替代原先整段散文式【审核提示词】。
    `global_rules`（模板级「内容审核全局规则」）作为补充追加其后。
    """
    cur = current_text[:CONTENT_TEXT_CAP]
    if len(current_text) > CONTENT_TEXT_CAP:
        cur += "\n（注意：本节正文超长，已截断，仅以上述内容为准）"
    ref = ref_text[:CONTENT_REF_TEXT_CAP]
    if len(ref_text) > CONTENT_REF_TEXT_CAP:
        ref += "\n（注意：引用章节正文超长，已截断）"
    kb = kb_text[:CONTENT_KB_TEXT_CAP]
    prompt_block = checklist_block
    if global_rules and global_rules.strip():
        prompt_block = f"{checklist_block}\n\n{global_rules.strip()}"
    return (
        "【当前章节及子节正文】\n"
        f"{cur}\n\n"
        "【引用章节正文】\n"
        f"{ref or '(无)'}\n\n"
        "【知识库检索片段】\n"
        f"{kb or '(无)'}\n\n"
        "【审核提示词】\n"
        f"{prompt_block}\n\n"
        "【审核逻辑】\n"
        "1. 对【审核提示词】中【检查项清单】的每个检查项逐项判定，按 item_id 回填 verdict，"
        "不得遗漏任何 item_id，也不得新增清单之外的检查项；判定判据遵循【审核总则】"
        "（量化型/清单型/存在性型的分档标准）与【判定附注】。\n"
        "2. 逐项核查【当前章节及子节正文】；不符合时 verdict=fail 并在 message 中明确指出缺失项或矛盾点；"
        "判 pass 时必须在 evidence 中引用正文中证明该内容存在的原文（≤50 字），"
        "引用不到原文的不得判 pass，按【审核总则】“未给出”处理（verdict=fail）。\n"
        "3. 使用【引用章节正文】与【知识库检索片段】做交叉验证与依据补充。\n"
        "4. 当【引用章节正文】或【知识库检索片段】为“(无)”时：\n"
        "   (a) 不得臆测外部依据，禁止编造规范条文/编号/页码；\n"
        "   (b) 仍须基于【当前章节及子节正文】给出实质性判定，不得因缺交叉依据就放弃核查；\n"
        "   (c) 仅当某检查项必须依赖引用章节或知识库才能判断时，verdict 才填 na；其它情形仍按 pass/fail 判定。\n"
        "5. 仅输出 JSON 对象；每条 fail 的检查项须同时给出问题、证据来源（当前章节/引用章节/知识库）及参考依据。\n"
        "6. verdict=fail 的检查项必须在 related 中给出可执行整改建议"
        "（fix: string，suggestions: string[]）。"
    )


def _full_document_prompt(
    doc_text: str,
    kb_text: str,
    review_prompt: str,
    heading_catalog: str,
) -> str:
    return (
        "【文档标题索引】\n"
        "以下为待审文档全部标题及其段落索引（定位问题时须优先使用 heading_para_index，勿臆造）：\n"
        f"{heading_catalog}\n\n"
        "【待审文档全文】\n"
        "标题行含 [hpi=N] 表示该标题在 Word 中的段落索引，与【文档标题索引】一致。\n"
        f"{doc_text}\n\n"
        "【知识库检索片段】\n"
        f"{kb_text[:FULL_DOCUMENT_KB_CAP] or '(无)'}\n\n"
        "【通篇审核提示词】\n"
        f"{review_prompt}\n\n"
        "【审核逻辑】\n"
        "1. 严格依据【通篇审核提示词】提取核查项，不得自行新增无关检查项。\n"
        "2. 在【待审文档全文】中逐项核查；结合【知识库检索片段】做交叉验证。\n"
        "3. 每条可定位到具体章节的问题，anchor 必须包含 heading_para_index（取自索引或正文 [hpi=N]）"
        "及 title_path（字符串数组，每级标题一项，须与索引中该 hpi 的完整路径一致）。\n"
        "4. 当【知识库检索片段】为“(无)”时：\n"
        "   (a) 不得臆测外部依据，禁止编造规范条文/编号/页码；\n"
        "   (b) 仍须基于【待审文档全文】给出实质性审核结论，不得因缺 KB 就放弃核查；\n"
        "   (c) 仅当某条核查项必须依赖知识库才能判断时，才在该 issue 的 evidence / related 中注明“无知识库可交叉验证”，并将 severity 设为 info；其它情形仍按 error / warning 出问题。\n"
        "5. 仅输出 JSON；issues 需含 message、evidence、anchor、related.suggestions（string[]）。\n"
        "6. anchor 输出示例：\n"
        '{"heading_para_index": 128, "title_path": ["六、施工管理及作业人员配备和分工", "4.其他作业人员"]}'
    )


def _extract_title_path_from_issue(issue: ReportIssue) -> list[str]:
    anchor = issue.anchor if isinstance(issue.anchor, dict) else {}
    path = parse_title_path_value(anchor.get("title_path"))
    if path:
        return path

    related = issue.related if isinstance(issue.related, dict) else {}
    loc = related.get("location")
    if isinstance(loc, str) and loc.strip():
        path = parse_title_path_value(loc)
        if path:
            return path
    if isinstance(loc, dict):
        path = parse_title_path_value(loc.get("chapter_path"))
        if path:
            return path
        path = parse_title_path_value(loc.get("chapter_text"))
        if path:
            return path

    for key in ("chapter", "chapter_a", "chapter_text", "title_path"):
        path = parse_title_path_value(related.get(key))
        if path:
            return path

    for text in (str(issue.message or ""), str(issue.evidence or "")):
        for line in text.split("\n"):
            if re.search(r"\s*[>＞]\s*", line):
                path = parse_title_path_value(line)
                if path:
                    return path
    return []


def _extract_hpi_from_issue(issue: ReportIssue) -> int | None:
    anchor = issue.anchor if isinstance(issue.anchor, dict) else {}
    hpi = _coerce_int_hpi(anchor.get("heading_para_index"))
    if hpi is not None:
        return hpi

    related = issue.related if isinstance(issue.related, dict) else {}
    loc = related.get("location")
    if isinstance(loc, dict):
        hpi = _coerce_int_hpi(loc.get("heading_para_index"))
        if hpi is not None:
            return hpi

    for text in (str(issue.evidence or ""), str(issue.message or "")):
        hpi = _extract_hpi_from_text(text)
        if hpi is not None:
            return hpi
    return None


def _write_full_document_location(
    issue: ReportIssue,
    *,
    title_path: list[str],
    heading_para_index: int | None,
) -> None:
    anchor = dict(issue.anchor) if isinstance(issue.anchor, dict) else {}
    related = dict(issue.related) if isinstance(issue.related, dict) else {}

    anchor["title_path"] = title_path
    if heading_para_index is not None:
        anchor["heading_para_index"] = heading_para_index
    elif "heading_para_index" in anchor:
        del anchor["heading_para_index"]

    chapter_text = " > ".join(title_path)
    related["location"] = {
        "chapter_path": title_path,
        "chapter_text": chapter_text,
        "heading_para_index": heading_para_index,
        "user_title": title_path[-1] if title_path else "",
    }
    issue.anchor = anchor
    issue.related = related


def _normalize_full_document_issue(
    issue: ReportIssue,
    heading_index: list[UserHeadingEntry],
) -> None:
    hpi = _extract_hpi_from_issue(issue)
    path = _extract_title_path_from_issue(issue)
    entry = resolve_heading_from_index(heading_index, hpi=hpi, title_path=path or None)

    if entry is not None:
        _write_full_document_location(
            issue,
            title_path=entry["title_path"],
            heading_para_index=entry["heading_para_index"],
        )
        return

    if path:
        _write_full_document_location(issue, title_path=path, heading_para_index=hpi)
        return

    if hpi is not None:
        by_hpi = {e["heading_para_index"]: e for e in heading_index}
        if hpi in by_hpi:
            e = by_hpi[hpi]
            _write_full_document_location(
                issue,
                title_path=e["title_path"],
                heading_para_index=e["heading_para_index"],
            )


def _load_full_document_config(tmpl: SchemeTemplate) -> FullDocumentReviewConfig | None:
    raw = tmpl.full_document_review_config
    if not raw or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return FullDocumentReviewConfig.model_validate(data)
    except Exception:
        return None


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
        image_result = extract_and_store_docx_images(
            docx_bytes=raw,
            source_object_key=task.object_key,
        )
        _append_log(
            db,
            task,
            "info",
            (
                "文档图片处理完成: "
                f"uploaded={image_result.uploaded_count}, "
                f"failed={image_result.failed_count}, "
                f"paragraphs_with_images={len(image_result.paragraph_image_keys)}"
            ),
        )
        db.commit()
        user_tree = parse_docx_to_tree(
            BytesIO(raw),
            paragraph_image_keys=image_result.paragraph_image_keys,
        )
        user_nodes = user_tree.get("nodes") or []

        review_timeout_seconds = get_review_timeout_seconds(db)
        match_mode = tmpl.structure_match_mode or "exact"
        llm_matcher = None
        if match_mode == "fuzzy":
            llm_matcher = build_llm_matcher(
                db,
                timeout_seconds=float(max(60.0, review_timeout_seconds)),
                log_sink=lambda level, msg: _append_log(db, task, level, msg),
            )
        mapping, struct_raw, match_records = align_template_user_trees(
            template_nodes,
            user_nodes,
            match_mode=match_mode,
            llm_matcher=llm_matcher,
        )
        structure_step = _structure_issues_to_report(
            struct_raw, match_records=match_records, match_mode=match_mode
        )

        provider = effective_default_provider(db)
        prompt_debug_enabled = get_review_prompt_debug_enabled(db)
        compilation_basis_concurrency = get_compilation_basis_concurrency(db)
        context_consistency_concurrency = get_context_consistency_concurrency(db)
        content_concurrency = get_content_concurrency(db)
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
                basis_work: list[tuple[int, dict[str, Any], str]] = []
                widx = 0
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
                    basis_work.append((widx, anchor, prompt))
                    widx += 1

                def _basis_run(payload: tuple[dict[str, Any], str]) -> Any:
                    anchor_b, pr = payload
                    ldb = SessionLocal()
                    try:
                        return _llm_review_execute(
                            ldb,
                            step_id=step_id,
                            user_prompt=pr,
                            anchor_base=anchor_b,
                            collect_debug=prompt_debug_enabled,
                            timeout_seconds=120.0,
                            timeout_fail_fast=False,
                            max_tokens=LLM_JSON_REVIEW_MAX_TOKENS,
                        )
                    finally:
                        ldb.close()

                basis_results = _bounded_parallel_map(
                    concurrency=compilation_basis_concurrency,
                    items=[(i, (a, p)) for i, a, p in basis_work],
                    worker=_basis_run,
                )
                basis_results.sort(key=lambda x: x[0])
                for _, pack in basis_results:
                    sub, usage, log_lines, dbg = pack
                    for level, msg in log_lines:
                        _append_log(db, task, level, msg)
                    if dbg is not None and debug_prompts is not None:
                        debug_prompts.append(dbg)
                    _merge_usage(token_usage_total, usage)
                    _write_usage_snapshot(task, token_usage_total)
                    for issue in sub.issues:
                        _normalize_basis_issue_related(issue)
                    merged.issues.extend(sub.issues)
                    if not sub.passed:
                        merged.passed = False
                merged.summary = (
                    "编制依据审核通过" if merged.passed else f"发现 {len(merged.issues)} 条编制依据相关问题"
                )
                report.steps.append(merged)

            elif step_id == "context_consistency":
                merged = ReportStep(step_id=step_id, passed=True, summary="", issues=[])
                # 复用模板级「内容审核全局规则」作为上下文一致性的【审核总则】约束
                ctx_global_rules = (tmpl.content_review_rules or "").strip()
                ctx_work: list[tuple[int, dict[str, Any], str, list[str]]] = []
                cidx = 0
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
                    raw_cp = tn.get("context_consistency_prompt")
                    cp = raw_cp.strip() if isinstance(raw_cp, str) else ""
                    prompt = _context_prompt(cur_title, cur_text, ref_blocks, cp or None, ctx_global_rules)
                    ref_path_strings = [str(rb[0]).strip() for rb in ref_blocks if str(rb[0]).strip()]
                    ctx_work.append((cidx, anchor, prompt, ref_path_strings))
                    cidx += 1

                ctx_updated_at = str(tmpl.updated_at.isoformat() if tmpl.updated_at else "")

                def _ctx_run(payload: tuple[dict[str, Any], str, str]) -> Any:
                    anchor_b, pr, node_tid = payload
                    ldb = SessionLocal()
                    ctx_logs: list[LogLine] = []
                    fingerprint = ""
                    try:
                        try:
                            provider, model = provider_model_pair(ldb)
                            fingerprint = prompt_fingerprint(
                                step_id=step_id,
                                provider=provider,
                                model=model,
                                prompt=pr,
                                template_updated_at=ctx_updated_at,
                            )
                            cached_step = cache_lookup(ldb, fingerprint)
                            if cached_step is not None:
                                ctx_logs.append(
                                    (
                                        "info",
                                        f"{step_id} 节点命中结果缓存 id={node_tid}"
                                        f"（章节与规则未变化，复用上次判定）",
                                    )
                                )
                                return (cached_step, EMPTY_USAGE, ctx_logs, None)
                        except Exception as e:
                            fingerprint = ""
                            ctx_logs.append(
                                ("warning", f"{step_id} 节点结果缓存查询失败 id={node_tid}: {e!s}")
                            )
                        sub, usage, log_lines, dbg = _llm_review_execute(
                            ldb,
                            step_id=step_id,
                            user_prompt=pr,
                            anchor_base=anchor_b,
                            collect_debug=prompt_debug_enabled,
                            timeout_seconds=120.0,
                            timeout_fail_fast=False,
                            max_tokens=LLM_JSON_REVIEW_MAX_TOKENS,
                        )
                        log_lines = ctx_logs + log_lines
                        if fingerprint:
                            try:
                                cache_store(
                                    ldb,
                                    fingerprint=fingerprint,
                                    step_id=step_id,
                                    template_node_id=node_tid,
                                    step=sub,
                                )
                            except Exception as e:
                                log_lines.append(
                                    ("warning", f"{step_id} 节点结果缓存写入失败 id={node_tid}: {e!s}")
                                )
                        return (sub, usage, log_lines, dbg)
                    finally:
                        ldb.close()

                ctx_results = _bounded_parallel_map(
                    concurrency=context_consistency_concurrency,
                    items=[(i, (a, p, str(a.get("template_node_id") or ""))) for i, a, p, _rfs in ctx_work],
                    worker=_ctx_run,
                )
                ctx_results.sort(key=lambda x: x[0])
                for i, (_, pack) in enumerate(ctx_results):
                    sub, usage, log_lines, dbg = pack
                    for level, msg in log_lines:
                        _append_log(db, task, level, msg)
                    if dbg is not None and debug_prompts is not None:
                        debug_prompts.append(dbg)
                    _merge_usage(token_usage_total, usage)
                    _write_usage_snapshot(task, token_usage_total)
                    _anchor = ctx_work[i][1]
                    _ref_paths = ctx_work[i][3]
                    _tp = _anchor.get("title_path") if isinstance(_anchor.get("title_path"), list) else []
                    for issue in sub.issues:
                        _normalize_context_consistency_issue(
                            issue,
                            current_title_path=_tp,
                            ref_full_paths=_ref_paths,
                        )
                    merged.issues.extend(sub.issues)
                    if not sub.passed:
                        merged.passed = False
                merged.summary = (
                    "上下文一致性审核通过" if merged.passed else f"发现 {len(merged.issues)} 条一致性问题"
                )
                report.steps.append(merged)

            elif step_id == "content":
                merged = ReportStep(step_id=step_id, passed=True, summary="", issues=[])
                # 模板级「内容审核全局规则」：作为 per-node 提示词的补充注入到 LLM prompt
                content_global_rules = (tmpl.content_review_rules or "").strip()
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

                content_items = [
                    (
                        i,
                        (
                            i,
                            tn,
                            template_nodes,
                            mapping,
                            dify_url,
                            dify_key,
                            review_timeout_seconds,
                            prompt_debug_enabled,
                            step_id,
                            len(content_nodes),
                            content_global_rules,
                            str(tmpl.updated_at.isoformat() if tmpl.updated_at else ""),
                        ),
                    )
                    for i, tn in enumerate(content_nodes)
                ]
                content_results = _bounded_parallel_map(
                    concurrency=content_concurrency,
                    items=content_items,
                    worker=_content_node_worker,
                )
                content_results.sort(key=lambda x: x[0])
                for _, pack in content_results:
                    _wi, sub, usage, logs, dbg = pack
                    pending_after_tokens: list[tuple[str, str]] = []
                    for level, msg in logs:
                        if "{tokens_placeholder}" in msg:
                            pending_after_tokens.append((level, msg))
                        else:
                            _append_log(db, task, level, msg)
                    _merge_usage(token_usage_total, usage)
                    _write_usage_snapshot(task, token_usage_total)
                    for level, msg in pending_after_tokens:
                        msg_out = msg.replace("{tokens_placeholder}", str(task.total_tokens or 0))
                        _append_log(db, task, level, msg_out)
                    if dbg is not None and debug_prompts is not None:
                        debug_prompts.append(dbg)
                    merged.issues.extend(sub.issues)
                    if not sub.passed:
                        merged.passed = False
                    db.commit()
                merged.summary = (
                    "内容审核完成" if merged.passed else f"发现 {len(merged.issues)} 条内容问题"
                )
                report.steps.append(merged)

            elif step_id == "full_document":
                fd_config = _load_full_document_config(tmpl)
                rp = (fd_config.review_prompt or "").strip() if fd_config else ""
                if not rp:
                    _append_log(db, task, "warning", "通篇审核已启用但未配置提示词，已跳过")
                    report.steps.append(
                        ReportStep(
                            step_id=step_id,
                            passed=True,
                            summary="通篇审核未配置提示词，已跳过",
                            issues=[],
                        )
                    )
                else:
                    heading_index = build_user_heading_index(user_nodes)
                    catalog_text, catalog_truncated = format_heading_catalog(
                        heading_index,
                        max_entries=FULL_DOCUMENT_HEADING_CATALOG_MAX,
                    )
                    if catalog_truncated:
                        _append_log(
                            db,
                            task,
                            "warning",
                            f"通篇审核标题索引已截断至 {FULL_DOCUMENT_HEADING_CATALOG_MAX} 条",
                        )
                    full_raw = collect_full_document_text(user_nodes)
                    doc_text = full_raw
                    if len(full_raw) > FULL_DOCUMENT_TEXT_CAP:
                        doc_text = full_raw[:FULL_DOCUMENT_TEXT_CAP]
                        _append_log(
                            db,
                            task,
                            "warning",
                            f"通篇审核文档正文已截断至 {FULL_DOCUMENT_TEXT_CAP} 字符（原文 {len(full_raw)} 字符）",
                        )
                    kb_text = ""
                    ds = fd_config.dify_dataset_id if fd_config else None
                    if ds and dify_url and dify_key:
                        kws = fd_config.knowledge_keywords if fd_config else []
                        qparts: list[str] = []
                        if isinstance(kws, list):
                            qparts.extend(str(x).strip() for x in kws if str(x).strip())
                        if not qparts:
                            qparts.append(name or category or "方案审核")
                        query = " ".join(qparts)[:250]
                        try:
                            kb_text = retrieve_dataset_chunks(
                                dify_url, dify_key, str(ds), query
                            )
                        except Exception as e:
                            _append_log(
                                db,
                                task,
                                "warning",
                                f"通篇审核知识库检索跳过 dataset={ds}: {e!s}",
                            )
                    prompt = _full_document_prompt(
                        doc_text, kb_text, rp, catalog_text
                    )
                    fd_timeout = float(max(180, review_timeout_seconds))
                    sub, usage, log_lines, dbg = _llm_review_execute(
                        db,
                        step_id=step_id,
                        user_prompt=prompt,
                        anchor_base={},
                        collect_debug=prompt_debug_enabled,
                        timeout_seconds=fd_timeout,
                        timeout_fail_fast=False,
                        system=FULL_DOCUMENT_JSON_SYSTEM,
                        max_tokens=LLM_JSON_REVIEW_MAX_TOKENS,
                    )
                    for level, msg in log_lines:
                        _append_log(db, task, level, msg)
                    _merge_usage(token_usage_total, usage)
                    _write_usage_snapshot(task, token_usage_total)
                    if dbg is not None and debug_prompts is not None:
                        debug_prompts.append(dbg)
                    unlocated = 0
                    for issue in sub.issues:
                        _normalize_full_document_issue(issue, heading_index)
                        loc = (issue.related or {}).get("location") if isinstance(issue.related, dict) else None
                        chapter_text = ""
                        if isinstance(loc, dict):
                            chapter_text = str(loc.get("chapter_text") or "").strip()
                        if not chapter_text:
                            unlocated += 1
                    if sub.issues:
                        _append_log(
                            db,
                            task,
                            "info",
                            f"通篇审核定位：{len(sub.issues) - unlocated}/{len(sub.issues)} 条已解析章节路径",
                        )
                    sub.summary = sub.summary or (
                        "通篇审核通过" if sub.passed else f"发现 {len(sub.issues)} 条通篇问题"
                    )
                    report.steps.append(sub)
                    db.commit()

        # 图审核（独立步骤，不进工作流）：模板有节点配置且模型就绪时执行
        image_nodes = [
            (tn, parse_node_image_config(tn))
            for tn in iter_nodes(template_nodes)
            if parse_node_image_config(tn) is not None
        ]
        if image_nodes:
            task.review_stage = IMAGE_STEP_ID
            _append_log(db, task, "info", f"开始步骤: {IMAGE_STEP_ID}（配置节点 {len(image_nodes)} 个）")
            db.commit()
            img_cfg = effective_image_review(db)
            if not img_cfg.ready:
                _append_log(
                    db, task, "warning",
                    "图审核已配置节点但模型未就绪（未启用或 MiniMax 凭据/图审核模型缺失），已跳过",
                )
                report.steps.append(
                    ReportStep(
                        step_id=IMAGE_STEP_ID,
                        passed=True,
                        summary="图审核模型未配置或未启用，已跳过",
                        issues=[],
                    )
                )
            else:
                img_global_rules = (tmpl.image_review_rules or "").strip()
                img_updated_at = str(tmpl.updated_at.isoformat() if tmpl.updated_at else "")
                img_concurrency = max(1, min(get_content_concurrency(db), 4))
                img_work: list[tuple[int, tuple[dict, Any, Any, str, str, list[str]]]] = []
                for i, (tn, node_img_cfg) in enumerate(image_nodes):
                    tid = str(tn.get("id") or "")
                    un = resolve_user_node(mapping, tid)
                    if un is None:
                        continue
                    tp_list = title_path_for_node(template_nodes, tid)
                    img_work.append(
                        (
                            i,
                            (
                                tn,
                                un,
                                node_img_cfg,
                                tid,
                                title_path_str(tp_list),
                                tp_list,
                            ),
                        )
                    )

                def _img_node_worker(payload: tuple[dict, Any, Any, str, str, list[str]]) -> Any:
                    tn, un, node_img_cfg, tid, tp_str, tp_list = payload
                    ldb = SessionLocal()
                    try:
                        _r = review_node_images(
                            ldb=ldb,
                            cfg=img_cfg,
                            template_node_id=tid,
                            node_title_path=tp_str,
                            config=node_img_cfg,
                            user_node=un,
                            global_rules=img_global_rules,
                            template_updated_at=img_updated_at,
                            debug_prompts=debug_prompts if prompt_debug_enabled else None,
                            title_path=tp_list,
                        )
                        return (tid, _r)
                    finally:
                        ldb.close()

                img_results = _bounded_parallel_map(
                    concurrency=img_concurrency,
                    items=img_work,
                    worker=_img_node_worker,
                )
                img_step = ReportStep(step_id=IMAGE_STEP_ID, passed=True, summary="", issues=[])
                node_summaries: list[str] = []
                for _, (tid, _r) in img_results:
                    for level, msg in _r.logs:
                        _append_log(db, task, level, msg)
                    img_step.issues.extend(_r.issues)
                    img_step.image_items.extend(_r.image_items)
                    if not _r.passed:
                        img_step.passed = False
                    if _r.summary:
                        node_summaries.append(f"{tid}: {_r.summary}")
                    db.commit()
                img_step.summary = (
                    "；".join(node_summaries)
                    if node_summaries
                    else ("图审核通过" if img_step.passed else f"发现 {len(img_step.issues)} 条图审核问题")
                )
                fd_idx = next(
                    (
                        i
                        for i, s in enumerate(report.steps)
                        if s.step_id == "full_document"
                    ),
                    len(report.steps),
                )
                report.steps.insert(fd_idx, img_step)
                _append_log(db, task, "info", f"图审核步骤完成: {img_step.summary}")
            task.review_stage = None
            db.commit()

        task.review_stage = None
        _append_log(db, task, "info", "审核步骤结束，开始生成审核报告")
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
                    step_label = WORD_COMMENT_STEP_LABEL_CN.get(st.step_id, st.step_id)
                    check_item = str((iss.related or {}).get("check_item_id") or "").strip()
                    item_prefix = f"【检查项 {check_item}】" if check_item else ""
                    txt = f"({step_label}) {item_prefix}{iss.message}"
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
