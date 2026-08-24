# 图审核两段式重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将图审核改为「视觉只识图 → 文本 LLM 按精简要求对多图描述一次判定（any-pass）」，并通过/不通过行均展示识别内容与始终落盘的审核提示词。

**Architecture:** 在 `image_review.py` 内拆出识图 prompt / 审核 prompt 纯函数、视觉 describe、文本 judge；`review_node_images` 编排两段缓存（识图指纹 + 审核指纹，版本 `img-3`）。`image_items` 增补 `kind`/`description`/`review_prompt_text`/`describe_prompt_text`。前端 `ImageReviewDetail` 展示全部图行并可展开审核提示词。文本判定复用 `chat_json`（默认内容审核模型）。

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / Pydantic；React + TypeScript + Ant Design；pytest；`chat_anthropic_messages`（视觉）、`chat_json`（文本）。

## Global Constraints

- 多图通过语义：至少一张满足全部已启用的图种/内容要素要求 → 节点通过（any-pass）。
- 图审核提示词与识图描述**始终**写入 `image_items`，不依赖 `prompt_debug_enabled`。
- 存在性仍为确定性代码，不进文本审核 prompt。
- 视觉只输出 `{kind, description}`，不做 `passed` 判定。
- 文本审核复用 `app.services.llm.chat.chat_json`（默认 provider），不新增独立图审文本模型配置。
- 模板 `image_review` JSON 三类勾选结构不变。
- 缓存版本 bump 为 `IMAGE_REVIEW_VERSION = "img-3"`，旧 `img-2` 视觉判定缓存自然失效。
- 后端测试：`cd backend && python -m pytest tests/test_image_review.py -v`
- 前端类型检查：`cd frontend && npx tsc --noEmit`
- Spec：`docs/superpowers/specs/2026-08-24-image-review-two-stage-design.md`

---

## File Structure

- **Modify** `backend/app/services/image_review.py` — 两段式核心（prompt、describe、judge、编排、缓存）。
- **Modify** `backend/tests/test_image_review.py` — 覆盖新行为；删除/改写依赖旧「视觉直接判定」的用例。
- **Modify** `backend/app/services/review_pipeline.py` — 调用处：图审核始终可收集提示词到 `image_items`（无需再为图审核把 `debug_prompts` 当唯一来源）；`review_node_images` 签名若增参则接线。
- **Modify** `frontend/src/api/types.ts` — `ImageReviewItem` 新字段。
- **Modify** `frontend/src/pages/ManualReviewPage.tsx` — `ImageReviewDetail` 全量行 + 展开；问题列表尽量带识别内容。

不新增独立文件（逻辑仍集中在现有 `image_review.py`，与仓库现状一致）。

---

### Task 1: 识图/审核 prompt 纯函数 + 双指纹

**Files:**
- Modify: `backend/app/services/image_review.py`
- Modify: `backend/tests/test_image_review.py`

**Interfaces:**
- Produces:
  - `DESCRIBE_PROMPT_VERSION = "desc-1"`
  - `JUDGE_PROMPT_VERSION = "judge-1"`
  - `IMAGE_REVIEW_VERSION = "img-3"`
  - `build_describe_user_prompt() -> str`
  - `build_judge_user_prompt(*, node_title_path, config, global_rules, captions, descriptions) -> str`
  - `image_describe_fingerprint(*, model, max_side, image_sha256) -> str`
  - `image_judge_fingerprint(*, text_provider, text_model, config, global_rules, template_updated_at, descriptions: list[tuple[str,str,str]]) -> str`  
    （descriptions 项为 `(kind, description, caption)`）

- [ ] **Step 1: Write the failing tests**

在 `backend/tests/test_image_review.py` 追加：

