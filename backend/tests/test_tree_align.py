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

    mapping, issues = align_template_user_trees(template, user)

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

    mapping, issues = align_template_user_trees(template, user)

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

    _, issues = align_template_user_trees(template, user)

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

    mapping, issues = align_template_user_trees(template, user)

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

    mapping, issues = align_template_user_trees(template, user)

    assert issues == []
    assert set(mapping.keys()) == {"t1", "t2"}
