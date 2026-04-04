import {
  ArrowDownOutlined,
  DownloadOutlined,
  EditOutlined,
  RollbackOutlined,
} from '@ant-design/icons'
import {
  App as AntApp,
  Button,
  Card,
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
import type { ReportStep, ReviewReportV1, ReviewTask } from '../api/types'

const STEP_LABELS: Record<string, string> = {
  structure: '结构审核',
  compilation_basis: '编制依据审核',
  context_consistency: '上下文一致性',
  content: '内容审核',
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

async function downloadWordV2(taskId: number): Promise<void> {
  const { data } = await api.get<{ url: string }>(
    `/review-tasks/${taskId}/output-download-url`,
  )
  const res = await fetch(data.url)
  if (!res.ok) throw new Error('下载失败')
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'word_v2.docx'
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

  const report = useMemo(() => parseReport(task?.review_result_json), [task])

  const steps: ReportStep[] = report?.steps ?? []

  const canExport = Boolean(task?.output_object_key?.trim())

  const handleExport = async () => {
    if (!task) return
    try {
      await downloadWordV2(task.id)
      message.success('已开始下载 word_v2.docx')
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
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Spin />
      </div>
    )
  }

  const activeStep = steps[Math.min(selectedIdx, Math.max(0, steps.length - 1))]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 'calc(100vh - 120px)' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 16,
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <Space>
          <Button icon={<RollbackOutlined />} onClick={() => navigate('/review')}>
            返回
          </Button>
          <Typography.Title level={4} style={{ margin: 0 }}>
            人工审阅 — 任务 #{task.id}
          </Typography.Title>
          <Typography.Text type="secondary">
            {task.scheme_category} / {task.scheme_name}
          </Typography.Text>
        </Space>
        <Space>
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

      <div style={{ display: 'flex', gap: 24, flex: 1, minHeight: 0 }}>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            paddingTop: 8,
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

        <Card style={{ flex: 1, overflow: 'auto' }} title="审核详情">
          {task.error_message && task.status === 'failed' ? (
            <Typography.Paragraph type="danger" style={{ marginBottom: 16 }}>
              {task.error_message}
            </Typography.Paragraph>
          ) : null}
          {!activeStep ? (
            <Typography.Paragraph type="secondary">
              等待任务完成或报告生成…
            </Typography.Paragraph>
          ) : (
            <>
              <Space style={{ marginBottom: 12 }}>
                <Tag color={activeStep.passed ? 'success' : 'error'}>
                  {activeStep.passed ? '通过' : '有问题'}
                </Tag>
                <Typography.Text type="secondary">{activeStep.summary}</Typography.Text>
              </Space>
              <Typography.Title level={5}>问题列表</Typography.Title>
              {activeStep.issues.length === 0 ? (
                <Typography.Text type="secondary">本步骤无问题项</Typography.Text>
              ) : (
                <List
                  dataSource={activeStep.issues}
                  renderItem={(it) => (
                    <List.Item>
                      <List.Item.Meta
                        title={
                          <Space wrap>
                            <Tag>{it.severity}</Tag>
                            <span>{it.message}</span>
                          </Space>
                        }
                        description={
                          <div>
                            {it.evidence ? (
                              <pre
                                style={{
                                  marginTop: 8,
                                  whiteSpace: 'pre-wrap',
                                  fontSize: 12,
                                  background: 'var(--ant-color-fill-quaternary)',
                                  padding: 8,
                                  borderRadius: 6,
                                }}
                              >
                                {it.evidence}
                              </pre>
                            ) : null}
                            {it.anchor && Object.keys(it.anchor).length > 0 ? (
                              <pre
                                style={{
                                  marginTop: 8,
                                  fontSize: 11,
                                  opacity: 0.85,
                                }}
                              >
                                {JSON.stringify(it.anchor, null, 2)}
                              </pre>
                            ) : null}
                          </div>
                        }
                      />
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
