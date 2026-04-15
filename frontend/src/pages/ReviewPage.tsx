import './ReviewPage.css'

import {
  AuditOutlined,
  CloudDownloadOutlined,
  DeleteOutlined,
  ExportOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  UploadOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import {
  App as AntApp,
  Button,
  Form,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from 'antd'
import type { UploadFile } from 'antd/es/upload/interface'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { ReviewTask, SchemeType } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import PageShell from '../components/PageShell'
import { DEFAULT_TABLE_PAGINATION } from '../config/tablePagination'
import { buildReviewExportFilename } from '../utils/reviewExportFilename'

const statusLabel: Record<string, string> = {
  pending: '排队中',
  processing: '处理中',
  succeeded: '已完成',
  failed: '失败',
}

const REVIEW_STAGE_LABELS: Record<string, string> = {
  structure: '结构审核',
  compilation_basis: '编制依据审核',
  context_consistency: '上下文一致性',
  content: '内容审核',
}

const tagSx = { border: 'none', marginInlineEnd: 0 } as const

function pillTag(text: string, background: string, color: string) {
  return (
    <Tag style={{ ...tagSx, background, color }}>
      {text}
    </Tag>
  )
}

function statusTag(status: string) {
  if (status === 'succeeded') {
    return pillTag(statusLabel[status] ?? status, '#f6ffed', '#237804')
  }
  if (status === 'failed') {
    return pillTag(statusLabel[status] ?? status, '#fff2f0', '#a8071a')
  }
  return pillTag(statusLabel[status] ?? status, '#e6f4ff', '#0958d9')
}

function taskStatusCell(row: ReviewTask) {
  if (row.status === 'processing' && row.review_stage) {
    const label = REVIEW_STAGE_LABELS[row.review_stage] ?? row.review_stage
    if (row.review_stage === 'content') {
      return pillTag(label, '#fff7e6', '#d46b08')
    }
    return pillTag(label, '#e6f4ff', '#0958d9')
  }
  return statusTag(row.status)
}

function formatDurationMinutes(durationMs?: number | null): string {
  if (typeof durationMs !== 'number' || !Number.isFinite(durationMs) || durationMs < 0) {
    return '—'
  }
  return (durationMs / 60000).toFixed(1)
}

function formatTokenCount(value?: number | null): string {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
    return '—'
  }
  return String(value)
}

function tokensCell(row: ReviewTask, isAdmin: boolean) {
  if (isAdmin) {
    return (
      <div className="review-page__tokens-split">
        <span>
          输入 <span className="review-page__tokens-num">{formatTokenCount(row.input_tokens)}</span>
        </span>
        <span>
          输出 <span className="review-page__tokens-num">{formatTokenCount(row.output_tokens)}</span>
        </span>
      </div>
    )
  }
  return formatTokenCount(row.total_tokens)
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

export default function ReviewPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { message } = AntApp.useApp()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const [schemeId, setSchemeId] = useState<number | null>(null)
  const [submitOpen, setSubmitOpen] = useState(false)
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [logModalTaskId, setLogModalTaskId] = useState<number | null>(null)
  const [logLoading, setLogLoading] = useState(false)
  const [logContent, setLogContent] = useState<string | null>(null)

  const { data: schemes = [], isLoading: schemesLoading } = useQuery({
    queryKey: ['schemes'],
    queryFn: async () => {
      const { data: rows } = await api.get<SchemeType[]>('/scheme-types')
      return rows
    },
  })

  const withTemplate = useMemo(
    () => schemes.filter((s) => s.template_configured),
    [schemes],
  )

  const {
    data: tasks = [],
    isLoading: tasksLoading,
  } = useQuery({
    queryKey: ['review-tasks'],
    queryFn: async () => {
      const { data } = await api.get<ReviewTask[]>('/review-tasks')
      return data
    },
    refetchInterval: (query) => {
      const rows = query.state.data
      if (!rows?.length) return 4000
      const active = rows.some(
        (r) => r.status === 'pending' || r.status === 'processing',
      )
      return active ? 3000 : false
    },
  })

  const reviewStats = useMemo(() => {
    const total = tasks.length
    const pendingManual = tasks.filter((t) => t.status === 'succeeded').length
    const anomaly = tasks.filter((t) => t.status === 'failed').length
    return { total, pendingManual, anomaly }
  }, [tasks])

  const submitMut = useMutation({
    mutationFn: async ({ sid, file }: { sid: number; file: File }) => {
      const fd = new FormData()
      fd.append('scheme_type_id', String(sid))
      fd.append('file', file)
      const { data } = await api.post<{ task: ReviewTask }>('/review-tasks', fd)
      return data
    },
    onSuccess: async () => {
      message.success('已提交审核任务')
      setSubmitOpen(false)
      setFileList([])
      await qc.invalidateQueries({ queryKey: ['review-tasks'] })
    },
    onError: (err: unknown) => {
      const detailMsg =
        err &&
        typeof err === 'object' &&
        'response' in err &&
        err.response &&
        typeof err.response === 'object' &&
        'data' in err.response &&
        err.response.data &&
        typeof err.response.data === 'object' &&
        'detail' in err.response.data
          ? String((err.response.data as { detail?: unknown }).detail)
          : ''
      message.error(detailMsg || '提交失败')
    },
  })

  const deleteMut = useMutation({
    mutationFn: async (taskId: number) => {
      await api.delete(`/review-tasks/${taskId}`)
    },
    onSuccess: async () => {
      message.success('已删除该审核任务')
      await qc.invalidateQueries({ queryKey: ['review-tasks'] })
    },
    onError: (err: unknown) => {
      const detailMsg =
        err &&
        typeof err === 'object' &&
        'response' in err &&
        err.response &&
        typeof err.response === 'object' &&
        'data' in err.response &&
        err.response.data &&
        typeof err.response.data === 'object' &&
        'detail' in err.response.data
          ? String((err.response.data as { detail?: unknown }).detail)
          : ''
      message.error(detailMsg || '删除失败')
    },
  })

  const handleDownloadTemplate = async () => {
    if (!schemeId) {
      message.warning('请先选择方案类型')
      return
    }
    try {
      const { data } = await api.get<{ url: string }>(
        `/scheme-types/${schemeId}/template/download-url`,
      )
      window.open(data.url, '_blank', 'noopener,noreferrer')
    } catch {
      message.warning('无法获取模版下载链接（该类型可能尚未上传模版）')
    }
  }

  const openSubmit = () => {
    if (!schemeId) {
      message.warning('请先选择方案类型')
      return
    }
    setFileList([])
    setSubmitOpen(true)
  }

  const confirmSubmit = () => {
    if (!schemeId) return
    const f = fileList[0]?.originFileObj
    if (!f) {
      message.warning('请选择要上传的 .docx 文件')
      return
    }
    submitMut.mutate({ sid: schemeId, file: f })
  }

  const openReviewLog = async (taskId: number) => {
    setLogModalTaskId(taskId)
    setLogLoading(true)
    setLogContent(null)
    try {
      const { data } = await api.get<ReviewTask>(`/review-tasks/${taskId}`)
      const text = data.review_log?.trim()
      setLogContent(text && text.length > 0 ? text : '暂无审核日志')
    } catch {
      message.error('加载审核日志失败')
      setLogContent(null)
    } finally {
      setLogLoading(false)
    }
  }

  const handleExport = async (row: ReviewTask) => {
    if (!row.output_object_key?.trim()) {
      message.warning('暂无带批注文档（任务未完成或结构审核未通过）')
      return
    }
    try {
      const name = buildReviewExportFilename(row.original_filename)
      await downloadWordV2(row.id, name)
      message.success(`已开始下载 ${name}`)
    } catch {
      message.error('导出失败')
    }
  }

  return (
    <div className="review-page">
      <PageShell
        icon={<FileSearchOutlined />}
        description="选择方案类型并上传 Word（.docx）发起智能审核；完成后可人工审阅、查看日志或导出带批注文档。"
      >
        <div className="review-page__stats">
          <div className="review-page__stat-card">
            <FileSearchOutlined className="review-page__stat-icon" aria-hidden />
            <div className="review-page__stat-body">
              <div className="review-page__stat-label">总审核数</div>
              <Typography.Title level={4} className="review-page__stat-value">
                {reviewStats.total}
              </Typography.Title>
            </div>
          </div>
          <div className="review-page__stat-card">
            <AuditOutlined className="review-page__stat-icon review-page__stat-icon--audit" aria-hidden />
            <div className="review-page__stat-body">
              <div className="review-page__stat-label">待人工审核</div>
              <Typography.Title level={4} className="review-page__stat-value">
                {reviewStats.pendingManual}
              </Typography.Title>
            </div>
          </div>
          <div className="review-page__stat-card">
            <WarningOutlined className="review-page__stat-icon review-page__stat-icon--warn" aria-hidden />
            <div className="review-page__stat-body">
              <div className="review-page__stat-label">审核异常</div>
              <Typography.Title level={4} className="review-page__stat-value">
                {reviewStats.anomaly}
              </Typography.Title>
            </div>
          </div>
        </div>

        <div className="review-page__filters">
          <Space wrap size="middle">
            <Select
              placeholder="选择方案类型"
              loading={schemesLoading}
              style={{ minWidth: 260 }}
              allowClear
              value={schemeId ?? undefined}
              onChange={(v) => setSchemeId(typeof v === 'number' ? v : null)}
              options={withTemplate.map((s) => ({
                value: s.id,
                label: `${s.category} / ${s.name}`,
              }))}
            />
            <Button icon={<CloudDownloadOutlined />} onClick={handleDownloadTemplate}>
              下载模版
            </Button>
            <Button type="primary" icon={<UploadOutlined />} onClick={openSubmit}>
              方案审核
            </Button>
          </Space>
        </div>

        <div className="review-page__table-wrap">
        <Table<ReviewTask>
          rowKey="id"
          size="middle"
          loading={tasksLoading}
          dataSource={tasks}
          locale={{ emptyText: '暂无审核任务' }}
          pagination={DEFAULT_TABLE_PAGINATION}
          columns={[
            { title: 'ID', dataIndex: 'id', width: 72 },
            ...(isAdmin
              ? [
                  {
                    title: '用户名',
                    key: 'owner_username',
                    width: 120,
                    ellipsis: true,
                    render: (_: unknown, row: ReviewTask) =>
                      row.owner_username?.trim() ? row.owner_username : '—',
                  },
                ]
              : []),
            {
              title: '方案类型',
              key: 'scheme',
              render: (_, row) => `${row.scheme_category} / ${row.scheme_name}`,
            },
            {
              title: '文件',
              key: 'original_filename',
              ellipsis: { showTitle: false },
              render: (_, row) => (
                <Tooltip title={row.original_filename}>
                  <Typography.Text ellipsis className="review-page__filename">
                    {row.original_filename}
                  </Typography.Text>
                </Tooltip>
              ),
            },
            {
              title: '状态',
              key: 'status',
              width: 130,
              render: (_, row) => taskStatusCell(row),
            },
            { title: '创建时间', dataIndex: 'created_at', width: 188 },
            {
              title: '审核耗时(分钟)',
              key: 'duration_ms',
              width: 132,
              align: 'right',
              render: (_, row) => formatDurationMinutes(row.duration_ms),
            },
            {
              title: '消耗词元',
              key: 'total_tokens',
              width: isAdmin ? 148 : 108,
              align: 'right',
              render: (_, row) => tokensCell(row, isAdmin),
            },
            {
              title: '操作',
              key: 'act',
              width: isAdmin ? 460 : 220,
              render: (_, row) => {
                const taskEnded =
                  row.status === 'succeeded' || row.status === 'failed'
                return (
                  <Space size="middle" wrap={false}>
                    <Tooltip
                      title={
                        taskEnded
                          ? undefined
                          : '任务处理结束后（已完成或失败）可进入人工审阅'
                      }
                    >
                      <Button
                        type="link"
                        size="small"
                        icon={<AuditOutlined />}
                        disabled={!taskEnded}
                        onClick={() => navigate(`/review/${row.id}/manual`)}
                      >
                        人工审阅
                      </Button>
                    </Tooltip>
                    {isAdmin ? (
                      <Button
                        type="link"
                        size="small"
                        icon={<FileTextOutlined />}
                        onClick={() => void openReviewLog(row.id)}
                      >
                        审核日志
                      </Button>
                    ) : null}
                    <Button
                      type="link"
                      size="small"
                      icon={<ExportOutlined />}
                      disabled={!row.output_object_key?.trim()}
                      onClick={() => void handleExport(row)}
                    >
                      导出报告
                    </Button>
                    {isAdmin ? (
                      <Popconfirm
                        title="删除该审核任务？"
                        description="将移除任务记录及已上传的文档，且不可恢复。"
                        okText="删除"
                        cancelText="取消"
                        okButtonProps={{
                          danger: true,
                          loading:
                            deleteMut.isPending &&
                            deleteMut.variables === row.id,
                        }}
                        onConfirm={() => deleteMut.mutate(row.id)}
                      >
                        <Button
                          type="link"
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                        >
                          删除
                        </Button>
                      </Popconfirm>
                    ) : null}
                  </Space>
                )
              },
            },
          ]}
        />
        </div>
      </PageShell>

      <Modal
        title="提交方案审核"
        open={submitOpen}
        onCancel={() => setSubmitOpen(false)}
        onOk={confirmSubmit}
        confirmLoading={submitMut.isPending}
        okText="提交"
        destroyOnClose
      >
        <p style={{ marginBottom: 12, color: 'rgba(0,0,0,0.55)', fontSize: 13 }}>
          将上传您编制的方案 Word（.docx），系统会创建异步任务并更新状态与结果。
        </p>
        <Form layout="vertical">
          <Form.Item label="方案类型" required>
            <Select
              disabled
              value={schemeId ?? undefined}
              options={withTemplate.map((s) => ({
                value: s.id,
                label: `${s.category} / ${s.name}`,
              }))}
              style={{ width: '100%' }}
            />
          </Form.Item>
          <Form.Item label="方案文件" required>
            <Upload.Dragger
              maxCount={1}
              accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              fileList={fileList}
              beforeUpload={(file) => {
                setFileList([
                  {
                    uid: file.uid,
                    name: file.name,
                    status: 'done',
                    originFileObj: file,
                  },
                ])
                return false
              }}
              onRemove={() => setFileList([])}
            >
              <p className="ant-upload-drag-icon">
                <UploadOutlined style={{ fontSize: 36, color: '#1677ff' }} />
              </p>
              <p className="ant-upload-text">点击或拖拽 .docx 到此处</p>
            </Upload.Dragger>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={logModalTaskId ? `审核日志 — 任务 #${logModalTaskId}` : '审核日志'}
        open={logModalTaskId !== null}
        onCancel={() => {
          setLogModalTaskId(null)
          setLogContent(null)
        }}
        footer={null}
        width={720}
        destroyOnClose
      >
        {logLoading ? (
          <Typography.Text type="secondary">加载中…</Typography.Text>
        ) : (
          <pre
            style={{
              margin: 0,
              maxHeight: 'min(60vh, 480px)',
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
              fontSize: 12,
              lineHeight: 1.5,
              padding: 12,
              background: 'var(--ant-color-fill-quaternary, rgba(0,0,0,0.04))',
              borderRadius: 8,
            }}
          >
            {logContent ?? ''}
          </pre>
        )}
      </Modal>
    </div>
  )
}
