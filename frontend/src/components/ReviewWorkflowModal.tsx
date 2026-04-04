import { App as AntApp, Button, Modal, Space, Switch, Typography } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { ReviewWorkflowData, TemplatePublic, WorkflowStepId } from '../api/types'

const LABELS: Record<WorkflowStepId, string> = {
  start: '起点',
  structure: '结构审核',
  compilation_basis: '编制依据',
  context_consistency: '上下文一致性',
  content: '内容审核',
  end: '结束',
}

const SLOT_ORDER: WorkflowStepId[] = [
  'start',
  'structure',
  'compilation_basis',
  'context_consistency',
  'content',
  'end',
]

function compileSteps(
  includeBasis: boolean,
  includeContext: boolean,
  includeContent: boolean,
  contentBeforeContext: boolean,
): WorkflowStepId[] {
  const mid: WorkflowStepId[] = []
  if (includeBasis) mid.push('compilation_basis')
  if (includeContext && includeContent) {
    if (contentBeforeContext) mid.push('content', 'context_consistency')
    else mid.push('context_consistency', 'content')
  } else if (includeContext) mid.push('context_consistency')
  else if (includeContent) mid.push('content')
  return ['start', 'structure', ...mid, 'end']
}

function isValidServerSteps(raw: unknown): raw is WorkflowStepId[] {
  if (!Array.isArray(raw) || raw.length < 3) return false
  const allowed = new Set<string>([
    'start',
    'structure',
    'compilation_basis',
    'context_consistency',
    'content',
    'end',
  ])
  if (raw.some((x) => typeof x !== 'string' || !allowed.has(x))) return false
  if (raw[0] !== 'start' || raw[1] !== 'structure' || raw[raw.length - 1] !== 'end') return false
  if (new Set(raw).size !== raw.length) return false
  const mid = raw.slice(2, -1)
  const optMid = new Set(['compilation_basis', 'context_consistency', 'content'])
  if (mid.some((m) => !optMid.has(m))) return false
  if (mid.filter((m) => m === 'compilation_basis').length > 1) return false
  if (mid.includes('compilation_basis') && mid[0] !== 'compilation_basis') return false
  const rest = mid.filter((m) => m !== 'compilation_basis')
  if (rest.length === 2) {
    const s = new Set(rest)
    if (s.size !== 2 || !s.has('context_consistency') || !s.has('content')) return false
  } else if (rest.length === 1) {
    if (rest[0] !== 'context_consistency' && rest[0] !== 'content') return false
  }
  return true
}

function parseSteps(steps: WorkflowStepId[]): {
  includeBasis: boolean
  includeContext: boolean
  includeContent: boolean
  contentBeforeContext: boolean
} {
  const includeBasis = steps.includes('compilation_basis')
  const includeContext = steps.includes('context_consistency')
  const includeContent = steps.includes('content')
  let contentBeforeContext = false
  if (includeContext && includeContent) {
    contentBeforeContext = steps.indexOf('content') < steps.indexOf('context_consistency')
  }
  return { includeBasis, includeContext, includeContent, contentBeforeContext }
}

const ROW_CENTERS = [44, 118, 192, 266, 340, 414]
const CANVAS_W = 440
const CX = CANVAS_W / 2
const CARD_H = 52
const HALF = CARD_H / 2

type Props = {
  open: boolean
  schemeName: string
  schemeTypeId: number
  template: TemplatePublic | null
  loading: boolean
  onClose: () => void
  onSaved: (t: TemplatePublic) => void
}

function WorkflowCanvas({ steps }: { steps: WorkflowStepId[] }) {
  const active = useMemo(() => new Set(steps), [steps])

  const segments = useMemo(() => {
    const out: { y1: number; y2: number }[] = []
    for (let i = 0; i < steps.length - 1; i++) {
      const ia = SLOT_ORDER.indexOf(steps[i])
      const ib = SLOT_ORDER.indexOf(steps[i + 1])
      if (ia < 0 || ib < 0) continue
      out.push({
        y1: ROW_CENTERS[ia] + HALF,
        y2: ROW_CENTERS[ib] - HALF,
      })
    }
    return out
  }, [steps])

  return (
    <div
      style={{
        position: 'relative',
        width: CANVAS_W,
        minHeight: 452,
        margin: '0 auto',
        background:
          'linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px)',
        backgroundSize: '20px 20px',
        borderRadius: 12,
        border: '1px solid var(--ant-color-border-secondary, #f0f0f0)',
      }}
    >
      <svg
        width={CANVAS_W}
        height={452}
        style={{ position: 'absolute', left: 0, top: 0, pointerEvents: 'none' }}
      >
        <defs>
          <marker
            id="workflow-arrow"
            markerWidth="8"
            markerHeight="8"
            refX="6"
            refY="4"
            orient="auto"
            markerUnits="strokeWidth"
          >
            <path d="M0,0 L8,4 L0,8 z" fill="#64748b" />
          </marker>
        </defs>
        {segments.map((s, i) => (
          <line
            key={i}
            x1={CX}
            y1={s.y1}
            x2={CX}
            y2={s.y2}
            stroke="#94a3b8"
            strokeWidth={2}
            markerEnd="url(#workflow-arrow)"
          />
        ))}
      </svg>
      {SLOT_ORDER.map((id, idx) => {
        const inPath = active.has(id)
        const optional =
          id === 'compilation_basis' || id === 'context_consistency' || id === 'content'
        const dim = optional && !inPath
        const top = ROW_CENTERS[idx] - HALF
        return (
          <div
            key={id}
            style={{
              position: 'absolute',
              left: CX - 108,
              top,
              width: 216,
              height: CARD_H,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 10,
              border: dim ? '2px dashed var(--ant-color-border, #d9d9d9)' : '2px solid #3b82f6',
              background: dim ? 'rgba(0,0,0,0.02)' : 'var(--ant-color-bg-container, #fff)',
              boxShadow: dim ? 'none' : '0 2px 8px rgba(59,130,246,0.12)',
              opacity: dim ? 0.45 : 1,
              fontWeight: 600,
              fontSize: 14,
              zIndex: 1,
            }}
          >
            {LABELS[id]}
          </div>
        )
      })}
    </div>
  )
}

