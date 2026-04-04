import { App as AntApp, Spin } from 'antd'
import type { ReactElement } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import AppLayout from './components/AppLayout'
import BasisPage from './pages/BasisPage'
import LoginPage from './pages/LoginPage'
import ManualReviewPage from './pages/ManualReviewPage'
import ReviewEditPlaceholderPage from './pages/ReviewEditPlaceholderPage'
import ReviewPage from './pages/ReviewPage'
import SchemesPage from './pages/SchemesPage'
import SettingsPage from './pages/SettingsPage'
import TemplatesPage from './pages/TemplatesPage'
import UsersPage from './pages/UsersPage'

function RequireAuth({ children }: { children: ReactElement }) {
  const { user, loading, token } = useAuth()
  if (loading) {
    return (
      <div className="app-auth-loading" role="status" aria-live="polite">
        <Spin size="large" />
        <p className="app-auth-loading__hint">正在验证登录状态…</p>
      </div>
    )
  }
  if (!token || !user) {
    return <Navigate to="/login" replace />
  }
  return children
}

function RequireAdmin({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="app-auth-loading" role="status" aria-live="polite">
        <Spin size="large" />
        <p className="app-auth-loading__hint">正在验证登录状态…</p>
      </div>
    )
  }
  if (user?.role !== 'admin') {
    return <Navigate to="/schemes" replace />
  }
  return children
}

function AppRoutes() {
  const { user, loading, token } = useAuth()

  return (
    <Routes>
      <Route
        path="/login"
        element={
          loading ? (
            <div className="app-auth-loading" role="status" aria-live="polite">
              <Spin size="large" />
              <p className="app-auth-loading__hint">加载中…</p>
            </div>
          ) : token && user ? (
            <Navigate to="/schemes" replace />
          ) : (
            <LoginPage />
          )
        }
      />
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/schemes" replace />} />
        <Route path="schemes" element={<SchemesPage />} />
        <Route path="review" element={<ReviewPage />} />
        <Route path="review/:taskId/manual" element={<ManualReviewPage />} />
        <Route path="review/:taskId/edit" element={<ReviewEditPlaceholderPage />} />
        <Route
          path="basis"
          element={
            <RequireAdmin>
              <BasisPage />
            </RequireAdmin>
          }
        />
        <Route
          path="templates"
          element={
            <RequireAdmin>
              <TemplatesPage />
            </RequireAdmin>
          }
        />
        <Route
          path="settings"
          element={
            <RequireAdmin>
              <SettingsPage />
            </RequireAdmin>
          }
        />
        <Route
          path="users"
          element={
            <RequireAdmin>
              <UsersPage />
            </RequireAdmin>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/schemes" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AntApp>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </AntApp>
  )
}
