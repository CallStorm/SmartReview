# 模板结构匹配开关（精确 / 模糊语义）设计

日期：2026-06-23
状态：设计稿（待评审）

## 背景与目标

当前结构审核（`backend/app/services/tree_align.py`）使用**精确字符串匹配**：模板章节标题与用户文档同级标题经 `norm_title`（仅折叠空白）后必须完全相等，否则判为 `missing_section`（error），并触发 fail-fast 终止整个审核流水线。

精确匹配的痛点：用户上传的方案文档常出现序号写法不同（`一、工程概况` vs `1.工程概况`）、全半角差异、尾部标点、轻微措辞改写等情况，导致本应通过的文档被判结构不合规，审核规则（编制依据 / 上下文一致性 / 内容 / 通篇审核）无法从模板配置正确取用。

目标：新增模板级开关。开关打开时启用模糊语义匹配，建立模板章节 → 用户章节的映射关系，提高结构审核命中率；**大前提不变：用户文档必须满足模板要求，不能少**（缺章节仍报 error 并 fail-fast）。同时在结构审核详情里展示完整映射关系。

## 范围

- 模板配置新增结构匹配模式开关。
- `align_template_user_trees` 增强为「精确归一化 + LLM 兜底」的同级递归模糊匹配。
- 审核报告结构步骤新增映射表数据；前端结构审核详情展示映射表。
- 精确模式行为完全不变（回归保护）。

非目标：顺序校验（`order_mismatch`）、跨层级匹配、模板层级数变更、新增 LLM 之外的嵌入/向量匹配方案。

## 决策摘要

| 维度 | 决定 |
|---|---|
| 匹配方法 | 规则归一化优先，剩余项 LLM 兜底 |
| 匹配粒度 | 同级递归，保持树形结构 |
| 无匹配处理 | 报 `missing_section`（error，保持"不能少"硬约束）；低信心仍映射但标记 |
| 开关默认 | 关闭（`exact`，等同现有行为） |
| 映射展示 | 全量映射表 |
| 多余章节 | 列出但仅 `info`，不阻断 |
| 开关与映射存储 | 方案 A：模板新增独立列 `structure_match_mode` + 报告 `ReportStep.mappings` 可选字段 |
| LLM 调用粒度 | 按层批量（一层剩余项一次调用） |
| 低信心阈值 | 默认 0.6（命名常量，可调） |

## 架构

### 数据模型

`SchemeTemplate` 新增列：

```python
structure_match_mode: str  # "exact" | "fuzzy"，默认 "exact"
```

Alembic 迁移：`add structure_match_mode to scheme_templates`，`server_default="exact"`，`nullable=False`。

`ReviewReportV1.ReportStep` 新增可选字段：

```python
class ReportStep(BaseModel):
    step_id: str
    passed: bool
    summary: str = ""
    issues: list[ReportIssue] = Field(default_factory=list)
    mappings: list[dict[str, Any]] = Field(default_factory=list)  # 新增，结构步骤专用
```

`mappings` 仅结构步骤填充，其它步骤保持空数组。旧报告无此字段，前端按空数组处理。

### 开关配置 API

- 新增 `PATCH /scheme-types/{scheme_id}/template/structure-match-mode`（admin）
  - body: `{"mode": "exact" | "fuzzy"}`
  - 校验取值合法性，更新 `SchemeTemplate.structure_match_mode`。
- 新增 schema `StructureMatchModeUpdate`。
- `TemplatePublic` 暴露 `structure_match_mode: str` 字段。
- 前端在模板配置区域（`ReviewWorkflowModal` / `TemplatesPage`）新增「结构匹配模式」单选：精确 / 模糊（语义），带说明文案：模糊模式允许序号、标点、措辞差异，缺章节仍判不合规。

### 标题归一化模块

新文件 `backend/app/services/title_normalize.py`，纯函数无副作用：

```python
def normalize_title_for_match(title: str) -> str:
    """模糊匹配用标题归一化：
    1. 全角→半角（数字、字母、括号、标点）
    2. 去前导序号：一、/1./1、/1.1/(一)/第一章/第1节 等
    3. 去尾部标点（。：:，,）
    4. 折叠空白、去首尾空白
    """
```

现有 `tree_align.norm_title`（仅折叠空白）**保持不动**，精确模式继续使用；归一化仅用于 fuzzy 模式的新匹配路径，两套互不干扰。

