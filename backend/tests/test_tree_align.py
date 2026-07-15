"""Tests for template/user document tree alignment (structure review)."""

from __future__ import annotations

from app.services.tree_align import align_template_user_trees


def _node(
    node_id: str,
    title: str,
    *,
    hpi: int | None = None,
    children: list[dict] | None = None,
) -> dict:
    n: dict = {"id": node_id, "title": title, "children": children or []}
    if hpi is not None:
        n["heading_para_index"] = hpi
    return n


def _issue_kinds(issues: list[dict]) -> list[str]:
    return [str(i.get("kind") or "") for i in issues]


def test_extra_section_between_template_sections_passes():
    template = [
        _node("t1", "A", children=[
            _node("t2", "B"),
            _node("t3", "C"),
        ]),
    ]
    user = [
        _node("u1", "A", hpi=0, children=[
            _node("u2", "附录", hpi=1),
            _node("u3", "B", hpi=2),
            _node("u4", "C", hpi=3),
        ]),
    ]

    mapping, issues, _records = align_template_user_trees(template, user)

    assert issues == []
    assert set(mapping.keys()) == {"t1", "t2", "t3"}


def test_trailing_extra_sections_passes():
    template = [
        _node("t1", "A"),
        _node("t2", "B"),
    ]
    user = [
        _node("u1", "A", hpi=0),
        _node("u2", "B", hpi=1),
        _node("u3", "附录", hpi=2),
    ]

    mapping, issues, _records = align_template_user_trees(template, user)

    assert issues == []
    assert set(mapping.keys()) == {"t1", "t2"}


def test_missing_template_section_fails():
    template = [
        _node("t1", "A"),
        _node("t2", "B"),
        _node("t3", "C"),
    ]
    user = [
        _node("u1", "A", hpi=0),
        _node("u2", "C", hpi=1),
    ]

    _, issues, _records = align_template_user_trees(template, user)

    assert _issue_kinds(issues) == ["missing_section"]
    assert "B" in issues[0]["message"]


def test_reversed_template_order_passes():
    template = [
        _node("t1", "A"),
        _node("t2", "B"),
        _node("t3", "C"),
    ]
    user = [
        _node("u1", "A", hpi=0),
        _node("u2", "C", hpi=1),
        _node("u3", "B", hpi=2),
    ]

    mapping, issues, _records = align_template_user_trees(template, user)

    assert issues == []
    assert set(mapping.keys()) == {"t1", "t2", "t3"}


def test_deeper_user_headings_pruned_no_extra_issues():
    template = [
        _node("t1", "A", children=[
            _node("t2", "B"),
        ]),
    ]
    user = [
        _node("u1", "A", hpi=0, children=[
            _node("u2", "B", hpi=1, children=[
                _node("u3", "Deep", hpi=2),
            ]),
        ]),
    ]

    mapping, issues, _records = align_template_user_trees(template, user)

    assert issues == []
    assert set(mapping.keys()) == {"t1", "t2"}


def test_fuzzy_normalized_matches_different_ordinal():
    template = [
        _node("t1", "一、工程概况", children=[_node("t2", "1.模板支撑体系")]),
    ]
    user = [
        _node("u1", "1.工程概况", hpi=0, children=[_node("u2", "一、模板支撑体系", hpi=1)]),
    ]
    mapping, issues, records = align_template_user_trees(
        template, user, match_mode="fuzzy"
    )
    assert issues == []
    assert set(mapping.keys()) == {"t1", "t2"}
    methods = {r["template_node_id"]: r["match_method"] for r in records}
    assert methods["t1"] == "normalized"
    assert methods["t2"] == "normalized"


def test_fuzzy_llm_matcher_handles_semantic_rewrite():
    template = [_node("t1", "施工管理及作业人员配备")]
    user = [_node("u1", "现场管理与人员配置", hpi=0)]

    def fake_matcher(t_titles, u_titles):
        return [
            {
                "template_title": t_titles[0],
                "user_title": u_titles[0],
                "confidence": 0.9,
                "matched": True,
            }
        ]

    mapping, issues, records = align_template_user_trees(
        template, user, match_mode="fuzzy", llm_matcher=fake_matcher
    )
    assert issues == []
    assert "t1" in mapping
    rec = next(r for r in records if r["template_node_id"] == "t1")
    assert rec["match_method"] == "semantic"
    assert rec["confidence"] == 0.9
    assert rec["low_confidence"] is False


def test_fuzzy_llm_unmatched_reports_missing():
    template = [
        _node("t1", "工程概况"),
        _node("t2", "完全不存在的东西"),
    ]
    user = [_node("u1", "1.工程概况", hpi=0)]

    def fake_matcher(t_titles, u_titles):
        return [
            {"template_title": "工程概况", "user_title": "1.工程概况", "confidence": 0.95, "matched": True},
            {"template_title": "完全不存在的东西", "user_title": None, "confidence": 0.1, "matched": False},
        ]

    _, issues, _ = align_template_user_trees(
        template, user, match_mode="fuzzy", llm_matcher=fake_matcher
    )
    assert _issue_kinds(issues) == ["missing_section"]


def test_fuzzy_low_confidence_still_maps_not_missing():
    template = [_node("t1", "施工管理及作业人员配备")]
    user = [_node("u1", "现场管理", hpi=0)]

    def fake_matcher(t_titles, u_titles):
        return [
            {"template_title": t_titles[0], "user_title": u_titles[0], "confidence": 0.4, "matched": True}
        ]

    mapping, issues, records = align_template_user_trees(
        template, user, match_mode="fuzzy", llm_matcher=fake_matcher
    )
    assert issues == []
    assert "t1" in mapping
    rec = next(r for r in records if r["template_node_id"] == "t1")
    assert rec["match_method"] == "semantic"
    assert rec["low_confidence"] is True


def test_fuzzy_extra_section_is_info():
    template = [_node("t1", "工程概况")]
    user = [
        _node("u1", "1.工程概况", hpi=0),
        _node("u2", "附录", hpi=1),
    ]
    _, issues, _ = align_template_user_trees(template, user, match_mode="fuzzy")
    kinds = _issue_kinds(issues)
    assert "extra_section" in kinds
    assert "missing_section" not in kinds


def test_fuzzy_one_to_one_conflict_higher_confidence_wins():
    template = [
        _node("t1", "施工管理及作业人员配备"),
        _node("t2", "材料管理"),
    ]
    user = [_node("u1", "现场管理与人员配置", hpi=0)]

    def fake_matcher(t_titles, u_titles):
        return [
            {"template_title": t_titles[0], "user_title": u_titles[0], "confidence": 0.9, "matched": True},
            {"template_title": t_titles[1], "user_title": u_titles[0], "confidence": 0.5, "matched": True},
        ]

    mapping, issues, _records = align_template_user_trees(
        template, user, match_mode="fuzzy", llm_matcher=fake_matcher
    )
    assert "t1" in mapping
    assert "t2" not in mapping
    assert "missing_section" in _issue_kinds(issues)


def test_exact_mode_unchanged_three_return_values():
    template = [_node("t1", "A"), _node("t2", "B")]
    user = [
        _node("u1", "A", hpi=0),
        _node("u2", "B", hpi=1),
        _node("u3", "附录", hpi=2),
    ]
    mapping, issues, records = align_template_user_trees(template, user, match_mode="exact")
    assert issues == []
    assert set(mapping.keys()) == {"t1", "t2"}
    methods = {r["template_node_id"]: r["match_method"] for r in records}
    assert methods == {"t1": "exact", "t2": "exact"}
