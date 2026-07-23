import { useQuery } from '@tanstack/react-query'
import { Card, Table, Tag, Typography } from 'antd'
import { Navigate } from 'react-router-dom'
import { api } from '../../shared/api'
import { useAuth } from '../../shared/auth-context'
import { PageTitle } from '../../shared/components'
import { dateTime } from '../../shared/format'
import type { AuditLog } from '../../shared/types'

const actionText: Record<string, string> = {
  'tenant.created': '创建账套', 'auth.login': '登录', 'member.created': '添加成员', 'member.updated': '调整成员',
  'source.created': '新增放单人员', 'source.updated': '修改放单人员', 'contractor.created': '新增学生头子',
  'contractor.updated': '修改做单方', 'performer.created': '新增实际做单人',
  'performer.updated': '修改实际做单人', 'points.coupon_redeemed': '兑换积分优惠券',
  'order.created': '创建订单', 'order.updated': '修改订单',
  'order.status_changed': '变更订单状态', 'fund.transaction_created': '登记资金流水',
  'fund.ledger_exported': '导出资金流水',
  'settlement.created': '生成结算单', 'settlement.confirmed': '确认结算', 'settlement.reversed': '冲正结算',
  'report.exported': '导出报表',
}

export function AuditPage() {
  const { me } = useAuth()
  const logs = useQuery({ queryKey: ['audit-logs'], queryFn: () => api.get<AuditLog[]>('/auth/audit-logs').then((res) => res.data), enabled: me?.role === 'OWNER' })
  if (me?.role !== 'OWNER') return <Navigate to="/" replace />

  return (
    <div className="page-stack">
      <PageTitle title="审计日志" description="关键改账、结算、权限与导出操作均保留操作者和参数摘要。" />
      <Card>
        <Table<AuditLog> rowKey="id" dataSource={logs.data} loading={logs.isLoading} pagination={{ pageSize: 20 }} columns={[
          { title: '时间', dataIndex: 'created_at', width: 170, render: dateTime },
          { title: '操作', dataIndex: 'action', width: 160, render: (value) => <Tag>{actionText[value] ?? value}</Tag> },
          { title: '操作者 ID', dataIndex: 'user_id', width: 110, render: (value) => value ?? '系统' },
          { title: '对象', width: 160, render: (_, item) => `${item.resource_type}${item.resource_id ? ` #${item.resource_id}` : ''}` },
          { title: '参数摘要', dataIndex: 'payload', render: (value) => value ? <Typography.Text code className="audit-payload">{JSON.stringify(value)}</Typography.Text> : '—' },
        ]} />
      </Card>
    </div>
  )
}