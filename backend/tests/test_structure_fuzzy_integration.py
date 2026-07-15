"""Fuzzy structure matching end-to-end integration tests."""

from __future__ import annotations

from app.schemas.review_report import ReportStep
from app.services.review_pipeline import _structure_issues_to_report
from app.services.tree_align import align_template_user_trees


def _node(node_id, title, *, hpi=None, children=None):
    n = {"id": node_id, "title": title, "children": children or []}
    if hpi is not None:
        n["heading_para_index"] = hpi
    return n


def test_fuzzy_pipeline_integration_normalized_match():
    template = [
        _node("t1", "一、工程概况", children=[_node("t2", "1.模板支撑体系")]),
    ]
    user = [
        _node("u1", "1.工程概况", hpi=0, children=[_node("u2", "一、模板支撑体系", hpi=1)]),
    ]
    mapping, issues, records = align_template_user_trees(
        template, user, match_mode="fuzzy", llm_matcher=None
    )
    step: ReportStep = _structure_issues_to_report(
        issues, match_records=records, match_mode="fuzzy"
    )
    assert step.passed is True
    assert len(step.mappings) == 2
    methods = {m["match_method"] for m in step.mappings}
    assert methods == {"normalized"}
    assert "normalized" in step.summary
    assert "t1" in mapping
    assert "t2" in mapping


def test_fuzzy_pipeline_integration_missing_fails_fast_data():
    template = [_node("t1", "工程概况"), _node("t2", "材料管理")]
    user = [_node("u1", "1.工程概况", hpi=0)]
    mapping, issues, records = align_template_user_trees(
        template, user, match_mode="fuzzy", llm_matcher=None
    )
    step = _structure_issues_to_report(issues, match_records=records, match_mode="fuzzy")
    assert step.passed is False
    assert any(i.related.get("kind") == "missing_section" for i in step.issues if i.related)
    missing_records = [m for m in step.mappings if m["match_method"] == "missing"]
    assert len(missing_records) == 1
    assert "t2" not in mapping
