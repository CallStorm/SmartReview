# 配置用 Excel 模版优化与模版管理页下载 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按设计优化配置用 Excel（空白 + 落地脚手架示例），放入 `frontend/public/config-templates/`，并在模版管理页提供下载入口与左下角说明。

**Architecture:** 用一次性 Python（openpyxl）脚本从现有落地脚手架 xlsx 改版生成两个静态文件，提交到 `frontend/public/`；TemplatesPage 用静态 URL 下载，不新增后端 API。Excel 仍为人工录入清单，不做导入。

**Tech Stack:** openpyxl 3.x；React + TypeScript + Ant Design；Vite public 静态资源。

## Global Constraints

- Spec：`docs/superpowers/specs/2026-08-28-config-excel-template-design.md`
- 受众：配置侧客户/管理员；系统**不**自动导入 Excel。
- Sheet 仅 6 张：说明与版本、章节结构_完整性、一致性规则、编制依据库、章节审查配置、知识库；**删除**审核流程图。
- 说明与版本字段：方案大类、方案名称、适用说明、编制人、更新日期（无模版版本/方案类型代码/填写约定）。
- 一致性规则：无严重等级列。
- 章节审查配置：无数值审核、审查侧重点；有图审核四列（启用/有无图/图种类/图内容）；**不加**编制依据审核列。
- 行内 Word 下载按钮文案改为「下载 Word」。
- 不做独立指引 Modal / md；左下角短说明即可。
- 不做管理员手册附录同步。
- **不要**擅自 `git commit`，除非用户明确要求提交。
- 源示例路径：`C:\Users\Administrator\Desktop\一建方案审核\落地脚手架\专项方案审核模版_落地脚手架final.xlsx`

---

## File Structure

- **Create** `scripts/build_config_excel_templates.py` — 生成空白 + 落地脚手架示例 xlsx（可重复运行）。
- **Create** `frontend/public/config-templates/专项方案审核配置模版_空白.xlsx`
- **Create** `frontend/public/config-templates/专项方案审核配置模版_落地脚手架示例.xlsx`
- **Modify** `frontend/src/pages/TemplatesPage.tsx` — PageShell `extra` 下载按钮；行内「下载 Word」；表下左下角说明文。
- **Create** `scripts/verify_config_excel_templates.py` — 断言两个 xlsx 表头/sheet 符合 spec（脚本验收，非 pytest 强依赖）。

不改后端、不改 `adminManualContent.ts`。

---

### Task 1: 生成脚本 + 两个 xlsx

**Files:**
- Create: `scripts/build_config_excel_templates.py`
- Create: `frontend/public/config-templates/专项方案审核配置模版_空白.xlsx`
- Create: `frontend/public/config-templates/专项方案审核配置模版_落地脚手架示例.xlsx`
- Create: `scripts/verify_config_excel_templates.py`

**Interfaces:**
- Consumes: 源 xlsx（路径见 Global Constraints）；openpyxl
- Produces: 上述两个文件；verify 脚本 exit 0 表示合格

- [ ] **Step 1: 编写 `build_config_excel_templates.py`**

脚本须：

1. 定义常量表头：

```python
META_FIELDS = ["方案大类", "方案名称", "适用说明", "编制人", "更新日期"]
STRUCTURE_HEADERS = ["章节编码", "章节标题", "是否校验", "完整性依据", "备注"]
CONSISTENCY_HEADERS = ["规则ID", "规则名称", "是否启用", "源章节编码", "目标章节编码", "检查说明"]
BASIS_HEADERS = ["依据ID", "文献类型", "标准号或文号", "文献名称", "版本或施行日期说明", "是否必引", "类别", "分类", "备注"]
CHAPTER_HEADERS = [
    "章节编码", "依赖章节编码", "知识库引用", "人工提示词",
    "图审核启用", "有无图", "图种类", "图内容",
]
KB_HEADERS = ["条目ID", "知识库名称", "TAG信息", "内容引用", "摘要说明", "是否启用", "备注"]
SHEET_ORDER = [
    "说明与版本", "章节结构_完整性", "一致性规则", "编制依据库", "章节审查配置", "知识库",
]
```

2. **空白模版**：新建 workbook，按 `SHEET_ORDER` 建表；说明与版本写「字段名|值」两列 + `META_FIELDS` 五行（值空，适用说明可写「请按实际方案类型填写」）；其余表只写表头一行。

3. **示例模版**：`load_workbook(源路径)`，然后：
   - 删除 sheet「审核流程图」（若存在）。
   - 重写「说明与版本」为仅 `META_FIELDS`：方案大类=`脚手架工程`，方案名称=`落地脚手架`，适用说明保留/写「落地脚手架专项方案审核配置示例」，编制人/更新日期可空。去掉旧字段与填写约定行。
   - 「一致性规则」：删除「严重等级」列；将检查说明等文本中含「基坑」的示例行改为与脚手架一致的表述（至少修正 CNS_006 一类残留）。
   - 「章节审查配置」：删除「数值审核」「审查侧重点」列；在末尾追加四列 `图审核启用/有无图/图种类/图内容`（示例行默认可空，或对明显含图的章节如 1.2 填「是」及简短说明，可选）。
   - 其余 sheet 数据保留；确保最终仅 `SHEET_ORDER` 六张表且顺序一致。

4. 输出目录：`frontend/public/config-templates/`（不存在则 `mkdir`）。

5. `if __name__ == "__main__"` 调用生成两个文件。

- [ ] **Step 2: 编写 `verify_config_excel_templates.py`**

