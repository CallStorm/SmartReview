import { App as AntApp, Button, Divider, Input, Modal, Select, Space, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type {
  DifyDatasetItem,
  FullDocumentReviewConfig,
  SchemeType,
  TemplatePublic,
} from '../api/types'

type Props = {
  open: boolean
  scheme: SchemeType | null
  template: TemplatePublic | null
  loading: boolean
  onClose: () => void
  onSaved: (t: TemplatePublic) => void
}

const emptyConfig = (): FullDocumentReviewConfig => ({
  review_prompt: '',
  dify_dataset_id: null,
  knowledge_keywords: [],
})

export default function FullDocumentReviewModal({
  open,
  scheme,
  template,
  loading,
  onClose,
  onSaved,
}: Props) {
  const { message } = AntApp.useApp()
  const [draft, setDraft] = useState<FullDocumentReviewConfig>(emptyConfig())
  const [saving, setSaving] = useState(false)

  const { data: difyDatasets = [], isLoading: datasetsLoading } = useQuery({
    queryKey: ['dify-datasets'],
    queryFn: async () => {
      const { data } = await api.get<DifyDatasetItem[]>('/settings/knowledge-base/datasets')
      return data
    },
    enabled: open,
    retry: false,
  })

  useEffect(() => {
    if (!open || !template) return
    const c = template.full_document_review_config
    setDraft({
      review_prompt: c?.review_prompt ?? '',
      dify_dataset_id: c?.dify_dataset_id ?? null,
      knowledge_keywords: c?.knowledge_keywords ?? [],
    })
  }, [open, template?.id, template?.updated_at, template?.full_document_review_config])

  async function handleSave() {
    if (!scheme) return
    setSaving(true)
    try {
      const { data } = await api.put<TemplatePublic>(
        `/scheme-types/${scheme.id}/template/full-document-review`,
        { full_document_review_config: draft },
      )
      message.success('通篇审核配置已保存')
      onSaved(data)
      onClose()
    } catch {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title={scheme ? `通篇审核 — ${scheme.category} / ${scheme.name}` : '通篇审核'}
      open={open}
      onCancel={onClose}
      width="min(720px, 96vw)"
      centered
      destroyOnClose
      footer={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            loading={saving}
            disabled={loading || !template}
            onClick={handleSave}
          >
            保存
          </Button>
        </Space>
      }
    >
      {loading ? (
        <Typography.Text type="secondary">加载模版信息…</Typography.Text>
      ) : !template ? (
        <Typography.Text type="secondary">请先上传 Word 模版</Typography.Text>
      ) : (
        <div>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
            通篇审核将待审 Word 全文与下方配置拼接为一次大模型调用。请在「审核工作流」中开启通篇审核后才会执行。
          </Typography.Paragraph>
          <Divider orientationMargin={0} style={{ margin: '0 0 12px' }}>
            审核提示词
          </Divider>
          <Input.TextArea
            rows={8}
            placeholder="填写通篇审核的检查要点、判定标准等…"
            value={draft.review_prompt}
            onChange={(e) => setDraft((d) => ({ ...d, review_prompt: e.target.value }))}
          />
          <Divider orientationMargin={0} style={{ margin: '16px 0 12px' }}>
            知识库
          </Divider>
          <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 6 }}>
            知识库（Dify）
          </Typography.Text>
          <Select
            allowClear
            showSearch
            loading={datasetsLoading}
            style={{ width: '100%', marginBottom: 12 }}
            placeholder={
              difyDatasets.length === 0 && !datasetsLoading
                ? '未加载到知识库（请检查 设置 → Dify）'
                : '选择知识库'
            }
            value={draft.dify_dataset_id ?? undefined}
            onChange={(v) => setDraft((d) => ({ ...d, dify_dataset_id: v ?? null }))}
            options={difyDatasets.map((d) => ({ value: d.id, label: d.name || d.id }))}
            optionFilterProp="label"
          />
          <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 6 }}>
            关键字（可多个，用于检索知识库；留空则使用方案名称）
          </Typography.Text>
          <Select
            mode="tags"
            style={{ width: '100%' }}
            placeholder="输入后回车添加关键字"
            value={draft.knowledge_keywords ?? []}
            onChange={(tags) => setDraft((d) => ({ ...d, knowledge_keywords: tags }))}
            tokenSeparators={[',', '，']}
          />
        </div>
      )}
    </Modal>
  )
}
