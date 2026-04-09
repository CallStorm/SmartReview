import { FormOutlined } from '@ant-design/icons'
import {
  App as AntApp,
  Button,
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
import type { DifyDatasetItem, SchemeType, TemplateNode, TemplatePublic } from '../api/types'
import PageShell from '../components/PageShell'
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

  const [uploadScheme, setUploadScheme] = useState<SchemeType | null>(null)
  const [workflowScheme, setWorkflowScheme] = useState<SchemeType | null>(null)
  const [workflowTemplate, setWorkflowTemplate] = useState<TemplatePublic | null>(null)
  const [workflowLoading, setWorkflowLoading] = useState(false)
  const [preview, setPreview] = useState<TemplatePublic | null>(null)
  const [structureDraft, setStructureDraft] = useState<{ nodes: TemplateNode[] } | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

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
    onError: () => message.error('上传失败'),
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

  const selectedNode = useMemo(() => {
    if (!selectedNodeId || !structureDraft?.nodes.length) return null
    return findNodeById(structureDraft.nodes, selectedNodeId)
  }, [selectedNodeId, structureDraft])

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
            width: 360,
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
                      window.open(data.url, '_blank', 'noopener,noreferrer')
                    } catch {
                      message.warning('无法获取下载链接')
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
                  <Input.TextArea
                    rows={6}
                    placeholder="填写该节点审核时的提示说明…"
                    value={selectedNode.review_prompt ?? ''}
                    onChange={(e) => patchSelected({ review_prompt: e.target.value })}
                  />
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
