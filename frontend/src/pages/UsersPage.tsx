import { TeamOutlined } from '@ant-design/icons'
import {
  App as AntApp,
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import type { UserListItem, UserRole } from '../api/types'
import PageShell from '../components/PageShell'
import { useAuth } from '../auth/AuthContext'
import { formatApiErrorMessage } from '../utils/apiError'

const ROLE_OPTIONS: { label: string; value: UserRole }[] = [
  { label: '普通用户', value: 'user' },
  { label: '管理员', value: 'admin' },
]

type CreateForm = {
  username: string
  phone: string
  password: string
  role: UserRole
}

type EditForm = {
  username: string
  phone: string
  password?: string
  role: UserRole
}

export default function UsersPage() {
  const qc = useQueryClient()
  const { message } = AntApp.useApp()
  const { user: currentUser } = useAuth()
  const [createOpen, setCreateOpen] = useState(false)
  const [editRow, setEditRow] = useState<UserListItem | null>(null)
  const [createForm] = Form.useForm<CreateForm>()
  const [editForm] = Form.useForm<EditForm>()

  const { data = [], isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      const { data: rows } = await api.get<UserListItem[]>('/users')
      return rows
    },
  })

  const createMut = useMutation({
    mutationFn: async (values: CreateForm) => {
      await api.post<UserListItem>('/users', {
        username: values.username.trim(),
        phone: values.phone.trim(),
        password: values.password,
        role: values.role,
      })
    },
    onSuccess: () => {
      message.success('用户已创建')
      setCreateOpen(false)
      createForm.resetFields()
      void qc.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (e) => message.error(formatApiErrorMessage(e, '创建失败')),
  })

  const updateMut = useMutation({
    mutationFn: async ({ id, values }: { id: number; values: EditForm }) => {
      const payload: Record<string, unknown> = {
        username: values.username.trim(),
        phone: values.phone.trim(),
        role: values.role,
      }
      if (values.password?.trim()) {
        payload.password = values.password
      }
      await api.patch<UserListItem>(`/users/${id}`, payload)
    },
    onSuccess: () => {
      message.success('已保存')
      setEditRow(null)
      editForm.resetFields()
      void qc.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (e) => message.error(formatApiErrorMessage(e, '保存失败')),
  })

  const deleteMut = useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/users/${id}`)
    },
    onSuccess: () => {
      message.success('已删除')
      void qc.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (e) => message.error(formatApiErrorMessage(e, '删除失败')),
  })

  const columns: ColumnsType<UserListItem> = [
    { title: 'ID', dataIndex: 'id', width: 72 },
    { title: '用户名', dataIndex: 'username', ellipsis: true },
    { title: '手机号', dataIndex: 'phone', width: 140 },
    {
      title: '角色',
      dataIndex: 'role',
      width: 100,
      render: (r: UserRole) => (r === 'admin' ? '管理员' : '普通用户'),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (t: string | null) => (t ? new Date(t).toLocaleString() : '—'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      fixed: 'right',
      render: (_, row) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => openEdit(row)}>
            编辑
          </Button>
          <Popconfirm
            title="确定删除该用户？"
            description="其审核任务记录将一并删除。"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            disabled={row.id === currentUser?.id}
            onConfirm={() => deleteMut.mutate(row.id)}
          >
            <Button type="link" size="small" danger disabled={row.id === currentUser?.id}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  function openEdit(row: UserListItem) {
    setEditRow(row)
    editForm.setFieldsValue({
      username: row.username,
      phone: row.phone,
      role: row.role,
      password: undefined,
    })
  }

  return (
    <PageShell
      icon={<TeamOutlined />}
      description="创建与管理登录账号；仅管理员可访问。"
      extra={
        <Button type="primary" onClick={() => setCreateOpen(true)}>
          添加用户
        </Button>
      }
    >
      <Table<UserListItem>
        rowKey="id"
        loading={isLoading}
        columns={columns}
        dataSource={data}
        pagination={false}
        scroll={{ x: 900 }}
      />

      <Modal
        title="添加用户"
        open={createOpen}
        onCancel={() => {
          setCreateOpen(false)
          createForm.resetFields()
        }}
        okText="创建"
        confirmLoading={createMut.isPending}
        onOk={() => void createForm.submit()}
        destroyOnClose
      >
        <Form<CreateForm>
          form={createForm}
          layout="vertical"
          initialValues={{ role: 'user' as UserRole }}
          onFinish={(v) => createMut.mutate(v)}
        >
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input autoComplete="off" maxLength={64} />
          </Form.Item>
          <Form.Item
            name="phone"
            label="手机号"
            rules={[{ required: true, message: '请输入手机号' }]}
          >
            <Input autoComplete="off" maxLength={20} />
          </Form.Item>
          <Form.Item
            name="password"
            label="初始密码"
            rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '至少 6 位' }]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select options={ROLE_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑用户"
        open={editRow !== null}
        onCancel={() => {
          setEditRow(null)
          editForm.resetFields()
        }}
        okText="保存"
        confirmLoading={updateMut.isPending}
        onOk={() => void editForm.submit()}
        destroyOnClose
      >
        {editRow ? (
          <Form<EditForm>
            form={editForm}
            layout="vertical"
            onFinish={(values) => updateMut.mutate({ id: editRow.id, values })}
          >
            <Form.Item
              name="username"
              label="用户名"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input autoComplete="off" maxLength={64} />
            </Form.Item>
            <Form.Item
              name="phone"
              label="手机号"
              rules={[{ required: true, message: '请输入手机号' }]}
            >
              <Input autoComplete="off" maxLength={20} />
            </Form.Item>
            <Form.Item
              name="password"
              label="新密码（留空则不修改）"
              rules={[
                {
                  validator: async (_, value: string | undefined) => {
                    const v = value?.trim() ?? ''
                    if (!v) return
                    if (v.length < 6) throw new Error('至少 6 位')
                  },
                },
              ]}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
            <Form.Item name="role" label="角色" rules={[{ required: true }]}>
              <Select options={ROLE_OPTIONS} />
            </Form.Item>
          </Form>
        ) : null}
      </Modal>
    </PageShell>
  )
}
