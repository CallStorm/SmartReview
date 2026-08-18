import { useQuery } from '@tanstack/react-query'
import { App as AntApp, Button, Empty, List, Modal, Space, Tag, Typography } from 'antd'
import { useState } from 'react'
import { api } from '../api/client'
import type { TemplatePublic } from '../api/types'

export interface PromptHistoryEntry {
  id: number
  node_id: string
  field: string
  node_title: string
  old_value: string
  new_value: string
  source: string
  changed_by: string
  changed_at: string
}

interface Props {
  open: boolean
  schemeTypeId: number
  /** 节点级字段传节点 id；全局规则/通篇审核传空串 */
  nodeId: string
  field: string
  title: string
  onClose: () => void
  onRestored: (template: TemplatePublic) => void
}

const FIELD_LABELS: Record<string, string> = {
  review_prompt: '审核提示词',
  context_consistency_prompt: '上下文一致性提示词',
  content_review_rules: '内容审核全局规则',
  full_document_review_prompt: '通篇审核提示词',
  image_review_rules: '图审核全局规则',
  image_review_missing_text: '图审核缺图提示文案',
  image_review: '图审核配置',
}

export default function PromptHistoryModal({
  open,
  schemeTypeId,
  nodeId,
  field,
  title,
  onClose,
  onRestored,
}: Props) {
  const { message } = AntApp.useApp()
  const [selected, setSelected] = useState<PromptHistoryEntry | null>(null)
  const [restoring, setRestoring] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['prompt-history', schemeTypeId, nodeId, field],
    queryFn: async () => {
      const params = new URLSearchParams({ field, limit: '50' })
      if (nodeId) params.set('node_id', nodeId)
      const { data } = await api.get<{ items: PromptHistoryEntry[] }>(
        `/scheme-types/${schemeTypeId}/template/prompt-history`,
        { params },
      )
      return data.items
    },
    enabled: open && schemeTypeId > 0,
  })

  async function restore(entry: PromptHistoryEntry) {
    setRestoring(true)
    try {
      const { data } = await api.post<TemplatePublic>(
        `/scheme-types/${schemeTypeId}/template/prompt-history/${entry.id}/restore`,
      )
      message.success('已回滚到历史版本')
      onRestored(data)
      setSelected(null)
      void refetch()
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined
      message.error(typeof detail === 'string' ? detail : '回滚失败')
    } finally {
      setRestoring(false)
    }
  }

  const items = data ?? []

  return (
    <Modal
      title={`提示词历史 - ${title}`}
      open={open}
      onCancel={onClose}
      footer={null}
      width={760}
      destroyOnClose
    >
      <List
        loading={isLoading}
        locale={{
          emptyText: (
            <Empty description="暂无变更记录（此字段自历史功能上线后未被修改过）" />
          ),
        }}
        dataSource={items}
        rowKey={(x) => String(x.id)}
        renderItem={(x) => (
          <List.Item
            style={{ cursor: 'pointer', flexDirection: 'column', alignItems: 'stretch' }}
            onClick={() => setSelected(x)}
          >
            <Space wrap>
              <Tag color={x.source === 'restore' ? 'orange' : 'blue'}>
                {x.source === 'restore' ? '回滚' : '编辑'}
              </Tag>
              <Typography.Text type="secondary">
                {new Date(x.changed_at).toLocaleString()} · {x.changed_by || '-'}
              </Typography.Text>
              <Typography.Text type="secondary">
                {FIELD_LABELS[x.field] ?? x.field}
                {x.node_id ? ` · ${x.node_id}` : ''}
              </Typography.Text>
            </Space>
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  修改前
                </Typography.Text>
                <Typography.Paragraph
                  style={{
                    fontSize: 12,
                    whiteSpace: 'pre-wrap',
                    maxHeight: 120,
                    overflow: 'auto',
                    background: '#fafafa',
                    padding: 8,
                    marginBottom: 0,
                  }}
                >
                  {x.old_value || '（空）'}
                </Typography.Paragraph>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  修改后
                </Typography.Text>
                <Typography.Paragraph
                  style={{
                    fontSize: 12,
                    whiteSpace: 'pre-wrap',
                    maxHeight: 120,
                    overflow: 'auto',
                    background: '#f6ffed',
                    padding: 8,
                    marginBottom: 0,
                  }}
                >
                  {x.new_value || '（空）'}
                </Typography.Paragraph>
              </div>
            </div>
            {selected?.id === x.id && (
              <Button
                size="small"
                danger
                loading={restoring}
                style={{ marginTop: 8, alignSelf: 'flex-start' }}
                onClick={(e) => {
                  e.stopPropagation()
                  void restore(x)
                }}
              >
                回滚到此版本之前
              </Button>
            )}
          </List.Item>
        )}
      />
    </Modal>
  )
}