### `align_template_user_trees` 增强

新签名：

```python
def align_template_user_trees(
    template_nodes: list[dict],
    user_nodes: list[dict],
    *,
    match_mode: Literal["exact", "fuzzy"] = "exact",
    llm_matcher: Callable[[list[str], list[str]], list[dict]] | None = None,
) -> tuple[dict[str, dict], list[dict], list[dict]]:
    # 返回 (mapping, issues, match_records)
```

返回值：

- `mapping`：`template_node_id -> user_node`，保留现有「优先用 hpi 在原始未裁剪树重定位」逻辑，供后续步骤取正文。
- `issues`：`missing_section`(error) / `extra_section`(info)。
- `match_records`（新）：每个模板节点一条：
  ```python
  {
    "template_node_id": str,
    "template_title": str,
    "title_path": list[str],
    "user_title": str | None,
    "heading_para_index": int | None,
    "match_method": "exact" | "normalized" | "semantic" | "missing",
    "confidence": float | None,
    "low_confidence": bool
  }
  ```

#### 每层匹配顺序（fuzzy 模式）

逐层递归，模板某层子节点只与「已匹配父节点」下的用户同级节点匹配：

1. **精确**：`norm_title`（折叠空白）相等 → `match_method="exact"`。
2. **归一化**：剩余项用 `normalize_title_for_match` 再比较 → `match_method="normalized"`。
3. **LLM 兜底**：仍剩余的模板标题 T' 与剩余用户同级标题 U'，调用 `llm_matcher(T', U')` 一次批量返回 1:1 映射 → `match_method="semantic"`（带 `confidence`）。
4. 该层结束，未被任何模板节点占用的用户节点 → 产出 `extra_section`(info)。

代码侧强制 1:1：LLM 若将多个模板标题指向同一用户标题，按 `confidence` 高者保留，其余判 `missing`。

LLM 返回项分级（`SEMANTIC_LOW_CONFIDENCE_THRESHOLD = 0.6`）：

- `matched=false` → `missing_section`（error，硬约束）
- `matched=true, confidence >= 0.6` → `semantic`
- `matched=true, confidence < 0.6` → `semantic` + `low_confidence=true`（仍映射，不报错）

#### exact 模式

完全走现有逻辑；`match_method` 全标 `exact`；**不产出** `extra_section`（保持现有"多余章节静默忽略"行为，避免改变精确模式语义）。`match_records` 仍生成（统一数据形状，便于前端始终渲染映射表），`match_method` 仅 `exact` / `missing`。

深度裁剪逻辑（`_template_max_depth` + `_prune_user_tree_to_depth`）不变，仍以模板最大层级为准。

### LLM 语义匹配实现

- 复用 `app.services.llm.chat.chat_json_with_usage`（含超时/重试/usage 统计），与现有 LLM 步骤同一基础设施。
- `llm_matcher` 由 `review_pipeline` 注入（便于测试时替换为假实现）。其内部用独立短会话 `SessionLocal`。
- 系统 Prompt（限定 JSON）：

  > 给定模板章节标题列表与用户文档同级章节标题列表。为每个模板标题在用户标题中找**语义对应**的那一个（1:1，每个用户标题最多被匹配一次）。仅当二者确属同一章节内容时 `matched=true`。返回 JSON 数组：`[{"template_title": str, "user_title": str|null, "confidence": 0.0~1.0, "matched": bool}]`。

- LLM 失败兜底：若调用异常，该层剩余模板标题全部判 `missing_section`，并写 `review_log` warning「结构语义匹配 LLM 失败，按缺失处理」。

### 报告生成

`_structure_issues_to_report` 扩展：

- 消费 `issues`：`missing_section` → severity `error`；`extra_section` → severity `info`。
- 将 `match_records` 写入 `step.mappings`。
- `summary`（fuzzy）：补充匹配统计，如「共 12 项映射（精确 8 / 归一化 3 / 语义 1），缺失 0，多余 2」；exact 模式 summary 保持现有文案。
- `passed`：仍为 `len([i for i in issues if i.severity=='error']) == 0`（info 不影响 passed）。

### fail-fast 不变

