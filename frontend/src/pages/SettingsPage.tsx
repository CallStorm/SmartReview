import { SettingOutlined } from '@ant-design/icons'
import {
  App as AntApp,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Row,
  Space,
  Switch,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, type ReactNode } from 'react'
import { api } from '../api/client'
import PageShell from '../components/PageShell'
import type {
  KnowledgeBaseSettings,
  DashboardSettings,
  ModelProviderSettings,
  ModelTestResult,
  OnlyofficeSettings,
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

type OnlyofficeForm = {
  docs_url: string
  callback_base_url: string
  editor_lang: string
  jwt_secret?: string
}

type DashboardForm = {
  refresh_interval_minutes: number
  prompt_debug_enabled: boolean
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
  const [ooForm] = Form.useForm<OnlyofficeForm>()
  const [dashboardForm] = Form.useForm<DashboardForm>()

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

  const { data: ooData, isLoading: ooLoading } = useQuery({
    queryKey: ['settings', 'onlyoffice'],
    queryFn: async () => {
      const { data: row } = await api.get<OnlyofficeSettings>('/settings/onlyoffice')
      return row
    },
  })

  const { data: dashboardData, isLoading: dashboardLoading } = useQuery({
    queryKey: ['settings', 'dashboard'],
    queryFn: async () => {
      const { data: row } = await api.get<DashboardSettings>('/settings/dashboard')
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

  useEffect(() => {
    if (ooData) {
      ooForm.setFieldsValue({
        docs_url: ooData.docs_url,
        callback_base_url: ooData.callback_base_url,
        editor_lang: ooData.editor_lang || 'zh',
        jwt_secret: '',
      })
    }
  }, [ooData, ooForm])

  useEffect(() => {
    if (dashboardData) {
      dashboardForm.setFieldsValue({
        refresh_interval_minutes: dashboardData.refresh_interval_minutes,
        prompt_debug_enabled: dashboardData.prompt_debug_enabled,
      })
    }
  }, [dashboardData, dashboardForm])

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

  const saveOoMut = useMutation({
    mutationFn: async (values: OnlyofficeForm) => {
      const payload: Record<string, string> = {
        docs_url: values.docs_url.trim(),
        callback_base_url: values.callback_base_url.trim(),
        editor_lang: (values.editor_lang || 'zh').trim(),
      }
      const k = values.jwt_secret?.trim()
      if (k) payload.jwt_secret = k
      await api.put<OnlyofficeSettings>('/settings/onlyoffice', payload)
    },
    onSuccess: async () => {
      message.success('已保存 OnlyOffice 配置')
      await qc.invalidateQueries({ queryKey: ['settings', 'onlyoffice'] })
    },
    onError: () => message.error('保存失败'),
  })

  const saveDashboardMut = useMutation({
    mutationFn: async (values: DashboardForm) => {
      await api.put<DashboardSettings>('/settings/dashboard', {
        refresh_interval_minutes: values.refresh_interval_minutes,
        prompt_debug_enabled: values.prompt_debug_enabled,
      })
    },
    onSuccess: async () => {
      message.success('已保存看板统计配置（调试开关仅对新任务生效）')
      await qc.invalidateQueries({ queryKey: ['settings', 'dashboard'] })
    },
    onError: () => message.error('保存失败'),
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

  const onlyofficeTab: ReactNode = (
    <Card title="OnlyOffice 在线文档" loading={ooLoading}>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        配置 ONLYOFFICE Document Server 地址、与文档服务一致的 JWT 密钥，以及<strong>文档服务能访问到的</strong>
        本 API 根地址（回调与拉取文档用）。若 Document Server 运行在 Docker 或远端，回调基址勿填本机
        localhost（除非 Docs 与 API 同机）。未在此填写时，将使用服务端环境变量中的兜底配置。
      </Typography.Paragraph>
      {ooData ? (
        <div style={{ marginBottom: 16 }}>
          <Space>
            <span>JWT 状态：</span>
            {ooData.jwt_configured ? (
              <Tag color="success">已配置（含环境变量兜底）</Tag>
            ) : (
              <Tag>未配置</Tag>
            )}
          </Space>
        </div>
      ) : null}
      <Form
        form={ooForm}
        layout="vertical"
        onFinish={(v) => saveOoMut.mutate(v)}
        disabled={saveOoMut.isPending}
        initialValues={{ editor_lang: 'zh' }}
      >
        <Form.Item
          label="Document Server 地址"
          name="docs_url"
          rules={[{ required: true, message: '请填写 Docs 根地址' }]}
          extra="例如 http://127.0.0.1:9080，用于加载 api.js 与打开编辑器"
        >
          <Input placeholder="http://127.0.0.1:9080" autoComplete="off" />
        </Form.Item>
        <Form.Item
          label="回调与文档 URL 基址"
          name="callback_base_url"
          rules={[{ required: true, message: '请填写 API 根地址' }]}
          extra="例如 http://192.168.1.10:8000（从 Document Server 容器内可访问）"
        >
          <Input placeholder="http://127.0.0.1:8000" autoComplete="off" />
        </Form.Item>
        <Form.Item label="编辑器界面语言" name="editor_lang">
          <Input placeholder="zh" autoComplete="off" />
        </Form.Item>
        <Form.Item
          label="JWT 密钥"
          name="jwt_secret"
          extra="须与 Document Server local.json 中 JWT secret 一致；留空表示不修改已保存的密钥"
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={saveOoMut.isPending}>
            保存
          </Button>
        </Form.Item>
      </Form>
    </Card>
  )

  const dashboardTab: ReactNode = (
    <Card title="数据看板统计" loading={dashboardLoading}>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        设置后台聚合统计的刷新间隔。看板页面将始终读取最近一次快照，不在请求时重算。
      </Typography.Paragraph>
      <Form
        form={dashboardForm}
        layout="vertical"
        onFinish={(v) => saveDashboardMut.mutate(v)}
        disabled={saveDashboardMut.isPending}
      >
        <Form.Item
          label="统计刷新间隔（分钟）"
          name="refresh_interval_minutes"
          rules={[{ required: true, message: '请填写刷新间隔' }]}
          extra="建议 5-240 分钟；修改后在下一轮调度生效"
        >
          <InputNumber min={5} max={240} precision={0} style={{ width: 220 }} />
        </Form.Item>
        <Form.Item
          label="方案审核提示词调试"
          name="prompt_debug_enabled"
          valuePropName="checked"
          extra="开启后会记录每一步最终拼接提示词，仅对开启后新任务生效，用于排查审核行为"
        >
          <Switch checkedChildren="开启" unCheckedChildren="关闭" />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={saveDashboardMut.isPending}>
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
    <PageShell
      icon={<SettingOutlined />}
      description="配置知识库（Dify）、大模型供应商与 OnlyOffice 文档服务，密钥仅保存在服务端。"
    >
      <div style={{ maxWidth: 1040 }}>
        <Tabs
          items={[
            { key: 'kb', label: '知识库', children: knowledgeTab },
            { key: 'model', label: '模型配置', children: modelTab },
            { key: 'dashboard', label: '数据看板', children: dashboardTab },
            { key: 'onlyoffice', label: 'OnlyOffice', children: onlyofficeTab },
          ]}
        />
      </div>
    </PageShell>
  )
}
