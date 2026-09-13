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
  PlusOutlined,
  SwapOutlined,
  TeamOutlined,
  TransactionOutlined,
  WalletOutlined,
} from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { App, Avatar, Button, Dropdown, Grid, Input, Layout, Menu, Space, Typography } from 'antd'
import { useMemo, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../shared/auth-context'
import { roleText } from '../shared/format'

const { Header, Sider, Content } = Layout

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '经营概览' },
  { key: '/orders', icon: <OrderedListOutlined />, label: '订单登记' },
  { key: '/alipay-pool', icon: <WalletOutlined />, label: '支付宝资金池', mode: 'JIJIHONG' },
  { key: '/partners', icon: <TeamOutlined />, label: '合作方', mode: 'FEDAICHU' },
  { key: '/funds', icon: <TransactionOutlined />, label: '资金流水' },
  { key: '/settlements', icon: <FileDoneOutlined />, label: '结算中心' },
  { key: '/reports', icon: <BookOutlined />, label: '报表中心' },
  { key: '/team', icon: <BankOutlined />, label: '成员权限', ownerOnly: true },
  { key: '/audit', icon: <AuditOutlined />, label: '审计日志', ownerOnly: true },
]

export function AppShell() {
  const { me, logout, switchTenant, createTenant } = useAuth()
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const screens = Grid.useBreakpoint()
  const [collapsed, setCollapsed] = useState(false)
  const compact = !screens.lg
  const visibleItems = useMemo(
    () => menuItems.filter(
      (item) =>
        (!item.ownerOnly || me?.role === 'OWNER')
        && (!item.mode || item.mode === me?.business_mode),
    ).map((item) => ({
      key: item.key,
      icon: item.icon,
      label: item.key === '/settlements' && me?.business_mode === 'JIJIHONG'
        ? '账号对账'
        : item.label,
    })),
    [me?.role, me?.business_mode],
  )
  const isJijihong = me?.business_mode === 'JIJIHONG'

  const changeTenant = async (tenantId: number) => {
    if (tenantId === me?.tenant_id) return
    try {
      await switchTenant(tenantId)
      queryClient.clear()
      navigate('/')
      message.success('已切换账套')
    } catch {
      message.error('账套切换失败')
    }
  }

  const addJijihongTenant = () => {
    let name = '季季红'
    modal.confirm({
      title: '新增季季红账套',
      content: (
        <Input
          defaultValue={name}
          placeholder="账套名称"
          onChange={(event) => { name = event.target.value }}
        />
      ),
      okText: '创建并切换',
      onOk: async () => {
        if (!name.trim()) throw new Error('请输入账套名称')
        const tenant = await createTenant(name.trim(), 'JIJIHONG')
        await changeTenant(tenant.id)
      },
    })
  }

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
          <span className="brand-mark">{isJijihong ? '季' : '费'}</span>
          {!collapsed && !compact && (
            <span>
              <strong>{isJijihong ? '季季红账本' : '费大厨账本'}</strong>
              <small>{isJijihong ? 'JI JI HONG' : 'FEI DA CHU'}</small>
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
            <Dropdown
              trigger={['click']}
              menu={{
                items: [
                  ...(me?.tenants ?? []).map((tenant) => ({
                    key: String(tenant.id),
                    icon: tenant.id === me?.tenant_id ? <SwapOutlined /> : undefined,
                    label: tenant.name + ' · ' + (tenant.business_mode === 'JIJIHONG' ? '季季红' : '费大厨'),
                  })),
                  { type: 'divider' as const },
                  {
                    key: 'create-jijihong',
                    icon: <PlusOutlined />,
                    label: '新增季季红账套',
                    disabled: me?.role !== 'OWNER',
                  },
                ],
                onClick: ({ key }) => {
                  if (key === 'create-jijihong') addJijihongTenant()
                  else void changeTenant(Number(key))
                },
              }}
            >
              <button className="tenant-title tenant-switcher" type="button">
                <Typography.Text strong>{me?.tenant_name}</Typography.Text>
                <Typography.Text type="secondary">
                  {isJijihong ? '季季红独立账套' : '费大厨独立账套'}
                </Typography.Text>
              </button>
            </Dropdown>
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
