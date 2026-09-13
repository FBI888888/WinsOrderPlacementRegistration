import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp, ConfigProvider, Spin } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './app/AppShell'
import { ProtectedRoute } from './app/ProtectedRoute'
import { AuthProvider } from './shared/AuthProvider'
import { useAuth } from './shared/auth-context'
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
const JijihongFundsPage = lazyPage(() => import('./modules/funds/JijihongFundsPage'), 'JijihongFundsPage')
const SettlementsPage = lazyPage(() => import('./modules/settlements/SettlementsPage'), 'SettlementsPage')
const AlipayReconciliationsPage = lazyPage(() => import('./modules/settlements/AlipayReconciliationsPage'), 'AlipayReconciliationsPage')
const ReportsPage = lazyPage(() => import('./modules/reports/ReportsPage'), 'ReportsPage')
const JijihongReportsPage = lazyPage(() => import('./modules/reports/JijihongReportsPage'), 'JijihongReportsPage')
const TeamPage = lazyPage(() => import('./modules/team/TeamPage'), 'TeamPage')
const AuditPage = lazyPage(() => import('./modules/audit/AuditPage'), 'AuditPage')
const AlipayPoolPage = lazyPage(() => import('./modules/alipay-pool/AlipayPoolPage'), 'AlipayPoolPage')

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 20_000, retry: 1, refetchOnWindowFocus: false },
  },
})

function FedaichuOnly({ children }: { children: React.ReactNode }) {
  const { me } = useAuth()
  return me?.business_mode === 'FEDAICHU' ? children : <Navigate to="/" replace />
}

function BusinessModePage({ fedaichu, jijihong }: { fedaichu: React.ReactNode; jijihong: React.ReactNode }) {
  const { me } = useAuth()
  return me?.business_mode === 'JIJIHONG' ? jijihong : fedaichu
}

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
                      <Route path="alipay-pool" element={<AlipayPoolPage />} />
                      <Route path="partners" element={<FedaichuOnly><PartnersPage /></FedaichuOnly>} />
                      <Route path="funds" element={<BusinessModePage fedaichu={<FundsPage />} jijihong={<JijihongFundsPage />} />} />
                      <Route path="settlements" element={<BusinessModePage fedaichu={<SettlementsPage />} jijihong={<AlipayReconciliationsPage />} />} />
                      <Route path="reports" element={<BusinessModePage fedaichu={<ReportsPage />} jijihong={<JijihongReportsPage />} />} />
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
