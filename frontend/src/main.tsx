import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import './index.css'

const queryClient = new QueryClient()

const appFontFamily =
  "'PingFang SC', 'Microsoft YaHei', system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"

const appLocale = {
  ...zhCN,
  Table: {
    ...zhCN.Table,
    emptyText: '暂无数据',
  },
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ConfigProvider
        locale={appLocale}
        theme={{
          algorithm: theme.defaultAlgorithm,
          token: {
            colorPrimary: '#1677ff',
            borderRadius: 8,
            fontFamily: appFontFamily,
            fontSize: 14,
            colorBgLayout: '#fafafa',
          },
          components: {
            Layout: {
              headerBg: '#ffffff',
              bodyBg: '#fafafa',
            },
            Table: {
              headerBg: '#fafafa',
            },
          },
        }}
      >
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ConfigProvider>
    </QueryClientProvider>
  </StrictMode>,
)
