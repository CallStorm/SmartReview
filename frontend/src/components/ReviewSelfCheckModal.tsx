import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Descriptions,
  Empty,
  List,
  Modal,
  Space,
  Spin,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { useState } from 'react'
import { api } from '../api/client'

interface SelfCheckResp {
  task_id: number
  filename: string
  total_issues: number
  severity_counts: Record<string, number>
  step_stats: { step_id: string; passed: boolean; issues: number }[]
  node_stats: Record<string, number>
  evidence_missing: { step: string; node_id: string; evidence: string }[]
  untraceable_issues: { step: string; node_id: string; message: string }[]
  doc_error: string
  missing_verdicts: string[]
  pass_without_evidence: string[]
  out_of_checklist: string[]
  fallback_parse_steps: string[]
  cache_hits: number
  verdicts: { ok: boolean }
}

interface Finding {
  id: number
  node_id: string
  node_title: string
  check_item_id: string
  check_item_text: string
  finding_type: string
  description: string
  status: string
}

interface Props {
  open: boolean
  taskId: number
  filename: string
  onClose: () => void
}

export default function ReviewSelfCheckModal({ open, taskId, filename, onClose }: Props) {
  const { message } = AntApp.useApp()
  const [suggestions, setSuggestions] = useState<
    { node_id: string; node_title: string; suggestion: string }[]
  >([])

  const selfCheck = useQuery({
    queryKey: ['self-check', taskId],
    queryFn: async () => {
      const { data } = await api.get<SelfCheckResp>(`/review-tasks/${taskId}/self-check`)
      return data
    },
    enabled: open && taskId > 0,
  })

  const findingsQ = useQuery({
    queryKey: ['ai-audit-findings', taskId],
    queryFn: async () => {
      const { data } = await api.get<{ items: Finding[] }>(`/review-tasks/${taskId}/ai-audit/findings`)
      return data.items
    },
    enabled: open && taskId > 0,
  })

  const runAuditMut = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ audited_nodes: number; findings_created: number; errors: string[] }>(
        `/review-tasks/${taskId}/ai-audit`,
      )
      return data
    },
    onSuccess: (res) => {
      message.success(`测评完成：复核 ${res.audited_nodes} 个章节，新增 ${res.findings_created} 条分歧`)
      if (res.errors?.length) message.warning(`${res.errors.length} 个章节复核失败`)
      void findingsQ.refetch()
    },
    onError: (err: unknown) => {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined
      message.error(typeof detail === 'string' ? detail : '测评执行失败')
    },
  })

  async function adjudicate(f: Finding, status: 'confirmed' | 'rejected' | 'unclear') {
    try {
      await api.patch(`/review-tasks/audit-findings/${f.id}`, { status })
      void findingsQ.refetch()
    } catch {
      message.error('裁决失败')
    }
  }

  const suggestMut = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{
        suggestions: { node_id: string; node_title: string; suggestion: string }[]
      }>(`/review-tasks/${taskId}/ai-audit/suggestions`)
      return data
    },
    onSuccess: (res) => {
      setSuggestions(res.suggestions)
      if (!res.suggestions.length) message.info('没有已确认的分歧，请先裁决确认至少一条')
    },
    onError: () => message.error('建议生成失败'),
  })

  const sc = selfCheck.data

  return (
    <Modal
      title={`AI 测评 - ${filename}`}
      open={open}
      onCancel={onClose}
      footer={null}
      width={860}
      destroyOnClose
    >
      <Tabs
        items={[
          {
            key: 'selfcheck',
            label: '体检报告（程序化）',
            children: (
              <Spin spinning={selfCheck.isLoading}>
                {sc && (
                  <div>
                    <Alert
                      style={{ marginBottom: 12 }}
                      type={sc.verdicts.ok ? 'success' : 'warning'}
                      showIcon
                      message={
                        sc.verdicts.ok
                          ? '体检通过：引文可溯源、判定无漏项、无越权问题'
                          : '体检发现异常项，请逐条核对'
                      }
                    />
                    {sc.doc_error && <Alert type="warning" showIcon message={sc.doc_error} style={{ marginBottom: 12 }} />}
                    <Descriptions size="small" bordered column={2}>
                      <Descriptions.Item label="问题总数">{sc.total_issues}</Descriptions.Item>
                      <Descriptions.Item label="级别分布">
                        严重 {sc.severity_counts.error} / 一般 {sc.severity_counts.warning} / 提示{' '}
                        {sc.severity_counts.info}
                      </Descriptions.Item>
                      <Descriptions.Item label="缓存命中节点">{sc.cache_hits}</Descriptions.Item>
                      <Descriptions.Item label="漏判检查项">
                        {sc.missing_verdicts.length ? (
                          <span style={{ color: '#cf1322' }}>{sc.missing_verdicts.join(', ')}</span>
                        ) : (
                          '无'
                        )}
                      </Descriptions.Item>
                      <Descriptions.Item label="pass 未附引证">
                        {sc.pass_without_evidence.length ? (
                          <span style={{ color: '#d46b08' }}>{sc.pass_without_evidence.join(', ')}</span>
                        ) : (
                          '无'
                        )}
                      </Descriptions.Item>
                      <Descriptions.Item label="清单外/越权输出">
                        {sc.out_of_checklist.length ? sc.out_of_checklist.join(', ') : '无'}
                      </Descriptions.Item>
                      <Descriptions.Item label="引文无法对上原文" span={2}>
                        {sc.evidence_missing.length ? (
                          <ul style={{ margin: 0, paddingLeft: 18 }}>
                            {sc.evidence_missing.map((e, i) => (
                              <li key={i}>
                                {e.node_id}（{e.step}）：{e.evidence}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          '无'
                        )}
                      </Descriptions.Item>
                    </Descriptions>
                    <Typography.Text type="secondary" style={{ display: 'block', margin: '12px 0 4px' }}>
                      节点问题密度
                    </Typography.Text>
                    <Space wrap>
                      {Object.entries(sc.node_stats).map(([nid, n]) => (
                        <Tag key={nid}>
                          {nid}: {n}
                        </Tag>
                      ))}
                      {!Object.keys(sc.node_stats).length && <Typography.Text type="secondary">无问题</Typography.Text>}
                    </Space>
                  </div>
                )}
              </Spin>
            ),
          },
          {
            key: 'adversarial',
            label: '对抗测评（LLM 复核）',
            children: (
              <div>
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message="对抗测评由模型独立复核上次的 pass/fail 判定，结果仅为嫌疑（第二意见），需管理员裁决。确认的分歧可一键生成提示词优化建议。"
                />
                <Space style={{ marginBottom: 12 }}>
                  <Button
                    type="primary"
                    loading={runAuditMut.isPending}
                    onClick={() => runAuditMut.mutate()}
                  >
                    {findingsQ.data?.length ? '重新测评（覆盖未裁决项）' : '启动对抗测评'}
                  </Button>
                  <Button
                    icon={undefined}
                    loading={suggestMut.isPending}
                    disabled={!findingsQ.data?.some((f) => f.status === 'confirmed')}
                    onClick={() => suggestMut.mutate()}
                  >
                    生成提示词优化建议（基于已确认分歧）
                  </Button>
                </Space>
                <List
                  loading={findingsQ.isLoading}
                  locale={{ emptyText: <Empty description="尚未测评或无分歧记录" /> }}
                  dataSource={findingsQ.data ?? []}
                  rowKey={(f) => String(f.id)}
                  renderItem={(f) => (
                    <List.Item
                      actions={[
                        f.status === 'pending' ? (
                          <Space key="act">
                            <Button size="small" type="primary" onClick={() => void adjudicate(f, 'confirmed')}>
                              确认
                            </Button>
                            <Button size="small" onClick={() => void adjudicate(f, 'rejected')}>
                              驳回
                            </Button>
                            <Button size="small" onClick={() => void adjudicate(f, 'unclear')}>
                              无法判定
                            </Button>
                          </Space>
                        ) : (
                          <Tag key="st" color={f.status === 'confirmed' ? 'green' : f.status === 'rejected' ? 'red' : 'default'}>
                            {f.status === 'confirmed' ? '已确认' : f.status === 'rejected' ? '已驳回' : '无法判定'}
                          </Tag>
                        ),
                      ]}
                    >
                      <List.Item.Meta
                        title={
                          <Space>
                            <Tag color={f.finding_type === 'missed_suspect' ? 'volcano' : 'purple'}>
                              {f.finding_type === 'missed_suspect' ? '漏检嫌疑' : '误报嫌疑'}
                            </Tag>
                            <Typography.Text code>{f.check_item_id}</Typography.Text>
                            <Typography.Text>{f.node_title}</Typography.Text>
                          </Space>
                        }
                        description={
                          <>
                            <Typography.Paragraph style={{ marginBottom: 4 }} type="secondary">
                              检查项：{f.check_item_text}
                            </Typography.Paragraph>
                            <Typography.Paragraph style={{ marginBottom: 0 }}>{f.description}</Typography.Paragraph>
                          </>
                        }
                      />
                    </List.Item>
                  )}
                />
                {suggestions.length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <Typography.Title level={5}>提示词优化建议</Typography.Title>
                    {suggestions.map((s, i) => (
                      <Card key={i} size="small" style={{ marginBottom: 8 }}>
                        <Typography.Text strong>
                          {s.node_title}（{s.node_id}）
                        </Typography.Text>
                        <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                          {s.suggestion}
                        </Typography.Paragraph>
                      </Card>
                    ))}
                  </div>
                )}
              </div>
            ),
          },
        ]}
      />
    </Modal>
  )
}