`review_pipeline.py` 中结构未通过（存在 error 即 missing）→ 任务 `failed` 并终止后续步骤。模糊匹配只提高命中率，不降低硬约束。fuzzy 模式下读取 `tmpl.structure_match_mode`，构造 `llm_matcher` 并传入 `align_template_user_trees`。

### Word 批注

- `missing_section`：无 hpi，不写批注（同现状）。
- `extra_section`(info)：不写批注（批注仅写 error/warning 级定位问题，避免噪音）。

### 前端 `StructureReviewDetail`

- 当前 `step.passed` 分支提前 return，需改为**始终渲染映射表区域**（passed 时只显示映射表 + 状态横幅，不显示问题时间轴/待处理项）。
- 映射表列：模板章节（title_path）→ 用户章节（user_title + hpi 链接）→ 匹配方式 Tag：
  - `exact`：绿「精确」
  - `normalized`：蓝「归一化」
  - `semantic`：青「语义」；`low_confidence` 时橙「语义·低信心」
  - `missing`：红「缺失」
  - `extra_section`（来自 issues）单列灰「多余」
- 现有 `KIND_LABEL` 已含 `extra_section`，复用；新增匹配方式标签配色。
- 问题时间轴 / 待处理项保持现有结构，`extra_section` 走 info 灰色，不提供"立即补全"按钮。

## 数据流

```
模板 structure_match_mode ─┐
                           ▼
review_pipeline 读取 mode
                           │
模板树 + 用户树 ──► align_template_user_trees(mode, llm_matcher)
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   mapping            issues           match_records
   (后续步骤定位)   (missing=err/extra=info)   │
        │                  │                  ▼
        │                  ▼          _structure_issues_to_report
        │           fail-fast?            │
        │              ├ 是 → failed       ▼
        │              └ 否 → 继续      ReportStep
        │                              (issues + mappings)
        ▼                                  │
   后续 LLM 步骤                            ▼
                              前端 StructureReviewDetail 渲染映射表
```

## 错误处理

- LLM 调用失败：该层剩余模板标题全部判 missing，写 warning 日志，审核继续走 fail-fast 判定（结构未通过 → 任务 failed）。
- LLM 返回非法 JSON / 违反 1:1：代码侧强制 1:1 去重（按 confidence），缺项判 missing；JSON 解析失败重试一次（复用现有重试逻辑），仍失败按 LLM 失败处理。
- 开关取值非法：API 层 400 拒绝。
- 旧报告无 `mappings`：前端按空数组处理。

## 测试

### `test_title_normalize.py`（新）

- 序号剥离：`一、工程概况` → `工程概况`；`1.工程概况` → `工程概况`；`1.1 概述` → `概述`；`(一)总则` → `总则`；`第一章 总则` → `总则`。
- 全半角：`１．工程概况` → `工程概况`。
- 尾部标点：`工程概况。` → `工程概况`。
- 空白折叠。

### `test_tree_align.py`（扩展）

- fuzzy 下序号不同能匹配（`一、工程概况` ↔ `1.工程概况`），`match_method="normalized"`。
- fuzzy 下 LLM 兜底匹配语义改写（注入假 `llm_matcher`），`match_method="semantic"`。
- fuzzy 下 LLM `matched=false` → `missing_section`(error)。
- fuzzy 下 `confidence < 0.6` → `semantic` + `low_confidence=true`，仍映射不报错。
- fuzzy 下多余用户章节 → `extra_section`(info)，不影响 `passed`。
- fuzzy 下 1:1 冲突：两个模板标题指向同一用户标题 → 高 confidence 保留，另一个 missing。
- exact 模式行为完全不变（回归保护）：多余章节不报、不产出 extra_section。
- 深度裁剪在 fuzzy 下仍生效。

### API / 集成

- `PATCH .../structure-match-mode` 合法/非法取值。
- `TemplatePublic` 含 `structure_match_mode`。
- 一条 fuzzy 端到端用例（注入假 LLM）：序号差异文档结构通过、映射表含 `normalized` 记录。

## 兼容性

- 默认 `exact`，既有模板与既有审核结果不受影响。
- `ReportStep.mappings` 为可选字段，旧报告无该字段不报错。
- 迁移加列带 `server_default`，存量行自动 `exact`。

## 开放项

- 低信心阈值 0.6 为默认常量，后续若需按模板调可再扩展配置。
- `order_mismatch` 仍为预留死代码，本设计不实现。
