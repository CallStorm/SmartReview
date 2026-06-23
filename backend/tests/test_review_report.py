from __future__ import annotations

from app.schemas.review_report import ReportStep, ReviewReportV1


def test_report_step_has_default_empty_mappings():
    step = ReportStep(step_id="structure", passed=True)
    assert step.mappings == []


def test_report_step_accepts_mappings():
    step = ReportStep(
        step_id="structure",
        passed=True,
        mappings=[{"template_node_id": "n1", "match_method": "exact"}],
    )
    assert step.mappings[0]["match_method"] == "exact"


def test_report_dump_includes_mappings():
    step = ReportStep(step_id="structure", passed=True, mappings=[{"template_node_id": "n1"}])
    report = ReviewReportV1(steps=[step])
    data = report.model_dump(mode="json")
    assert data["steps"][0]["mappings"] == [{"template_node_id": "n1"}]
