import { useMutation } from '@tanstack/react-query'
import { App as AntApp, Alert, Button, Modal, Space, Spin, Typography } from 'antd'
import { api } from '../api/client'

interface Props {
  open: boolean
  schemeTypeId: number
  kind: 'review_prompt' | 'context_consistency_prompt'
  nodeTitle: string
  schemeName: string
  currentText: string
  onClose: () => void
  /** 管理员确认后，把优化文本写入编辑态（不直接保存） */
  onApply: (optimized: string) => void
}

interface OptimizeResp {
  optimized_text: string
  changes: string[]
}

export default function PromptOptimizeModal({
  open,
  schemeTypeId,
  kind,
  nodeTitle,
  schemeName,
  currentText,
  onClose,
  onApply,
}: Props) {
  const { message } = AntApp.useApp()

  const mut = useMutation({
    mutationFn: async (): Promise<OptimizeResp> => {
      const { data } = await api.post<OptimizeResp>(
        `/scheme-types/${schemeTypeId}/template/optimize-prompt`,
        {
          kind,
          node_title: nodeTitle,
          scheme_name: schemeName,
          current_text: currentText,
        },
      )
      return data
    },
    onError: (err: unknown) => {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined
      message.error(typeof detail === 'string' ? detail : '优化请求失败')
    },
  })

  return (
    <Modal
      title={`AI 优化提示词 - ${nodeTitle || schemeName}`}
      open={open}
      onCancel={onClose}
      width={860}
      destroyOnClose
      footer={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            disabled={!mut.data?.optimized_text}
            onClick={() => {
              if (mut.data?.optimized_text) {
                onApply(mut.data.optimized_text)
                onClose()
              }
            }}
          >
            采用优化结果（填入编辑框，稍后手动保存）
          </Button>
        </Space>
      }
    >
      {mut.isPending && (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <Spin tip="模型优化中，约需 10~30 秒…" />
        </div>
      )}
      {mut.isError && <Alert type="error" message="优化失败，可重试" showIcon />}
      {mut.data && (
        <div>
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 12 }}
            message="采用后仅填入编辑框，不会自动保存；请核对内容后点「保存」，保存会自动记入历史、可回滚。"
          />
          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <Typography.Text type="secondary">当前提示词</Typography.Text>
              <Typography.Paragraph
                style={{
                  whiteSpace: 'pre-wrap',
                  fontSize: 12,
                  background: '#fafafa',
                  padding: 8,
                  maxHeight: 320,
                  overflow: 'auto',
                }}
              >
                {currentText}
              </Typography.Paragraph>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <Typography.Text type="secondary">优化后</Typography.Text>
              <Typography.Paragraph
                style={{
                  whiteSpace: 'pre-wrap',
                  fontSize: 12,
                  background: '#f6ffed',
                  padding: 8,
                  maxHeight: 320,
                  overflow: 'auto',
                }}
              >
                {mut.data.optimized_text}
              </Typography.Paragraph>
            </div>
          </div>
          {mut.data.changes.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <Typography.Text type="secondary">修改说明</Typography.Text>
              <ul style={{ margin: '6px 0', paddingLeft: 20 }}>
                {mut.data.changes.map((c, i) => (
                  <li key={i} style={{ fontSize: 13 }}>
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {mut.isIdle && (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            将按「一句一行一条检查项 / 逐字段比对」原则改写当前提示词，文字取自原文、不新增审核要求。
          </Typography.Text>
          <Button type="primary" onClick={() => mut.mutate()}>
            开始优化
          </Button>
        </Space>
      )}
    </Modal>
  )
}