对两个文件断言：

- `wb.sheetnames == SHEET_ORDER`
- 说明与版本 A 列字段集合 == `META_FIELDS`（且不含「方案类型代码」「模版版本」）
- 一致性规则表头 == `CONSISTENCY_HEADERS`（无「严重等级」）
- 章节审查配置表头 == `CHAPTER_HEADERS`
- 示例文件 B 列方案大类/方案名称为脚手架工程/落地脚手架
- 全文（示例）不应再出现 `DEEP_EXCAVATION`

失败时 `sys.exit(1)` 并打印原因。

- [ ] **Step 3: 运行生成与校验**

```powershell
cd C:\Users\Administrator\Desktop\SmartReview
python scripts/build_config_excel_templates.py
python scripts/verify_config_excel_templates.py
```

Expected: 两脚本 exit 0；`frontend/public/config-templates/` 下两个 xlsx 存在。

- [ ] **Step 4: 人工 spot-check（可选）**

用 Excel 或 `python -c` 打开示例，确认无「审核流程图」、章节审查配置有图审核四列。

---

### Task 2: 模版管理页下载入口 + 左下角说明 + 「下载 Word」

**Files:**
- Modify: `frontend/src/pages/TemplatesPage.tsx`

**Interfaces:**
- Consumes: 静态路径  
  `/config-templates/专项方案审核配置模版_空白.xlsx`  
  `/config-templates/专项方案审核配置模版_落地脚手架示例.xlsx`
- Produces: 页级下载按钮；左下角说明；行内「下载 Word」

- [ ] **Step 1: 在文件顶部（组件外）增加常量**

```ts
const CONFIG_EXCEL_BLANK = '/config-templates/专项方案审核配置模版_空白.xlsx'
const CONFIG_EXCEL_SAMPLE = '/config-templates/专项方案审核配置模版_落地脚手架示例.xlsx'

function downloadStaticFile(url: string, filename: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}
```

- [ ] **Step 2: PageShell 增加 `extra` 下载按钮**

当前：

```tsx
<PageShell
  icon={<FormOutlined />}
  description="按方案类型上传 Word 模版、配置标题树规则与审核工作流。"
>
```

改为（文案可微调，须含两个下载）：

```tsx
<PageShell
  icon={<FormOutlined />}
  description="按方案类型上传 Word 模版、配置标题树规则与审核工作流。"
  extra={
    <Space wrap>
      <Button
        onClick={() =>
          downloadStaticFile(CONFIG_EXCEL_BLANK, '专项方案审核配置模版_空白.xlsx')
        }
      >
        下载空白配置模版
      </Button>
      <Button
        onClick={() =>
          downloadStaticFile(
            CONFIG_EXCEL_SAMPLE,
            '专项方案审核配置模版_落地脚手架示例.xlsx',
          )
        }
      >
        下载落地脚手架示例
      </Button>
    </Space>
  }
>
```

- [ ] **Step 3: 行内按钮「下载」→「下载 Word」**

在操作列中，将下载 Word 的 `<Button>...下载</Button>` 文案改为 `下载 Word`（逻辑仍为现有 `/template/download-url` 流程，勿改）。

- [ ] **Step 4: 表格下方左下角说明**

在 `</Table>` 之后、`</PageShell>` 之前增加：

```tsx
<Typography.Paragraph
  type="secondary"
  style={{ marginTop: 16, marginBottom: 0, maxWidth: 720 }}
>
  配置用 Excel：请下载空白模版或落地脚手架示例填写后，在本页按方案类型手工录入（系统不自动导入）。
  章节结构以 Word 模版标题为准；图审核请在「章节审查配置」对应列填写，并在审核工作流中开启。
</Typography.Paragraph>
```

- [ ] **Step 5: 类型检查**

```powershell
cd C:\Users\Administrator\Desktop\SmartReview\frontend
npx tsc --noEmit
```

Expected: 无新增错误。

- [ ] **Step 6: 浏览器 spot-check**

打开模版管理页：可见两个下载按钮；点击可下载 xlsx；行内为「下载 Word」；左下角有说明文。

---

### Task 3: 对照 spec 验收

**Files:** 无代码变更（验收）

- [ ] **Step 1: 再跑 verify 脚本**

```powershell
python scripts/verify_config_excel_templates.py
```

Expected: exit 0

- [ ] **Step 2: 对照 spec 交付清单勾选**

- [ ] 空白 xlsx 表头正确  
- [ ] 示例 xlsx 方案大类/名称正确，无 DEEP_EXCAVATION / 审核流程图 / 严重等级 / 数值审核 / 审查侧重点  
- [ ] 有图审核四列  
- [ ] public 静态可下载  
- [ ] TemplatesPage UI 三项（双下载、下载 Word、左下角说明）  
- [ ] 无导入 API、无指引 Modal、无手册附录改动  

---

## Self-Review (plan author)

| Spec 要求 | Task |
|-----------|------|
| 6 sheet + 删流程图 | Task 1 |
| 说明与版本字段 | Task 1 |
| 一致性无严重等级 | Task 1 |
| 章节审查图审核四列、无数值/侧重点、无编制依据列 | Task 1 |
| 示例纠错 | Task 1 |
| public 静态托管 | Task 1 |
| 页级双下载 | Task 2 |
| 下载 Word 改名 | Task 2 |
| 左下角说明 | Task 2 |
| 不做导入/Modal/手册 | Global Constraints + Task 3 验收 |

无 TBD 占位；提交需用户明确要求。
