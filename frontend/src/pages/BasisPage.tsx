import {
  App as AntApp,
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Table,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import type { BasisItem } from '../api/types'

export default function BasisPage() {
  const qc = useQueryClient()
  const { message } = AntApp.useApp()
  const { data = [], isLoading } = useQuery({
    queryKey: ['basis'],
    queryFn: async () => {
      const { data: rows } = await api.get<BasisItem[]>('/basis')
      return rows
    },
  })

  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<BasisItem | null>(null)
  const [form] = Form.useForm()

  const saveMutation = useMutation({
    mutationFn: async (values: Record<string, unknown>) => {
      if (editing) {
        const { basis_id: _b, ...patch } = values
        await api.patch(`/basis/${editing.id}`, patch)
      } else {
        await api.post('/basis', values)
      }
    },
    onSuccess: async () => {
      message.success('已保存')
      setOpen(false)
      setEditing(null)
      form.resetFields()
      await qc.invalidateQueries({ queryKey: ['basis'] })
    },
    onError: () => message.error('保存失败'),
  })

  const delMutation = useMutation({
    mutationFn: async (id: number) => api.delete(`/basis/${id}`),
    onSuccess: async () => {
      message.success('已删除')
      await qc.invalidateQueries({ queryKey: ['basis'] })
    },
    onError: () => message.error('删除失败'),
  })

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button
          type="primary"
          onClick={() => {
            setEditing(null)
            form.resetFields()
            setOpen(true)
          }}
        >
          新建编制依据
        </Button>
      </Space>
      <Table
        rowKey="id"
        loading={isLoading}
        scroll={{ x: 1200 }}
        dataSource={data}
        columns={[
          { title: '依据ID', dataIndex: 'basis_id', width: 120, fixed: 'left' },
          { title: '文献类型', dataIndex: 'doc_type', width: 88 },
          { title: '标准号', dataIndex: 'standard_no', width: 140 },
          { title: '文献名称', dataIndex: 'doc_name', width: 220 },
          { title: '效力状态', dataIndex: 'effect_status', width: 88 },
          {
            title: '必引',
            dataIndex: 'is_mandatory',
            width: 72,
            render: (v: boolean) => (v ? '是' : '否'),
          },
          { title: '方案大类', dataIndex: 'scheme_category', width: 160 },
          { title: '方案名称', dataIndex: 'scheme_name', width: 140 },
          { title: '备注', dataIndex: 'remark' },
          {
            title: '操作',
            key: 'actions',
            fixed: 'right',
            width: 160,
            render: (_: unknown, row: BasisItem) => (
              <Space>
                <Button
                  type="link"
                  onClick={() => {
                    setEditing(row)
                    form.setFieldsValue({ ...row })
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
        ]}
      />
      <Modal
        title={editing ? '编辑编制依据' : '新建编制依据'}
        open={open}
        width={640}
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
          initialValues={{
            doc_type: '',
            standard_no: '',
            doc_name: '',
            effect_status: '',
            is_mandatory: false,
            scheme_category: '',
            scheme_name: '',
            remark: '',
          }}
        >
          <Form.Item
            name="basis_id"
            label="依据ID"
            rules={[{ required: true }]}
            hidden={!!editing}
          >
            <Input disabled={!!editing} />
          </Form.Item>
          {editing && (
            <Form.Item label="依据ID">
              <Input value={editing.basis_id} disabled />
            </Form.Item>
          )}
          <Form.Item name="doc_type" label="文献类型">
            <Input />
          </Form.Item>
          <Form.Item name="standard_no" label="标准号">
            <Input />
          </Form.Item>
          <Form.Item name="doc_name" label="文献名称">
            <Input />
          </Form.Item>
          <Form.Item name="effect_status" label="效力状态">
            <Input />
          </Form.Item>
          <Form.Item name="is_mandatory" label="是否必引" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="scheme_category" label="方案大类">
            <Input />
          </Form.Item>
          <Form.Item name="scheme_name" label="方案名称">
            <Input />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
