import { Spin } from 'antd'
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../shared/auth-context'

export function ProtectedRoute() {
  const { me, loading } = useAuth()
  if (loading) {
    return (
      <div className="full-page-center">
        <Spin size="large" />
      </div>
    )
  }
  return me ? <Outlet /> : <Navigate to="/login" replace />
}