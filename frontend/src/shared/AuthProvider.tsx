import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, getAccessToken, setAccessToken } from './api'
import { AuthContext } from './auth-context'
import type { Me } from './types'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  const reloadMe = async () => {
    const { data } = await api.get<Me>('/auth/me')
    setMe(data)
  }

  useEffect(() => {
    const bootstrap = async () => {
      try {
        if (!getAccessToken()) {
          const { data } = await api.post<{ access_token: string }>('/auth/refresh')
          setAccessToken(data.access_token)
        }
        await reloadMe()
      } catch {
        setAccessToken(null)
        setMe(null)
      } finally {
        setLoading(false)
      }
    }
    void bootstrap()
    const expire = () => setMe(null)
    window.addEventListener('auth:expired', expire)
    return () => window.removeEventListener('auth:expired', expire)
  }, [])

  const login = async (email: string, password: string) => {
    const { data } = await api.post<{ access_token: string }>('/auth/login', { email, password })
    setAccessToken(data.access_token)
    await reloadMe()
  }

  const register = async (payload: {
    tenant_name: string
    name: string
    email: string
    password: string
  }) => {
    const { data } = await api.post<{ access_token: string }>('/auth/register', payload)
    setAccessToken(data.access_token)
    await reloadMe()
  }

  const logout = async () => {
    try {
      await api.post('/auth/logout')
    } finally {
      setAccessToken(null)
      setMe(null)
    }
  }

  const value = useMemo(
    () => ({ me, loading, login, register, logout, reloadMe }),
    [me, loading],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}