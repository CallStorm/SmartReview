import './AppLayout.css'

import {
  AppstoreOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  FormOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Avatar, Button, Layout, Menu } from 'antd'
import { useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const { Header, Sider, Content } = Layout

/** 静态资源来自 `frontend/public/brand-logo.png`（由陕建数科 logo 素材同步） */
const SIDEBAR_LOGO_SRC = `${import.meta.env.BASE_URL}brand-logo.png`

export default function AppLayout() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const [collapsed, setCollapsed] = useState(false)

  const isOnlyofficeEdit = /^\/review\/[^/]+\/edit$/.test(loc.pathname)

  const items = [
    { key: '/schemes', icon: <AppstoreOutlined />, label: '方案类型管理' },
    { key: '/review', icon: <FileSearchOutlined />, label: '方案审核' },
    ...(user?.role === 'admin'
      ? [
          { key: '/basis', icon: <FileTextOutlined />, label: '编制依据管理' },
          { key: '/templates', icon: <FormOutlined />, label: '模板管理' },
          { key: '/settings', icon: <SettingOutlined />, label: '设置' },
        ]
      : []),
  ]

  return (
    <Layout style={{ minHeight: '100vh', background: '#fafafa', display: 'flex' }}>
      <Sider
        collapsed={collapsed}
        width={248}
        collapsedWidth={80}
        theme="light"
        style={{
          overflow: 'hidden',
          borderRight: '1px solid #f0f0f0',
        }}
      >
        <div className="app-sider-inner">
          <div
            className={
              collapsed
                ? 'app-sider-brand app-sider-brand--collapsed'
                : 'app-sider-brand'
            }
          >
            <div className="app-sider-logo-clip">
              <img
                className="app-sider-logo"
                src={SIDEBAR_LOGO_SRC}
                alt="陕建数科"
                draggable={false}
              />
            </div>
          </div>

          <Menu
            mode="inline"
            theme="light"
            className="app-sider-menu"
            selectedKeys={[loc.pathname]}
            items={items}
            inlineCollapsed={collapsed}
            onClick={({ key }) => nav(key)}
          />

          <div className="app-sider-footer">
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                marginBottom: collapsed ? 0 : 12,
                justifyContent: collapsed ? 'center' : 'flex-start',
              }}
            >
              <Avatar
                size={collapsed ? 36 : 40}
                icon={<UserOutlined />}
                style={{
                  background: '#f5f5f5',
                  color: 'rgba(0,0,0,0.45)',
                  flexShrink: 0,
                }}
              />
              {!collapsed && (
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div
                    style={{
                      fontWeight: 600,
                      color: 'rgba(0,0,0,0.88)',
                      lineHeight: 1.3,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {user?.username}
                  </div>
                  <div style={{ fontSize: 12, color: 'rgba(0,0,0,0.45)', marginTop: 2 }}>
                    {user?.role === 'admin' ? '管理员' : '普通用户'}
                  </div>
                </div>
              )}
            </div>
            {!collapsed ? (
              <Button
                type="text"
                icon={<LogoutOutlined />}
                onClick={() => {
                  logout()
                  nav('/login')
                }}
                block
                style={{
                  justifyContent: 'flex-start',
                  color: 'rgba(0,0,0,0.65)',
                  height: 40,
                  paddingInline: 8,
                }}
              >
                退出登录
              </Button>
            ) : (
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <Button
                  type="text"
                  icon={<LogoutOutlined />}
                  aria-label="退出登录"
                  onClick={() => {
                    logout()
                    nav('/login')
                  }}
                  className="app-collapse-btn"
                  style={{ width: 40, height: 40 }}
                />
              </div>
            )}
          </div>
        </div>
      </Sider>

      <Layout
        style={{
          flex: 1,
          minWidth: 0,
          background: '#fafafa',
          ...(isOnlyofficeEdit
            ? {
                minHeight: '100vh',
                display: 'flex',
                flexDirection: 'column' as const,
              }
            : {}),
        }}
      >
        <Header className="app-main-header">
          <Button
            type="default"
            className="app-collapse-btn"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? '展开菜单' : '折叠菜单'}
          />
        </Header>
        <Content
          style={
            isOnlyofficeEdit
              ? {
                  margin: 0,
                  padding: 0,
                  flex: 1,
                  minHeight: 0,
                  overflow: 'hidden',
                  display: 'flex',
                  flexDirection: 'column',
                }
              : { margin: 24, minHeight: 280 }
          }
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
