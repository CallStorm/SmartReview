# backend/tests/test_title_normalize.py
from __future__ import annotations

from app.services.title_normalize import normalize_title_for_match


def test_strips_chinese_ordinal_prefix():
    assert normalize_title_for_match("一、工程概况") == "工程概况"


def test_strips_arabic_dot_prefix():
    assert normalize_title_for_match("1.工程概况") == "工程概况"


def test_strips_arabic_chinese_comma_prefix():
    assert normalize_title_for_match("1、工程概况") == "工程概况"


def test_strips_nested_numeric_prefix():
    assert normalize_title_for_match("1.1 概述") == "概述"


def test_strips_paren_chinese_ordinal():
    assert normalize_title_for_match("(一)总则") == "总则"


def test_strips_chapter_prefix():
    assert normalize_title_for_match("第一章 总则") == "总则"


def test_strips_section_prefix():
    assert normalize_title_for_match("第1节 总则") == "总则"


def test_fullwidth_to_halfwidth():
    assert normalize_title_for_match("１．工程概况") == "工程概况"


def test_strips_trailing_punct():
    assert normalize_title_for_match("工程概况。") == "工程概况"
    assert normalize_title_for_match("工程概况：") == "工程概况"


def test_collapses_whitespace():
    assert normalize_title_for_match("  工程   概况  ") == "工程 概况"


def test_idempotent():
    once = normalize_title_for_match("一、工程概况。")
    twice = normalize_title_for_match(once)
    assert once == twice == "工程概况"
