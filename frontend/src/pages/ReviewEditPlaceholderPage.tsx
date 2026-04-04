import { RollbackOutlined } from '@ant-design/icons'
import { Button, Typography } from 'antd'
import { useNavigate, useParams } from 'react-router-dom'

export default function ReviewEditPlaceholderPage() {
  const { taskId } = useParams<{ taskId: string }>()
  const navigate = useNavigate()

  return (
    <div style={{ padding: 24 }}>
      <Button
        icon={<RollbackOutlined />}
        onClick={() => navigate(`/review/${taskId}/manual`)}
        style={{ marginBottom: 24 }}
      >
        返回审阅
      </Button>
      <Typography.Title level={4}>在线编辑（OnlyOffice）</Typography.Title>
      <Typography.Paragraph type="secondary">
        任务 #{taskId}：此页面预留用于接入 OnlyOffice 文档编辑。当前尚未配置编辑器。
      </Typography.Paragraph>
    </div>
  )
}