```python
from app.services.image_review import (
    IMAGE_REVIEW_VERSION,
    build_describe_user_prompt,
    build_judge_user_prompt,
    image_describe_fingerprint,
    image_judge_fingerprint,
    NodeImageConfig,
)


def test_image_review_version_is_img3():
    assert IMAGE_REVIEW_VERSION == "img-3"


def test_build_describe_user_prompt_is_short_and_non_judging():
    p = build_describe_user_prompt()
    assert "不要判断是否合格" in p
    assert "路线图" in p  # 示例图种
    assert "审核要求" not in p


def test_build_judge_user_prompt_includes_all_descriptions_and_kind_only():
    p = build_judge_user_prompt(
        node_title_path="八、应急 > 3.救援医院信息",
        config=NodeImageConfig(kind_note="路线图"),
        global_rules="",
        captions=["丹凤县江南医院…"],
        descriptions=[("路线图", "绿色路径从营销中心到医院方向")],
    )
    assert "路线图" in p
    assert "图1" in p
    assert "绿色路径" in p
    assert "不要额外提高标准" in p
    assert "至少一张" in p
    # 未启用 content → 不应出现空的内容要素行强加标准
    assert "内容要素：" not in p or "内容要素：\n" not in p


def test_describe_and_judge_fingerprints_differ_by_inputs():
    d1 = image_describe_fingerprint(model="vl", max_side=1536, image_sha256="aaa")
    d2 = image_describe_fingerprint(model="vl", max_side=1536, image_sha256="bbb")
    assert d1 != d2
    j1 = image_judge_fingerprint(
        text_provider="deepseek",
        text_model="deepseek-v4-flash",
        config=NodeImageConfig(kind_note="路线图"),
        global_rules="",
        template_updated_at="t1",
        descriptions=[("路线图", "有路径", "cap")],
    )
    j2 = image_judge_fingerprint(
        text_provider="deepseek",
        text_model="deepseek-v4-flash",
        config=NodeImageConfig(kind_note="平面布置图"),
        global_rules="",
        template_updated_at="t1",
        descriptions=[("路线图", "有路径", "cap")],
    )
    assert j1 != j2
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && python -m pytest tests/test_image_review.py::test_image_review_version_is_img3 tests/test_image_review.py::test_build_describe_user_prompt_is_short_and_non_judging tests/test_image_review.py::test_build_judge_user_prompt_includes_all_descriptions_and_kind_only tests/test_image_review.py::test_describe_and_judge_fingerprints_differ_by_inputs -v
```

Expected: IMPORT/ATTR errors（函数尚未存在）或 version 仍为 `img-2`。

- [ ] **Step 3: Implement prompt builders + fingerprints**

在 `image_review.py`：

1. 设 `IMAGE_REVIEW_VERSION = "img-3"`，增加 `DESCRIBE_PROMPT_VERSION` / `JUDGE_PROMPT_VERSION`。
2. 实现 `build_describe_user_prompt`（文案与 spec §视觉识图一致）。
3. 实现 `build_judge_user_prompt`（文案与 spec §文本 LLM 审核一致；仅 append 已启用的 kind/content 行；有 `global_rules` 才加【全局规则】；附图列表用 `图{i}`）。
4. 实现两个 fingerprint：`json.dumps(..., sort_keys=True)` + sha256，payload 必须含对应 prompt version 与 `IMAGE_REVIEW_VERSION`。
5. 保留旧 `image_node_fingerprint` 可删或改为内部废弃；若测试仍引用则改为测新指纹函数（本 Task 测试已切新函数）。更新文件顶部 docstring 说明两段式。

删除或改写 `_IMAGE_SYSTEM_BASE` / `_image_user_prompt`：识图用短 system（「只描述所见，不判定合格」）；审核用文本 `chat_json` 的 system（「方案附图审核，只按要求与识别结果判定」）。

- [ ] **Step 4: Run tests — expect PASS**

