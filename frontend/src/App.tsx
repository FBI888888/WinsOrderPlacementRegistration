import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp, ConfigProvider, Spin } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './app/AppShell'
import { ProtectedRoute } from './app/ProtectedRoute'
import { AuthProvider } from './shared/AuthProvider'
import './App.css'

const lazyPage = <T extends Record<string, unknown>, K extends keyof T>(
  loader: () => Promise<T>,
  name: K,
) => lazy(() => loader().then((module) => ({ default: module[name] as React.ComponentType })))

const LoginPage = lazyPage(() => import('./modules/auth/LoginPage'), 'LoginPage')
const DashboardPage = lazyPage(() => import('./modules/dashboard/DashboardPage'), 'DashboardPage')
const OrdersPage = lazyPage(() => import('./modules/orders/OrdersPage'), 'OrdersPage')
const PartnersPage = lazyPage(() => import('./modules/partners/PartnersPage'), 'PartnersPage')
const FundsPage = lazyPage(() => import('./modules/funds/FundsPage'), 'FundsPage')
const SettlementsPage = lazyPage(() => import('./modules/settlements/SettlementsPage'), 'SettlementsPage')
const ReportsPage = lazyPage(() => import('./modules/reports/ReportsPage'), 'ReportsPage')
const TeamPage = lazyPage(() => import('./modules/team/TeamPage'), 'TeamPage')
const AuditPage = lazyPage(() => import('./modules/audit/AuditPage'), 'AuditPage')

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 20_000, retry: 1, refetchOnWindowFocus: false },
  },
})

function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#315c4c',
          colorInfo: '#315c4c',
          colorSuccess: '#2f7a55',
          colorWarning: '#b7791f',
          colorError: '#b7473a',
          borderRadius: 8,
          fontFamily:
            "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif",
        },
        components: {
          Layout: { bodyBg: '#f3f5f4', headerBg: '#ffffff', siderBg: '#ffffff' },
          Table: { headerBg: '#f7f8f7', headerColor: '#48534e', cellPaddingBlock: 12 },
          Card: { headerBg: 'transparent' },
        },
      }}
    >
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <BrowserRouter>
              <Suspense fallback={<div className="full-page-center"><Spin size="large" /></div>}>
                <Routes>
                  <Route path="/login" element={<LoginPage />} />
                  <Route element={<ProtectedRoute />}>
                    <Route element={<AppShell />}>
                      <Route index element={<DashboardPage />} />
                      <Route path="orders" element={<OrdersPage />} />
                      <Route path="partners" element={<PartnersPage />} />
                      <Route path="funds" element={<FundsPage />} />
                      <Route path="settlements" element={<SettlementsPage />} />
                      <Route path="reports" element={<ReportsPage />} />
                      <Route path="team" element={<TeamPage />} />
                      <Route path="audit" element={<AuditPage />} />
                    </Route>
                  </Route>
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Suspense>
            </BrowserRouter>
          </AuthProvider>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  )
}

export default App