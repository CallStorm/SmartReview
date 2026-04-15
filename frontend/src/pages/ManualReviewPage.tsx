import {
  ArrowDownOutlined,
  DownloadOutlined,
  EditOutlined,
  EyeOutlined,
  RollbackOutlined,
} from '@ant-design/icons'
import {
  App as AntApp,
  Button,
  Card,
  Collapse,
  Empty,
  List,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { ReportStep, ReviewReportV1, ReviewSettings, ReviewTask } from '../api/types'
import StructureReviewDetail from '../components/StructureReviewDetail'
import { buildReviewExportFilename } from '../utils/reviewExportFilename'

const STEP_LABELS: Record<string, string> = {
  structure: '结构审核',
  compilation_basis: '编制依据审核',
  context_consistency: '上下文一致性',
  content: '内容审核',
}

const SEVERITY_META: Record<string, { label: string; color: string }> = {
  error: { label: '严重', color: 'red' },
  warning: { label: '警告', color: 'gold' },
  info: { label: '提示', color: 'blue' },
}

function asStringArray(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.map((x) => String(x ?? '').trim()).filter(Boolean)
}

function extractStandardsText(text: string): string[] {
  if (!text.trim()) return []
  const regex =
    /\b(?:GB|JGJ|DBJ|DB|CECS|T\/[A-Z]+)\s*[\-\/]?\s*\d{2,6}(?:\.\d+)?(?:-\d{4})?\b/gi
  const hits = text.match(regex) ?? []
  return Array.from(new Set(hits.map((x) => x.replace(/\s+/g, ' ').trim())))
}

function extractAiSuggestions(related: Record<string, unknown> | undefined): string[] {
  if (!related) return []
  const out: string[] = []
  const pushText = (v: unknown) => {
    const s = String(v ?? '').trim()
    if (s) out.push(s)
  }
  const arr = related.suggestions
  if (Array.isArray(arr)) {
    arr.forEach((x) => pushText(x))
  }
  pushText(related.suggestion)
  pushText(related.optimize_suggestion)
  pushText(related.optimization_suggestion)
  return Array.from(new Set(out))
}

function parseReport(json: string | null | undefined): ReviewReportV1 | null {
  if (!json?.trim()) return null
  try {
    const o = JSON.parse(json) as ReviewReportV1
    if (!o || !Array.isArray(o.steps)) return null
    return o
  } catch {
    return null
  }
}

async function downloadWordV2(taskId: number, downloadName: string): Promise<void> {
  const { data } = await api.get<{ url: string }>(
    `/review-tasks/${taskId}/output-download-url`,
  )
  const res = await fetch(data.url)
  if (!res.ok) throw new Error('下载失败')
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = downloadName
  a.rel = 'noopener'
  a.click()
  URL.revokeObjectURL(a.href)
}

export default function ManualReviewPage() {
  const { taskId } = useParams<{ taskId: string }>()
  const id = Number(taskId)
  const navigate = useNavigate()
  const { message } = AntApp.useApp()
  const [selectedIdx, setSelectedIdx] = useState(0)

  const { data: task, isLoading } = useQuery({
    queryKey: ['review-task', id],
    queryFn: async () => {
      const { data } = await api.get<ReviewTask>(`/review-tasks/${id}`)
      return data
    },
    enabled: Number.isFinite(id) && id > 0,
    refetchInterval: (q) =>
      q.state.data?.status === 'pending' || q.state.data?.status === 'processing'
        ? 3000
        : false,
  })
  const { data: reviewSettings } = useQuery({
    queryKey: ['settings', 'review'],
    queryFn: async () => {
      const { data } = await api.get<ReviewSettings>('/settings/review')
      return data
    },
  })

  const report = useMemo(() => parseReport(task?.review_result_json), [task])

  const steps: ReportStep[] = report?.steps ?? []

  const canExport = Boolean(task?.output_object_key?.trim())

  const handleExport = async () => {
    if (!task) return
    try {
      const name = buildReviewExportFilename(task.original_filename)
      await downloadWordV2(task.id, name)
      message.success(`已开始下载 ${name}`)
    } catch {
      message.error('导出失败（可能尚无批注文档）')
    }
  }

  if (!Number.isFinite(id) || id <= 0) {
    return (
      <Typography.Text type="danger">无效的任务 ID</Typography.Text>
    )
  }

  if (isLoading || !task) {
    return (
      <div
        style={{
          height: '100%',
          minHeight: 0,
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#fff',
        }}
      >
        <Spin />
      </div>
    )
  }

  const activeStep = steps[Math.min(selectedIdx, Math.max(0, steps.length - 1))]
  const activeDebugPrompts =
    task.debug_prompts?.filter((p) => p.step_id === activeStep?.step_id) ?? []

  return (
    <div
      style={{
        height: '100%',
        minHeight: 0,
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        background: '#fff',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
          flexWrap: 'wrap',
          gap: 12,
          padding: '10px 16px',
          borderBottom: '1px solid #f0f0f0',
        }}
      >
        <Space align="start" size={12} wrap>
          <Button icon={<RollbackOutlined />} onClick={() => navigate('/review')}>
            返回
          </Button>
          <div style={{ minWidth: 0 }}>
            <Typography.Title level={4} style={{ margin: 0 }}>
              {activeStep?.step_id === 'structure'
                ? `人工审阅 · ${STEP_LABELS.structure}`
                : `人工审阅 — 任务 #${task.id}`}
            </Typography.Title>
            <Typography.Text
              type="secondary"
              style={{ display: 'block', fontSize: 13, marginTop: 2 }}
            >
              方案审核 / {task.original_filename?.trim() || '未命名文档'} /{' '}
              {activeStep
                ? STEP_LABELS[activeStep.step_id] ?? activeStep.step_id
                : '—'}
            </Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              {activeStep?.step_id === 'structure'
                ? `任务 #${task.id} · ${task.scheme_category} / ${task.scheme_name}`
                : `${task.scheme_category} / ${task.scheme_name}`}
            </Typography.Text>
          </div>
        </Space>
        <Space>
          <Button
            icon={<EyeOutlined />}
            disabled={!canExport}
            onClick={() => navigate(`/review/${task.id}/preview`)}
          >
            预览
          </Button>
          <Button
            icon={<EditOutlined />}
            disabled={!canExport}
            onClick={() => navigate(`/review/${task.id}/edit`)}
          >
            编辑
          </Button>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            disabled={!canExport}
            onClick={() => void handleExport()}
          >
            导出 Word
          </Button>
        </Space>
      </div>

      <div style={{ display: 'flex', gap: 0, flex: 1, minHeight: 0 }}>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            flexShrink: 0,
            padding: '12px 10px 12px 12px',
            borderRight: '1px solid #f0f0f0',
          }}
        >
          {steps.length === 0 ? (
            <Empty description="暂无审核步骤数据" />
          ) : (
            steps.map((s, i) => (
              <div
                key={`${s.step_id}-${i}`}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                }}
              >
                <Button
                  type="default"
                  shape="circle"
                  size="large"
                  onClick={() => setSelectedIdx(i)}
                  style={{
                    width: 48,
                    height: 48,
                    borderColor: s.passed ? '#52c41a' : '#ff4d4f',
                    color: s.passed ? '#52c41a' : '#ff4d4f',
                    fontWeight: 600,
                    background: selectedIdx === i ? 'rgba(22, 119, 255, 0.08)' : undefined,
                  }}
                >
                  {i + 1}
                </Button>
                <Typography.Text
                  style={{
                    marginTop: 6,
                    fontSize: 12,
                    maxWidth: 88,
                    textAlign: 'center',
                  }}
                >
                  {STEP_LABELS[s.step_id] ?? s.step_id}
                </Typography.Text>
                {i < steps.length - 1 && (
                  <ArrowDownOutlined
                    style={{ margin: '8px 0', color: 'rgba(0,0,0,0.35)' }}
                  />
                )}
              </div>
            ))
          )}
        </div>

        <Card
          style={{
            flex: 1,
            minWidth: 0,
            display: 'flex',
            flexDirection: 'column',
            borderRadius: 0,
            border: 'none',
            boxShadow: 'none',
          }}
          styles={{ body: { flex: 1, overflow: 'auto', padding: 16 } }}
          title="审核详情"
        >
          {task.error_message && task.status === 'failed' ? (
            <Typography.Paragraph type="danger" style={{ marginBottom: 16 }}>
              {task.error_message}
            </Typography.Paragraph>
          ) : null}
          {!activeStep ? (
            <Typography.Paragraph type="secondary">
              等待任务完成或报告生成…
            </Typography.Paragraph>
          ) : activeStep.step_id === 'structure' ? (
            <StructureReviewDetail
              task={task}
              step={activeStep}
              onNavigateEdit={() => navigate(`/review/${task.id}/edit`)}
            />
          ) : (
            <>
              <Space style={{ marginBottom: 12 }}>
                <Tag color={activeStep.passed ? 'success' : 'error'}>
                  {activeStep.passed ? '通过' : '有问题'}
                </Tag>
                <Typography.Text type="secondary">{activeStep.summary}</Typography.Text>
              </Space>
              {reviewSettings?.prompt_debug_enabled ? (
                <>
                  <Typography.Title level={5}>拼接提示词（调试）</Typography.Title>
                  {activeDebugPrompts.length === 0 ? (
                    <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
                      未开启调试开关，或该任务在开启前执行，暂无可展示提示词。
                    </Typography.Text>
                  ) : (
                    <Collapse
                      style={{ marginBottom: 16 }}
                      items={activeDebugPrompts.map((item, idx) => ({
                        key: `${item.step_id}-${item.template_node_id}-${idx}`,
                        label: item.template_node_id
                          ? `节点 ${item.template_node_id} · ${item.prompt_length} 字符`
                          : `提示词 #${idx + 1} · ${item.prompt_length} 字符`,
                        children: (
                          <pre
                            style={{
                              margin: 0,
                              whiteSpace: 'pre-wrap',
                              fontSize: 12,
                              background: 'var(--ant-color-fill-quaternary)',
                              padding: 8,
                              borderRadius: 6,
                            }}
                          >
                            {item.prompt_text}
                          </pre>
                        ),
                      }))}
                    />
                  )}
                </>
              ) : null}
              <Typography.Title level={5}>问题列表</Typography.Title>
              {activeStep.issues.length === 0 ? (
                <Typography.Text type="secondary">本步骤无问题项</Typography.Text>
              ) : (
                <List
                  dataSource={activeStep.issues}
                  renderItem={(it) => (
                    <List.Item>
                      {(() => {
                        const titlePath = asStringArray(it.anchor?.title_path)
                        const templateNodeId =
                          it.anchor?.template_node_id !== undefined &&
                          it.anchor?.template_node_id !== null
                            ? String(it.anchor.template_node_id)
                            : ''
                        const headingParaIndex =
                          it.anchor?.heading_para_index !== undefined &&
                          it.anchor?.heading_para_index !== null
                            ? String(it.anchor.heading_para_index)
                            : ''
                        const userTitle =
                          it.anchor?.user_title !== undefined && it.anchor?.user_title !== null
                            ? String(it.anchor.user_title)
                            : ''
                        const relatedEntries = Object.entries(it.related ?? {}).filter(
                          ([, v]) => v !== undefined && v !== null && String(v).trim().length > 0,
                        )
                        const relatedText = relatedEntries
                          .map(([k, v]) => `${k}=${String(v)}`)
                          .join('；')
                        const standards = Array.from(
                          new Set(
                            [
                              ...extractStandardsText(it.message ?? ''),
                              ...extractStandardsText(it.evidence ?? ''),
                              ...extractStandardsText(relatedText),
                            ].filter(Boolean),
                          ),
                        )
                        const suggestions = extractAiSuggestions(it.related)
                        const showStandardReference = activeStep?.step_id === 'compilation_basis'
                        return (
                          <Card
                            size="small"
                            style={{
                              width: '100%',
                              borderRadius: 8,
                              background: '#fff',
                              boxShadow: '0 1px 3px rgba(0, 0, 0, 0.06)',
                            }}
                          >
                            <div style={{ marginBottom: 10 }}>
                              <Space wrap>
                                <Tag color={SEVERITY_META[it.severity]?.color ?? 'default'}>
                                  {SEVERITY_META[it.severity]?.label ?? it.severity}
                                </Tag>
                                <Typography.Text strong>问题：{it.message}</Typography.Text>
                              </Space>
                              {!!it.evidence?.trim() && (
                                <Typography.Paragraph
                                  type="secondary"
                                  style={{ marginTop: 8, marginBottom: 0 }}
                                >
                                  原因：{it.evidence}
                                </Typography.Paragraph>
                              )}
                            </div>

                            <div
                              style={{
                                marginBottom: 10,
                                padding: '10px 12px',
                                borderRadius: 6,
                                background: 'var(--ant-color-fill-quaternary)',
                              }}
                            >
                              <Typography.Text strong style={{ fontSize: 12 }}>
                                定位数据
                              </Typography.Text>
                              <ul style={{ margin: '8px 0 0 18px', padding: 0 }}>
                                {titlePath.length > 0 && <li>章节：{titlePath.join(' > ')}</li>}
                                {!!templateNodeId && <li>模板节点：{templateNodeId}</li>}
                                {!!userTitle && <li>文档标题：{userTitle}</li>}
                                {!!headingParaIndex && <li>段落索引：{headingParaIndex}</li>}
                                {!!relatedText && <li>附加依据：{relatedText}</li>}
                              </ul>
                            </div>

                            <div
                              style={{
                                padding: '10px 12px',
                                borderRadius: 6,
                                background: '#f6ffed',
                                border: '1px solid #d9f7be',
                              }}
                            >
                              <Typography.Text strong style={{ fontSize: 12 }}>
                                优化建议
                              </Typography.Text>
                              <ul style={{ margin: '8px 0 0 18px', padding: 0 }}>
                                {suggestions.length > 0 ? (
                                  suggestions.map((s, idx) => (
                                    <li key={`${it.issue_id || it.message}-s-${idx}`}>{s}</li>
                                  ))
                                ) : (
                                  <li>模型未返回整改建议，请在模板提示词中补充“输出 suggestions”。</li>
                                )}
                              </ul>
                              {showStandardReference ? (
                                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                                  规范参考：
                                  {standards.length > 0
                                    ? standards.map((s) => ` ${s}`).join('；')
                                    : ' 未识别到明确规范编号，建议补充引用条款（如 GB 50204、JGJ 162 等）。'}
                                </Typography.Text>
                              ) : null}
                            </div>

                            {it.anchor && Object.keys(it.anchor).length > 0 ? (
                              <Collapse
                                ghost
                                style={{ marginTop: 4 }}
                                items={[
                                  {
                                    key: 'raw-anchor',
                                    label: '查看原始定位数据',
                                    children: (
                                      <pre
                                        style={{
                                          marginTop: 0,
                                          marginBottom: 0,
                                          fontSize: 11,
                                          opacity: 0.85,
                                          whiteSpace: 'pre-wrap',
                                          wordBreak: 'break-word',
                                        }}
                                      >
                                        {JSON.stringify(it.anchor, null, 2)}
                                      </pre>
                                    ),
                                  },
                                ]}
                              />
                            ) : null}
                          </Card>
                        )
                      })()}
                    </List.Item>
                  )}
                />
              )}
            </>
          )}
        </Card>
      </div>
    </div>
  )
}