同 Step 2 命令。Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/image_review.py backend/tests/test_image_review.py
git commit -m "refactor(image-review): 两段式 prompt 与双指纹 (img-3)"
```

---

### Task 2: 视觉识图 + 文本判定 + 重写 `review_node_images`

**Files:**
- Modify: `backend/app/services/image_review.py`
- Modify: `backend/tests/test_image_review.py`
- Modify: `backend/app/services/review_pipeline.py`（仅当签名变化时接线；默认 `chat_json(ldb, ...)` 已够用）

**Interfaces:**
- Consumes: Task 1 builders/fingerprints；`compress_image_bytes`；`chat_anthropic_messages`；`chat_json`；`cache_lookup`/`cache_store`；`provider_model_pair`
- Produces: 更新后的 `review_node_images(...)` — 行为符合 spec；`image_items` 含：
  - `kind`, `description`, `summary`（`f"{kind}。{description}"`）, `passed`, `review_prompt_text`, `describe_prompt_text`, 既有定位字段
- `_vision_describe_image(cfg, image_bytes) -> dict` 返回 `kind`/`description`
- `_text_judge_node(ldb, user_prompt) -> dict` 返回 `passed`/`summary`/`issues`/`matched_image_indexes`

- [ ] **Step 1: Write failing orchestration tests**

```python
def test_two_stage_kind_route_map_any_pass(db_session, monkeypatch):
    """视觉只描述；文本判定图1为路线图 → 节点通过；两图都有 description；带 review_prompt_text。"""
    calls = {"vision": 0, "text": 0}

    def fake_get(key):
        # 任意非空 bytes；压缩路径会被 mock 掉
        return b"fake-image-bytes"

    def fake_describe(*, cfg, image_bytes):
        calls["vision"] += 1
        # 按调用次序：第一张路线图，第二张照片
        if calls["vision"] == 1:
            return {"kind": "路线图", "description": "绿线路径与推荐路线面板"}
        return {"kind": "照片", "description": "工地现场"}

    def fake_judge(ldb, *, user_prompt, system, max_tokens=2048):
        calls["text"] += 1
        assert "路线图" in user_prompt
        assert "图1" in user_prompt and "图2" in user_prompt
        return {
            "passed": True,
            "summary": "第1张为路线图，满足要求",
            "issues": [],
            "matched_image_indexes": [1],
        }

    monkeypatch.setattr("app.services.image_review.minio_storage.get_object_bytes", fake_get)
    monkeypatch.setattr("app.services.image_review._vision_describe_image", fake_describe)
    monkeypatch.setattr("app.services.image_review.chat_json", fake_judge)
    # 避免真实压缩依赖有效图片
    monkeypatch.setattr(
        "app.services.image_review.compress_image_bytes",
        lambda data, *, max_side: ("image/jpeg", "aaa"),
    )

    user_node = {
        "id": "u1",
        "content": [
            "cap-a",
            "[附图] reviews/1/images/a.png",
            "cap-b",
            "[附图] reviews/1/images/b.png",
        ],
        "children": [],
    }
    res = review_node_images(
        ldb=db_session,
        cfg=_cfg(max_per_node=10),
        template_node_id="n37",
        node_title_path="八、应急 > 3.救援医院信息",
        config=NodeImageConfig(kind_note="路线图"),
        user_node=user_node,
        global_rules="",
        template_updated_at="t1",
        title_path=["八、应急", "3.救援医院信息"],
    )
    assert res.passed is True
    assert calls["vision"] == 2
    assert calls["text"] == 1
    assert len(res.image_items) == 2
    assert res.image_items[0]["passed"] is True
    assert res.image_items[1]["passed"] is False
    assert "路线图" in res.image_items[0]["summary"]
    assert res.image_items[0]["description"]
    assert "至少一张" in res.image_items[0]["review_prompt_text"]
    assert res.image_items[0]["review_prompt_text"] == res.image_items[1]["review_prompt_text"]
    assert res.image_items[0]["describe_prompt_text"]