export default function ReviewWorkflowModal({
  open,
  schemeName,
  schemeTypeId,
  template,
  loading,
  onClose,
  onSaved,
}: Props) {
  const { message } = AntApp.useApp()
  const [includeBasis, setIncludeBasis] = useState(false)
  const [includeContext, setIncludeContext] = useState(false)
  const [includeContent, setIncludeContent] = useState(false)
  const [contentBeforeContext, setContentBeforeContext] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open || !template) return
    const raw = template.review_workflow?.steps
    if (isValidServerSteps(raw)) {
      const p = parseSteps(raw)
      setIncludeBasis(p.includeBasis)
      setIncludeContext(p.includeContext)
      setIncludeContent(p.includeContent)
      setContentBeforeContext(p.contentBeforeContext)
    } else {
      setIncludeBasis(false)
      setIncludeContext(false)
      setIncludeContent(false)
      setContentBeforeContext(false)
    }
  }, [open, template?.id, template?.updated_at, template?.review_workflow])

  const steps = useMemo(
    () => compileSteps(includeBasis, includeContext, includeContent, contentBeforeContext),
    [includeBasis, includeContext, includeContent, contentBeforeContext],
  )

  async function handleSave() {
    setSaving(true)
    try {
      const body: { review_workflow: ReviewWorkflowData } = {
        review_workflow: { steps },
      }
      const { data } = await api.put<TemplatePublic>(
        `/scheme-types/${schemeTypeId}/template/review-workflow`,
        body,
      )
      message.success('审核工作流已保存')
      onSaved(data)
      onClose()
    } catch (err: unknown) {
      const raw =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined
      let text = '保存失败'
      if (typeof raw === 'string') text = raw
      else if (Array.isArray(raw)) {
        const parts = raw.map((x) =>
          x && typeof x === 'object' && 'msg' in x ? String((x as { msg: unknown }).msg) : JSON.stringify(x),
        )
        text = parts.join('；')
      }
      message.error(text)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title={`审核工作流 — ${schemeName}`}
      open={open}
      onCancel={onClose}
      width="min(560px, 96vw)"
      centered
      destroyOnClose
      footer={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            起点与结构审核必选；编制依据可选且位于中间步骤最前；可再开启上下文/内容并调整二者顺序
          </Typography.Text>
          <Space>
            <Button onClick={onClose}>取消</Button>
            <Button type="primary" loading={saving} disabled={loading || !template} onClick={handleSave}>
              保存
            </Button>
          </Space>
        </div>
      }
    >
      {loading ? (
        <Typography.Text type="secondary">加载模版信息…</Typography.Text>
      ) : !template ? (
        <Typography.Text type="secondary">请先上传 Word 模版后再配置工作流</Typography.Text>
      ) : (
        <div>
          <WorkflowCanvas steps={steps} />
          <div style={{ marginTop: 20, padding: '12px 16px', background: '#fafafa', borderRadius: 8 }}>
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Typography.Text>{LABELS.compilation_basis}</Typography.Text>
                <Switch checked={includeBasis} onChange={setIncludeBasis} />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Typography.Text>{LABELS.context_consistency}</Typography.Text>
                <Switch checked={includeContext} onChange={setIncludeContext} />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Typography.Text>{LABELS.content}</Typography.Text>
                <Switch checked={includeContent} onChange={setIncludeContent} />
              </div>
              {includeContext && includeContent ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                    执行顺序
                  </Typography.Text>
                  <Button size="small" onClick={() => setContentBeforeContext((v) => !v)}>
                    {contentBeforeContext
                      ? '当前：内容审核 → 上下文一致性'
                      : '当前：上下文一致性 → 内容审核'}
                  </Button>
                </div>
              ) : null}
            </Space>
          </div>
        </div>
      )}
    </Modal>
  )
}
