"""内容审核 checks[] 逐项判定归一化（_normalize_content_checks）单测。"""

from __future__ import annotations

from app.schemas.review_report import ReportStep
from app.services.review_pipeline import _normalize_content_checks

ITEMS = [
    {"id": "n20-1", "text": "主材进场质量检查标准"},
    {"id": "n20-2", "text": "各阶段检查节点"},
]


def test_fail_becomes_issue_with_check_item_trace():
    data = {
        "passed": False,
        "summary": "发现 1 条",
        "checks": [
            {"item_id": "n20-1", "verdict": "fail", "severity": "error",
             "message": "未给出尺寸允许偏差", "evidence": "正文仅写实测尺寸",
             "related": {"fix": "补充允许偏差", "suggestions": ["列出偏差表"]}},
            {"item_id": "n20-2", "verdict": "pass", "evidence": "各阶段检查节点已列明"},
        ],
    }
    step, logs = _normalize_content_checks("content", data, {"template_node_id": "n20"}, ITEMS)
    assert isinstance(step, ReportStep)
    assert step.passed is False
    assert len(step.issues) == 1
    issue = step.issues[0]
    assert issue.related["check_item_id"] == "n20-1"
    assert issue.related["check_item"] == "主材进场质量检查标准"
    assert logs == []


def test_unknown_item_id_dropped():
    data = {"checks": [
        {"item_id": "n99-9", "verdict": "fail", "message": "越权问题"},
        {"item_id": "n20-1", "verdict": "pass"},
        {"item_id": "n20-2", "verdict": "pass"},
    ]}
    step, logs = _normalize_content_checks("content", data, {}, ITEMS)
    assert step is not None
    assert step.issues == []
    assert step.passed is True
    assert any("不在清单内" in msg for _, msg in logs)


def test_duplicate_item_keeps_first_only():
    data = {"checks": [
        {"item_id": "n20-1", "verdict": "fail", "severity": "warning", "message": "第一条"},
        {"item_id": "n20-1", "verdict": "fail", "severity": "error", "message": "第二条"},
        {"item_id": "n20-2", "verdict": "pass"},
    ]}
    step, logs = _normalize_content_checks("content", data, {}, ITEMS)
    assert len(step.issues) == 1
    assert step.issues[0].message == "第一条"
    assert any("重复" in msg for _, msg in logs)


def test_missing_items_logged():
    data = {"checks": [{"item_id": "n20-1", "verdict": "pass"}]}
    step, logs = _normalize_content_checks("content", data, {}, ITEMS)
    assert step.passed is True
    assert any("漏判" in msg and "n20-2" in msg for _, msg in logs)


def test_legacy_issues_shape_returns_none_for_fallback():
    data = {"passed": False, "issues": [{"severity": "error", "message": "x"}]}
    step, logs = _normalize_content_checks("content", data, {}, ITEMS)
    assert step is None
    assert any("降级" in msg for _, msg in logs)


def test_na_and_bad_severity_handling():
    data = {"checks": [
        {"item_id": "n20-1", "verdict": "na"},
        {"item_id": "n20-2", "verdict": "FAIL", "severity": "critical", "message": ""},
    ]}
    step, logs = _normalize_content_checks("content", data, {}, ITEMS)
    assert len(step.issues) == 1
    issue = step.issues[0]
    # verdict 大小写不敏感；非法 severity 回落 error；空 message 回退检查项原文
    assert issue.severity == "error"
    assert "n20-2" in issue.message


def test_pass_without_evidence_logged():
    data = {"checks": [
        {"item_id": "n20-1", "verdict": "pass"},  # 无引文
        {"item_id": "n20-2", "verdict": "pass", "evidence": "正文引用"},
    ]}
    step, logs = _normalize_content_checks("content", data, {}, ITEMS)
    assert step.passed is True
    assert any("未附原文引文" in msg and "n20-1" in msg for _, msg in logs)
    assert not any("n20-2" in msg for _, msg in logs)
