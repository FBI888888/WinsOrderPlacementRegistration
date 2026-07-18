import {
  AuditOutlined,
  BankOutlined,
  BookOutlined,
  DashboardOutlined,
  FileDoneOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  OrderedListOutlined,
  TeamOutlined,
  TransactionOutlined,
} from '@ant-design/icons'
import { Avatar, Button, Dropdown, Grid, Layout, Menu, Space, Typography } from 'antd'
import { useMemo, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../shared/auth-context'
import { roleText } from '../shared/format'

const { Header, Sider, Content } = Layout

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '经营概览' },
  { key: '/orders', icon: <OrderedListOutlined />, label: '订单登记' },
  { key: '/partners', icon: <TeamOutlined />, label: '合作方' },
  { key: '/funds', icon: <TransactionOutlined />, label: '资金流水' },
  { key: '/settlements', icon: <FileDoneOutlined />, label: '结算中心' },
  { key: '/reports', icon: <BookOutlined />, label: '报表中心' },
  { key: '/team', icon: <BankOutlined />, label: '成员权限', ownerOnly: true },
  { key: '/audit', icon: <AuditOutlined />, label: '审计日志', ownerOnly: true },
]

export function AppShell() {
  const { me, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const screens = Grid.useBreakpoint()
  const [collapsed, setCollapsed] = useState(false)
  const compact = !screens.lg
  const visibleItems = useMemo(
    () => menuItems.filter((item) => !item.ownerOnly || me?.role === 'OWNER'),
    [me?.role],
  )

  return (
    <Layout className="app-layout">
      <Sider
        theme="light"
        width={232}
        collapsedWidth={compact ? 0 : 72}
        collapsed={compact || collapsed}
        className="app-sider"
        trigger={null}
      >
        <button className="brand" type="button" onClick={() => navigate('/')}>
          <span className="brand-mark">账</span>
          {!collapsed && !compact && (
            <span>
              <strong>做单账本</strong>
              <small>ORDER LEDGER</small>
            </span>
          )}
        </button>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={visibleItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header className="app-header">
          <Space>
            {!compact && (
              <Button
                type="text"
                aria-label={collapsed ? '展开菜单' : '收起菜单'}
                icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={() => setCollapsed((value) => !value)}
              />
            )}
            {compact && (
              <Dropdown
                trigger={['click']}
                menu={{ items: visibleItems, onClick: ({ key }) => navigate(key) }}
              >
                <Button icon={<MenuUnfoldOutlined />}>菜单</Button>
              </Dropdown>
            )}
            <div className="tenant-title">
              <Typography.Text strong>{me?.tenant_name}</Typography.Text>
              <Typography.Text type="secondary">独立账套</Typography.Text>
            </div>
          </Space>
          <Dropdown
            trigger={['click']}
            menu={{
              items: [
                {
                  key: 'logout',
                  icon: <LogoutOutlined />,
                  label: '退出登录',
                  onClick: () => void logout(),
                },
              ],
            }}
          >
            <button className="user-menu" type="button">
              <Avatar>{me?.name?.slice(0, 1)}</Avatar>
              <span>
                <strong>{me?.name}</strong>
                <small>{roleText[me?.role ?? '']}</small>
              </span>
            </button>
          </Dropdown>
        </Header>
        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}