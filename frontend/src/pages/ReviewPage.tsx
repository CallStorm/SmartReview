import {
  CloudDownloadOutlined,
  ExportOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import {
  App as AntApp,
  Button,
  Descriptions,
  Form,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd'
import type { UploadFile } from 'antd/es/upload/interface'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '../api/client'
import type { ReviewTask, SchemeType } from '../api/types'

const statusLabel: Record<string, string> = {
  pending: '排队中',
  processing: '处理中',
  succeeded: '已完成',
  failed: '失败',
}

function statusTag(status: string) {
  const color =
    status === 'succeeded' ? 'success' : status === 'failed' ? 'error' : 'processing'
  return <Tag color={color}>{statusLabel[status] ?? status}</Tag>
}

export default function ReviewPage() {
  const qc = useQueryClient()
  const { message } = AntApp.useApp()
  const [schemeId, setSchemeId] = useState<number | null>(null)
  const [submitOpen, setSubmitOpen] = useState(false)
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [detail, setDetail] = useState<ReviewTask | null>(null)
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

  return (
    <div>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
          marginBottom: 20,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <FileSearchOutlined style={{ fontSize: 22, color: '#1677ff' }} />
          <span style={{ fontSize: 18, fontWeight: 600 }}>方案审核</span>
        </div>
        <Space wrap size="middle" style={{ justifyContent: 'flex-end' }}>
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

      <Table<ReviewTask>
        rowKey="id"
        loading={tasksLoading}
        dataSource={tasks}
        pagination={{ pageSize: 15, showSizeChanger: true }}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 72 },
          {
            title: '方案类型',
            key: 'scheme',
            render: (_, row) => `${row.scheme_category} / ${row.scheme_name}`,
          },
          { title: '文件', dataIndex: 'original_filename', ellipsis: true },
          {
            title: '状态',
            dataIndex: 'status',
            width: 110,
            render: (s: string) => statusTag(s),
          },
          { title: '创建时间', dataIndex: 'created_at', width: 188 },
          {
            title: '操作',
            key: 'act',
            width: 280,
            render: (_, row) => (
              <Space size="small" wrap>
                <Button type="link" size="small" onClick={() => setDetail(row)}>
                  人工审阅
                </Button>
                <Button
                  type="link"
                  size="small"
                  icon={<FileTextOutlined />}
                  onClick={() => void openReviewLog(row.id)}
                >
                  审核日志
                </Button>
                <Button
                  type="link"
                  size="small"
                  icon={<ExportOutlined />}
                  onClick={() => message.info('导出报告功能开发中')}
                >
                  导出报告
                </Button>
              </Space>
            ),
          },
        ]}
      />

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

      <Modal
        title={`人工审阅 — 任务 #${detail?.id ?? ''}`}
        open={!!detail}
        onCancel={() => setDetail(null)}
        footer={null}
        width={640}
        destroyOnClose
      >
        {detail && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="方案类型">
              {detail.scheme_category} / {detail.scheme_name}
            </Descriptions.Item>
            <Descriptions.Item label="文件">{detail.original_filename}</Descriptions.Item>
            <Descriptions.Item label="状态">{statusTag(detail.status)}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{detail.created_at}</Descriptions.Item>
            <Descriptions.Item label="更新时间">{detail.updated_at}</Descriptions.Item>
            {detail.error_message && (
              <Descriptions.Item label="错误">{detail.error_message}</Descriptions.Item>
            )}
            {detail.result_text && (
              <Descriptions.Item label="审核结果">
                <pre
                  style={{
                    margin: 0,
                    whiteSpace: 'pre-wrap',
                    fontFamily: 'inherit',
                    fontSize: 13,
                  }}
                >
                  {detail.result_text}
                </pre>
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>
    </div>
  )
}
