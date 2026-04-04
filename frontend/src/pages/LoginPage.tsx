import './LoginPage.css'

import { App as AntApp, Button, Form, Input, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export default function LoginPage() {
  const { login } = useAuth()
  const nav = useNavigate()
  const { message } = AntApp.useApp()

  return (
    <div className="login-page">
      <div className="login-page__card">
        <h1 className="login-page__title">施工方案审核系统</h1>
        <p className="login-page__subtitle">请输入您的登录信息</p>

        <Form
          className="login-page__form"
          layout="vertical"
          requiredMark={false}
          onFinish={async (v) => {
            const phone = (v.phone as string)?.trim() || ''
            if (!phone) {
              message.warning('请输入账号或手机号')
              return
            }
            try {
              await login(phone, v.password as string)
              message.success('登录成功')
              nav('/schemes', { replace: true })
            } catch {
              message.error('登录失败')
            }
          }}
        >
          <Form.Item
            name="phone"
            label="账号/手机号"
            rules={[{ required: true, message: '请输入账号或手机号' }]}
          >
            <Input autoComplete="username" placeholder="账号/手机号" allowClear />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password autoComplete="current-password" placeholder="请输入密码" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button className="login-page__submit" type="primary" htmlType="submit" block>
              登录
            </Button>
          </Form.Item>
        </Form>

        <Typography.Text className="login-page__footer" type="secondary">
          施工方案审核管理系统 v1.0
        </Typography.Text>
      </div>
    </div>
  )
}
