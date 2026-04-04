import {
  App as AntApp,
  Button,
  Card,
  Col,
  Form,
  Input,
  Row,
  Space,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, type ReactNode } from 'react'
import { api } from '../api/client'
import type {
  KnowledgeBaseSettings,
  ModelProviderSettings,
  ModelTestResult,
  ProviderId,
} from '../api/types'

type KbForm = { dify_base_url: string; dify_api_key?: string }

type ModelForm = {
  volcengine_base_url: string
  volcengine_api_key?: string
  volcengine_endpoint_id: string
  minimax_base_url: string
  minimax_api_key?: string
  minimax_model: string
}

function volcengineTestReady(m: ModelProviderSettings | undefined) {
  if (!m) return false
  const v = m.volcengine
  return Boolean(v.api_key_configured && v.base_url.trim() && v.endpoint_id.trim())
}

function minimaxTestReady(m: ModelProviderSettings | undefined) {
  if (!m) return false
  const x = m.minimax
  return Boolean(x.api_key_configured && x.base_url.trim() && x.model.trim())
}

export default function SettingsPage() {
  const qc = useQueryClient()
  const { message } = AntApp.useApp()
  const [kbForm] = Form.useForm<KbForm>()
  const [modelForm] = Form.useForm<ModelForm>()

  const { data: kbData, isLoading: kbLoading } = useQuery({
    queryKey: ['settings', 'knowledge-base'],
    queryFn: async () => {
      const { data: row } = await api.get<KnowledgeBaseSettings>('/settings/knowledge-base')
      return row
    },
  })

  const { data: modelData, isLoading: modelLoading } = useQuery({
    queryKey: ['settings', 'model-providers'],
    queryFn: async () => {
      const { data: row } = await api.get<ModelProviderSettings>('/settings/model-providers')
      return row
    },
  })

  useEffect(() => {
    if (kbData) {
      kbForm.setFieldsValue({ dify_base_url: kbData.dify_base_url, dify_api_key: '' })
    }
  }, [kbData, kbForm])

  useEffect(() => {
    if (modelData) {
      modelForm.setFieldsValue({
        volcengine_base_url: modelData.volcengine.base_url,
        volcengine_api_key: '',
        volcengine_endpoint_id: modelData.volcengine.endpoint_id,
        minimax_base_url: modelData.minimax.base_url,
        minimax_api_key: '',
        minimax_model: modelData.minimax.model,
      })
    }
  }, [modelData, modelForm])

  const saveKbMut = useMutation({
    mutationFn: async (values: KbForm) => {
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

  const saveModelMut = useMutation({
    mutationFn: async (values: ModelForm) => {
      const payload: Record<string, unknown> = {
        volcengine_base_url: values.volcengine_base_url.trim(),
        volcengine_endpoint_id: values.volcengine_endpoint_id.trim(),
        minimax_base_url: values.minimax_base_url.trim(),
        minimax_model: values.minimax_model.trim(),
      }
      const vk = values.volcengine_api_key?.trim()
      if (vk) payload.volcengine_api_key = vk
      const mk = values.minimax_api_key?.trim()
      if (mk) payload.minimax_api_key = mk
      await api.put<ModelProviderSettings>('/settings/model-providers', payload)
    },
    onSuccess: async () => {
      message.success('已保存模型配置')
      await qc.invalidateQueries({ queryKey: ['settings', 'model-providers'] })
    },
    onError: () => message.error('保存失败'),
  })

  const setDefaultMut = useMutation({
    mutationFn: async (provider: ProviderId | null) => {
      await api.put<ModelProviderSettings>('/settings/model-providers', {
        default_provider: provider,
      })
    },
    onSuccess: async (_, provider) => {
      message.success(provider == null ? '已清除默认供应商' : '已设为默认供应商')
      await qc.invalidateQueries({ queryKey: ['settings', 'model-providers'] })
    },
    onError: () => message.error('更新失败'),
  })

  const testMut = useMutation({
    mutationFn: async (provider: ProviderId) => {
      const { data } = await api.post<ModelTestResult>('/settings/model-providers/test', {
        provider,
      })
      return data
    },
    onSuccess: (data) => {
      if (data.ok) {
        message.success(
          `连接成功${data.latency_ms != null ? `（${data.latency_ms} ms）` : ''}：${data.preview ?? ''}`,
        )
      } else {
        message.error(data.error || '测试失败')
      }
    },
    onError: (err: unknown) => {
      const ax = err as { response?: { data?: { detail?: string } } }
      message.error(ax.response?.data?.detail ?? '请求失败')
    },
  })

  const defaultSummaryLabel = useMemo(() => {
    const d = modelData?.default_provider
    if (d === 'volcengine') return '火山引擎（OpenAI 兼容）'
    if (d === 'minimax') return 'MiniMax（Anthropic）'
    return '未指定'
  }, [modelData])

  const knowledgeTab: ReactNode = (
    <Card title="知识库服务（Dify）" loading={kbLoading}>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        配置 Dify 开放 API 根地址与密钥，供后续检索等功能使用。密钥仅保存在服务端，不会回显完整内容。
      </Typography.Paragraph>

      {kbData ? (
        <div style={{ marginBottom: 16 }}>
          <Space>
            <span>密钥状态：</span>
            {kbData.api_key_configured ? (
              <Tag color="success">已配置</Tag>
            ) : (
              <Tag>未配置</Tag>
            )}
          </Space>
        </div>
      ) : null}

      <Form
        form={kbForm}
        layout="vertical"
        onFinish={(v) => saveKbMut.mutate(v)}
        disabled={saveKbMut.isPending}
      >
        <Form.Item
          label="Dify 服务地址"
          name="dify_base_url"
          rules={[{ required: true, message: '请填写服务地址' }]}
        >
          <Input placeholder="例如 http://10.73.2.13/v1" autoComplete="off" />
        </Form.Item>
        <Form.Item label="API 密钥" name="dify_api_key" extra="留空表示不修改已保存的密钥">
          <Input.Password placeholder="dataset-…" autoComplete="new-password" />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={saveKbMut.isPending}>
            保存
          </Button>
        </Form.Item>
      </Form>
    </Card>
  )

  const modelTab: ReactNode = (
    <div>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        分别配置火山引擎（OpenAI 兼容）与 MiniMax 国内版（Anthropic
        形态）。请先保存再测试连接。密钥不回显。
      </Typography.Paragraph>

      <Form
        form={modelForm}
        layout="vertical"
        size="small"
        onFinish={(v) => saveModelMut.mutate(v)}
        disabled={saveModelMut.isPending || modelLoading}
        initialValues={{
          volcengine_base_url: '',
          volcengine_endpoint_id: '',
          minimax_base_url: '',
          minimax_model: '',
        }}
      >
        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <Card
              size="small"
              title={
                <Space size={4}>
                  <span>火山引擎</span>
                  <Tag style={{ marginInlineEnd: 0 }}>OpenAI</Tag>
                </Space>
              }
              loading={modelLoading}
              styles={{ body: { paddingBlock: 12 } }}
              extra={
                modelData?.volcengine.api_key_configured ? (
                  <Tag color="success" style={{ margin: 0 }}>
                    已配密钥
                  </Tag>
                ) : (
                  <Tag style={{ margin: 0 }}>未配密钥</Tag>
                )
              }
            >
              <Form.Item
                label="接入地址"
                name="volcengine_base_url"
                tooltip="OpenAI 兼容根路径，建议含 /v3"
              >
                <Input placeholder="…/api/v3" autoComplete="off" />
              </Form.Item>
              <Form.Item label="API Key" name="volcengine_api_key" tooltip="留空不修改已存密钥">
                <Input.Password autoComplete="new-password" />
              </Form.Item>
              <Form.Item label="接入点 ID" name="volcengine_endpoint_id" tooltip="作为 model，如 ep-…">
                <Input placeholder="ep-xxxx" autoComplete="off" />
              </Form.Item>
              <Space wrap size="small">
                <Button type="primary" size="small" htmlType="submit" loading={saveModelMut.isPending}>
                  保存
                </Button>
                <Tooltip
                  title={
                    volcengineTestReady(modelData)
                      ? ''
                      : '请先保存并填写接入地址、接入点与密钥'
                  }
                >
                  <Button
                    size="small"
                    disabled={!volcengineTestReady(modelData)}
                    loading={testMut.isPending}
                    onClick={() => testMut.mutate('volcengine')}
                  >
                    测试连接
                  </Button>
                </Tooltip>
                {modelData?.default_provider === 'volcengine' ? (
                  <Tag color="blue" style={{ margin: 0 }}>
                    默认
                  </Tag>
                ) : (
                  <Button
                    size="small"
                    type="default"
                    loading={setDefaultMut.isPending}
                    disabled={saveModelMut.isPending || modelLoading}
                    onClick={() => setDefaultMut.mutate('volcengine')}
                  >
                    设为默认
                  </Button>
                )}
              </Space>
            </Card>
          </Col>

          <Col xs={24} md={12}>
            <Card
              size="small"
              title={
                <Space size={4}>
                  <span>MiniMax</span>
                  <Tag style={{ marginInlineEnd: 0 }}>Anthropic</Tag>
                </Space>
              }
              loading={modelLoading}
              styles={{ body: { paddingBlock: 12 } }}
              extra={
                modelData?.minimax.api_key_configured ? (
                  <Tag color="success" style={{ margin: 0 }}>
                    已配密钥
                  </Tag>
                ) : (
                  <Tag style={{ margin: 0 }}>未配密钥</Tag>
                )
              }
            >
              <Form.Item
                label="接入地址"
                name="minimax_base_url"
                tooltip="Anthropic 兼容根路径，将请求 …/v1/messages"
              >
                <Input placeholder="…/anthropic" autoComplete="off" />
              </Form.Item>
              <Form.Item label="API Key" name="minimax_api_key" tooltip="留空不修改已存密钥">
                <Input.Password autoComplete="new-password" />
              </Form.Item>
              <Form.Item label="模型名" name="minimax_model" tooltip="如 MiniMax-M2.7">
                <Input placeholder="MiniMax-M2.7" autoComplete="off" />
              </Form.Item>
              <Space wrap size="small">
                <Button type="primary" size="small" htmlType="submit" loading={saveModelMut.isPending}>
                  保存
                </Button>
                <Tooltip
                  title={
                    minimaxTestReady(modelData)
                      ? ''
                      : '请先保存并填写接入地址、模型名与密钥'
                  }
                >
                  <Button
                    size="small"
                    disabled={!minimaxTestReady(modelData)}
                    loading={testMut.isPending}
                    onClick={() => testMut.mutate('minimax')}
                  >
                    测试连接
                  </Button>
                </Tooltip>
                {modelData?.default_provider === 'minimax' ? (
                  <Tag color="blue" style={{ margin: 0 }}>
                    默认
                  </Tag>
                ) : (
                  <Button
                    size="small"
                    type="default"
                    loading={setDefaultMut.isPending}
                    disabled={saveModelMut.isPending || modelLoading}
                    onClick={() => setDefaultMut.mutate('minimax')}
                  >
                    设为默认
                  </Button>
                )}
              </Space>
            </Card>
          </Col>
        </Row>
      </Form>

      <Typography.Paragraph style={{ marginBottom: 8 }}>
        <Typography.Text strong>当前默认供应商：</Typography.Text>{' '}
        <Typography.Text>{defaultSummaryLabel}</Typography.Text>
        {modelData?.default_provider ? (
          <>
            {' '}
            <Button
              type="link"
              size="small"
              style={{ padding: 0, height: 'auto' }}
              loading={setDefaultMut.isPending}
              onClick={() => setDefaultMut.mutate(null)}
            >
              清除默认
            </Button>
          </>
        ) : null}
      </Typography.Paragraph>
    </div>
  )

  return (
    <div style={{ maxWidth: 1040 }}>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        设置
      </Typography.Title>

      <Tabs
        items={[
          { key: 'kb', label: '知识库', children: knowledgeTab },
          { key: 'model', label: '模型配置', children: modelTab },
        ]}
      />
    </div>
  )
}
