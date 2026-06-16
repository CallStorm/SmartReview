import './HelpPage.css'

import {
  BookOutlined,
  CloudDownloadOutlined,
  PlayCircleOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons'
import { Button, Card, Collapse, Space, Table, Typography } from 'antd'
import { useMemo } from 'react'
import { useAuth } from '../auth/AuthContext'
import PageShell from '../components/PageShell'
import {
  adminGuideSteps,
  helpDownloads,
  helpFaq,
  helpIntro,
  helpVideos,
  userGuideSteps,
} from '../config/helpContent'

const { Paragraph, Text } = Typography

export default function HelpPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const guideItems = useMemo(() => {
    const items = [
      {
        key: 'user',
        label: '普通用户操作指南',
        children: (
          <ol className="help-guide-list">
            {userGuideSteps.map((step) => (
              <li key={step.title}>
                <Text strong>{step.title}</Text>
                <Paragraph className="help-guide-list__text">{step.content}</Paragraph>
              </li>
            ))}
          </ol>
        ),
      },
    ]
    if (isAdmin) {
      items.push({
        key: 'admin',
        label: '管理员配置指南',
        children: (
          <ol className="help-guide-list">
            {adminGuideSteps.map((step, index) => (
              <li key={step.title}>
                <Text strong>
                  {index + 1}. {step.title}
                </Text>
                <Paragraph className="help-guide-list__text">{step.content}</Paragraph>
              </li>
            ))}
          </ol>
        ),
      })
    }
    return items
  }, [isAdmin])

  const faqColumns = [
    {
      title: '现象',
      dataIndex: 'question',
      key: 'question',
      width: '32%',
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: '原因与处理',
      dataIndex: 'answer',
      key: 'answer',
    },
  ]

  return (
    <PageShell
      icon={<BookOutlined />}
      description="了解系统功能、观看操作视频、下载示例方案"
    >
      <div className="help-page">
        <Card title="系统介绍" className="help-page__card">
          <Paragraph>{helpIntro.summary}</Paragraph>
          <Paragraph>
            <Text strong>普通用户：</Text>
            {helpIntro.userRole}
          </Paragraph>
          <Paragraph style={{ marginBottom: 0 }}>
            <Text strong>管理员：</Text>
            {helpIntro.adminRole}
          </Paragraph>
        </Card>

        <Card title="操作指南" className="help-page__card">
          <Collapse
            defaultActiveKey={isAdmin ? ['user', 'admin'] : ['user']}
            items={guideItems}
          />
        </Card>

        <Card
          title={
            <Space>
              <PlayCircleOutlined />
              操作视频
            </Space>
          }
          className="help-page__card"
        >
          <div className="help-video-list">
            {helpVideos.map((video) => (
              <div key={video.id} className="help-video-item">
                <Typography.Title level={5} className="help-video-item__title">
                  {video.title}
                </Typography.Title>
                <Paragraph className="help-video-item__desc" type="secondary">
                  {video.description}
                </Paragraph>
                <div className="help-video-player">
                  <video controls preload="metadata" src={video.src}>
                    您的浏览器不支持视频播放，请升级浏览器后重试。
                  </video>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card title="示例方案" className="help-page__card">
          <div className="help-download-list">
            {helpDownloads.map((item) => (
              <div key={item.id} className="help-download-item">
                <div className="help-download-item__main">
                  <Typography.Title level={5} className="help-download-item__title">
                    {item.title}
                  </Typography.Title>
                  <Paragraph className="help-download-item__desc" type="secondary">
                    {item.description}
                  </Paragraph>
                </div>
                <Button
                  type="primary"
                  icon={<CloudDownloadOutlined />}
                  href={item.href}
                  download={item.filename}
                >
                  下载示例
                </Button>
              </div>
            ))}
          </div>
        </Card>

        <Card
          title={
            <Space>
              <QuestionCircleOutlined />
              常见问题
            </Space>
          }
          className="help-page__card"
        >
          <Table
            columns={faqColumns}
            dataSource={helpFaq.map((item, index) => ({
              key: String(index),
              ...item,
            }))}
            pagination={false}
            size="middle"
          />
        </Card>
      </div>
    </PageShell>
  )
}
