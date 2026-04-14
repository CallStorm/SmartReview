import './AppLayout.css'

import {
  AppstoreOutlined,
  BarChartOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  FormOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SettingOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import { Avatar, Button, Layout, Menu } from 'antd'
import { useMemo, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { BRAND_LOGO_SRC } from '../config/brand'
import { resolvePageTitle } from '../utils/pageTitle'

const { Header, Sider, Content } = Layout

function resolveMenuSelectedKey(pathname: string): string {
  if (pathname.startsWith('/review')) return '/review'
  if (pathname.startsWith('/schemes')) return '/schemes'
  if (pathname.startsWith('/dashboard')) return '/dashboard'
  if (pathname.startsWith('/basis')) return '/basis'
  if (pathname.startsWith('/templates')) return '/templates'
  if (pathname.startsWith('/users')) return '/users'
  if (pathname.startsWith('/settings')) return '/settings'
  return pathname
}

export default function AppLayout() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const [collapsed, setCollapsed] = useState(false)

  const isOnlyofficeEdit = /^\/review\/[^/]+\/(edit|preview)$/.test(loc.pathname)
  const isManualReview = /^\/review\/[^/]+\/manual$/.test(loc.pathname)
  const pageTitle = resolvePageTitle(loc.pathname)

  const items: MenuProps['items'] = useMemo(() => {
    const businessItems: MenuProps['items'] = [
      { key: '/review', icon: <FileSearchOutlined />, label: '方案审核' },
      { key: '/schemes', icon: <AppstoreOutlined />, label: '方案类型管理' },
    ]

    if (user?.role !== 'admin') {
      return [{ key: '/review', icon: <FileSearchOutlined />, label: '方案审核' }]
    }

    return [
      {
        type: 'group',
        label: '总览',
        children: [
          { key: '/dashboard', icon: <BarChartOutlined />, label: '数据看板' },
        ],
      },
      {
        type: 'group',
        label: '业务',
        children: businessItems,
      },
      {
        type: 'group',
        label: '管理',
        children: [
          { key: '/basis', icon: <FileTextOutlined />, label: '编制依据管理' },
          { key: '/templates', icon: <FormOutlined />, label: '模板管理' },
          { key: '/users', icon: <TeamOutlined />, label: '用户管理' },
          { key: '/settings', icon: <SettingOutlined />, label: '设置' },
        ],
      },
    ]
  }, [user?.role])

  return (
    <Layout
      style={{
        height: '100vh',
        maxHeight: '100vh',
        overflow: 'hidden',
        background: '#fafafa',
        display: 'flex',
      }}
    >
      <Sider
        className="app-root-sider"
        collapsed={collapsed}
        width={248}
        collapsedWidth={80}
        theme="light"
        style={{
          height: '100%',
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
                src={BRAND_LOGO_SRC}
                alt="陕建数科"
                draggable={false}
              />
            </div>
          </div>

          <Menu
            mode="inline"
            theme="light"
            className="app-sider-menu"
            selectedKeys={[resolveMenuSelectedKey(loc.pathname)]}
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
          minHeight: 0,
          maxHeight: '100%',
          background: '#fafafa',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <Header className="app-main-header">
          <div className="app-main-header__left">
            <Button
              type="default"
              className="app-collapse-btn"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed((c) => !c)}
              aria-label={collapsed ? '展开菜单' : '折叠菜单'}
            />
            <h1 className="app-main-header__title">{pageTitle}</h1>
          </div>
          <span className="app-main-header__meta" aria-hidden>
            v1.0
          </span>
        </Header>
        <Content
          className="app-content app-content--main"
          style={{
            margin: 0,
            padding: 0,
            flex: 1,
            minHeight: 0,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div
            className={
              isOnlyofficeEdit
                ? 'app-outlet app-outlet--fill app-outlet--flush'
                : isManualReview
                  ? 'app-outlet app-outlet--fill'
                  : 'app-outlet app-outlet--scroll'
            }
          >
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  )
}
