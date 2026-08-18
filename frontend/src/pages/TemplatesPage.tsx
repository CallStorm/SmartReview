import { FormOutlined, HistoryOutlined, RobotOutlined } from '@ant-design/icons'
import {
  App as AntApp,
  Button,
  Card,
  Checkbox,
  Divider,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tree,
  Typography,
  Upload,
} from 'antd'
import type { DataNode } from 'antd/es/tree'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { DifyDatasetItem, SchemeType, TemplateNode, TemplatePublic, UploadSettings } from '../api/types'
import PageShell from '../components/PageShell'
import FullDocumentReviewModal from '../components/FullDocumentReviewModal'
import PromptHistoryModal from '../components/PromptHistoryModal'
import PromptOptimizeModal from '../components/PromptOptimizeModal'
import PromptRegressionModal from '../components/PromptRegressionModal'
import ReviewWorkflowModal from '../components/ReviewWorkflowModal'
import { DEFAULT_TABLE_PAGINATION } from '../config/tablePagination'
import {
  cloneTemplateStructure,
  findNodeById,
  flattenNodePickerItems,
  patchNodeInTree,
} from '../utils/templateTree'

function nodesToTreeData(nodes: TemplateNode[]): DataNode[] {
  return nodes.map((n) => ({
    title: (
      <span>
        <Typography.Text strong>{n.title}</Typography.Text>
        <Typography.Text type="secondary" style={{ marginLeft: 8 }}>
          L{n.level}
        </Typography.Text>
      </span>
    ),
    key: n.id,
    children: nodesToTreeData(n.children ?? []),
  }))
}