def test_two_stage_all_fail_still_has_descriptions(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.image_review.minio_storage.get_object_bytes", lambda k: b"x"
    )
    monkeypatch.setattr(
        "app.services.image_review._vision_describe_image",
        lambda **kw: {"kind": "照片", "description": "无路径"},
    )
    monkeypatch.setattr(
        "app.services.image_review.chat_json",
        lambda *a, **k: {
            "passed": False,
            "summary": "无路线图",
            "issues": [{"severity": "error", "message": "未见路线图", "evidence": "均为照片"}],
            "matched_image_indexes": [],
        },
    )
    monkeypatch.setattr(
        "app.services.image_review.compress_image_bytes",
        lambda data, *, max_side: ("image/jpeg", "aaa"),
    )
    user_node = {
        "id": "u1",
        "content": ["c", "[附图] reviews/1/images/a.png"],
        "children": [],
    }
    res = review_node_images(
        ldb=db_session,
        cfg=_cfg(),
        template_node_id="n1",
        node_title_path="x",
        config=NodeImageConfig(kind_note="路线图"),
        user_node=user_node,
        global_rules="",
        template_updated_at="t1",
    )
    assert res.passed is False
    assert len(res.issues) >= 1
    assert res.image_items[0]["passed"] is False
    assert res.image_items[0]["description"] == "无路径"
    assert res.image_items[0]["review_prompt_text"]
```

同时：**删除或改写**任何仍假设 `_vision_judge_image` / 旧 `_image_user_prompt` 做判定的测试。保留存在性、缺图 info、collect、compress 等测试。

- [ ] **Step 2: Run new tests — expect FAIL**

```bash
cd backend && python -m pytest tests/test_image_review.py::test_two_stage_kind_route_map_any_pass tests/test_image_review.py::test_two_stage_all_fail_still_has_descriptions -v
```

Expected: FAIL（旧编排仍走视觉判定或无新字段）。

- [ ] **Step 3: Implement two-stage `review_node_images`**

实现要点（写进 `image_review.py`）：

1. **`_vision_describe_image`**：`compress_image_bytes` → `chat_anthropic_messages`（短 system + `build_describe_user_prompt`）→ `extract_json_object` → 规范化 `kind`/`description` 字符串。
2. **编排**：
   - 存在性逻辑保持。
   - `needs_vision` 且有图：取图、截断 `max_per_node`。
   - 逐图：算 `image_describe_fingerprint`；`cache_lookup` 命中则用缓存的 `{kind,description}`；否则调用 describe 并 `cache_store` 一个仅含描述的小 `ReportStep`（或专用 payload：`passed=True, summary=json.dumps({kind,description})`，lookup 后解析）。推荐：缓存 step 的 `summary` 存 JSON `{"kind","description"}`，`step_id="image_describe"`。
   - 拼 `build_judge_user_prompt`；算 `image_judge_fingerprint`（descriptions 列表）；命中则恢复整节点 `passed/issues/image_items`；否则 `chat_json(ldb, user_message=prompt, system=JUDGE_SYSTEM, max_tokens=2048)`。
   - 将 `matched_image_indexes`（1-based）映射到每图 `passed`；未匹配为 False。
   - **每条 image_item** 写入 `kind/description/summary/review_prompt_text/describe_prompt_text`。
   - 不通过时把 judge `issues` 转为 `ReportIssue`（`anchor.template_node_id`；若能对应图则带 `related.image_object_key` / description）。
   - **不要**再因 `debug_prompts is not None` 跳过缓存；提示词已在 `image_items`。若传入 `debug_prompts` 列表，可额外 append 审核 prompt 一条（兼容旧调试页），但非必须。
3. 移除旧 `_vision_judge_image` 单段判定路径（或留 private 未引用亦可删）。
4. `provider_model_pair(ldb)` 用于 judge 指纹的 text provider/model。

- [ ] **Step 4: Run full image_review tests**

```bash
cd backend && python -m pytest tests/test_image_review.py -v
```

Expected: 全部 PASS。若 `test_fingerprint_stable_and_content_sensitive` 仍测旧函数，改为测新指纹或删除。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/image_review.py backend/tests/test_image_review.py backend/app/services/review_pipeline.py
git commit -m "feat(image-review): 视觉识图 + 文本LLM节点级判定"
```

---

