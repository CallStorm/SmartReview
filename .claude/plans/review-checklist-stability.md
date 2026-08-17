# 内容审核「逐项清单判定 + 结果缓存」改造

## 背景（maoyu 7 次审核分析结论）

- 7 次审核流程完整（31 节点全跑、无超时），文档基本未变（输入 tokens 恒定 96k~97k），
  但每次只报出全部问题的一个随机子集（4/14/2/4/3/3/2 条），同一问题 severity 摇摆，
  622 还出现 10 条违反全局规则的越权问题。
- 根因：① 输出 schema 只让模型"列问题"，不强制逐检查项给结论（漏检是结构性的）；
  ② DeepSeek temp=0 仍非确定；③ 检查项判据措辞灰区大；④ 全局规则只有文字约束、无程序校验。

## 目标（对应用户三条大原则）

1. 一次审核把配置的检查项**全部**判定一遍 → 逐项清单输出，fail 才成为 issue。
2. 每条问题必须挂到具体检查项（`related.check_item_id`），无主问题程序性丢弃。
3. 同文档 + 同规则 + 同模型 → 重复审核结果**逐条一致** → 节点级结果缓存。

## 改动内容

### 1. 新模块 `backend/app/services/checklist.py`

- `split_check_items(review_prompt: str) -> tuple[list[dict], list[str]]`
  - 确定性拆分（不调 LLM）：优先按 ①②③… 序号拆；否则按 。/；/？ 切句。
  - 识别"判定说明句"（`如果判断`/`注意`/`以上确实`/`该节中的`/`无需`/`不需要` 等开头）
    归入附注 notes，不作为检查项。
  - 节点若在 parsed_structure 里显式配置 `check_items: [{id?, text}]`，直接使用（id 缺省
    自动生成 `{node_id}-{k}`），跳过自动拆分 —— 为后台后续结构化配置预留，本期不做前端 UI。
- `build_checklist_block(items, notes) -> str`：渲染编号清单 + 附注。
- `CHECKLIST_VERSION = "1"`：缓存指纹组成部分；提示词逻辑变更时手动 bump。

### 2. `review_pipeline.py` 内容审核步骤改造

- 新增 `CONTENT_JSON_SYSTEM`（仅 content 步骤使用，`_llm_review_execute` 已支持 `system=` 覆盖）：
  要求输出 `{"passed", "summary", "checks": [{"item_id", "verdict": "pass|fail|na",
  "severity", "message", "evidence", "related": {"fix", "suggestions"}}]}`，
  **每个 item_id 必须出现且仅出现一次**。
- `_content_prompt` 重写：
  - 【检查项清单】：逐条 `item_id + 检查项原文`，判定判据沿用全局规则第 3 条
    （量化/清单/存在性）逐项写明"判 fail 的条件"；
  - 【附注】：判定说明句原样保留；
  - 【审核总则】（content_review_rules）注入方式不变；
  - 正文超 16000 字符截断时：prompt 内注明"正文已截断"，并写 review_log warning（P5）。
- 新增 `_normalize_content_checks(data, anchor_base, items)`：
  - `verdict=fail` 且 item_id 在清单内 → ReportIssue（`related.check_item_id` / `check_item` 附检查项原文）；
  - 每个 item 最多 1 条（by construction）；item_id 不在清单内的丢弃 + log；
  - 模型漏判的 item → log warning（可观测，不臆造补齐）；
  - 兼容降级：模型仍返回旧 `issues[]`（无 checks）时走原 `_normalize_llm_step` 并 log 一次提示。
- `_content_node_worker`：拆分 → 构造 prompt → 缓存查询 → （miss 时）LLM → 归一化 → 缓存写入。

### 3. 节点结果缓存（content 步骤）

- 新表 `review_result_cache`（alembic migration `025_review_result_cache.py`）：
  `id, fingerprint (sha256, unique), step_id, template_node_id, payload_json (ReportStep), created_at`。
- 指纹 = sha256(`CHECKLIST_VERSION | step_id | provider | model | 检查项清单 JSON |
  content_review_rules | template.updated_at | current_text | ref_text | dataset_id + query`)。
  - **不含**知识库检索文本（Dify 检索本身波动；用 dataset_id+query 代替，避免缓存永远 miss）。
- worker 内：hit → 直接复用 ReportStep（log "内容审核节点命中缓存"）；miss → LLM 后写入。
  缓存读写异常只 log warning，不影响审核主流程。

### 4. 审计报告展示检查项（轻量）

- `related.check_item_id/check_item` 随 issue 存入 review_result_json（related 是自由 dict，
  ReportIssue schema、前端类型、docx/pdf 渲染链路均透传，无需改结构）。
- `review_report_content.py`：问题列前缀 `【检查项 {check_item_id}】`（存在时），
  docx/pdf 报告与前端无需其他改动。

### 5. 模板 12 配置修正（P4，线上 + 本地各执行一次）

- 先 GET 备份 `parsed_structure` 原文到 `backups/`。
- n17（四>1.技术参数）`review_prompt` 删除末句
  "该节中的技术参数应与1.1节一致，材料及设备技术参数应与3.2节一致。"
  （跨章核对已由 context_consistency 步骤的 n17↔n14 配对负责；该句当前导致连续 3 次
  "无法核验与 1.1/3.2 节一致性" 的 info 噪声）。
- 线上经 `PUT /api/scheme-types/12/template/structure`（admin）执行并复核；
  本地等用户启动后同样执行。

### 6. 测试（backend/tests，unittest 风格与现有一致）

- `test_checklist.py`：用模板 12 真实 prompt 做拆分用例（含 ① 型/散文型/附注句识别/
  显式 check_items 覆盖）。
- `test_content_checks_normalize.py`：fail→issue、无主丢弃、每项 1 条上限、漏判告警、
  旧 issues 降级路径、截断告警。
- `test_review_result_cache.py`：同输入同指纹、任一组成部分变化指纹变。
- 跑全量 `backend/tests`。

### 7. 本地验证（用户本地启动 http://localhost:5173 后执行，密码同线上）

- 从线上 `GET /api/review-tasks/627/output-download-url` 下载批注版 docx 作为待审文档
  （word_parser 只读正文段落/表格，不读批注，正文与原文等价）。
- 本地以 admin 提交同一文档 2 次：
  - 第 2 次各内容节点应命中缓存，issue 与第 1 次**逐条一致**（对比 review_result_json）；
  - review_log 出现"命中缓存"。
- 修改文档某一节的一处文字后提交第 3 次：仅该节重新审核，其余节点仍命中缓存。
- 向用户输出三次审核的对比矩阵。

## 不做的事（明确排除）

- 不改 context_consistency / compilation_basis / full_document 步骤的提示词与缓存
  （后续可按同模式扩展）。
- 不做检查项编辑前端 UI（后端已支持显式 `check_items` 字段，管理端暂继续编辑整段
  review_prompt，自动拆分兜底）。
- 不部署线上；部署由用户决定。