function buildTemplateFileName(schemeName: string): string {
  const now = new Date()
  const yyyy = now.getFullYear()
  const mm = String(now.getMonth() + 1).padStart(2, '0')
  const dd = String(now.getDate()).padStart(2, '0')
  const safeSchemeName = (schemeName || '模板').replace(/[\\/:*?"<>|]/g, '_').trim() || '模板'
  return `${safeSchemeName}_${yyyy}${mm}${dd}.docx`
}

export default function TemplatesPage() {
  const qc = useQueryClient()
  const { message } = AntApp.useApp()
  const { data: schemes = [], isLoading } = useQuery({
    queryKey: ['schemes'],
    queryFn: async () => {
      const { data: rows } = await api.get<SchemeType[]>('/scheme-types')
      return rows
    },
  })

  const { data: uploadSettings } = useQuery({
    queryKey: ['settings', 'upload'],
    queryFn: async () => {
      try {
        const { data } = await api.get<UploadSettings>('/settings/upload')
        return data
      } catch {
        // 静默：按默认 100MB 兜底
        return null
      }
    },
  })
  const maxUploadMb = uploadSettings?.max_upload_mb ?? 100

  const [uploadScheme, setUploadScheme] = useState<SchemeType | null>(null)
  const [workflowScheme, setWorkflowScheme] = useState<SchemeType | null>(null)
  const [workflowTemplate, setWorkflowTemplate] = useState<TemplatePublic | null>(null)
  const [workflowLoading, setWorkflowLoading] = useState(false)
  const [fullDocScheme, setFullDocScheme] = useState<SchemeType | null>(null)
  const [fullDocTemplate, setFullDocTemplate] = useState<TemplatePublic | null>(null)
  const [fullDocLoading, setFullDocLoading] = useState(false)
  const [preview, setPreview] = useState<TemplatePublic | null>(null)
  const [structureDraft, setStructureDraft] = useState<{ nodes: TemplateNode[] } | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [globalRulesDraft, setGlobalRulesDraft] = useState<string>('')
  const [imageRulesDraft, setImageRulesDraft] = useState<string>('')
  const [missingTextDraft, setMissingTextDraft] = useState<string>('')
  const [historyCtx, setHistoryCtx] = useState<{ nodeId: string; field: string; title: string } | null>(null)
  const [regressionOpen, setRegressionOpen] = useState(false)
  const [optimizeCtx, setOptimizeCtx] = useState<{
    kind: 'review_prompt' | 'context_consistency_prompt'
    currentText: string
  } | null>(null)
  const [splitPreview, setSplitPreview] = useState<{ items: { id: string; text: string }[]; notes: string[] } | null>(null)
  const [splitLoading, setSplitLoading] = useState(false)

  const { data: difyDatasets = [], isLoading: datasetsLoading } = useQuery({
    queryKey: ['dify-datasets'],
    queryFn: async () => {
      const { data } = await api.get<DifyDatasetItem[]>('/settings/knowledge-base/datasets')
      return data
    },
    enabled: !!preview,
    retry: false,
  })

  useEffect(() => {
    if (preview?.parsed_structure?.nodes?.length) {
      setStructureDraft(cloneTemplateStructure({ nodes: preview.parsed_structure.nodes }))
    } else {
      setStructureDraft(null)
    }
    setSelectedNodeId(null)
  }, [preview?.id, preview?.updated_at, preview?.parsed_structure])

  const uploadMut = useMutation({
    mutationFn: async ({ schemeId, file }: { schemeId: number; file: File }) => {
      const fd = new FormData()
      fd.append('file', file)
      const { data } = await api.post<{ template: TemplatePublic; message: string }>(
        `/scheme-types/${schemeId}/template`,
        fd,
      )
      return data
    },
    onSuccess: (res) => {
      message.success(res.message === 'updated' ? '模版已更新' : '模版已上传')
      setUploadScheme(null)
      void qc.invalidateQueries({ queryKey: ['template', res.template.scheme_type_id] })
      void qc.invalidateQueries({ queryKey: ['schemes'] })
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
      message.error(detailMsg || '上传失败')
    },
  })

  const saveStructureMut = useMutation({
    mutationFn: async () => {
      if (!preview?.scheme_type_id || !structureDraft) {
        throw new Error('无可保存的结构')
      }
      const { data } = await api.put<TemplatePublic>(
        `/scheme-types/${preview.scheme_type_id}/template/structure`,
        { parsed_structure: structureDraft },
      )
      return data
    },
    onSuccess: (updated) => {
      message.success('结构 JSON 已更新到服务器')
      setPreview(updated)
      void qc.invalidateQueries({ queryKey: ['schemes'] })
    },
    onError: (err: unknown) => {
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
    },
  })

  const saveGlobalRulesMut = useMutation({
    mutationFn: async (rules: string) => {
      if (!preview?.scheme_type_id) {
        throw new Error('缺少方案 id')
      }
      const { data } = await api.put<TemplatePublic>(
        `/scheme-types/${preview.scheme_type_id}/template/content-review-rules`,
        { content_review_rules: rules },
      )
      return data
    },
    onSuccess: (updated) => {
      message.success('已保存内容审核全局规则')
      setPreview(updated)
      setGlobalRulesDraft(updated.content_review_rules ?? '')
      void qc.invalidateQueries({ queryKey: ['schemes'] })
    },
    onError: (err: unknown) => {
      const raw =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined
      message.error(typeof raw === 'string' ? raw : '保存失败')
    },
  })

  const saveImageRulesMut = useMutation({
    mutationFn: async (rules: string) => {
      if (!preview?.scheme_type_id) {
        throw new Error('缺少方案 id')
      }
      const { data } = await api.put<TemplatePublic>(
        `/scheme-types/${preview.scheme_type_id}/template/image-review-rules`,
        { image_review_rules: rules },
      )
      return data
    },
    onSuccess: (updated) => {
      message.success('已保存图审核全局规则')
      setPreview(updated)
      setImageRulesDraft(updated.image_review_rules ?? '')
      void qc.invalidateQueries({ queryKey: ['schemes'] })
    },
    onError: (err: unknown) => {
      const raw =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined
      message.error(typeof raw === 'string' ? raw : '保存失败')
    },
  })

  const saveMissingTextMut = useMutation({
    mutationFn: async (text: string) => {
      if (!preview?.scheme_type_id) {
        throw new Error('缺少方案 id')
      }
      const { data } = await api.put<TemplatePublic>(
        `/scheme-types/${preview.scheme_type_id}/template/image-review-missing-text`,
        { image_review_missing_text: text },
      )
      return data
    },
    onSuccess: (updated) => {
      message.success('已保存缺图提示文案')
      setPreview(updated)
      setMissingTextDraft(updated.image_review_missing_text ?? '')
      void qc.invalidateQueries({ queryKey: ['schemes'] })
    },
    onError: (err: unknown) => {
      const raw =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined
      message.error(typeof raw === 'string' ? raw : '保存失败')
    },
  })

  const selectedNode = useMemo(() => {
    if (!selectedNodeId || !structureDraft?.nodes.length) return null
    return findNodeById(structureDraft.nodes, selectedNodeId)
  }, [selectedNodeId, structureDraft])

  // 拆分预览：审核提示词变化 600ms 后自动刷新（确定性，不调 LLM）
  const reviewPromptForPreview = selectedNode?.review_prompt ?? ''
  const previewNodeId = selectedNode?.id ?? ''
  const previewSchemeId = preview?.scheme_type_id ?? 0
  useEffect(() => {
    if (!previewSchemeId || !previewNodeId) {
      setSplitPreview(null)
      return
    }
    if (!reviewPromptForPreview.trim()) {
      setSplitPreview(null)
      return
    }
    let cancelled = false
    setSplitLoading(true)
    const timer = setTimeout(async () => {
      try {
        const { data } = await api.post<{
          items: { id: string; text: string }[]
          notes: string[]
        }>(`/scheme-types/${previewSchemeId}/template/split-preview`, {
          node_id: previewNodeId,
          review_prompt: reviewPromptForPreview,
        })
        if (!cancelled) setSplitPreview(data)
      } catch {
        if (!cancelled) setSplitPreview(null)
      } finally {
        if (!cancelled) setSplitLoading(false)
      }
    }, 600)
    return () => {
      cancelled = true
      clearTimeout(timer)
      setSplitLoading(false)
    }
  }, [previewSchemeId, previewNodeId, reviewPromptForPreview])

  const refPickerItems = useMemo(() => {
    if (!structureDraft?.nodes.length) return []
    return flattenNodePickerItems(structureDraft.nodes)
  }, [structureDraft])

  const refSelectOptions = useMemo(() => {
    if (!selectedNodeId) return refPickerItems
    return refPickerItems.filter((o) => o.id !== selectedNodeId)
  }, [refPickerItems, selectedNodeId])

  const treeData = useMemo(
    () => (structureDraft?.nodes?.length ? nodesToTreeData(structureDraft.nodes) : []),
    [structureDraft],
  )

  function patchSelected(patch: Partial<TemplateNode>) {
    if (!selectedNodeId || !structureDraft) return
    setStructureDraft({
      nodes: patchNodeInTree(structureDraft.nodes, selectedNodeId, patch),
    })
  }

  return (
    <PageShell
      icon={<FormOutlined />}
      description="按方案类型上传 Word 模版、配置标题树规则与审核工作流。"
    >
      <Table
        rowKey="id"
        size="middle"
        loading={isLoading}
        dataSource={schemes}
        scroll={{ x: 'max-content' }}
        locale={{ emptyText: '暂无方案类型' }}
        pagination={DEFAULT_TABLE_PAGINATION}
        columns={[
          { title: '方案ID', dataIndex: 'id', width: 72 },
          {
            title: '方案大类',
            dataIndex: 'category',
            ellipsis: true,
            width: 160,
          },
          { title: '方案名称', dataIndex: 'name', ellipsis: true },
          {
            title: '模版状态',
            key: 'template_status',
            width: 100,
            render: (_: unknown, row: SchemeType) =>
              row.template_configured ? (
                <Tag color="success">已配置</Tag>
              ) : (
                <Tag>未配置</Tag>
              ),
          },
          {
            title: '工作流状态',
            key: 'workflow_status',
            width: 100,
            render: (_: unknown, row: SchemeType) =>
              row.workflow_configured ? (
                <Tag color="processing">已设置</Tag>
              ) : (
                <Tag>未配置</Tag>
              ),
          },
          {
            title: '操作',
            key: 'actions',
            width: 440,
            fixed: 'right',
            render: (_: unknown, row: SchemeType) => (
              <Space size="small" wrap={false} style={{ whiteSpace: 'nowrap' }}>
                <Button type="primary" size="small" onClick={() => setUploadScheme(row)}>
                  {row.template_configured ? '更新 Word' : '上传 Word'}
                </Button>
                <Button
                  size="small"
                  onClick={async () => {
                    try {
                      const { data } = await api.get<TemplatePublic>(
                        `/scheme-types/${row.id}/template`,
                      )
                      setPreview(data)
                      setGlobalRulesDraft(data.content_review_rules ?? '')
                      setImageRulesDraft(data.image_review_rules ?? '')
                      setMissingTextDraft(data.image_review_missing_text ?? '')
                    } catch {
                      message.warning('该方案尚未上传模版')
                    }
                  }}
                >
                  规则设置
                </Button>
                <Button
                  size="small"
                  onClick={async () => {
                    setFullDocScheme(row)
                    setFullDocLoading(true)
                    setFullDocTemplate(null)
                    try {
                      const { data } = await api.get<TemplatePublic>(
                        `/scheme-types/${row.id}/template`,
                      )
                      setFullDocTemplate(data)
                    } catch {
                      message.warning('该方案尚未上传模版')
                    } finally {
                      setFullDocLoading(false)
                    }
                  }}
                >
                  通篇审核
                </Button>
                <Button
                  size="small"
                  onClick={async () => {
                    setWorkflowScheme(row)
                    setWorkflowLoading(true)
                    setWorkflowTemplate(null)
                    try {
                      const { data } = await api.get<TemplatePublic>(
                        `/scheme-types/${row.id}/template`,
                      )
                      setWorkflowTemplate(data)
                    } catch {
                      message.warning('该方案尚未上传模版')
                    } finally {
                      setWorkflowLoading(false)
                    }
                  }}
                >
                  审核工作流
                </Button>
                <Button
                  size="small"
                  onClick={async () => {
                    try {
                      const { data } = await api.get<{ url: string }>(
                        `/scheme-types/${row.id}/template/download-url`,
                      )
                      const res = await fetch(data.url)
                      if (!res.ok) throw new Error('download failed')
                      const blob = await res.blob()
                      const a = document.createElement('a')
                      a.href = URL.createObjectURL(blob)
                      a.download = buildTemplateFileName(row.name)
                      document.body.appendChild(a)
                      a.click()
                      a.remove()
                      URL.revokeObjectURL(a.href)
                    } catch {
                      message.warning('下载失败，请稍后重试')
                    }
                  }}
                >
                  下载
                </Button>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title={preview ? `模版结构 — ${preview.original_filename}` : '模版结构'}
        open={!!preview}
        onCancel={() => setPreview(null)}
        width="min(1180px, 96vw)"
        centered
        destroyOnClose
        footer={
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button
              type="primary"
              loading={saveStructureMut.isPending}
              disabled={!structureDraft?.nodes?.length}
              onClick={() => saveStructureMut.mutate()}
            >
              更新
            </Button>
          </div>
        }
        styles={{ body: { paddingTop: 12 } }}
      >
        <Card
          size="small"
          type="inner"
          title="内容审核全局规则"
          styles={{ body: { paddingBottom: 8 } }}
          style={{ marginBottom: 12 }}
        >
          <Typography.Paragraph type="secondary" style={{ marginTop: 0, marginBottom: 8 }}>
            模板级规则。保存后会作为每个节点「审核提示词」的补充追加到内容审核（per-node）LLM 的 prompt 里；
            不影响通篇审核、上下文一致性、编制依据三步。
          </Typography.Paragraph>
          <Input.TextArea
            rows={4}
            value={globalRulesDraft}
            onChange={(e) => setGlobalRulesDraft(e.target.value)}
            placeholder="例如：必须检查每页是否有页码；引用的法规必须在知识库检索片段中能找到…"
          />
          <Space style={{ marginTop: 8 }}>
            <Button
              type="primary"
              loading={saveGlobalRulesMut.isPending}
              onClick={() => saveGlobalRulesMut.mutate(globalRulesDraft)}
            >
              保存全局规则
            </Button>
            <Button
              icon={<HistoryOutlined />}
              disabled={!preview?.scheme_type_id}
              onClick={() =>
                setHistoryCtx({ nodeId: '', field: 'content_review_rules', title: '内容审核全局规则' })
              }
            >
              历史
            </Button>
            <Button
              disabled={!preview?.scheme_type_id}
              onClick={() => setRegressionOpen(true)}
            >
              回归测试
            </Button>
          </Space>
        </Card>
        <Card
          size="small"
          type="inner"
          title="图审核全局规则"
          styles={{ body: { paddingBottom: 8 } }}
          style={{ marginBottom: 12 }}
        >
          <Typography.Paragraph type="secondary" style={{ marginTop: 0, marginBottom: 8 }}>
            模板级规则。注入到每个配置了图审核的节点的视觉模型 prompt，作为图件判定的通用约束；
            不影响内容审核、上下文一致性等文本步骤。
          </Typography.Paragraph>
          <Input.TextArea
            rows={3}
            value={imageRulesDraft}
            onChange={(e) => setImageRulesDraft(e.target.value)}
            placeholder="例如：图例与标注应齐全可辨；手绘草图视为不满足要求…"
          />
          <Space style={{ marginTop: 8 }}>
            <Button
              type="primary"
              loading={saveImageRulesMut.isPending}
              onClick={() => saveImageRulesMut.mutate(imageRulesDraft)}
            >
              保存图审核规则
            </Button>
            <Button
              icon={<HistoryOutlined />}
              disabled={!preview?.scheme_type_id}
              onClick={() =>
                setHistoryCtx({ nodeId: '', field: 'image_review_rules', title: '图审核全局规则' })
              }
            >
              历史
            </Button>
          </Space>
          <Divider style={{ margin: '14px 0 10px' }} />
          <Typography.Text strong>缺图提示文案</Typography.Text>
          <Typography.Paragraph type="secondary" style={{ marginTop: 4, marginBottom: 8 }}>
            节点配置了图审核（图种/内容要素）但文档未检出附图时，在问题列表展示的说明文字；
            留空使用默认「无图审核」。
          </Typography.Paragraph>
          <Input
            value={missingTextDraft}
            onChange={(e) => setMissingTextDraft(e.target.value)}
            placeholder="无图审核"
            maxLength={100}
          />
          <Space style={{ marginTop: 8 }}>
            <Button
              type="primary"
              loading={saveMissingTextMut.isPending}
              onClick={() => saveMissingTextMut.mutate(missingTextDraft)}
            >
              保存缺图提示文案
            </Button>
            <Button
              icon={<HistoryOutlined />}
              disabled={!preview?.scheme_type_id}
              onClick={() =>
                setHistoryCtx({
                  nodeId: '',
                  field: 'image_review_missing_text',
                  title: '图审核缺图提示文案',
                })
              }
            >
              历史
            </Button>
          </Space>
        </Card>
        <Divider style={{ margin: '0 0 12px' }} />
        {structureDraft?.nodes?.length ? (
          <div style={{ display: 'flex', gap: 16, minHeight: 520 }}>
            <div
              style={{
                flex: '0 0 360px',
                borderRight: '1px solid var(--ant-color-split, #f0f0f0)',
                paddingRight: 12,
                overflow: 'auto',
                maxHeight: '68vh',
              }}
            >
              <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                标题树（点击节点在右侧配置）
              </Typography.Text>
              <Tree
                showLine
                defaultExpandAll
                treeData={treeData}
                selectedKeys={selectedNodeId ? [selectedNodeId] : []}
                onSelect={(keys) => {
                  setSelectedNodeId(keys.length ? String(keys[0]) : null)
                }}
              />
            </div>
            <div style={{ flex: 1, minWidth: 0, overflow: 'auto', maxHeight: '68vh' }}>
              {!selectedNode ? (
                <Typography.Text type="secondary">请在左侧选择一个节点</Typography.Text>
              ) : (
                <div>
                  <Typography.Title level={5} style={{ marginTop: 0 }}>
                    {selectedNode.title}
                    <Typography.Text type="secondary" style={{ marginLeft: 8 }}>
                      （{selectedNode.id}）
                    </Typography.Text>
                  </Typography.Title>
                  <Divider orientationMargin={0} style={{ margin: '12px 0' }}>
                    引用
                  </Divider>
                  <Typography.Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 8 }}>
                    可选择树中其他节点作为关联引用（不选表示不引用）
                  </Typography.Paragraph>
                  <Select
                    mode="multiple"
                    allowClear
                    style={{ width: '100%' }}
                    placeholder="选择引用的节点"
                    value={selectedNode.ref_node_ids ?? []}
                    onChange={(ids) => patchSelected({ ref_node_ids: ids })}
                    options={refSelectOptions.map((o) => ({ value: o.id, label: o.label }))}
                    optionFilterProp="label"
                    showSearch
                  />
                  <Divider orientationMargin={0} style={{ margin: '12px 0' }}>
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
                    value={selectedNode.dify_dataset_id ?? undefined}
                    onChange={(v) => patchSelected({ dify_dataset_id: v ?? null })}
                    options={difyDatasets.map((d) => ({ value: d.id, label: d.name || d.id }))}
                    optionFilterProp="label"
                  />
                  <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 6 }}>
                    关键字（可多个）
                  </Typography.Text>
                  <Select
                    mode="tags"
                    style={{ width: '100%' }}
                    placeholder="输入后回车添加关键字"
                    value={selectedNode.knowledge_keywords ?? []}
                    onChange={(tags) => patchSelected({ knowledge_keywords: tags })}
                    tokenSeparators={[',', '，']}
                  />
                  <Divider orientationMargin={0} style={{ margin: '12px 0' }}>
                    审核提示词
                  </Divider>
                  <Space style={{ marginBottom: 8 }}>
                    <Button
                      size="small"
                      icon={<HistoryOutlined />}
                      onClick={() =>
                        setHistoryCtx({
                          nodeId: selectedNode.id,
                          field: 'review_prompt',
                          title: `${selectedNode.title} · 审核提示词`,
                        })
                      }
                    >
                      历史
                    </Button>
                    <Button
                      size="small"
                      icon={<RobotOutlined />}
                      disabled={!selectedNode.review_prompt?.trim()}
                      onClick={() =>
                        setOptimizeCtx({
                          kind: 'review_prompt',
                          currentText: selectedNode.review_prompt ?? '',
                        })
                      }
                    >
                      AI优化
                    </Button>
                  </Space>
                  <Input.TextArea
                    rows={6}
                    placeholder="填写该节点审核时的提示说明…（一句一行一条检查项，下行实时显示拆分结果）"
                    value={selectedNode.review_prompt ?? ''}
                    onChange={(e) => patchSelected({ review_prompt: e.target.value })}
                  />
                  <Card size="small" style={{ marginTop: 8 }} styles={{ body: { padding: 8 } }}>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      拆分预览{splitLoading ? '（更新中…）' : ''}
                      {splitPreview
                        ? `：共 ${splitPreview.items.length} 条检查项${splitPreview.notes.length ? `，${splitPreview.notes.length} 条判定附注` : ''}`
                        : ''}
                    </Typography.Text>
                    {splitPreview && (
                      <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                        {splitPreview.items.map((it) => (
                          <li key={it.id} style={{ fontSize: 12 }}>
                            <Typography.Text code>{it.id}</Typography.Text>{' '}
                            <Typography.Text style={{ fontSize: 12 }}>{it.text}</Typography.Text>
                          </li>
                        ))}
                        {splitPreview.notes.map((n, i) => (
                          <li key={`note-${i}`} style={{ fontSize: 12 }}>
                            <Tag color="default" style={{ fontSize: 11 }}>
                              附注
                            </Tag>
                            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                              {n}
                            </Typography.Text>
                          </li>
                        ))}
                      </ul>
                    )}
                  </Card>
                  <Divider orientationMargin={0} style={{ margin: '12px 0' }}>
                    上下文一致性校验
                  </Divider>
                  <Typography.Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 8 }}>
                    选择需与本章节对照的节点，用于审核时检查跨章节表述是否一致、是否存在语义冲突（不选表示不做该项比对）
                  </Typography.Paragraph>
                  <Select
                    mode="multiple"
                    allowClear
                    style={{ width: '100%' }}
                    placeholder="选择参与一致性比对的节点"
                    value={selectedNode.context_consistency_ref_node_ids ?? []}
                    onChange={(ids) => patchSelected({ context_consistency_ref_node_ids: ids })}
                    options={refSelectOptions.map((o) => ({ value: o.id, label: o.label }))}
                    optionFilterProp="label"
                    showSearch
                  />
                  <Typography.Paragraph type="secondary" style={{ fontSize: 13, marginTop: 12, marginBottom: 8 }}>
                    可选：填写本节点一致性检查的重点、术语口径、数据字段对应关系等，供模型在比对时遵循
                  </Typography.Paragraph>
                  <Space style={{ marginTop: 4, marginBottom: 8 }}>
                    <Button
                      size="small"
                      icon={<HistoryOutlined />}
                      onClick={() =>
                        setHistoryCtx({
                          nodeId: selectedNode.id,
                          field: 'context_consistency_prompt',
                          title: `${selectedNode.title} · 上下文一致性提示词`,
                        })
                      }
                    >
                      历史
                    </Button>
                    <Button
                      size="small"
                      icon={<RobotOutlined />}
                      disabled={!selectedNode.context_consistency_prompt?.trim()}
                      onClick={() =>
                        setOptimizeCtx({
                          kind: 'context_consistency_prompt',
                          currentText: selectedNode.context_consistency_prompt ?? '',
                        })
                      }
                    >
                      AI优化
                    </Button>
                  </Space>
                  <Input.TextArea
                    rows={4}
                    placeholder="例如：重点核对工程量与附件表是否一致；术语「开挖」与「土方开挖」视为同义…"
                    value={selectedNode.context_consistency_prompt ?? ''}
                    onChange={(e) => patchSelected({ context_consistency_prompt: e.target.value })}
                  />
                  <Divider orientationMargin={0} style={{ margin: '12px 0' }}>
                    编制依据
                  </Divider>
                  <Typography.Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 8 }}>
                    默认关闭；开启后对该节点执行编制依据相关审核，关闭则跳过
                  </Typography.Paragraph>
                  <Space align="center" size="middle">
                    <Typography.Text>编制依据审核</Typography.Text>
                    <Switch
                      checked={selectedNode.compilation_basis_audit_enabled === true}
                      onChange={(on) => patchSelected({ compilation_basis_audit_enabled: on })}
                      checkedChildren="开"
                      unCheckedChildren="关"
                    />
                  </Space>
                  <Divider orientationMargin={0} style={{ margin: '12px 0' }}>
                    图审核
                  </Divider>
                  <Typography.Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 8 }}>
                    审核本章节（含子章节）的附图，与内容审核相互独立。「是否有图」为确定性检查不耗模型；
                    「图种」「内容要素」逐图调用视觉模型判定。配置随结构一并保存。
                  </Typography.Paragraph>
                  {(() => {
                    const imgCfg = selectedNode.image_review
                    const setImg = (patch: Partial<NonNullable<TemplateNode['image_review']>>) => {
                      const base = imgCfg ?? { enabled: true }
                      patchSelected({ image_review: { ...base, ...patch } })
                    }
                    const setCat = (
                      cat: 'existence' | 'kind' | 'content',
                      patch: { enabled?: boolean; note?: string },
                    ) => {
                      setImg({ [cat]: { ...(imgCfg?.[cat] ?? {}), ...patch } })
                    }
                    return (
                      <div>
                        <Space align="center" size="middle" style={{ marginBottom: 8 }}>
                          <Typography.Text>启用图审核</Typography.Text>
                          <Switch
                            checked={imgCfg?.enabled === true}
                            onChange={(on) => setImg({ enabled: on })}
                            checkedChildren="开"
                            unCheckedChildren="关"
                          />
                          <Button
                            size="small"
                            icon={<HistoryOutlined />}
                            onClick={() =>
                              setHistoryCtx({
                                nodeId: selectedNode.id,
                                field: 'image_review',
                                title: `${selectedNode.title} · 图审核配置`,
                              })
                            }
                          >
                            历史
                          </Button>
                        </Space>
                        {imgCfg?.enabled ? (
                          <div style={{ display: 'grid', gap: 10 }}>
                            {(
                              [
                                {
                                  key: 'existence' as const,
                                  label: '是否有图',
                                  hint: '确定性检查：子树内存在附图即通过，无需模型。补充说明写图件名，缺图时随问题展示',
                                  ph: '如：施工总平面布置图、悬挑区域结构平面布置图',
                                },
                                {
                                  key: 'kind' as const,
                                  label: '图种识别',
                                  hint: '视觉模型判断图片是否为要求的图种（如路线图、布置图，而非无关照片）',
                                  ph: '如：本图应为应急救援路线图',
                                },
                                {
                                  key: 'content' as const,
                                  label: '内容要素',
                                  hint: '视觉模型逐图核对图上应标明的要素是否齐全',
                                  ph: '如：应标明集合点、疏散路线方向、安全出口位置',
                                },
                              ] as const
                            ).map((row) => (
                              <div
                                key={row.key}
                                style={{
                                  border: '1px solid var(--ant-color-split, #f0f0f0)',
                                  borderRadius: 6,
                                  padding: '6px 10px',
                                }}
                              >
                                <Checkbox
                                  checked={imgCfg?.[row.key]?.enabled === true}
                                  onChange={(e) => setCat(row.key, { enabled: e.target.checked })}
                                >
                                  <Typography.Text strong>{row.label}</Typography.Text>
                                </Checkbox>
                                <Typography.Text
                                  type="secondary"
                                  style={{ display: 'block', fontSize: 12, margin: '2px 0 6px' }}
                                >
                                  {row.hint}
                                </Typography.Text>
                                {imgCfg?.[row.key]?.enabled ? (
                                  <Input.TextArea
                                    rows={2}
                                    value={imgCfg?.[row.key]?.note ?? ''}
                                    onChange={(e) => setCat(row.key, { note: e.target.value })}
                                    placeholder={row.ph}
                                  />
                                ) : null}
                              </div>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    )
                  })()}
                </div>
              )}
            </div>
          </div>
        ) : (
          <Typography.Text type="secondary">
            无可展示的标题结构（请确认 Word 使用了标题样式）
          </Typography.Text>
        )}
      </Modal>

      <PromptHistoryModal
        open={!!historyCtx}
        schemeTypeId={preview?.scheme_type_id ?? 0}
        nodeId={historyCtx?.nodeId ?? ''}
        field={historyCtx?.field ?? ''}
        title={historyCtx?.title ?? ''}
        onClose={() => setHistoryCtx(null)}
        onRestored={(updated) => setPreview(updated)}
      />

      <PromptRegressionModal
        open={regressionOpen}
        schemeTypeId={preview?.scheme_type_id ?? 0}
        schemeName={preview?.original_filename ?? ''}
        onClose={() => setRegressionOpen(false)}
      />

      <PromptOptimizeModal
        open={!!optimizeCtx}
        schemeTypeId={preview?.scheme_type_id ?? 0}
        kind={optimizeCtx?.kind ?? 'review_prompt'}
        nodeTitle={selectedNode?.title ?? ''}
        schemeName={preview ? `${preview.original_filename ?? ''}` : ''}
        currentText={optimizeCtx?.currentText ?? ''}
        onClose={() => setOptimizeCtx(null)}
        onApply={(text) => {
          if (!optimizeCtx) return
          patchSelected({ [optimizeCtx.kind]: text } as Partial<TemplateNode>)
          message.info('已填入优化结果，请核对后点「更新」保存')
        }}
      />

      <ReviewWorkflowModal
        open={!!workflowScheme}
        schemeName={workflowScheme?.name ?? ''}
        schemeTypeId={workflowScheme?.id ?? 0}
        template={workflowTemplate}
        loading={workflowLoading}
        onClose={() => {
          setWorkflowScheme(null)
          setWorkflowTemplate(null)
        }}
        onSaved={() => {
          void qc.invalidateQueries({ queryKey: ['schemes'] })
        }}
      />

      <FullDocumentReviewModal
        open={!!fullDocScheme}
        scheme={fullDocScheme}
        template={fullDocTemplate}
        loading={fullDocLoading}
        onClose={() => {
          setFullDocScheme(null)
          setFullDocTemplate(null)
        }}
        onSaved={() => {
          void qc.invalidateQueries({ queryKey: ['schemes'] })
        }}
      />

      <Modal
        title={uploadScheme ? `上传模版 — ${uploadScheme.name}` : '上传模版'}
        open={!!uploadScheme}
        onCancel={() => setUploadScheme(null)}
        footer={null}
        destroyOnClose
      >
        <Upload.Dragger
          accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          maxCount={1}
          beforeUpload={(file) => {
            const maxBytes = maxUploadMb * 1024 * 1024
            if (file.size > maxBytes) {
              message.warning(`文件超过 ${maxUploadMb} MB 限制`)
              return Upload.LIST_IGNORE
            }
            if (!uploadScheme) return false
            uploadMut.mutate({ schemeId: uploadScheme.id, file })
            return false
          }}
          disabled={uploadMut.isPending}
        >
          <p>点击或拖拽 .docx 到此上传</p>
        </Upload.Dragger>
      </Modal>
    </PageShell>
  )
}
