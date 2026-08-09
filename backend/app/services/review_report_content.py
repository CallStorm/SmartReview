"""Shared audit-report content helpers (issue fields, step tables, summary)."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.models.scheme_review_task import ReviewTaskStatus, SchemeReviewTask
from app.schemas.review_report import ReportIssue, ReportStep, ReviewReportV1
from app.services.review_pipeline import WORD_COMMENT_STEP_LABEL_CN

STEP_ORDER = [
    "structure",
    "compilation_basis",
    "context_consistency",
    "content",
    "full_document",
]

SECTION_NUM_CN = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]

STRUCTURE_KIND_LABEL: dict[str, str] = {
    "missing_section": "缺失章节",
    "order_mismatch": "顺序不符",
    "extra_section": "多余章节",
}

STEP_DESCRIPTION: dict[str, str] = {
    "structure": "对照模版检查必备章节是否齐全（多余章节与章节顺序不校验）。",
    "compilation_basis": "审核方案编制依据是否完整覆盖现行必引规范，并识别废止误引。",
    "context_consistency": "检查方案各章节之间参数、描述是否前后一致。",
    "content": "按模版节点逐项核查章节内容是否满足审核要求。",
    "full_document": "对全文进行通篇审核，识别跨章节或整体性风险。",
}

_STANDARD_RE = re.compile(
    r"\b(?:GB|JGJ|DBJ|DB|CECS|T/[A-Z]+)\s*[\-/]?\s*\d{2,6}(?:\.\d+)?(?:-\d{4})?\b",
    re.IGNORECASE,
)

DISCLAIMER = (
    "注意：本报告由 AI 自动审核生成，未经人工逐条复核，仅供参考，请方案编制者自行核查。"
)


def as_string_array(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


def parse_title_path_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return as_string_array(value)
    if isinstance(value, str) and value.strip():
        return [p.strip() for p in re.split(r"\s*[>＞]\s*", value) if p.strip()]
    return []


def title_path(issue: ReportIssue) -> str:
    path = parse_title_path_value((issue.anchor or {}).get("title_path"))
    if path:
        return " > ".join(path)
    related = issue.related or {}
    loc = related.get("location")
    if isinstance(loc, dict):
        chapter_path = parse_title_path_value(loc.get("chapter_path"))
        if chapter_path:
            return " > ".join(chapter_path)
        chapter_text = str(loc.get("chapter_text") or "").strip()
        if chapter_text:
            return chapter_text
    if isinstance(loc, str) and loc.strip():
        parsed = parse_title_path_value(loc)
        if parsed:
            return " > ".join(parsed)
        return loc.strip()
    chapter = parse_title_path_value(related.get("chapter"))
    if chapter:
        return " > ".join(chapter)
    for key in ("chapter_text", "chapter_a"):
        text = str(related.get(key) or "").strip()
        if text:
            return text
    return ""


def original_text(issue: ReportIssue) -> str:
    related = issue.related or {}
    text = str(related.get("original_text") or "").strip()
    if text:
        return text
    return str(issue.evidence or "").strip()


def suggestions(issue: ReportIssue) -> list[str]:
    related = issue.related or {}
    out: list[str] = []
    raw = related.get("suggestions")
    if isinstance(raw, list):
        for item in raw:
            s = str(item or "").strip()
            if s:
                out.append(s)
    for key in ("suggestion", "optimize_suggestion", "optimization_suggestion"):
        s = str(related.get(key) or "").strip()
        if s:
            out.append(s)
    seen: set[str] = set()
    unique: list[str] = []
    for s in out:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def standards(issue: ReportIssue) -> str:
    related = issue.related or {}
    doc_name = str(related.get("doc_name") or "").strip()
    standard_no = str(related.get("standard_no") or "").strip()
    if doc_name and standard_no:
        return f"《{doc_name}》{standard_no}"
    if doc_name:
        return f"《{doc_name}》"
    if standard_no:
        return standard_no
    combined = f"{issue.message} {issue.evidence}"
    hits = _STANDARD_RE.findall(combined)
    if hits:
        return "、".join(dict.fromkeys(h.replace(" ", "") for h in hits))
    return ""


def basis_category(issue: ReportIssue) -> str:
    related = issue.related or {}
    raw = str(related.get("category") or "").strip()
    if raw in ("现行缺失", "废止误引"):
        return raw
    message = str(issue.message or "")
    if "废止" in message or "失效" in message:
        return "废止误引"
    return "现行缺失"


def context_chapter_pair(issue: ReportIssue) -> tuple[str, str]:
    related = issue.related or {}
    chapter_from_path = title_path(issue)
    raw_a = str(
        related.get("chapter_a") or related.get("current_chapter") or ""
    ).strip()
    path_b = parse_title_path_value(related.get("chapter_b_path"))
    raw_b = str(
        related.get("chapter_b")
        or related.get("ref_chapter")
        or related.get("compare_chapter")
        or ""
    ).strip()
    compare = " > ".join(path_b) if path_b else (raw_b or "—")
    chapter = chapter_from_path or raw_a or "—"
    return chapter, compare


def structure_kind_label(kind: str) -> str:
    return STRUCTURE_KIND_LABEL.get(kind, kind or "—")


def scheme_display_name(task: SchemeReviewTask) -> str:
    raw = (task.original_filename or "").strip() or "document"
    return re.sub(r"\.docx$", "", raw, flags=re.IGNORECASE).strip() or "document"


def format_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    try:
        return value.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


def status_label(status: str) -> str:
    mapping = {
        ReviewTaskStatus.pending: "排队中",
        ReviewTaskStatus.processing: "处理中",
        ReviewTaskStatus.succeeded: "已完成",
        ReviewTaskStatus.failed: "失败",
    }
    return mapping.get(status, status)


def format_suggestions(issue: ReportIssue) -> str:
    related = issue.related or {}
    fix = str(related.get("fix") or "").strip()
    items = suggestions(issue)
    parts: list[str] = []
    if fix:
        parts.append(f"改为：{fix}")
    parts.extend(items)
    return "\n".join(parts) if parts else "—"


def build_summary(report: ReviewReportV1, task: SchemeReviewTask) -> str:
    steps_by_id = {s.step_id: s for s in report.steps}
    parts: list[str] = []
    total_issues = 0
    for step_id in STEP_ORDER:
        step = steps_by_id.get(step_id)
        if step is None:
            continue
        n = len(step.issues)
        if n:
            label = WORD_COMMENT_STEP_LABEL_CN.get(step_id, step_id)
            parts.append(f"{label} {n} 项")
            total_issues += n
    passed_count = sum(1 for s in report.steps if s.passed)
    step_count = len(report.steps)
    status_text = status_label(str(task.status))
    detail = "、".join(parts) if parts else "未发现明显问题"
    conclusion = (
        "全部步骤已通过"
        if passed_count == step_count and total_issues == 0
        else f"共 {step_count} 个步骤，{passed_count} 个通过"
    )
    return (
        f"本次审核任务状态为「{status_text}」，{conclusion}。"
        f"累计发现 {total_issues} 项待关注问题（{detail}）。"
        "请结合下文明细逐项核查并整改。"
    )


def meta_kv_rows(
    task: SchemeReviewTask,
    report: ReviewReportV1,
    *,
    system_name: str,
) -> list[tuple[str, str]]:
    st = task.scheme_type
    scheme_type_text = f"{st.category} / {st.name}" if st else "—"
    audit_time = format_dt(task.finished_at or task.updated_at)
    passed_count = sum(1 for s in report.steps if s.passed)
    return [
        ("方案类型", scheme_type_text),
        ("审核时间", audit_time),
        (
            "审核状态",
            f"{status_label(str(task.status))}（{passed_count}/{len(report.steps)} 步骤通过）",
        ),
        ("生成系统", system_name),
        ("摘要", build_summary(report, task)),
    ]


def structure_table_rows(step: ReportStep) -> list[list[str]]:
    rows: list[list[str]] = []
    for issue in step.issues:
        kind = str((issue.related or {}).get("kind") or "")
        chapter = title_path(issue) or "—"
        rows.append([chapter, structure_kind_label(kind), issue.message])
    return rows


def compilation_basis_table_rows(step: ReportStep) -> list[list[str]]:
    rows: list[list[str]] = []
    for issue in step.issues:
        suggestion_items = suggestions(issue)
        rows.append(
            [
                issue.message,
                basis_category(issue),
                title_path(issue) or "—",
                original_text(issue) or "无",
                "；".join(suggestion_items) if suggestion_items else "—",
                standards(issue) or "—",
            ]
        )
    return rows


def context_consistency_table_rows(step: ReportStep) -> list[list[str]]:
    rows: list[list[str]] = []
    for issue in step.issues:
        chapter, compare = context_chapter_pair(issue)
        suggestion_items = suggestions(issue)
        rows.append(
            [
                chapter,
                compare,
                issue.message,
                "；".join(suggestion_items) if suggestion_items else "—",
            ]
        )
    return rows


def content_like_groups(step: ReportStep) -> list[tuple[str, list[list[str]]]]:
    grouped: dict[str, list[ReportIssue]] = defaultdict(list)
    for issue in step.issues:
        key = title_path(issue) or "未定位章节"
        grouped[key].append(issue)
    out: list[tuple[str, list[list[str]]]] = []
    for chapter, issues in grouped.items():
        rows: list[list[str]] = []
        for idx, issue in enumerate(issues, start=1):
            rows.append(
                [
                    str(idx),
                    issue.message,
                    original_text(issue) or "无",
                    format_suggestions(issue),
                ]
            )
        out.append((chapter, rows))
    return out


def iter_ordered_steps(report: ReviewReportV1) -> list[ReportStep]:
    steps_by_id = {s.step_id: s for s in report.steps}
    ordered: list[ReportStep] = []
    for step_id in STEP_ORDER:
        step = steps_by_id.get(step_id)
        if step is not None:
            ordered.append(step)
    for step in report.steps:
        if step.step_id not in STEP_ORDER:
            ordered.append(step)
    return ordered


def section_heading(section_num: int, step: ReportStep) -> str:
    label = WORD_COMMENT_STEP_LABEL_CN.get(step.step_id, step.step_id)
    num = (
        SECTION_NUM_CN[section_num - 1]
        if section_num <= len(SECTION_NUM_CN)
        else str(section_num)
    )
    return f"{num}、{label}"
