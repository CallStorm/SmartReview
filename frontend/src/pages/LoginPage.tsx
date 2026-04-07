import './LoginPage.css'

import { App as AntApp, Button, Form, Input } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { BRAND_LOGO_SRC } from '../config/brand'
import { formatApiErrorMessage } from '../utils/apiError'

const SYSTEM_NAME = '方案智能审核'

export default function LoginPage() {
  const { login } = useAuth()
  const nav = useNavigate()
  const { message } = AntApp.useApp()
  const [logoFailed, setLogoFailed] = useState(false)

  return (
    <div className="login-page">
      <div className="login-page__shell">
        <div className="login-page__form-column">
          <div className="login-page__form-stack">
            <div className="login-page__card">
              <header className="login-page__masthead">
                <div className="login-page__masthead-logo">
                  {!logoFailed ? (
                    <img
                      className="login-page__masthead-logo-img"
                      src={BRAND_LOGO_SRC}
                      alt=""
                      draggable={false}
                      onError={() => setLogoFailed(true)}
                    />
                  ) : (
                    <span className="login-page__masthead-logo-fallback" aria-hidden>
                      审
                    </span>
                  )}
                </div>
                <span className="login-page__masthead-divider" aria-hidden />
                <span className="login-page__masthead-name">{SYSTEM_NAME}</span>
              </header>

              <div className="login-page__tabs" role="tablist">
                <span className="login-page__tab login-page__tab--active" role="tab" aria-selected="true">
                  密码登录
                </span>
              </div>

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
                  } catch (err) {
                    message.error(formatApiErrorMessage(err, '登录失败'))
                  }
                }}
              >
                <Form.Item
                  className="login-page__field login-page__field--account"
                  name="phone"
                  rules={[{ required: true, message: '请输入账号或手机号' }]}
                >
                  <Input
                    aria-label="账号或手机号"
                    autoComplete="username"
                    placeholder="请输入账号或手机号"
                    allowClear
                    size="large"
                  />
                </Form.Item>
                <Form.Item
                  className="login-page__field login-page__field--password"
                  name="password"
                  rules={[{ required: true, message: '请输入密码' }]}
                >
                  <Input.Password
                    aria-label="密码"
                    autoComplete="current-password"
                    placeholder="请输入密码"
                    size="large"
                  />
                </Form.Item>
                <Form.Item style={{ marginBottom: 0 }}>
                  <Button className="login-page__submit" type="primary" htmlType="submit" block size="large">
                    立即登录
                  </Button>
                </Form.Item>
              </Form>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
