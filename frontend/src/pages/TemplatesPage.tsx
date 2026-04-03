import {
  App as AntApp,
  Button,
  Modal,
  Space,
  Table,
  Tag,
  Tree,
  Upload,
  Typography,
} from 'antd'
import type { DataNode } from 'antd/es/tree'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import type { SchemeType, TemplateNode, TemplatePublic } from '../api/types'

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
  const [preview, setPreview] = useState<TemplatePublic | null>(null)

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

  return (
    <div>
      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={schemes}
        scroll={{ x: 'max-content' }}
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
            title: '操作',
            key: 'actions',
            width: 268,
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
                  结构
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

      <Modal
        title="模版结构（标题树）"
        open={!!preview}
        onCancel={() => setPreview(null)}
        width={720}
        footer={null}
        destroyOnClose
      >
        {preview?.parsed_structure?.nodes?.length ? (
          <Tree treeData={nodesToTreeData(preview.parsed_structure.nodes)} />
        ) : (
          <Typography.Text type="secondary">无可展示的标题结构（请确认 Word 使用了标题样式）</Typography.Text>
        )}
      </Modal>
    </div>
  )
}
