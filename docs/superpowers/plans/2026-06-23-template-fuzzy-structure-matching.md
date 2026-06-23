# 模板结构匹配开关（精确 / 模糊语义）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为模板新增结构匹配模式开关（exact/fuzzy），fuzzy 模式下用「精确 → 归一化 → LLM 按层批量兜底」的同级递归匹配建立模板→用户章节映射，并在结构审核详情展示全量映射表；缺章节仍 fail-fast。

**Architecture:** 模板新增独立列 `structure_match_mode`（默认 exact）。新增 `title_normalize.py` 纯函数模块做标题归一化。`align_template_user_trees` 增强为接受 `match_mode` 与可注入 `llm_matcher`，返回 `(mapping, issues, match_records)`。`ReportStep` 新增可选 `mappings` 字段。前端 `StructureReviewDetail` 始终渲染映射表。

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / Alembic / Pydantic（后端）；React + TypeScript + Ant Design + @tanstack/react-query（前端）。后端测试用 pytest，前端用 `npm run build`/`tsc` 类型检查。

## Global Constraints

- 默认 `structure_match_mode="exact"`，既有模板与既有审核结果行为完全不变。
- 硬约束不变：缺章节报 `missing_section`(error) 并 fail-fast；低信心（<0.6）仍映射但标 `low_confidence`，不报错。
- 多余章节：fuzzy 模式下列为 `extra_section`(info)，不阻断；exact 模式不产出 extra_section（保持现状静默忽略）。
- LLM 按层批量调用；LLM 失败时该层剩余模板标题全部判 missing 并写 warning 日志。
- 复用现有 `app.services.llm.chat.chat_json_with_usage` 基础设施。
- 现有 `tree_align.norm_title`（仅折叠空白）保持不动；归一化仅用于 fuzzy 新路径。
- 低信心阈值 `SEMANTIC_LOW_CONFIDENCE_THRESHOLD = 0.6` 为模块常量。
- 后端测试运行命令：`cd backend && python -m pytest <path> -v`（仓库根用 `python -m pytest backend/tests/...`）。
- 前端类型检查：`cd frontend && npx tsc --noEmit`。

---

## File Structure

- **Create** `backend/app/services/title_normalize.py` — 标题归一化纯函数（fuzzy 匹配用）。
- **Create** `backend/tests/test_title_normalize.py` — 归一化单元测试。
- **Create** `backend/alembic/versions/022_template_structure_match_mode.py` — 加列迁移。
- **Modify** `backend/app/models/scheme_template.py` — 新增 `structure_match_mode` 列。
- **Modify** `backend/app/schemas/review_report.py` — `ReportStep` 新增 `mappings` 字段。
- **Modify** `backend/app/schemas/template.py` — 新增 `StructureMatchModeUpdate`；`TemplatePublic` 暴露 `structure_match_mode`。
- **Modify** `backend/app/api/templates.py` — 新增 PATCH 端点；`_template_public` 透传字段。
- **Modify** `backend/app/services/tree_align.py` — 增强 `align_template_user_trees`。
- **Modify** `backend/tests/test_tree_align.py` — fuzzy 用例 + exact 回归。
- **Create** `backend/app/services/structure_llm_matcher.py` — LLM 语义匹配器（注入到 align）。
- **Modify** `backend/app/services/review_pipeline.py` — 读取 mode、构造 matcher、消费 match_records。
- **Modify** `frontend/src/api/types.ts` — `TemplatePublic.structure_match_mode`、`ReportStep.mappings`、`StructureMatchMethod` 类型。
- **Modify** `frontend/src/components/ReviewWorkflowModal.tsx` — 新增结构匹配模式开关并保存。
- **Modify** `frontend/src/components/StructureReviewDetail.tsx` — 渲染映射表。

---

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

### Task 2: 模板模型与迁移加列

**Files:**
- Modify: `backend/app/models/scheme_template.py`
- Create: `backend/alembic/versions/022_template_structure_match_mode.py`

**Interfaces:**
- Produces: `SchemeTemplate.structure_match_mode: Mapped[str]`（默认 `"exact"`，取值 `"exact" | "fuzzy"`）。

- [ ] **Step 1: Add the column to the model**

修改 `backend/app/models/scheme_template.py`，在 `full_document_review_config` 字段后、`parsed_at` 之前新增：

```python
    structure_match_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="exact", default="exact"
    )
```

（`String` 已在文件顶部 import。）

- [ ] **Step 2: Create the alembic migration**

```python
# backend/alembic/versions/022_template_structure_match_mode.py
"""add structure_match_mode to templates

Revision ID: 022
Revises: 021
Create Date: 2026-06-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "templates",
        sa.Column(
            "structure_match_mode",
            sa.String(length=16),
            nullable=False,
            server_default="exact",
        ),
    )


def downgrade() -> None:
    op.drop_column("templates", "structure_match_mode")
```

- [ ] **Step 3: Verify migration is wired (head check)**

Run: `cd backend && python -m alembic heads`
Expected: a single head `022` (or `022 (...)`). If two heads appear, the `down_revision` is wrong — fix it.

- [ ] **Step 4: Run a fresh sqlite migration smoke test**

