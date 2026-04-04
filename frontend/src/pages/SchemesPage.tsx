import { AppstoreOutlined } from '@ant-design/icons'
import { App as AntApp, Button, Form, Input, Modal, Popconfirm, Space, Table } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import type { SchemeType } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import PageShell from '../components/PageShell'

export default function SchemesPage() {
  const qc = useQueryClient()
  const { user } = useAuth()
  const { message } = AntApp.useApp()
  const isAdmin = user?.role === 'admin'

  const { data = [], isLoading } = useQuery({
    queryKey: ['schemes'],
    queryFn: async () => {
      const { data: rows } = await api.get<SchemeType[]>('/scheme-types')
      return rows
    },
  })

  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<SchemeType | null>(null)
  const [form] = Form.useForm()

  const saveMutation = useMutation({
    mutationFn: async (values: {
      category: string
      name: string
      remark?: string
    }) => {
      if (editing) {
        await api.patch(`/scheme-types/${editing.id}`, values)
      } else {
        await api.post('/scheme-types', values)
      }
    },
    onSuccess: async () => {
      message.success('已保存')
      setOpen(false)
      setEditing(null)
      form.resetFields()
      await qc.invalidateQueries({ queryKey: ['schemes'] })
    },
    onError: () => message.error('保存失败'),
  })

  const delMutation = useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/scheme-types/${id}`)
    },
    onSuccess: async () => {
      message.success('已删除')
      await qc.invalidateQueries({ queryKey: ['schemes'] })
    },
    onError: () => message.error('删除失败'),
  })

  return (
    <PageShell
      icon={<AppstoreOutlined />}
      description="维护施工方案大类与名称，供审核任务与 Word 模版绑定使用。"
      extra={
        isAdmin ? (
          <Button
            type="primary"
            onClick={() => {
              setEditing(null)
              form.resetFields()
              setOpen(true)
            }}
          >
            新建方案类型
          </Button>
        ) : undefined
      }
    >
      <Table
        rowKey="id"
        size="middle"
        loading={isLoading}
        dataSource={data}
        locale={{ emptyText: '暂无方案类型' }}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 72 },
          { title: '方案大类', dataIndex: 'category' },
          { title: '方案名称', dataIndex: 'name' },
          { title: '备注', dataIndex: 'remark' },
          ...(isAdmin
            ? [
                {
                  title: '操作',
                  key: 'actions',
                  render: (_: unknown, row: SchemeType) => (
                    <Space>
                      <Button
                        type="link"
                        onClick={() => {
                          setEditing(row)
                          form.setFieldsValue({
                            category: row.category,
                            name: row.name,
                            remark: row.remark ?? '',
                          })
                          setOpen(true)
                        }}
                      >
                        编辑
                      </Button>
                      <Popconfirm title="确定删除？" onConfirm={() => delMutation.mutate(row.id)}>
                        <Button type="link" danger>
                          删除
                        </Button>
                      </Popconfirm>
                    </Space>
                  ),
                },
              ]
            : []),
        ]}
      />
      <Modal
        title={editing ? '编辑方案类型' : '新建方案类型'}
        open={open}
        onCancel={() => {
          setOpen(false)
          setEditing(null)
          form.resetFields()
        }}
        onOk={() => form.submit()}
        confirmLoading={saveMutation.isPending}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(v) => saveMutation.mutate(v)}
          initialValues={{ category: '', remark: '' }}
        >
          <Form.Item
            name="category"
            label="方案大类"
            rules={[{ required: true, message: '请输入方案大类' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="name" label="方案名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  )
}
