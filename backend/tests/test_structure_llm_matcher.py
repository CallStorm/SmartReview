"""Tests for structure LLM matcher helpers."""

from __future__ import annotations

from app.services.structure_llm_matcher import _build_prompt, _parse_llm_pairs


def test_parse_llm_pairs_valid():
    raw = [
        {"template_title": "工程概况", "user_title": "1.工程概况", "confidence": 0.9, "matched": True},
        {"template_title": "材料", "user_title": None, "confidence": 0.1, "matched": False},
    ]
    out = _parse_llm_pairs(raw, ["工程概况", "材料"], ["1.工程概况"])
    assert len(out) == 2
    by_t = {p["template_title"]: p for p in out}
    assert by_t["工程概况"]["matched"] is True
    assert by_t["工程概况"]["user_title"] == "1.工程概况"
    assert by_t["材料"]["matched"] is False
    assert by_t["材料"]["user_title"] is None


def test_parse_llm_pairs_clamps_confidence():
    raw = [
        {"template_title": "A", "user_title": "a", "confidence": 1.5, "matched": True},
    ]
    out = _parse_llm_pairs(raw, ["A"], ["a"])
    assert out[0]["confidence"] == 1.0


def test_build_prompt_contains_both_lists():
    p = _build_prompt(["工程概况", "材料"], ["1.工程概况"])
    assert "工程概况" in p
    assert "1.工程概况" in p
    assert "JSON" in p