Run:
```bash
cd backend && rm -f /tmp/sr_test.db && SR_DATABASE_URL="sqlite:////tmp/sr_test.db" python -m alembic upgrade head
```
Expected: `Running upgrade 021 -> 022` printed, exit 0. (Uses an ephemeral sqlite file; the env may already bind `SR_DATABASE_URL` — if not, this still exercises migration DDL on a throwaway DB. If `SR_DATABASE_URL` is not honored, fall back to running `python -c "from alembic.config import Config; from alembic import command; command.upgrade(Config('alembic.ini'), 'head')"` against a throwaway URL set via `SQLALCHEMY_DATABASE_URL` env if the alembic env reads it; otherwise skip and rely on Step 3 + Task 11 integration.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/scheme_template.py backend/alembic/versions/022_template_structure_match_mode.py
git commit -m "feat: add structure_match_mode column to templates"
```

---

### Task 3: 报告 schema 加 mappings 字段

**Files:**
- Modify: `backend/app/schemas/review_report.py`
- Test: `backend/tests/test_review_report.py`（若不存在则创建）

**Interfaces:**
- Produces: `ReportStep.mappings: list[dict[str, Any]]`（默认空 list）。

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_review_report.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_review_report.py -v`
Expected: FAIL — `ReportStep` has no attribute `mappings`.

- [ ] **Step 3: Add the field**

修改 `backend/app/schemas/review_report.py` 的 `ReportStep`，在 `issues` 字段后新增：

```python
    mappings: list[dict[str, Any]] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_review_report.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/review_report.py backend/tests/test_review_report.py
git commit -m "feat: add mappings field to ReportStep for structure review"
```

---

### Task 4: 模板 schema 与 API 端点

**Files:**
- Modify: `backend/app/schemas/template.py`
- Modify: `backend/app/api/templates.py`
- Test: `backend/tests/test_templates_structure_match_mode.py`

**Interfaces:**
- Produces:
  - `StructureMatchModeUpdate(mode: Literal["exact","fuzzy"])`
  - `TemplatePublic.structure_match_mode: str`
  - `PATCH /scheme-types/{scheme_id}/template/structure-match-mode`（admin），返回 `TemplatePublic`。

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_templates_structure_match_mode.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine, SessionLocal
from app.models.scheme_template import SchemeTemplate
from app.models.scheme_type import SchemeType
from app.models.user import User, UserRole
from app.core.security import hash_password
from app.main import app, get_db


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_auth(client):
    db = SessionLocal()
    user = User(username="admin_smm", phone="13900000001", password_hash=hash_password("pw"), role=UserRole.admin)
    db.add(user)
    db.commit()
    db.close()
    resp = client.post("/auth/login", json={"username": "admin_smm", "password": "pw"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _ensure_scheme_template():
    db = SessionLocal()
    st = SchemeType(category="cat_smm", name="name_smm", remark=None)
    db.add(st)
    db.commit()
    db.refresh(st)
    tmpl = SchemeTemplate(
        scheme_type_id=st.id,
        minio_bucket="b",
        object_key="k",
        original_filename="t.docx",
        parsed_structure='{"nodes":[]}',
    )
    db.add(tmpl)
    db.commit()
    sid = st.id
    db.close()
    return sid


def test_patch_sets_fuzzy_mode(client, admin_auth):
    sid = _ensure_scheme_template()
    resp = client.patch(
        f"/scheme-types/{sid}/template/structure-match-mode",
        json={"mode": "fuzzy"},
        headers=admin_auth,
    )
    assert resp.status_code == 200
    assert resp.json()["structure_match_mode"] == "fuzzy"


def test_patch_rejects_invalid_mode(client, admin_auth):
    sid = _ensure_scheme_template()
    resp = client.patch(
        f"/scheme-types/{sid}/template/structure-match-mode",
        json={"mode": "weird"},
        headers=admin_auth,
    )
    assert resp.status_code == 422


def test_template_public_exposes_mode(client, admin_auth):
    sid = _ensure_scheme_template()
    resp = client.get(f"/scheme-types/{sid}/template", headers=admin_auth)
    assert resp.status_code == 200
    assert resp.json()["structure_match_mode"] in ("exact", "fuzzy")
```

Note: 登录端点路径与字段名以现有 `app/api` 中 auth 路由为准；若实际路径/字段不同（如 `/api/auth/login` 或 `phone` 登录），实现者需先 `grep -n "auth/login\|def login" backend/app/api` 核对后调整 fixture。测试目的仅是覆盖 PATCH 端点与 TemplatePublic 透传。

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_templates_structure_match_mode.py -v`
Expected: FAIL — 404 on PATCH route (route not defined) and 422/missing field.

- [ ] **Step 3: Add schema**

修改 `backend/app/schemas/template.py`：

顶部 import 补 `Literal`（已有 `Any`）：
```python
from typing import Any, Literal
```

在 `ReviewWorkflowUpdate` 之后新增：
```python
class StructureMatchModeUpdate(BaseModel):
    mode: Literal["exact", "fuzzy"]
```

修改 `TemplatePublic`，在 `full_document_review_config` 字段后新增：
```python
    structure_match_mode: str = "exact"
```

- [ ] **Step 4: Add API endpoint and wire _template_public**

修改 `backend/app/api/templates.py`：

import 处补 `StructureMatchModeUpdate`：
```python
from app.schemas.template import (
    DownloadUrlResponse,
    FullDocumentReviewConfigUpdate,
    ReviewWorkflowUpdate,
    StructureMatchModeUpdate,
    TemplatePublic,
    TemplateStructureUpdate,
    TemplateUploadResponse,
)
```

在 `_template_public` 中，构造 `TemplatePublic(...)` 时在 `full_document_review_config=full_doc,` 之后加：
```python
        structure_match_mode=t.structure_match_mode or "exact",
```

在 `update_template_full_document_review` 之后新增端点：
```python
@router.patch(
    "/scheme-types/{scheme_id}/template/structure-match-mode",
    response_model=TemplatePublic,
)
def update_template_structure_match_mode(
    scheme_id: int,
    body: StructureMatchModeUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> TemplatePublic:
    scheme = db.get(SchemeType, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="方案类型不存在")
    t = db.query(SchemeTemplate).filter(SchemeTemplate.scheme_type_id == scheme_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="尚未上传模版")
    t.structure_match_mode = body.mode
    db.commit()
    db.refresh(t)
    return _template_public(t)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_templates_structure_match_mode.py -v`
Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/template.py backend/app/api/templates.py backend/tests/test_templates_structure_match_mode.py
git commit -m "feat: add structure_match_mode template config and PATCH endpoint"
```

---

### Task 5: 增强 align_template_user_trees（exact + 归一化，不含 LLM）

本任务实现 `match_mode` 参数与归一化匹配、`match_records` 返回、`extra_section`(info)，LLM 路径通过可注入 `llm_matcher` 占位（None 时跳过）。LLM 匹配器实现在 Task 6，pipeline 注入在 Task 8。

**Files:**
- Modify: `backend/app/services/tree_align.py`
- Modify: `backend/tests/test_tree_align.py`

**Interfaces:**
- Produces:
  ```python
  def align_template_user_trees(
      template_nodes: list[dict[str, Any]],
      user_nodes: list[dict[str, Any]],
      *,
      match_mode: Literal["exact", "fuzzy"] = "exact",
      llm_matcher: Callable[[list[str], list[str]], list[dict[str, Any]]] | None = None,
  ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
      # returns (mapping, issues, match_records)
  ```
- `llm_matcher(template_titles: list[str], user_titles: list[str]) -> list[dict]`，每个 dict 形如
  `{"template_title": str, "user_title": str | None, "confidence": float, "matched": bool}`。
- `match_records` 每条：`{"template_node_id","template_title","title_path","user_title","heading_para_index","match_method","confidence","low_confidence"}`。
- `issues` 中 `extra_section` 项：`{"kind":"extra_section","message":...,"user_title":...,"heading_para_index":...,"title_path":...}`。

- [ ] **Step 1: Write the failing tests**

在 `backend/tests/test_tree_align.py` 顶部 import 补充：
```python
from app.services.title_normalize import normalize_title_for_match  # noqa: F401  (sanity)
```
并在文件末尾追加（保留现有测试不动）：

```python
def _node_fuzzy(node_id, title, *, hpi=None, children=None):
    return _node(node_id, title, hpi=hpi, children=children or [])


def test_fuzzy_normalized_matches_different_ordinal():
    template = [
        _node_fuzzy("t1", "一、工程概况", children=[_node_fuzzy("t2", "1.模板支撑体系")]),
    ]
    user = [
        _node_fuzzy("u1", "1.工程概况", hpi=0, children=[_node_fuzzy("u2", "一、模板支撑体系", hpi=1)]),
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
    template = [_node_fuzzy("t1", "施工管理及作业人员配备")]
    user = [_node_fuzzy("u1", "现场管理与人员配置", hpi=0)]

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
        _node_fuzzy("t1", "工程概况"),
        _node_fuzzy("t2", "完全不存在的东西"),
    ]
    user = [_node_fuzzy("u1", "1.工程概况", hpi=0)]

    def fake_matcher(t_titles, u_titles):
        # only first template title matches
        return [
            {"template_title": "工程概况", "user_title": "1.工程概况", "confidence": 0.95, "matched": True},
            {"template_title": "完全不存在的东西", "user_title": None, "confidence": 0.1, "matched": False},
        ]

    _, issues, _ = align_template_user_trees(
        template, user, match_mode="fuzzy", llm_matcher=fake_matcher
    )
    assert _issue_kinds(issues) == ["missing_section"]


def test_fuzzy_low_confidence_still_maps_not_missing():
    template = [_node_fuzzy("t1", "施工管理及作业人员配备")]
    user = [_node_fuzzy("u1", "现场管理", hpi=0)]

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
    template = [_node_fuzzy("t1", "工程概况")]
    user = [
        _node_fuzzy("u1", "1.工程概况", hpi=0),
        _node_fuzzy("u2", "附录", hpi=1),
    ]
    _, issues, _ = align_template_user_trees(template, user, match_mode="fuzzy")
    kinds = _issue_kinds(issues)
    assert "extra_section" in kinds
    # extra must not be missing_section
    assert "missing_section" not in kinds


def test_fuzzy_one_to_one_conflict_higher_confidence_wins():
    template = [
        _node_fuzzy("t1", "施工管理及作业人员配备"),
        _node_fuzzy("t2", "材料管理"),
    ]
    user = [_node_fuzzy("u1", "现场管理与人员配置", hpi=0)]

    def fake_matcher(t_titles, u_titles):
        return [
            {"template_title": t_titles[0], "user_title": u_titles[0], "confidence": 0.9, "matched": True},
            {"template_title": t_titles[1], "user_title": u_titles[0], "confidence": 0.5, "matched": True},
        ]

    mapping, issues, records = align_template_user_trees(
        template, user, match_mode="fuzzy", llm_matcher=fake_matcher
    )
    # t1 wins u1 (higher confidence); t2 has no user node -> missing
    assert "t1" in mapping
    assert "t2" not in mapping
    assert "missing_section" in _issue_kinds(issues)


def test_exact_mode_unchanged_three_return_values():
    # exact mode must still work with the new 3-tuple return and not emit extra_section
    template = [_node_fuzzy("t1", "A"), _node_fuzzy("t2", "B")]
    user = [
        _node_fuzzy("u1", "A", hpi=0),
        _node_fuzzy("u2", "B", hpi=1),
        _node_fuzzy("u3", "附录", hpi=2),  # extra, must be ignored in exact mode
    ]
    mapping, issues, records = align_template_user_trees(template, user, match_mode="exact")
    assert issues == []
    assert set(mapping.keys()) == {"t1", "t2"}
    methods = {r["template_node_id"]: r["match_method"] for r in records}
    assert methods == {"t1": "exact", "t2": "exact"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_tree_align.py -v`
Expected: existing 4 tests FAIL first (they unpack `mapping, issues = ...` — a 2-tuple — but the new return is a 3-tuple). This is expected; Step 3 rewrites the function, and the existing tests' unpacking must be updated to `mapping, issues, _records = align_template_user_trees(...)` in all 4 existing tests:
- `test_extra_section_between_template_sections_passes`
- `test_trailing_extra_sections_passes`
- `test_missing_template_section_fails`
- `test_reversed_template_order_passes`
- `test_deeper_user_headings_pruned_no_extra_issues`

(5 existing tests total — update each `mapping, issues = ...` line to `mapping, issues, _records = ...`.) The new tests also fail (no fuzzy behavior yet).

**Pre-Step 3 fix:** Before/while rewriting the function, update the 5 existing test call sites in `backend/tests/test_tree_align.py` to unpack three values (`mapping, issues, _records = ...`). `test_missing_template_section_fails` uses `_, issues = ...` → change to `_, issues, _records = ...`.

- [ ] **Step 3: Rewrite align_template_user_trees**

用以下内容**整体替换** `backend/app/services/tree_align.py` 中 `align_template_user_trees` 函数（保留文件顶部 `norm_title`、`title_path_str`、`_node_title`、`_template_max_depth`、`_prune_user_tree_to_depth`、`_index_nodes_by_heading_para` 不变）。新增模块顶部 import：

```python
from typing import Any, Callable, Literal
```
（替换原 `from typing import Any`。）

新增模块常量（紧跟 import 之后）：
```python
SEMANTIC_LOW_CONFIDENCE_THRESHOLD = 0.6
```

替换后的函数：

```python
def _record(
    *,
    tid: str,
    title: str,
    path: list[str],
    user_title: str | None,
    hpi: int | None,
    method: str,
    confidence: float | None = None,
    low_confidence: bool = False,
) -> dict[str, Any]:
    return {
        "template_node_id": tid,
        "template_title": title,
        "title_path": list(path),
        "user_title": user_title,
        "heading_para_index": hpi,
        "match_method": method,
        "confidence": confidence,
        "low_confidence": low_confidence,
    }


def _normalized_match(
    want: str,
    candidates: list[tuple[int, dict[str, Any]]],
) -> tuple[int | None, str]:
    """Exact-on-normalized match. Returns (candidate_index, method)."""
    from app.services.title_normalize import normalize_title_for_match

    want_n = normalize_title_for_match(want)
    for idx, uc in candidates:
        if normalize_title_for_match(_node_title(uc)) == want_n:
            return idx, "normalized"
    return None, "normalized"


def align_template_user_trees(
    template_nodes: list[dict[str, Any]],
    user_nodes: list[dict[str, Any]],
    *,
    match_mode: Literal["exact", "fuzzy"] = "exact",
    llm_matcher: Callable[[list[str], list[str]], list[dict[str, Any]]] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Returns (template_id -> user_node, structure_issues, match_records).

    match_mode:
      - exact (default): whitespace-normalized exact equality only; extra user
        sections silently ignored (backward compatible).
      - fuzzy: exact -> normalized -> LLM (via llm_matcher) per level; unmatched
        template sections become missing_section (error); extra user sections
        become extra_section (info).

    match_records: one entry per template node with match_method in
    exact|normalized|semantic|missing.
    """
    path_prefix: list[str] = []
    original_user_nodes = user_nodes
    max_depth = _template_max_depth(template_nodes)
    if max_depth > 0:
        user_nodes = _prune_user_tree_to_depth(user_nodes, max_depth)
    mapping: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    original_nodes_by_hpi: dict[int, dict[str, Any]] = {}
    _index_nodes_by_heading_para(original_user_nodes, original_nodes_by_hpi)

    def _map_user_node(tid: str, uc: dict[str, Any]) -> None:
        if not tid:
            return
        hpi = uc.get("heading_para_index")
        if isinstance(hpi, int) and hpi in original_nodes_by_hpi:
            mapping[tid] = original_nodes_by_hpi[hpi]
        else:
            mapping[tid] = uc

    def walk(
        t_children: list[dict[str, Any]],
        u_children: list[dict[str, Any]],
        path: list[str],
    ) -> None:
        used: set[int] = set()
        # stage 1: exact (whitespace) match
        pending_t: list[tuple[int, dict[str, Any]]] = []
        for tc in t_children:
            tid = str(tc.get("id") or "")
            want = _node_title(tc)
            found_j: int | None = None
            for j in range(len(u_children)):
                if j in used:
                    continue
                if _node_title(u_children[j]) == want:
                    found_j = j
                    break
            if found_j is not None:
                used.add(found_j)
                uc = u_children[found_j]
                _map_user_node(tid, uc)
                records.append(
                    _record(
                        tid=tid, title=want, path=path + [want],
                        user_title=str(uc.get("title") or ""),
                        hpi=uc.get("heading_para_index"),
                        method="exact",
                    )
                )
                _recurse(tc, uc, path + [want])
            else:
                pending_t.append((len(pending_t), tc))

        if match_mode != "fuzzy" or not pending_t:
            # exact mode: remaining template children are missing; no extra reporting.
            for _, tc in pending_t:
                tid = str(tc.get("id") or "")
                want = _node_title(tc)
                issues.append(
                    {"kind": "missing_section", "message": f"缺少章节：{want}",
                     "template_node_id": tid, "title_path": path + [want]}
                )
                records.append(
                    _record(tid=tid, title=want, path=path + [want],
                            user_title=None, hpi=None, method="missing")
                )
                _recurse(tc, None, path + [want])
            if match_mode == "fuzzy":
                _report_extras(u_children, used, path)
            return

        # stage 2: normalized match on pending
        still_pending: list[dict[str, Any]] = []
        for _, tc in pending_t:
            tid = str(tc.get("id") or "")
            want = _node_title(tc)
            cand = [(j, u_children[j]) for j in range(len(u_children)) if j not in used]
            idx, _ = _normalized_match(want, cand)
            if idx is not None:
                used.add(idx)
                uc = u_children[idx]
                _map_user_node(tid, uc)
                records.append(
                    _record(tid=tid, title=want, path=path + [want],
                            user_title=str(uc.get("title") or ""),
                            hpi=uc.get("heading_para_index"), method="normalized")
                )
                _recurse(tc, uc, path + [want])
            else:
                still_pending.append(tc)

        # stage 3: LLM match on still-pending vs remaining unused user nodes
        if still_pending:
            remaining = [(j, u_children[j]) for j in range(len(u_children)) if j not in used]
            llm_pairs: list[tuple[dict[str, Any], int | None, float, bool]] = []
            if llm_matcher is not None and remaining:
                t_titles = [str(tc.get("title") or "") for tc in still_pending]
                u_titles = [str(uc.get("title") or "") for _, uc in remaining]
                try:
                    raw = llm_matcher(t_titles, u_titles)
                except Exception:
                    raw = []
                llm_pairs = _resolve_llm_pairs(raw, still_pending, remaining, used)
            for tc in still_pending:
                tid = str(tc.get("id") or "")
                want = _node_title(tc)
                pair = next((p for p in llm_pairs if p[0] is tc), None)
                if pair is not None and pair[1] is not None:
                    uc = u_children[pair[1]]
                    _map_user_node(tid, uc)
                    conf = pair[2]
                    low = pair[2] is not None and pair[2] < SEMANTIC_LOW_CONFIDENCE_THRESHOLD
                    records.append(
                        _record(tid=tid, title=want, path=path + [want],
                                user_title=str(uc.get("title") or ""),
                                hpi=uc.get("heading_para_index"),
                                method="semantic", confidence=conf, low_confidence=low)
                    )
                    _recurse(tc, uc, path + [want])
                else:
                    issues.append(
                        {"kind": "missing_section", "message": f"缺少章节：{want}",
                         "template_node_id": tid, "title_path": path + [want]}
                    )
                    records.append(
                        _record(tid=tid, title=want, path=path + [want],
                                user_title=None, hpi=None, method="missing")
                    )
                    _recurse(tc, None, path + [want])

        _report_extras(u_children, used, path)

    def _recurse(tc: dict[str, Any], uc: dict[str, Any] | None, path: list[str]) -> None:
        next_t = tc.get("children") or []
        if not next_t:
            return
        if uc is None:
            # template children with no matched user node -> all missing
            for sub in next_t:
                sid = str(sub.get("id") or "")
                swant = _node_title(sub)
                issues.append(
                    {"kind": "missing_section", "message": f"缺少章节：{swant}",
                     "template_node_id": sid, "title_path": path + [swant]}
                )
                records.append(
                    _record(tid=sid, title=swant, path=path + [swant],
                            user_title=None, hpi=None, method="missing")
                )
                _recurse(sub, None, path + [swant])
        else:
            walk(next_t, uc.get("children") or [], path)

    def _report_extras(u_children: list[dict[str, Any]], used: set[int], path: list[str]) -> None:
        if match_mode != "fuzzy":
            return
        for j, uc in enumerate(u_children):
            if j in used:
                continue
            utitle = str(uc.get("title") or "")
            issues.append(
                {"kind": "extra_section", "message": f"多余章节：{utitle}",
                 "user_title": utitle, "heading_para_index": uc.get("heading_para_index"),
                 "title_path": path + [utitle]}
            )

    walk(template_nodes, user_nodes, path_prefix)
    return mapping, issues, records


def _resolve_llm_pairs(
    raw: list[dict[str, Any]],
    still_pending: list[dict[str, Any]],
    remaining: list[tuple[int, dict[str, Any]]],
    used: set[int],
) -> list[tuple[dict[str, Any], int | None, float, bool]]:
    """Enforce 1:1 from LLM output. Higher confidence wins on conflicts."""
    if not isinstance(raw, list):
        return []
    title_to_tc = {str(tc.get("title") or ""): tc for tc in still_pending}
    title_to_uj = {str(uc.get("title") or ""): j for j, uc in remaining}
    # collect candidate pairs with confidence
    candidates: dict[str, list[tuple[int, float, bool]]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        t_title = str(item.get("template_title") or "").strip()
        u_title = item.get("user_title")
        matched = bool(item.get("matched"))
        conf = item.get("confidence")
        try:
            conf_f = float(conf) if conf is not None else 0.0
        except (TypeError, ValueError):
            conf_f = 0.0
        tc = title_to_tc.get(t_title)
        if tc is None or not matched or not isinstance(u_title, str):
            continue
        uj = title_to_uj.get(u_title.strip())
        if uj is None or uj in used:
            continue
        candidates.setdefault(t_title, []).append((uj, conf_f, True))

    out: list[tuple[dict[str, Any], int | None, float, bool]] = []
    assigned_u: set[int] = set()
    # order template nodes by their best available confidence desc to resolve conflicts
    order = sorted(
        still_pending,
        key=lambda tc: max((c for _, c, _ in candidates.get(str(tc.get("title") or ""), [])), default=0.0),
        reverse=True,
    )
    for tc in order:
        t_title = str(tc.get("title") or "")
        cands = [(uj, c, m) for uj, c, m in candidates.get(t_title, []) if uj not in assigned_u]
        if not cands:
            out.append((tc, None, 0.0, False))
            continue
        uj, c, m = max(cands, key=lambda x: x[1])
        assigned_u.add(uj)
        out.append((tc, uj, c, m))
    return out
```

注意：`_recurse` 中 exact 模式的 missing 子树处理会与原行为一致（原 `walk` 在 found_j is None 时 `continue` 不递归子树；但原行为下父节点 missing 后其子节点是否报缺取决于原实现——原 `walk` 对 missing 只 append issue 后 `continue`，不递归子节点，即子节点不单独报缺。为保持 exact 回归，需确认 `_recurse(tc, None, ...)` 在 exact 路径不被调用）。**修正**：exact 路径 `pending_t` 分支里调用 `_recurse(tc, None, ...)` 会为子节点额外报 missing，这与原行为不同。需将 exact 分支改为不递归：

在 `if match_mode != "fuzzy" or not pending_t:` 分支内，把对 `pending_t` 的处理改为：
```python
            for _, tc in pending_t:
                tid = str(tc.get("id") or "")
                want = _node_title(tc)
                issues.append(
                    {"kind": "missing_section", "message": f"缺少章节：{want}",
                     "template_node_id": tid, "title_path": path + [want]}
                )
                records.append(
                    _record(tid=tid, title=want, path=path + [want],
                            user_title=None, hpi=None, method="missing")
                )
                # exact mode: do NOT recurse into unmatched subtree (preserve original behavior)
                if match_mode == "fuzzy":
                    _recurse(tc, None, path + [want])
```
（exact 时跳过递归；fuzzy 且 `not pending_t` 时该分支本就不进 pending 循环。）

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_tree_align.py -v`
Expected: all tests PASS (existing 4 + new 8).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/tree_align.py backend/tests/test_tree_align.py
git commit -m "feat: fuzzy structure matching (normalized + LLM) in tree_align"
```

---

### Task 6: LLM 语义匹配器

**Files:**
- Create: `backend/app/services/structure_llm_matcher.py`
- Test: `backend/tests/test_structure_llm_matcher.py`

**Interfaces:**
- Produces: `build_llm_matcher(db: Session, *, timeout_seconds: float) -> Callable[[list[str], list[str]], list[dict[str, Any]]]`
- 返回的 matcher 接受 `(template_titles, user_titles)`，返回 list of
  `{"template_title","user_title"|None,"confidence":float,"matched":bool}`。
- matcher 内部用独立 `SessionLocal()` 与 `chat_json_with_usage`，失败时返回全 unmatched（让 align 判 missing），并通过传入的 `log_sink` 记录（可选）。为保持测试可注入，matcher 失败时直接返回 `[{"template_title":t,"user_title":None,"confidence":0.0,"matched":False} for t in template_titles]`。

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_structure_llm_matcher.py
from __future__ import annotations

from app.services.structure_llm_matcher import _parse_llm_pairs, _build_prompt


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_structure_llm_matcher.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/structure_llm_matcher.py
"""LLM-based semantic matcher for fuzzy structure alignment.

Provides a per-level batch matcher that asks the LLM to pair template
section titles with user section titles (1:1). Used by review_pipeline
when structure_match_mode == "fuzzy".
"""

from __future__ import annotations

import json
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.llm.chat import chat_json_with_usage

_SYSTEM = (
    "你是工程文档结构对齐助手。给定模板章节标题列表与用户文档同级章节标题列表，"
    "为每个模板标题在用户标题中找语义对应的那一个（1:1，每个用户标题最多被匹配一次）。"
    "仅当二者确属同一章节内容时 matched=true。返回一个 JSON 对象："
    '{"pairs":[{"template_title":string,"user_title":string|null,"confidence":0.0~1.0,"matched":boolean}]}。'
    "不要输出 markdown 代码块或多余解释。"
)


def _build_prompt(template_titles: list[str], user_titles: list[str]) -> str:
    return (
        "模板章节标题列表：\n"
        + json.dumps(template_titles, ensure_ascii=False)
        + "\n\n用户文档同级章节标题列表：\n"
        + json.dumps(user_titles, ensure_ascii=False)
        + "\n\n请输出 JSON。"
    )


def _clamp01(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


def _parse_llm_pairs(
    raw: Any,
    template_titles: list[str],
    user_titles: list[str],
) -> list[dict[str, Any]]:
    """Normalize LLM output into a per-template-title dict list."""
    user_set = set(user_titles)
    pairs: list[dict[str, Any]] = []
    raw_pairs: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        p = raw.get("pairs")
        if isinstance(p, list):
            raw_pairs = [x for x in p if isinstance(x, dict)]
    elif isinstance(raw, list):
        raw_pairs = [x for x in raw if isinstance(x, dict)]

    by_t: dict[str, dict[str, Any]] = {}
    for item in raw_pairs:
        t = str(item.get("template_title") or "").strip()
        u = item.get("user_title")
        matched = bool(item.get("matched"))
        u_str = u.strip() if isinstance(u, str) else None
        if not t or t not in template_titles:
            continue
        if matched and (not u_str or u_str not in user_set):
            matched = False
            u_str = None
        entry = {
            "template_title": t,
            "user_title": u_str,
            "confidence": _clamp01(item.get("confidence")),
            "matched": matched,
        }
        # keep first occurrence per template title
        by_t.setdefault(t, entry)

    for t in template_titles:
        pairs.append(
            by_t.get(
                t,
                {"template_title": t, "user_title": None, "confidence": 0.0, "matched": False},
            )
        )
    return pairs


def build_llm_matcher(
    db: Session,
    *,
    timeout_seconds: float = 60.0,
    log_sink: Callable[[str, str], None] | None = None,
) -> Callable[[list[str], list[str]], list[dict[str, Any]]]:
    """Return a matcher(template_titles, user_titles) -> list[dict].

    Uses a fresh SessionLocal per call. On any failure returns all unmatched
    (so align treats them as missing) and logs a warning via log_sink.
    """

    def matcher(template_titles: list[str], user_titles: list[str]) -> list[dict[str, Any]]:
        if not template_titles or not user_titles:
            return [
                {"template_title": t, "user_title": None, "confidence": 0.0, "matched": False}
                for t in template_titles
            ]
        ldb = SessionLocal()
        try:
            data, _usage = chat_json_with_usage(
                ldb,
                user_message=_build_prompt(template_titles, user_titles),
                system=_SYSTEM,
                max_tokens=4096,
                timeout=timeout_seconds,
            )
            return _parse_llm_pairs(data, template_titles, user_titles)
        except Exception as e:
            if log_sink is not None:
                log_sink("warning", f"结构语义匹配 LLM 失败，按缺失处理: {e!s}")
            return [
                {"template_title": t, "user_title": None, "confidence": 0.0, "matched": False}
                for t in template_titles
            ]
        finally:
            ldb.close()

    return matcher
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_structure_llm_matcher.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/structure_llm_matcher.py backend/tests/test_structure_llm_matcher.py
git commit -m "feat: add LLM semantic matcher for fuzzy structure alignment"
```

---

### Task 7: pipeline 接入 fuzzy 模式与 mappings

**Files:**
- Modify: `backend/app/services/review_pipeline.py`

**Interfaces:**
- Consumes: `align_template_user_trees(..., match_mode, llm_matcher)` (Task 5), `build_llm_matcher` (Task 6), `SchemeTemplate.structure_match_mode` (Task 2).
- Produces: structure `ReportStep` with `.mappings` populated; fuzzy summary with match stats; LLM matcher usage merged into token totals.

- [ ] **Step 1: Update imports and helper**

在 `backend/app/services/review_pipeline.py` 顶部 import 区，紧接现有 `from app.services.tree_align import ...` 之后新增：

```python
from app.services.structure_llm_matcher import build_llm_matcher
```

修改 `_structure_issues_to_report` 签名与实现，使其额外接收 `match_records` 并填充 `mappings` 与 fuzzy 统计 summary。**整体替换**该函数：

```python
def _structure_issues_to_report(
    structure_raw: list[dict[str, Any]],
    *,
    match_records: list[dict[str, Any]] | None = None,
    match_mode: str = "exact",
) -> ReportStep:
    issues: list[ReportIssue] = []
    by_kind: dict[str, int] = {"missing_section": 0, "extra_section": 0}
    for raw in structure_raw:
        kind = str(raw.get("kind") or "")
        if kind in by_kind:
            by_kind[kind] += 1
        tp = raw.get("title_path") or []
        if not isinstance(tp, list):
            tp = []
        hpi = raw.get("heading_para_index")
        tid = raw.get("template_node_id")
        anchor: dict[str, Any] = {"title_path": tp}
        if tid is not None and str(tid).strip():
            anchor["template_node_id"] = tid
        ut = raw.get("user_title")
        if ut is not None and str(ut).strip():
            anchor["user_title"] = str(ut).strip()
        if isinstance(hpi, int):
            anchor["heading_para_index"] = hpi
        if kind == "missing_section":
            sev: Literal["error", "warning", "info"] = "error"
        elif kind == "extra_section":
            sev = "info"
        elif kind == "order_mismatch":
            sev = "warning"
        else:
            sev = "error"
        issues.append(
            ReportIssue(
                severity=sev,
                message=str(raw.get("message") or ""),
                evidence="",
                anchor=anchor,
                related={"kind": kind},
            )
        )

    records = match_records or []
    method_counts: dict[str, int] = {}
    low_count = 0
    for r in records:
        m = str(r.get("match_method") or "")
        method_counts[m] = method_counts.get(m, 0) + 1
        if r.get("low_confidence"):
            low_count += 1

    error_count = by_kind["missing_section"]
    extra_count = by_kind["extra_section"]
    passed = error_count == 0

    if not issues and not records:
        summary = "结构审核通过"
    elif match_mode == "fuzzy":
        parts = [f"共 {len(records)} 项映射"]
        seg: list[str] = []
        for m in ("exact", "normalized", "semantic"):
            if method_counts.get(m):
                seg.append(f"{m} {method_counts[m]}")
        if seg:
            parts.append("（" + " / ".join(seg) + "）")
        if low_count:
            parts.append(f"低信心 {low_count}")
        if error_count:
            parts.append(f"缺失 {error_count}")
        if extra_count:
            parts.append(f"多余 {extra_count}")
        summary = "".join(parts)
    else:
        if not issues:
            summary = "结构审核通过"
        else:
            parts = [f"共 {len(issues)} 项结构问题"]
            if error_count:
                parts.append(f"（缺失 {error_count}）")
            summary = "".join(parts)

    return ReportStep(
        step_id="structure",
        passed=passed,
        summary=summary,
        issues=issues,
        mappings=records,
    )
```

- [ ] **Step 2: Wire match_mode + llm_matcher into the pipeline call site**

在 `run_review_pipeline` 中，找到现有调用（约 1086 行）：
```python
        mapping, struct_raw = align_template_user_trees(template_nodes, user_nodes)
        structure_step = _structure_issues_to_report(struct_raw)
```
替换为：
```python
        match_mode = (tmpl.structure_match_mode or "exact")
        llm_matcher = None
        if match_mode == "fuzzy":
            llm_matcher = build_llm_matcher(
                db,
                timeout_seconds=float(max(60.0, review_timeout_seconds)),
                log_sink=lambda level, msg: _append_log(db, task, level, msg),
            )
        mapping, struct_raw, match_records = align_template_user_trees(
            template_nodes,
            user_nodes,
            match_mode=match_mode,
            llm_matcher=llm_matcher,
        )
        structure_step = _structure_issues_to_report(
            struct_raw, match_records=match_records, match_mode=match_mode
        )
```

注意：`review_timeout_seconds` 在原调用处之后才定义（原 1091 行）。需将该变量的读取上移到 `mapping, struct_raw = ...` 之前。具体：把
```python
        review_timeout_seconds = get_review_timeout_seconds(db)
```
从原位置移到 `align_template_user_trees` 调用之前（紧跟 `tmpl` 校验之后即可）。其余并发量读取保持原位不动。

- [ ] **Step 3: Verify the module imports cleanly**

Run: `cd backend && python -c "import app.services.review_pipeline"`
Expected: no error.

- [ ] **Step 4: Run the structure-related test suites**

Run: `cd backend && python -m pytest tests/test_tree_align.py tests/test_title_normalize.py tests/test_structure_llm_matcher.py tests/test_review_report.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/review_pipeline.py
git commit -m "feat: wire fuzzy structure matching and mappings into review pipeline"
```

---

### Task 8: 前端类型与 API 调用

**Files:**
- Modify: `frontend/src/api/types.ts`

**Interfaces:**
- Produces: `TemplatePublic.structure_match_mode`、`StructureMatchMode`、`ReportStep.mappings`、`StructureMapping` 类型。

- [ ] **Step 1: Add types**

修改 `frontend/src/api/types.ts`：

在 `FullDocumentReviewConfig` 接口之后新增：
```typescript
export type StructureMatchMode = 'exact' | 'fuzzy'

export interface StructureMapping {
  template_node_id: string
  template_title: string
  title_path: string[]
  user_title?: string | null
  heading_para_index?: number | null
  match_method: 'exact' | 'normalized' | 'semantic' | 'missing'
  confidence?: number | null
  low_confidence?: boolean
}
```

修改 `TemplatePublic`，在 `full_document_review_config` 字段后新增：
```typescript
  structure_match_mode: StructureMatchMode
```

修改 `ReportStep`，在 `issues` 字段后新增：
```typescript
  mappings?: StructureMapping[]
```

- [ ] **Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors (or only pre-existing unrelated errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/types.ts
git commit -m "feat(frontend): add structure match mode and mapping types"
```

---

### Task 9: 前端模板配置开关

**Files:**
- Modify: `frontend/src/components/ReviewWorkflowModal.tsx`

**Interfaces:**
- Produces: 在工作流弹窗内新增「结构匹配模式」Radio（精确/模糊），保存时调用 `PATCH /scheme-types/{id}/template/structure-match-mode`。

- [ ] **Step 1: Add the switch UI and save handler**

修改 `frontend/src/components/ReviewWorkflowModal.tsx`：

顶部 import 调整为：
```typescript
import { App as AntApp, Button, Modal, Radio, Space, Switch, Typography } from 'antd'
import type { RadioChangeEvent } from 'antd'
```
并在 import 类型处补 `StructureMatchMode`：
```typescript
import type { ReviewWorkflowData, StructureMatchMode, TemplatePublic, WorkflowStepId } from '../api/types'
```

在 `Props` 内的 state 区（`includeFullDocument` 之后）新增：
```typescript
  const [matchMode, setMatchMode] = useState<StructureMatchMode>('exact')
  const [modeSaving, setModeSaving] = useState(false)
```

在 `useEffect`（解析 `template.review_workflow`）内末尾追加：
```typescript
    setMatchMode((template.structure_match_mode === 'fuzzy' ? 'fuzzy' : 'exact'))
```

在 `handleSave` 之后新增保存函数：
```typescript
  async function handleSaveMatchMode(next: StructureMatchMode) {
    setModeSaving(true)
    try {
      const { data } = await api.patch<TemplatePublic>(
        `/scheme-types/${schemeTypeId}/template/structure-match-mode`,
        { mode: next },
      )
      message.success('结构匹配模式已保存')
      onSaved(data)
    } catch (err: unknown) {
      const raw =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined
      message.error(typeof raw === 'string' ? raw : '保存失败')
      setMatchMode(next === 'fuzzy' ? 'exact' : 'fuzzy')
    } finally {
      setModeSaving(false)
    }
  }
```

在弹窗内的开关组容器（`<Space direction="vertical">` 内，`full_document` Switch 之后）追加：
```tsx
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <Typography.Text>结构匹配模式</Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
                    模糊模式允许序号、标点、措辞差异，缺章节仍判不合规
                  </Typography.Text>
                </div>
                <Radio.Group
                  size="small"
                  value={matchMode}
                  disabled={modeSaving || loading || !template}
                  onChange={(e: RadioChangeEvent) => {
                    const v = e.target.value as StructureMatchMode
                    setMatchMode(v)
                    void handleSaveMatchMode(v)
                  }}
                >
                  <Radio.Button value="exact">精确</Radio.Button>
                  <Radio.Button value="fuzzy">模糊（语义）</Radio.Button>
                </Radio.Group>
              </div>
```

- [ ] **Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ReviewWorkflowModal.tsx
git commit -m "feat(frontend): add structure match mode switch in workflow modal"
```

---

### Task 10: 前端结构审核详情映射表

**Files:**
- Modify: `frontend/src/components/StructureReviewDetail.tsx`

**Interfaces:**
- Consumes: `ReportStep.mappings` (Task 8)。始终渲染映射表；passed 时只显示映射表 + 状态横幅。

- [ ] **Step 1: Add mapping table rendering**

修改 `frontend/src/components/StructureReviewDetail.tsx`：

顶部 import 追加 `Table` 与类型 `StructureMapping`：
```typescript
import { ..., Table, ... } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { ..., StructureMapping, ... } from '../api/types'
```

新增匹配方式标签辅助函数（放在 `KIND_DETAIL` 之后）：
```typescript
const METHOD_LABEL: Record<string, string> = {
  exact: '精确',
  normalized: '归一化',
  semantic: '语义',
  missing: '缺失',
}

const METHOD_TAG_COLOR: Record<string, string> = {
  exact: 'green',
  normalized: 'blue',
  semantic: 'cyan',
  missing: 'red',
}
```

新增映射表列定义与组件（在组件函数内、`return` 之前）：
```typescript
  const mappings: StructureMapping[] = Array.isArray(step.mappings) ? step.mappings : []

  const mappingColumns: ColumnsType<StructureMapping> = [
    {
      title: '模板章节',
      dataIndex: 'title_path',
      render: (_: unknown, r: StructureMapping) =>
        (r.title_path && r.title_path.length ? r.title_path : [r.template_title]).join(' > '),
    },
    {
      title: '用户文档章节',
      dataIndex: 'user_title',
      render: (v: unknown, r: StructureMapping) =>
        r.match_method === 'missing' ? '—' : `${v ?? ''}${r.heading_para_index != null ? `（hpi=${r.heading_para_index}）` : ''}`,
    },
    {
      title: '匹配方式',
      dataIndex: 'match_method',
      width: 130,
      render: (_: unknown, r: StructureMapping) => (
        <Space size={4} wrap>
          <Tag color={METHOD_TAG_COLOR[r.match_method] ?? 'default'}>
            {METHOD_LABEL[r.match_method] ?? r.match_method}
          </Tag>
          {r.low_confidence ? <Tag color="orange">低信心</Tag> : null}
          {r.confidence != null && r.match_method === 'semantic' ? (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {r.confidence.toFixed(2)}
            </Typography.Text>
          ) : null}
        </Space>
      ),
    },
  ]
```

修改 passed 分支（当前 `if (step.passed || step.issues.length === 0)` 提前 return）：在该分支的返回 JSX 中，`{templateModal}` 之前插入映射表区块：
```tsx
        {mappings.length > 0 ? (
          <>
            <Typography.Title level={5} style={{ marginTop: 16 }}>
              章节映射关系
            </Typography.Title>
            <Table<StructureMapping>
              size="small"
              rowKey={(r) => r.template_node_id}
              columns={mappingColumns}
              dataSource={mappings}
              pagination={mappings.length > 20 ? { pageSize: 20 } : false}
            />
          </>
        ) : null}
```

修改未通过分支：在「问题时间轴」之前同样插入上述映射表区块（`mappings.length > 0` 判断包裹）。映射表区块代码与 passed 分支一致，复用同一 `mappingColumns` / `mappings`。

- [ ] **Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/StructureReviewDetail.tsx
git commit -m "feat(frontend): show structure mapping table in review detail"
```

---

### Task 11: 端到端集成校验

**Files:**
- Test: `backend/tests/test_structure_fuzzy_integration.py`（新建）

**Interfaces:**
- 验证 fuzzy 模式下，序号差异的文档经注入假 LLM matcher 后结构通过、映射表含 normalized 记录、`ReportStep.mappings` 非空。

- [ ] **Step 1: Write the integration test**

```python
# backend/tests/test_structure_fuzzy_integration.py
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
    assert "归一化" in step.summary


def test_fuzzy_pipeline_integration_missing_fails_fast_data():
    # missing section must be error and reflected in report
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
```

- [ ] **Step 2: Run the integration test**

Run: `cd backend && python -m pytest tests/test_structure_fuzzy_integration.py -v`
Expected: 2 tests PASS.

- [ ] **Step 3: Run the full backend test suite to confirm no regressions**

Run: `cd backend && python -m pytest -q`
Expected: all tests PASS (no regressions in existing structure/parse tests).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_structure_fuzzy_integration.py
git commit -m "test: fuzzy structure matching end-to-end integration"
```

---

## Self-Review Notes

**Spec coverage:**
- 模板开关（独立列）→ Task 2。
- 开关 API + TemplatePublic → Task 4。
- 前端开关 → Task 9。
- 标题归一化 → Task 1。
- align 增强（精确/归一化/LLM/missing/extra/match_records）→ Task 5。
- LLM 匹配器（按层批量、1:1、失败兜底）→ Task 6。
- ReportStep.mappings → Task 3。
- pipeline 接入 + fuzzy summary → Task 7。
- 映射表展示（始终渲染）→ Task 10。
- 多余章节 extra_section(info) → Task 5（fuzzy only）。
- fail-fast 不变 → Task 5/7（error=missing 触发）。
- 回归保护（exact 不变）→ Task 5 `test_exact_mode_unchanged_*` + Task 11 全量。
- 阈值 0.6 常量 → Task 5 `SEMANTIC_LOW_CONFIDENCE_THRESHOLD`。

**Type consistency:**
- `align_template_user_trees` 返回三元组 `(mapping, issues, match_records)` 在 Task 5/7/11 一致。
- `llm_matcher` 签名 `(list[str], list[str]) -> list[dict]` 在 Task 5/6 一致；dict 字段 `template_title/user_title/confidence/matched` 一致。
- `match_records` 字段名 `template_node_id/template_title/title_path/user_title/heading_para_index/match_method/confidence/low_confidence` 在 Task 5/7/8/10 一致。
- `match_method` 取值 `exact|normalized|semantic|missing` 在后端常量与前端 `METHOD_LABEL` 一致。

**注意点（实现者务必遵守）：**
- Task 5 Step 3 中标注的 exact 路径"不递归子树"修正必须落地，否则会改变 exact 回归行为。
- Task 7 Step 2 中 `review_timeout_seconds` 必须上移到 align 调用之前。
- Task 4 测试 fixture 的登录路径/字段需先 grep 核对现有 auth 路由再调整。