### Task 3: 前端类型与附图明细表

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/pages/ManualReviewPage.tsx`

**Interfaces:**
- Consumes: `image_items[].kind|description|summary|passed|review_prompt_text|describe_prompt_text`
- Produces: 全量附图表明细；展开显示 `review_prompt_text`

- [ ] **Step 1: Extend `ImageReviewItem`**

```typescript
export interface ImageReviewItem {
  template_node_id?: string
  title_path?: string[]
  review_category?: string
  image_object_key: string
  image_caption?: string
  passed: boolean
  summary: string
  kind?: string
  description?: string
  review_prompt_text?: string
  describe_prompt_text?: string
  issues?: { severity: string; message: string; evidence?: string }[]
}
```

- [ ] **Step 2: Rewrite `ImageReviewDetail`**

- `dataSource = items`（**不要** `filter(passed)`）。
- 新增列「结果」：`passed ? 通过 : 不通过` Tag。
- 「识别出的图内容」：优先 `summary`，否则拼接 `kind`+`description`，再否则 `-`。
- `expandable.expandedRowRender`：展示 `r.review_prompt_text`；若空则文案：`该任务为旧版图审核结果，未落盘审核提示词`。
- 可选：同展开区内若有 `describe_prompt_text`，用小标题「识图提示词」另块展示。
- 标题由「通过列表」改为「附图明细」。
- **不再**依赖 `debugPrompts` 查找 prompt（可保留参数但忽略，或从调用处去掉）。

- [ ] **Step 3: 问题列表带识别内容（图审核）**

在 `activeStep.step_id === 'image_review'` 的「图件」列或旁侧：用 `related.image_object_key` 在 `activeStep.image_items` 里查找对应 item，展示其 `summary`/`description`（字号 12、secondary）。

- [ ] **Step 4: Typecheck**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 无 error。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/pages/ManualReviewPage.tsx
git commit -m "feat(ui): 图审核附图明细展示识别内容与审核提示词"
```

---

### Task 4: 回归与手动验收清单

**Files:** 无强制代码变更（若发现 pipeline 仍传 `debug_prompts=...` 导致误解，可加注释说明图审核以 `image_items` 为准）。

- [ ] **Step 1: 后端全量相关测试**

```bash
cd backend && python -m pytest tests/test_image_review.py -v
```

Expected: PASS。

- [ ] **Step 2: 对照 spec 验收清单（手工或预发）**

1. 节点仅配置图种「路线图」、附图为导航截图 → 应通过；展开提示词短且含「不要额外提高标准」。
2. 关闭「记录每步拼接提示词」再跑任务 → 附图行仍有识别内容，`+` 仍能看到 `review_prompt_text`。
3. 多图一路线图一无关图 → 节点通过；路线图行 `passed=true`。
4. 全部不满足 → 节点不通过；明细表仍有识别内容。
5. 仅存在性有图 → 不调视觉/文本（日志无视觉调用）。
6. 旧任务打开详情 → 无新字段时不崩溃，展开提示旧版。

- [ ] **Step 3: Commit**（若有注释/小修）

```bash
git add -u
git commit -m "chore(image-review): 两段式回归与注释"
```

若无变更可跳过 commit。

---

## Spec coverage self-check

| Spec 要求 | Task |
|-----------|------|
| 视觉只识图 | Task 2 `_vision_describe_image` |
| 文本 LLM 审核 | Task 2 `chat_json` judge |
| 多图描述合并 + any-pass | Task 2 + tests |
| 提示词精简精确 | Task 1 builders |
| 识别列通过/不通过都有 | Task 2 items + Task 3 表 |
| `+` 展开审核提示词且不依赖调试 | Task 2 落盘 + Task 3 |
| 双段缓存 img-3 | Task 1–2 |
| 存在性确定性 | 保留既有路径 + Task 2 |
| 706/707「路线图」不再加戏 | Task 1 judge 文案 + Task 4 验收 |

## Placeholder scan

无 TBD；函数名与字段与 Tasks 一致。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-24-image-review-two-stage.md`.

**Two execution options:**

1. **Subagent-Driven（推荐）** — 每任务新开子代理，任务间复审  
2. **Inline Execution** — 本会话按 executing-plans 连续做完  

Which approach?
