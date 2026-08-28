"""上下文一致性 issue 归一化：对照章节缺省时回退到配置的 ref 路径。"""

from __future__ import annotations

from app.schemas.review_report import ReportIssue
from app.services.review_pipeline import _normalize_context_consistency_issue


def _issue(**related):
    return ReportIssue(severity="error", message="数量不一致", related=dict(related))


def test_fills_chapter_a_from_current_path():
    issue = _issue(chapter_a="旧名")
    _normalize_context_consistency_issue(
        issue,
        current_title_path=["六、施工管理", "3.特种作业人员"],
        ref_full_paths=["三、施工计划 > 3.劳动力计划"],
    )
    assert issue.related["chapter_a"] == "六、施工管理 > 3.特种作业人员"


def test_fills_chapter_b_when_llm_omits_single_ref():
    """任务 736：模型未回填 chapter_b 时，用唯一对照章节兜底。"""
    issue = _issue()  # no chapter_b
    _normalize_context_consistency_issue(
        issue,
        current_title_path=["六、施工管理及作业人员配备和分工", "3.特种作业人员"],
        ref_full_paths=["三、施工计划 > 3.劳动力计划"],
    )
    assert issue.related["chapter_b"] == "三、施工计划 > 3.劳动力计划"


def test_expands_short_chapter_b_to_full_ref_path():
    issue = _issue(chapter_b="3.劳动力计划")
    _normalize_context_consistency_issue(
        issue,
        current_title_path=["六、施工管理", "3.特种作业人员"],
        ref_full_paths=["三、施工计划 > 3.劳动力计划"],
    )
    assert issue.related["chapter_b"] == "三、施工计划 > 3.劳动力计划"


def test_multi_ref_picks_by_message_mention():
    issue = ReportIssue(
        severity="error",
        message="与对照章节劳动力计划中人数不一致",
        related={},
    )
    _normalize_context_consistency_issue(
        issue,
        current_title_path=["六、施工管理", "3.特种作业人员"],
        ref_full_paths=[
            "三、施工计划 > 2.材料与设备计划",
            "三、施工计划 > 3.劳动力计划",
        ],
    )
    assert issue.related["chapter_b"] == "三、施工计划 > 3.劳动力计划"


def test_multi_ref_joins_when_no_hint():
    issue = _issue()
    _normalize_context_consistency_issue(
        issue,
        current_title_path=["六、施工管理", "4.其他作业人员"],
        ref_full_paths=[
            "三、施工计划 > 2.材料与设备计划",
            "三、施工计划 > 3.劳动力计划",
        ],
    )
    assert "材料与设备计划" in issue.related["chapter_b"]
    assert "劳动力计划" in issue.related["chapter_b"]
