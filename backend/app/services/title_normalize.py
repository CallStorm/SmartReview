# backend/app/services/title_normalize.py
"""Title normalization for fuzzy structure matching.

Strips leading ordinals/numbering, normalizes fullwidth->halfwidth,
removes trailing punctuation, and collapses whitespace. Used only by
fuzzy matching; exact matching continues to use tree_align.norm_title.
"""

from __future__ import annotations

import re
import unicodedata

# Leading ordinal/numbering forms:
#   一、 1. 1、 1.1 (一) 第一章 第1节 1)
# Numeric prefixes split into two branches so that a trailing terminator
# (./、/)) is required for a plain number (1./1、/1)) but optional for a
# nested dotted number (1.1/1.1.1). This strips "1.1 概述" without also
# stripping a bare leading number like "2024" in "2024年度审计报告".
_LEADING_PREFIX_RE = re.compile(
    r"""^\s*(?:
        第[零一二三四五六七八九十百千0-9]+[章节篇部条]   # 第一章 / 第1节
      | [\(（][零一二三四五六七八九十0-9]+[\)）]          # (一) / (1)
      | [0-9]+(?:[\.][0-9]+)+[\.、\)]?                  # 1.1 / 1.1.1 (nested; terminator optional)
      | [0-9]+[\.、\)]                                  # 1. / 1、 / 1) (plain; terminator required)
      | [零一二三四五六七八九十百千]+\、                 # 一、
    )\s*""",
    re.VERBOSE,
)

_TRAILING_PUNCT_RE = re.compile(r"[。：:，,；;\s]+$")


def _fullwidth_to_halfwidth(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def normalize_title_for_match(title: str) -> str:
    text = _fullwidth_to_halfwidth(title or "")
    text = _LEADING_PREFIX_RE.sub("", text)
    text = _TRAILING_PUNCT_RE.sub("", text)
    text = " ".join(text.split())
    return text.strip()
