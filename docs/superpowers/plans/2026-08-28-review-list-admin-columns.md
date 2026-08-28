# 方案审核列表精简 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 精简方案审核任务列表主表列，并将低频操作收入「更多」菜单，管理员视图不再横向拥挤。

**Architecture:** 仅改 `ReviewPage` 前端：主表保留用户名（管理员）/ 文件（含方案类型副行）/ 状态 / 短时间 / 操作；次要指标放 `Table.expandable`；操作列外露「人工审阅」「导出方案」，其余进 Ant Design `Dropdown`。业务回调与权限判断保持不变。

**Tech Stack:** React、Ant Design 5（Table / Dropdown / Button / Popconfirm / Tooltip）、现有 `ReviewPage.css`

**Spec:** `docs/superpowers/specs/2026-08-28-review-list-admin-columns-design.md`

## Global Constraints

- 不改后端 API、权限、导出/删除/测评逻辑
- 普通用户能力集不变（无用户名列、无管理员专属菜单）
- 删除仍须 Popconfirm
- 无前端单测基建时，以浏览器手工验收为主；不新增测试框架

---

## File map

| File | Role |
|------|------|
| `frontend/src/pages/ReviewPage.tsx` | 列定义、时间格式、文件单元格、expandable、操作 Dropdown |
| `frontend/src/pages/ReviewPage.css` | 文件副行、展开明细、操作列样式 |
| `frontend/src/config/adminManualContent.ts` | 管理员手册文案对齐 |

---

### Task 1: 辅助函数与样式

**Files:**
- Modify: `frontend/src/pages/ReviewPage.tsx`（顶部 helpers）
- Modify: `frontend/src/pages/ReviewPage.css`

**Interfaces:**
- Produces: `formatCreatedAtShort(iso: string): string`；保留现有 `formatDurationMinutes` / `formatTokenCount` / `tokensCell` 供展开区复用

- [ ] **Step 1: 增加短时间格式化**

在 `formatTokenCount` 附近加入：

```tsx
function formatCreatedAtShort(iso: string): string {
  // 兼容 "2026-08-25T10:15:34" / 带 Z / 空格分隔
  const d = new Date(iso.includes('T') || iso.includes(' ') ? iso : iso)
  if (Number.isNaN(d.getTime())) return iso || '—'
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${mm}-${dd} ${hh}:${mi}`
}
```

- [ ] **Step 2: 追加 CSS**

在 `ReviewPage.css` 增加（可替换过窄的 `.review-page__filename` max-width）：

```css
.review-page__file-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  max-width: 360px;
}

.review-page__filename {
  display: block;
  max-width: 100%;
}

.review-page__scheme-sub {
  font-size: 12px;
  line-height: 1.35;
  color: rgba(0, 0, 0, 0.45);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.review-page__expand {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px 24px;
  padding: 4px 8px;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.65);
}

.review-page__expand dt {
  margin: 0;
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
}

.review-page__expand dd {
  margin: 0;
  color: rgba(0, 0, 0, 0.88);
  font-variant-numeric: tabular-nums;
}

