import { SettingOutlined } from '@ant-design/icons'
import {
  App as AntApp,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Image,
  Input,
  InputNumber,
  Row,
  Space,
  Switch,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, type ReactNode } from 'react'
import type { UploadFile } from 'antd'
import { api } from '../api/client'
import PageShell from '../components/PageShell'
import type {
  KnowledgeBaseSettings,
  DashboardSettings,
  ModelProviderSettings,
  ModelTestResult,
  OnlyofficeSettings,
  ProviderId,
  ReviewSettings,
} from '../api/types'

type KbForm = { dify_base_url: string; dify_dataset_name_prefix: string; dify_api_key?: string }

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
}

type ReviewForm = {
  review_timeout_seconds: number
  prompt_debug_enabled: boolean
  worker_parallel_tasks: number
  compilation_basis_concurrency: number
  context_consistency_concurrency: number
  content_concurrency: number
  system_name: string
  logo_file?: UploadFile[]
  favicon_file?: UploadFile[]
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

function normalizeUploadEvent(event: { fileList?: UploadFile[] } | UploadFile[]) {
  if (Array.isArray(event)) return event
  return event?.fileList ?? []
}

export default function SettingsPage() {
  const qc = useQueryClient()
  const { message } = AntApp.useApp()
  const [kbForm] = Form.useForm<KbForm>()
  const [modelForm] = Form.useForm<ModelForm>()
  const [ooForm] = Form.useForm<OnlyofficeForm>()
  const [dashboardForm] = Form.useForm<DashboardForm>()
  const [reviewForm] = Form.useForm<ReviewForm>()

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

  const { data: reviewData, isLoading: reviewLoading } = useQuery({
    queryKey: ['settings', 'review'],
    queryFn: async () => {
      const { data: row } = await api.get<ReviewSettings>('/settings/review')
      return row
    },
  })

  useEffect(() => {
    if (kbData) {
      kbForm.setFieldsValue({
        dify_base_url: kbData.dify_base_url,
        dify_dataset_name_prefix: kbData.dify_dataset_name_prefix,
        dify_api_key: '',
      })
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
      })
    }
  }, [dashboardData, dashboardForm])

  useEffect(() => {
    if (reviewData) {
      reviewForm.setFieldsValue({
        review_timeout_seconds: reviewData.review_timeout_seconds,
        prompt_debug_enabled: reviewData.prompt_debug_enabled,
        worker_parallel_tasks: reviewData.worker_parallel_tasks,
        compilation_basis_concurrency: reviewData.compilation_basis_concurrency,
        context_consistency_concurrency: reviewData.context_consistency_concurrency,
        content_concurrency: reviewData.content_concurrency,
        system_name: reviewData.system_name,
        logo_file: [],
        favicon_file: [],
      })
    }
  }, [reviewData, reviewForm])

  const saveKbMut = useMutation({
    mutationFn: async (values: KbForm) => {
      const payload: { dify_base_url: string; dify_dataset_name_prefix: string; dify_api_key?: string } = {
        dify_base_url: values.dify_base_url.trim(),
        dify_dataset_name_prefix: values.dify_dataset_name_prefix.trim(),
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
      })
    },
    onSuccess: async () => {
      message.success('已保存看板统计配置')
      await qc.invalidateQueries({ queryKey: ['settings', 'dashboard'] })
    },
    onError: () => message.error('保存失败'),
  })

  const saveReviewMut = useMutation({
    mutationFn: async (values: ReviewForm) => {
      const formData = new FormData()
      formData.append('review_timeout_seconds', String(values.review_timeout_seconds))
      formData.append('prompt_debug_enabled', String(Boolean(values.prompt_debug_enabled)))
      formData.append('worker_parallel_tasks', String(values.worker_parallel_tasks))
      formData.append(
        'compilation_basis_concurrency',
        String(values.compilation_basis_concurrency),
      )
      formData.append(
        'context_consistency_concurrency',
        String(values.context_consistency_concurrency),
      )
      formData.append('content_concurrency', String(values.content_concurrency))
      formData.append('system_name', values.system_name.trim())
      const logoFile = values.logo_file?.[0]?.originFileObj
      const faviconFile = values.favicon_file?.[0]?.originFileObj
      if (logoFile) formData.append('logo_file', logoFile)
      if (faviconFile) formData.append('favicon_file', faviconFile)
      await api.put<ReviewSettings>('/settings/review', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    },
    onSuccess: async () => {
      message.success('已保存审核与品牌配置（调试开关与并发仅对新领取任务生效）')
      await qc.invalidateQueries({ queryKey: ['settings', 'review'] })
      await qc.invalidateQueries({ queryKey: ['settings', 'review', 'public-branding'] })
      reviewForm.setFieldsValue({ logo_file: [], favicon_file: [] })
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
        <Form.Item
          label="知识库名称前缀过滤"
          name="dify_dataset_name_prefix"
          extra="仅展示名称以该前缀开头的知识库。留空表示不过滤。"
        >
          <Input placeholder="例如 项目A-" autoComplete="off" />
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
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={saveDashboardMut.isPending}>
            保存
          </Button>
        </Form.Item>
      </Form>
    </Card>
  )

  const reviewTab: ReactNode = (
    <Card title="审核配置" loading={reviewLoading}>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0, marginBottom: 0 }}>
        这里统一维护系统名称、登录页 / 菜单 logo、浏览器标签图标，以及审核运行参数。保存后，标题与图标会立即更新；超时、调试与并发通常仅对新任务生效。
      </Typography.Paragraph>
      <Form
        form={reviewForm}
        layout="vertical"
        onFinish={(v) => saveReviewMut.mutate(v)}
        disabled={saveReviewMut.isPending}
        style={{ marginTop: 16 }}
      >
        <Card
          type="inner"
          size="small"
          title={<Typography.Text strong>品牌展示</Typography.Text>}
          styles={{ body: { paddingBottom: 8 } }}
        >
          <Row gutter={[16, 16]}>
            <Col xs={24} lg={12}>
              <Form.Item
                label="系统名称"
                name="system_name"
                rules={[{ required: true, message: '请填写系统名称' }]}
                extra="登录页主标题与浏览器 tab title 使用此值。"
              >
                <Input maxLength={100} placeholder="例如：智能方案审核" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} md={12}>
              <Form.Item
                label="展示 Logo"
                name="logo_file"
                valuePropName="fileList"
                getValueFromEvent={normalizeUploadEvent}
                extra="用于登录页和左上角菜单。支持 PNG / JPG / SVG / WEBP，单文件不超过 2MB。"
              >
                <Upload beforeUpload={() => false} maxCount={1} accept=".png,.jpg,.jpeg,.svg,.webp" listType="picture">
                  <Button>选择 Logo</Button>
                </Upload>
              </Form.Item>
              {reviewData?.logo_url ? (
                <div style={{ marginTop: -8 }}>
                  <Typography.Text type="secondary">当前 Logo：</Typography.Text>
                  <div style={{ marginTop: 8 }}>
                    <Image
                      src={reviewData.logo_url}
                      alt={reviewData.system_name}
                      preview={false}
                      style={{ maxHeight: 40, width: 'auto', objectFit: 'contain' }}
                    />
                  </div>
                </div>
              ) : (
                <Typography.Text type="secondary">当前使用默认 Logo。</Typography.Text>
              )}
            </Col>

            <Col xs={24} md={12}>
              <Form.Item
                label="浏览器 Tab 图标"
                name="favicon_file"
                valuePropName="fileList"
                getValueFromEvent={normalizeUploadEvent}
                extra="用于浏览器标签页。支持 PNG / SVG / ICO / JPG / WEBP，单文件不超过 2MB。"
              >
                <Upload
                  beforeUpload={() => false}
                  maxCount={1}
                  accept=".png,.jpg,.jpeg,.svg,.webp,.ico"
                  listType="picture"
                >
                  <Button>选择 Tab 图标</Button>
                </Upload>
              </Form.Item>
              {reviewData?.favicon_url ? (
                <div style={{ marginTop: -8 }}>
                  <Typography.Text type="secondary">当前图标：</Typography.Text>
                  <div style={{ marginTop: 8 }}>
                    <Image
                      src={reviewData.favicon_url}
                      alt="favicon"
                      preview={false}
                      width={32}
                      height={32}
                    />
                  </div>
                </div>
              ) : (
                <Typography.Text type="secondary">当前使用默认 Tab 图标。</Typography.Text>
              )}
            </Col>
          </Row>
        </Card>

        <Card
          type="inner"
          size="small"
          title={
            <Space size={8}>
              <Typography.Text strong>运行与超时</Typography.Text>
              <Typography.Text type="secondary" style={{ fontWeight: 400, fontSize: 13 }}>
                单节点模型调用与上传等阶段的等待上限
              </Typography.Text>
            </Space>
          }
          styles={{ body: { paddingBottom: 8 } }}
        >
          <Form.Item
            label="审核超时（秒）"
            name="review_timeout_seconds"
            rules={[{ required: true, message: '请填写审核超时' }]}
            extra="建议 30～600。内容审核单节点模型调用超过该值将 fail-fast 并终止任务。"
          >
            <InputNumber min={30} max={600} precision={0} style={{ width: '100%', maxWidth: 280 }} />
          </Form.Item>
        </Card>

        <Card
          type="inner"
          size="small"
          title={<Typography.Text strong>调试</Typography.Text>}
          style={{ marginTop: 16 }}
          styles={{ body: { paddingBottom: 8 } }}
        >
          <Form.Item
            label="记录每步拼接提示词"
            name="prompt_debug_enabled"
            valuePropName="checked"
            extra="开启后审核结果中附带调试提示词，仅对开启后新提交的任务生效。"
          >
            <Switch checkedChildren="开" unCheckedChildren="关" />
          </Form.Item>
        </Card>

        <Card
          type="inner"
          size="small"
          title={<Typography.Text strong>并发与吞吐</Typography.Text>}
          style={{ marginTop: 16 }}
        >
          <Typography.Paragraph type="secondary" style={{ marginTop: 0, marginBottom: 0 }}>
            数值越大整体越快，但更容易触发上游限流。工作流步骤顺序不变，仅在「编制依据 / 上下文一致性 / 内容」各大类内部并行；范围均为 1～8。
          </Typography.Paragraph>

          <Divider plain style={{ margin: '16px 0 12px' }}>
            <Typography.Text type="secondary">任务队列</Typography.Text>
          </Divider>
          <Typography.Paragraph type="secondary" style={{ marginTop: 0, marginBottom: 12, fontSize: 13 }}>
            单个 worker 进程内，同时从队列领取并执行的审核任务数量。
          </Typography.Paragraph>
          <Form.Item
            label="同时处理任务数"
            name="worker_parallel_tasks"
            rules={[{ required: true, message: '请填写' }]}
          >
            <InputNumber min={1} max={8} precision={0} style={{ width: '100%', maxWidth: 280 }} />
          </Form.Item>

          <Divider plain style={{ margin: '20px 0 12px' }}>
            <Typography.Text type="secondary">审核步骤（各大类内）</Typography.Text>
          </Divider>
          <Typography.Paragraph type="secondary" style={{ marginTop: 0, marginBottom: 16, fontSize: 13 }}>
            以下三项分别控制对应审核阶段内、按模版节点拆分的并行度。
          </Typography.Paragraph>
          <Row gutter={[16, 16]}>
            <Col xs={24} sm={12} lg={8}>
              <Form.Item
                label="编制依据"
                name="compilation_basis_concurrency"
                rules={[{ required: true, message: '请填写' }]}
              >
                <InputNumber min={1} max={8} precision={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} lg={8}>
              <Form.Item
                label="上下文一致性"
                name="context_consistency_concurrency"
                rules={[{ required: true, message: '请填写' }]}
              >
                <InputNumber min={1} max={8} precision={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12} lg={8}>
              <Form.Item
                label="内容审核"
                name="content_concurrency"
                rules={[{ required: true, message: '请填写' }]}
              >
                <InputNumber min={1} max={8} precision={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        <Divider style={{ margin: '20px 0 16px' }} />
        <Form.Item style={{ marginBottom: 0 }}>
          <Button type="primary" htmlType="submit" loading={saveReviewMut.isPending}>
            保存审核与品牌配置
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
      description="配置品牌展示、知识库（Dify）、大模型供应商与 OnlyOffice 文档服务，密钥仅保存在服务端。"
    >
      <div style={{ maxWidth: 1040 }}>
        <Tabs
          items={[
            { key: 'kb', label: '知识库', children: knowledgeTab },
            { key: 'model', label: '模型配置', children: modelTab },
            { key: 'dashboard', label: '数据看板', children: dashboardTab },
            { key: 'review', label: '审核配置', children: reviewTab },
            { key: 'onlyoffice', label: 'OnlyOffice', children: onlyofficeTab },
          ]}
        />
      </div>
    </PageShell>
  )
}
