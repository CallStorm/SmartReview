"""AI 测评（确定性体检层）。

对一次已完成的审核任务做程序化体检，不调用 LLM：

1. 证据引文存在性：每个 issue 的 evidence 必须能在文档原文中找到
   （归一化空白后子串匹配），找不到说明模型幻觉/引文失真。
2. 溯源性：issue.related.check_item_id 必须是有效编号（内容审核步骤）。
3. 日志体检：漏判检查项、pass 未附引证、清单外输出、降级解析
   （从 review_log 的 WARNING 行解析，这些只存在于日志里）。
4. 统计：各级别问题数、各步骤/节点问题密度、缓存命中数。

输出 JSON 结构供前端「AI 测评」弹窗渲染；对抗测评（LLM 二次评审）
见 review_adversarial.py，与本层解耦。
"""

from __future__ import annotations

import json
import re
from io import BytesIO
from typing import Any

from sqlalchemy.orm import Session

from app.models import SchemeReviewTask, SchemeTemplate
from app.services import minio_storage
from app.services.word_parser import parse_docx_to_tree

# review_log 中 WARNING 行的匹配模式（与 review_pipeline 中的措辞保持一致）
_RE_MISSING = re.compile(r"模型漏判 (\d+) 个检查项: ([\w,\-]+)")
_RE_PASS_NO_EV = re.compile(r"(\d+) 个检查项判 pass 但未附原文引文（[^）]*）: ([\w,\-]+)")
_RE_DROPPED = re.compile(r"输出的检查项 (\S*) 不在清单内，已丢弃")
_RE_FALLBACK = re.compile(r"模型未按检查项清单输出 checks，降级为 issues 解析")
_RE_CACHE_HIT = re.compile(r"节点命中结果缓存")

_WS_RE = re.compile(r"\s+")

# 引文归一化时统一的全半角引号（模型常混用）
_QUOTE_MAP = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})

# 描述式引文的分片边界：evidence 常是“当前章节表格中“工种”列为“架子工””这类
# 复合描述而非逐字引用，按标点/引号切成片段，任一片段能在原文找到即视为可对上。
_FRAG_SPLIT_RE = re.compile(r'[，。；、：:|"\'（）()\[\]【】《》\s]+')
_MIN_FRAGMENT_LEN = 3


def _fragments(text: str) -> list[str]:
    normalized = (text or "").translate(_QUOTE_MAP)
    return [
        f
        for f in (_norm_text(x) for x in _FRAG_SPLIT_RE.split(normalized))
        if len(f) >= _MIN_FRAGMENT_LEN
    ]


def _norm_text(s: str) -> str:
    return _WS_RE.sub("", (s or "").translate(_QUOTE_MAP))


def _collect_tree_text(nodes: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for n in nodes:
        content = n.get("content")
        if isinstance(content, list):
            out.extend(str(p) for p in content if p)
        out.extend(_collect_tree_text(n.get("children") or []))
    return out


def _load_doc_text(task: SchemeReviewTask) -> str:
    raw = minio_storage.get_object_bytes(task.object_key)
    tree = parse_docx_to_tree(BytesIO(raw))
    return "\n".join(_collect_tree_text(tree.get("nodes") or []))


def _parse_log_warnings(log: str) -> dict[str, Any]:
    missing_ids: list[str] = []
    pass_no_evidence_ids: list[str] = []
    dropped: list[str] = []
    fallback_steps: list[str] = []
    cache_hits = 0
    for line in log.splitlines():
        if "WARNING" in line or "warning" in line:
            m = _RE_MISSING.search(line)
            if m:
                missing_ids.extend(x for x in m.group(2).split(",") if x)
            m = _RE_PASS_NO_EV.search(line)
            if m:
                pass_no_evidence_ids.extend(x for x in m.group(2).split(",") if x)
            m = _RE_DROPPED.search(line)
            if m:
                dropped.append(m.group(1))
            if _RE_FALLBACK.search(line):
                # 行格式: [ts] WARNING content 模型未按检查项清单输出...
                fallback_steps.append(line.split("WARNING")[-1].strip().split()[0])
        elif _RE_CACHE_HIT.search(line):
            cache_hits += 1
    return {
        "missing_verdicts": missing_ids,
        "pass_without_evidence": pass_no_evidence_ids,
        "out_of_checklist": dropped,
        "fallback_parse_steps": fallback_steps,
        "cache_hits": cache_hits,
    }


def run_selfcheck(db: Session, task: SchemeReviewTask) -> dict[str, Any]:
    """执行确定性体检，返回报告 dict。"""
    raw = task.review_result_json
    report = json.loads(raw) if isinstance(raw, str) else (raw or {})
    steps = report.get("steps") or []

    severity_counts = {"error": 0, "warning": 0, "info": 0}
    step_stats: list[dict[str, Any]] = []
    node_stats: dict[str, int] = {}
    evidence_missing: list[dict[str, str]] = []
    untraceable: list[dict[str, str]] = []
    total_issues = 0

    try:
        doc_text = _norm_text(_load_doc_text(task))
    except Exception as e:
        doc_text = ""
        doc_error = f"文档读取/解析失败，引文存在性检查跳过: {e!s}"
    else:
        doc_error = ""

    for s in steps:
        issues = s.get("issues") or []
        step_id = str(s.get("step_id") or "")
        step_sev = {"error": 0, "warning": 0, "info": 0}
        for i in issues:
            total_issues += 1
            sev = str(i.get("severity") or "info")
            if sev in step_sev:
                step_sev[sev] += 1
                severity_counts[sev] += 1
            anchor = (i.get("anchor") or {})
            node_id = str(anchor.get("template_node_id") or "")
            if node_id:
                node_stats[node_id] = node_stats.get(node_id, 0) + 1
            evidence = str(i.get("evidence") or "").strip()
            if doc_text and evidence:
                # 引文（或其任一片段）在原文中完全找不到 -> 幻觉/失真嫌疑
                if _norm_text(evidence) not in doc_text and not any(
                    f in doc_text for f in _fragments(evidence)
                ):
                    evidence_missing.append(
                        {
                            "step": step_id,
                            "node_id": node_id,
                            "evidence": evidence[:80],
                        }
                    )
            if step_id == "content":
                rel = i.get("related") or {}
                if not str(rel.get("check_item_id") or "").strip():
                    untraceable.append(
                        {
                            "step": step_id,
                            "node_id": node_id,
                            "message": str(i.get("message") or "")[:80],
                        }
                    )
        step_stats.append(
            {
                "step_id": step_id,
                "passed": bool(s.get("passed")),
                "issues": len(issues),
                "severity": step_sev,
            }
        )

    log_info = _parse_log_warnings(task.review_log or "")

    return {
        "task_id": task.id,
        "filename": task.original_filename,
        "total_issues": total_issues,
        "severity_counts": severity_counts,
        "step_stats": step_stats,
        "node_stats": dict(sorted(node_stats.items(), key=lambda kv: -kv[1])),
        "evidence_missing": evidence_missing,
        "untraceable_issues": untraceable,
        "doc_error": doc_error,
        **log_info,
        "verdicts": {
            # 体检结论：绿灯/黄灯/红灯
            "ok": not (
                evidence_missing
                or untraceable
                or log_info["missing_verdicts"]
                or log_info["pass_without_evidence"]
                or log_info["fallback_parse_steps"]
            ),
        },
    }
