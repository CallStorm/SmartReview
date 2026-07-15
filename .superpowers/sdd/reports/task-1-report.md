# Task 1 Report: 标题归一化纯函数 (Title Normalization Pure Function)

## Status: DONE_WITH_CONCERNS

## What was implemented

A standalone pure-function module that normalizes section titles for later
fuzzy structure matching. The function `normalize_title_for_match(title: str)
-> str` performs four transforms, in order:

1. **Fullwidth → halfwidth** via `unicodedata.normalize("NFKC", ...)` (handles
   `１．` → `1.`, fullwidth colon `：` → `:`, fullwidth digits, etc.).
2. **Strip leading ordinal/numbering prefix** via a compiled VERBOSE regex
   covering: `第N章/节/篇/部/条`, `(一)/(1)`, nested dotted numbers `1.1`,
   plain terminated numbers `1./1、/1)`, and Chinese ordinals `一、`.
3. **Strip trailing punctuation** (`。：:，,；;` and trailing whitespace).
4. **Collapse whitespace** — `" ".join(text.split())` — then strip.

The function is pure (no I/O, no globals), handles `None`/empty via
`title or ""`, and is idempotent (verified by test).

## Files changed

- **Created** `backend/app/services/title_normalize.py` (44 lines) — the
  `normalize_title_for_match` pure function + helpers.
- **Created** `backend/tests/test_title_normalize.py` (50 lines) — 11 tests,
  transcribed verbatim from the brief.
- No other files touched. No dependencies on other tasks.

## TDD evidence

### RED (test written first, implementation absent)

Command:
```
cd backend && python -m pytest tests/test_title_normalize.py -v
```
Output (tail):
```
collected 0 items / 1 error
ERROR collecting tests/test_title_normalize.py
ImportError while importing test module '...test_title_normalize.py'.
tests\test_title_normalize.py:4: in <module>
    from app.services.title_normalize import normalize_title_for_match
E   ModuleNotFoundError: No module named 'app.services.title_normalize'
1 error in 0.20s
```
RED confirmed — fails with `ModuleNotFoundError` exactly as the brief expected.

### GREEN (implementation written, all tests pass)

Command:
```
cd backend && python -m pytest tests/test_title_normalize.py -v
```
Output:
```
collected 11 items
tests/test_title_normalize.py::test_strips_chinese_ordinal_prefix PASSED [  9%]
tests/test_title_normalize.py::test_strips_arabic_dot_prefix PASSED      [ 18%]
tests/test_title_normalize.py::test_strips_arabic_chinese_comma_prefix PASSED [ 27%]
tests/test_title_normalize.py::test_strips_nested_numeric_prefix PASSED  [ 36%]
tests/test_title_normalize.py::test_strips_paren_chinese_ordinal PASSED  [ 45%]
tests/test_title_normalize.py::test_strips_chapter_prefix PASSED         [ 54%]
tests/test_title_normalize.py::test_strips_section_prefix PASSED         [ 63%]
tests/test_title_normalize.py::test_fullwidth_to_halfwidth PASSED        [ 72%]
tests/test_title_normalize.py::test_strips_trailing_punct PASSED         [ 81%]
tests/test_title_normalize.py::test_collapses_whitespace PASSED          [ 90%]
tests/test_title_normalize.py::test_idempotent PASSED                    [100%]
11 passed in 0.02s
```
GREEN confirmed — 11/11 passing, output pristine (no warnings, no skips).

### Regression check (full backend suite)
```
cd backend && python -m pytest tests/ -q
```
Output: `26 passed in 1.17s` (15 pre-existing + 11 new). No regressions.

## Commit

- SHA: `d9ec8f5`
- Subject: `feat: add title normalization helper for fuzzy structure matching`
- Branch: `feat/fuzzy-structure-matching` (not on `main`)
- Files: `backend/app/services/title_normalize.py`, `backend/tests/test_title_normalize.py`

## Self-review

### Completeness
- [x] `normalize_title_for_match(title: str) -> str` produced, matching the
      specified interface.
- [x] Both files created at the exact paths in the brief.
- [x] All 11 tests pass; full suite green; no other files touched.

### Quality
- Module is standalone (stdlib only: `re`, `unicodedata`), pure, documented.
- Regex uses `re.VERBOSE` with per-branch comments for readability.
- `title or ""` guards `None` input defensively.

### YAGNI
- Did NOT add bare-number stripping (e.g. `3 设计原则`) — untested and would
  harmfully strip years/quantities from real titles. Added only the capability
  the tests require.
- Did NOT add options/configuration, logging, or coupling to other modules.

### Testing
- Tests cover every form listed in the brief (Chinese/Arabic ordinals, nested
  numerics, parenthesized ordinals, chapter/section prefixes, fullwidth,
  trailing punct, whitespace, idempotence).
- RED → GREEN cycle followed and evidenced above.

## Concerns

### 1. Brief code defect — required a deviation from "exact code" (main concern)

The brief's provided implementation regex for numeric prefixes was:
```
[0-9]+(?:[\.][0-9]+)*[\.、\)]
```
This **does not pass the brief's own test** `test_strips_nested_numeric_prefix`
(`"1.1 概述"` → expected `"概述"`). The regex requires a trailing terminator
(`.`, `、`, or `)`) after the final digit. For `"1.1 概述"` there is no
terminator after the second `1` (just a space), so the engine backtracks and
matches only `1.` (first digit + dot-as-terminator), leaving `"1 概述"`.

The brief's comment itself lists `1.1` as a case to handle, so this is an
internal inconsistency in the brief (test ≠ implementation).

**Fix applied (minimal, capability-scoped):** split the numeric alternative
into two branches so a trailing terminator is *required* for a plain number
but *optional* for a nested dotted number:
```
[0-9]+(?:[\.][0-9]+)+[\.、\)]?   # 1.1 / 1.1.1 (nested; terminator optional)
[0-9]+[\.、\)]                   # 1. / 1、 / 1) (plain; terminator required)
```
This was chosen over the one-character fix (`[\.、\)]?` on the original
single branch) because the latter would also strip *bare* leading numbers
(e.g. `2024` from `"2024年度审计报告"`), adding untested and harmful
behavior — a YAGNI violation. The two-branch fix adds **only** the `1.1`
capability the test requires and preserves the original design's safety
(no bare-number stripping). All 11 tests pass; the full suite is green.

This is a deviation from the brief's literal implementation code, made
necessary by the hard requirement that all tests pass.

### 2. Untested edge cases (by design, flagging for the downstream task)
- Bare leading numbers (`3 设计原则`, `2024年度审计报告`) are **not** stripped.
  This is intentional (matches original design intent) but the later
  fuzzy-matching task should confirm this is acceptable for real document
  titles; if bare-number stripping is needed, add it with a test.
- NFKC normalization is broad (affects more than digits/punctuation). It is
  desirable here and tested, but worth noting it could transform unexpected
  characters in pathological inputs.
- Whitespace collapse replaces any internal whitespace run with a single
  space; titles with deliberate multi-space formatting lose that. Acceptable
  for matching, not for display.
