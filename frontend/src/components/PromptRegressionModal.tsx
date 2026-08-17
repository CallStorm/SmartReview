import { useMutation } from '@tanstack/react-query'
import {
  Alert,
  App as AntApp,
  Button,
  InputNumber,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import { useState } from 'react'
import { api } from '../api/client'
import type { ReviewTask } from '../api/types'

interface Pair {
  original_task_id: number
  rerun_task_id: number
  filename: string
}

interface CompareItem {
  original_task_id: number
  rerun_task_id: number
  filename: string
  original_issue_count: number
  rerun_issue_count: number
  added: { step: string; node_id: string; check_item_id: string; severity: string; message: string }[]
  removed: { step: string; node_id: string; check_item_id: string; severity: string; message: string }[]
}

interface Props {
  open: boolean
  schemeTypeId: number
  schemeName: string
  onClose: () => void
}

export default function PromptRegressionModal({ open, schemeTypeId, schemeName, onClose }: Props) {
  const { message } = AntApp.useApp()
  const [taskLimit, setTaskLimit] = useState<number>(5)
  const [pairs, setPairs] = useState<Pair[]>([])
  const [statuses, setStatuses] = useState<Record<number, string>>({})
  const [results, setResults] = useState<CompareItem[]>([])
  const [polling, setPolling] = useState(false)

  const startMut = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ pairs: Pair[] }>(
        `/scheme-types/${schemeTypeId}/prompt-regression`,
        { task_limit: taskLimit },
      )
      return data.pairs
    },
    onSuccess: (res) => {
      setPairs(res)
      setResults([])
      setStatuses({})
      message.success(`已创建 ${res.length} 个回归任务（带 [回归] 前缀），结果缓存使成本仅限变更节点`)
      startPolling(res.map((p) => p.rerun_task_id))
    },
    onError: (err: unknown) => {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined
      message.error(typeof detail === 'string' ? detail : '回归任务创建失败')
    },
  })

  function startPolling(rerunIds: number[]) {
    setPolling(true)
    const timer = setInterval(async () => {
      try {
        const { data: tasks } = await api.get<ReviewTask[]>('/review-tasks')
        const byId = new Map(tasks.map((t) => [t.id, t]))
        const next: Record<number, string> = {}
        let allDone = true
        for (const id of rerunIds) {
          const st = byId.get(id)?.status ?? 'missing'
          next[id] = st
          if (st !== 'succeeded' && st !== 'failed') allDone = false
        }
        setStatuses(next)
        if (allDone) {
          clearInterval(timer)
          setPolling(false)
          void runCompare()
        }
      } catch {
        /* 轮询失败下次重试 */
      }
    }, 5000)
  }

  async function runCompare() {
    try {
      const { data } = await api.post<{ results: CompareItem[]; errors: string[] }>(
        `/scheme-types/${schemeTypeId}/prompt-regression/compare`,
        { pairs },
      )
      setResults(data.results)
      if (data.errors?.length) message.warning(`${data.errors.length} 对任务对比失败（可能未完成）`)
    } catch {
      message.error('对比失败')
    }
  }

  const allDone = !polling && pairs.length > 0 && Object.keys(statuses).length === pairs.length &&
    Object.values(statuses).every((s) => s === 'succeeded' || s === 'failed')

  return (
    <Modal
      title={`提示词回归测试 - ${schemeName}`}
      open={open}
      onCancel={() => {
        setPairs([])
        setResults([])
        setStatuses({})
        onClose()
      }}
      footer={null}
      width={860}
      destroyOnClose
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="修改模板提示词保存后，用最近几份历史文档自动重跑一遍，对比前后问题集差异，验证优化是变好还是变坏。结果缓存保证只有受提示词变化影响的节点会重新调用模型。"
      />
      <Space style={{ marginBottom: 12 }}>
        <Typography.Text>最近文档份数：</Typography.Text>
        <InputNumber min={1} max={20} value={taskLimit} onChange={(v) => setTaskLimit(v ?? 5)} />
        <Button type="primary" loading={startMut.isPending} onClick={() => startMut.mutate()}>
          创建回归任务
        </Button>
        {allDone && (
          <Button onClick={() => void runCompare()}>刷新对比结果</Button>
        )}
      </Space>

      {pairs.length > 0 && (
        <Table
          size="small"
          rowKey="rerun_task_id"
          dataSource={pairs}
          pagination={false}
          columns={[
            { title: '文档', dataIndex: 'filename', ellipsis: true },
            { title: '源任务', dataIndex: 'original_task_id', width: 90 },
            { title: '回归任务', dataIndex: 'rerun_task_id', width: 90 },
            {
              title: '回归状态',
              key: 'status',
              width: 110,
              render: (_: unknown, p: Pair) => {
                const st = statuses[p.rerun_task_id]
                if (!st) return polling ? <Tag>排队/运行中…</Tag> : <Tag>未开始</Tag>
                return (
                  <Tag color={st === 'succeeded' ? 'green' : st === 'failed' ? 'red' : 'processing'}>
                    {st}
                  </Tag>
                )
              },
            },
          ]}
        />
      )}

      {results.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Typography.Title level={5}>问题集对比</Typography.Title>
          {results.map((r) => (
            <div key={r.rerun_task_id} style={{ marginBottom: 12 }}>
              <Typography.Text strong>{r.filename}</Typography.Text>
              <Typography.Text type="secondary" style={{ marginLeft: 8 }}>
                原问题 {r.original_issue_count} 个 → 回归 {r.rerun_issue_count} 个
              </Typography.Text>
              {r.added.length === 0 && r.removed.length === 0 ? (
                <Alert type="success" showIcon message="问题集完全一致（未受本次提示词变化影响）" style={{ marginTop: 6 }} />
              ) : (
                <div style={{ marginTop: 6 }}>
                  {r.added.length > 0 && (
                    <div>
                      <Typography.Text type="secondary">新增问题（{r.added.length}）</Typography.Text>
                      <ul style={{ margin: '4px 0', paddingLeft: 18 }}>
                        {r.added.map((i, k) => (
                          <li key={k} style={{ fontSize: 12 }}>
                            <Tag color="volcano" style={{ fontSize: 11 }}>{i.severity}</Tag>
                            {i.check_item_id ? <Typography.Text code>{i.check_item_id}</Typography.Text> : null} {i.message}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {r.removed.length > 0 && (
                    <div>
                      <Typography.Text type="secondary">不再报出（{r.removed.length}）</Typography.Text>
                      <ul style={{ margin: '4px 0', paddingLeft: 18 }}>
                        {r.removed.map((i, k) => (
                          <li key={k} style={{ fontSize: 12 }}>
                            <Tag style={{ fontSize: 11 }}>{i.severity}</Tag>
                            {i.check_item_id ? <Typography.Text code>{i.check_item_id}</Typography.Text> : null} {i.message}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}
