### Task 1: 标题归一化纯函数

**Files:**
- Create: `backend/app/services/title_normalize.py`
- Test: `backend/tests/test_title_normalize.py`

**Interfaces:**
- Produces: `normalize_title_for_match(title: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_title_normalize.py -v`
Expected: FAIL with ModuleNotFoundError / ImportError for `app.services.title_normalize`.

- [ ] **Step 3: Write minimal implementation**

```python
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
_LEADING_PREFIX_RE = re.compile(
    r"""^\s*(?:
        第[零一二三四五六七八九十百千0-9]+[章节篇部条]   # 第一章 / 第1节
      | [\(（][零一二三四五六七八九十0-9]+[\)）]          # (一) / (1)
      | [0-9]+(?:[\.][0-9]+)*[\.、\)]                   # 1. / 1.1 / 1、 / 1)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_title_normalize.py -v`
Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/title_normalize.py backend/tests/test_title_normalize.py
git commit -m "feat: add title normalization helper for fuzzy structure matching"
```

---

