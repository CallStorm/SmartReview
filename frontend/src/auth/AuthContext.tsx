import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api } from '../api/client'
import type { UserPublic } from '../api/types'

interface AuthState {
  user: UserPublic | null
  token: string | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null)
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('token'))
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    const t = localStorage.getItem('token')
    if (!t) {
      setUser(null)
      setToken(null)
      return
    }
    const { data } = await api.get<UserPublic>('/auth/me')
    setUser(data)
    setToken(t)
  }, [])

  useEffect(() => {
    ;(async () => {
      try {
        if (localStorage.getItem('token')) await refresh()
      } catch {
        localStorage.removeItem('token')
        setUser(null)
        setToken(null)
      } finally {
        setLoading(false)
      }
    })()
  }, [refresh])

  const login = useCallback(async (username: string, password: string) => {
    const { data } = await api.post<{ access_token: string }>('/auth/login', {
      username,
      password,
    })
    localStorage.setItem('token', data.access_token)
    setToken(data.access_token)
    await refresh()
  }, [refresh])

  const logout = useCallback(() => {
    localStorage.removeItem('token')
    setUser(null)
    setToken(null)
  }, [])

  const value = useMemo(
    () => ({ user, token, loading, login, logout, refresh }),
    [user, token, loading, login, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