.review-page__actions {
  display: inline-flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 0;
}
```

并更新 `@media (max-width: 576px)` 中 `.review-page__file-cell { max-width: 200px; }`。

- [ ] **Step 3: 手工检查**

确认 CSS 无语法错误、类名与后续 JSX 一致。本任务不单独 commit（与 Task 2 一并提交亦可；若单独提交则 message：`style: add review list file/expand styles`）。

---

### Task 2: 主表列 + 行展开 + 操作「更多」

**Files:**
- Modify: `frontend/src/pages/ReviewPage.tsx`（`Table` columns / expandable / imports）
- Modify: `frontend/src/config/adminManualContent.ts`（`review-admin` intro）

**Interfaces:**
- Consumes: `formatCreatedAtShort`、CSS 类名、现有 `handleExport` / `openReviewLog` / `handleAuditReportExport` / `handleAuditReportDocxExport` / `deleteMut` / `setSelfCheckTask`
- Produces: 符合 spec 的列表 UI

- [ ] **Step 1: 补充 imports**

```tsx
import {
  // ...existing
  MoreOutlined,
} from '@ant-design/icons'
import {
  // ...existing
  Dropdown,
} from 'antd'
import type { MenuProps } from 'antd'
```

- [ ] **Step 2: 文件列渲染（合并方案类型）**

替换原「方案类型」列与「文件」列为一个「文件」列：

```tsx
{
  title: '文件',
  key: 'file',
  ellipsis: { showTitle: false },
  render: (_: unknown, row: ReviewTask) => {
    const scheme = `${row.scheme_category} / ${row.scheme_name}`
    const tip = `${row.original_filename}\n${scheme}\n#${row.id}`
    return (
      <Tooltip title={<span style={{ whiteSpace: 'pre-line' }}>{tip}</span>}>
        <div className="review-page__file-cell">
          <Typography.Text ellipsis className="review-page__filename">
            {row.original_filename}
          </Typography.Text>
          <span className="review-page__scheme-sub">{scheme}</span>
        </div>
      </Tooltip>
    )
  },
},
```

- [ ] **Step 3: 精简列集合**

`columns` 最终顺序：

1. 管理员：`用户名`（现有）
2. `文件`（上一步）
3. `状态`（现有 `taskStatusCell`）
4. `创建时间`：`width: 110`，`render: (_, row) => <Tooltip title={row.created_at}>{formatCreatedAtShort(row.created_at)}</Tooltip>`
5. `操作`（下一步）

**删除**独立列：`ID`、`方案类型`、`审核耗时(分钟)`、`消耗词元`。

- [ ] **Step 4: expandable 明细**

在 `Table` 上增加：

```tsx
expandable={{
  expandedRowRender: (row) => (
    <dl className="review-page__expand">
      {isAdmin ? (
        <>
          <div>
            <dt>任务 ID</dt>
            <dd>{row.id}</dd>
          </div>
          <div>
            <dt>方案类型</dt>
            <dd>{`${row.scheme_category} / ${row.scheme_name}`}</dd>
          </div>
          <div>
            <dt>审核耗时(分钟)</dt>
            <dd>{formatDurationMinutes(row.duration_ms)}</dd>
          </div>
          <div>
            <dt>输入词元</dt>
            <dd>{formatTokenCount(row.input_tokens)}</dd>
          </div>
          <div>
            <dt>输出词元</dt>
            <dd>{formatTokenCount(row.output_tokens)}</dd>
          </div>
        </>
      ) : (
        <>
          <div>
            <dt>审核耗时(分钟)</dt>
            <dd>{formatDurationMinutes(row.duration_ms)}</dd>
          </div>
          <div>
            <dt>消耗词元</dt>
            <dd>{formatTokenCount(row.total_tokens)}</dd>
          </div>
        </>
      )}
    </dl>
  ),
}}
```

- [ ] **Step 5: 操作列 Dropdown**

操作列 `width: isAdmin ? 200 : 160`，结构示意：

```tsx
{
  title: '操作',
  key: 'act',
  width: isAdmin ? 200 : 160,
  render: (_: unknown, row: ReviewTask) => {
    const taskEnded = row.status === 'succeeded' || row.status === 'failed'
    const moreItems: MenuProps['items'] = [
      {
        key: 'audit-report',
        icon: <ProfileOutlined />,
        label: '审核报告',
        disabled: !taskEnded,
        onClick: () => void handleAuditReportExport(row),
      },
      ...(isAdmin
        ? [
            {
              key: 'log',
              icon: <FileTextOutlined />,
              label: '审核日志',
              onClick: () => void openReviewLog(row.id),
            },
            {
              key: 'self-check',
              icon: <SafetyCertificateOutlined />,
              label: 'AI测评',
              disabled: row.status !== 'succeeded',
              onClick: () => setSelfCheckTask(row),
            },
            {
              key: 'docx-report',
              icon: <FileWordOutlined />,
              label: 'Word 报告',
              disabled: !taskEnded,
              onClick: () => void handleAuditReportDocxExport(row),
            },
            { type: 'divider' as const },
            {
              key: 'delete',
              icon: <DeleteOutlined />,
              label: '删除',
              danger: true,
              onClick: () => {
                /* 不用 onClick 直接删：见下方 Popconfirm 包一层自定义项，或 Dropdown.destroyPopupOnHide + 行内 Popconfirm 触发 */
              },
            },
          ]
        : []),
    ]
    // 删除：用 Dropdown 的 items 里 key=delete 配合 Modal.confirm，或把删除从菜单提出用 Popconfirm 包住 Dropdown 子项。
    // 推荐：删除项 onClick 里调用 Modal.confirm（AntApp.useApp().modal），与现有 Popconfirm 文案一致。
    return (
      <div className="review-page__actions">
        <Tooltip title={taskEnded ? undefined : '任务处理结束后（已完成或失败）可进入人工审阅'}>
          <Button type="link" size="small" icon={<AuditOutlined />} disabled={!taskEnded}
            onClick={() => navigate(`/review/${row.id}/manual`)}>
            人工审阅
          </Button>
        </Tooltip>
        <Tooltip title={taskEnded ? undefined : '任务处理结束后（已完成或失败）可导出方案'}>
          <Button type="link" size="small" icon={<ExportOutlined />} disabled={!taskEnded}
            onClick={() => void handleExport(row)}>
            导出方案
          </Button>
        </Tooltip>
        <Dropdown menu={{ items: moreItems }} trigger={['click']}>
          <Button type="link" size="small" icon={<MoreOutlined />}>
            更多
          </Button>
        </Dropdown>
      </div>
    )
  },
}
```

**删除交互（必须落地）：** 在 `ReviewPage` 内使用 `const { message, modal } = AntApp.useApp()`，删除菜单项：

```tsx
onClick: () => {
  modal.confirm({
    title: '删除该审核任务？',
    content: '将移除任务记录及已上传的文档，且不可恢复。',
    okText: '删除',
    okButtonProps: { danger: true },
    cancelText: '取消',
    onOk: () => deleteMut.mutateAsync(row.id),
  })
},
```

移除原操作列中的 `Popconfirm` 包装（逻辑等价）。

- [ ] **Step 6: 更新管理员手册文案**

`adminManualContent.ts` 中 `review-admin` 的 `intro` 改为：

```ts
'管理员在方案审核页可查看全部用户的任务（含「用户名」列）。主表精简为文件、状态、时间与常用操作；展开行可查看任务 ID、耗时与 Token（输入/输出）。低频操作（审核日志、报告、AI测评、删除等）收在「更多」菜单。',
```

- [ ] **Step 7: 手工验收**

1. 管理员登录 `/review`：主表无 ID / 方案类型 / 耗时 / 词元独立列；有展开箭头。
2. 展开一行可见 ID、方案类型、耗时、输入/输出词元。
3. 操作仅「人工审阅」「导出方案」「更多」；更多内功能可用且禁用条件正确。
4. 普通用户：无用户名；更多仅「审核报告」；展开为耗时 + 总词元。
5. `npm run build`（或项目既有 frontend typecheck）通过。

- [ ] **Step 8: Commit（仅当用户要求提交时执行）**

```bash
git add frontend/src/pages/ReviewPage.tsx frontend/src/pages/ReviewPage.css frontend/src/config/adminManualContent.ts docs/superpowers/specs/2026-08-28-review-list-admin-columns-design.md docs/superpowers/plans/2026-08-28-review-list-admin-columns.md
git commit -m "$(cat <<'EOF'
简化方案审核列表：主表精简列并将低频操作收入更多菜单。

EOF
)"
```

---

## Spec coverage (self-review)

| Spec 要求 | Task |
|-----------|------|
| 主表列精简 + 文件合并方案类型 | Task 2 |
| 短时间格式 | Task 1–2 |
| 行展开次要指标 | Task 2 |
| 操作主按钮 + 更多 | Task 2 |
| 手册文案 | Task 2 Step 6 |
| 不改 API | 全局约束 |

无占位符；删除改用 `modal.confirm` 与 Popconfirm 文案对齐。
