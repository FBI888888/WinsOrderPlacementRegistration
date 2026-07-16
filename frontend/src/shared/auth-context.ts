import { createContext, useContext } from 'react'
import type { Me } from './types'

export interface AuthContextValue {
  me: Me | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (data: { tenant_name: string; name: string; email: string; password: string }) => Promise<void>
  logout: () => Promise<void>
  reloadMe: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}