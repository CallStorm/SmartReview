import { App as AntApp, Button, Card, Form, Input, Space, Tag, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api } from '../api/client'
import type { KnowledgeBaseSettings } from '../api/types'

export default function SettingsPage() {
  const qc = useQueryClient()
  const { message } = AntApp.useApp()
  const [form] = Form.useForm<{ dify_base_url: string; dify_api_key?: string }>()

  const { data, isLoading } = useQuery({
    queryKey: ['settings', 'knowledge-base'],
    queryFn: async () => {
      const { data: row } = await api.get<KnowledgeBaseSettings>('/settings/knowledge-base')
      return row
    },
  })

  useEffect(() => {
    if (data) {
      form.setFieldsValue({ dify_base_url: data.dify_base_url, dify_api_key: '' })
    }
  }, [data, form])

  const saveMut = useMutation({
    mutationFn: async (values: { dify_base_url: string; dify_api_key?: string }) => {
      const payload: { dify_base_url: string; dify_api_key?: string } = {
        dify_base_url: values.dify_base_url.trim(),
      }
      const k = values.dify_api_key?.trim()
      if (k) payload.dify_api_key = k
      await api.put<KnowledgeBaseSettings>('/settings/knowledge-base', payload)
    },
    onSuccess: async () => {
      message.success('已保存知识库配置')
      await qc.invalidateQueries({ queryKey: ['settings', 'knowledge-base'] })
    },
    onError: () => message.error('保存失败'),
  })

  return (
    <div style={{ maxWidth: 640 }}>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        设置
      </Typography.Title>

      <Card title="知识库服务（Dify）" loading={isLoading}>
        <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
          配置 Dify 开放 API 根地址与密钥，供后续检索等功能使用。密钥仅保存在服务端，不会回显完整内容。
        </Typography.Paragraph>

        {data ? (
          <div style={{ marginBottom: 16 }}>
            <Space>
              <span>密钥状态：</span>
              {data.api_key_configured ? (
                <Tag color="success">已配置</Tag>
              ) : (
                <Tag>未配置</Tag>
              )}
            </Space>
          </div>
        ) : null}

        <Form
          form={form}
          layout="vertical"
          onFinish={(v) => saveMut.mutate(v)}
          disabled={saveMut.isPending}
        >
          <Form.Item
            label="Dify 服务地址"
            name="dify_base_url"
            rules={[{ required: true, message: '请填写服务地址' }]}
          >
            <Input placeholder="例如 http://10.73.2.13/v1" autoComplete="off" />
          </Form.Item>
          <Form.Item
            label="API 密钥"
            name="dify_api_key"
            extra="留空表示不修改已保存的密钥"
          >
            <Input.Password placeholder="dataset-…" autoComplete="new-password" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={saveMut.isPending}>
              保存
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
