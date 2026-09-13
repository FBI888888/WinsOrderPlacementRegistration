import { DownloadOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { App, Button, Card, DatePicker, Select, Space, Statistic, Table } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { api, errorMessage } from '../../shared/api'
import { Money, PageTitle } from '../../shared/components'
import type { JijihongBreakdownRow, JijihongDailyRow, JijihongReportSummary } from '../../shared/types'

const { RangePicker } = DatePicker

export function JijihongReportsPage() {
  const { message } = App.useApp()
  const [range, setRange] = useState<[string, string]>([dayjs().startOf('month').format('YYYY-MM-DD'), dayjs().format('YYYY-MM-DD')])
  const [groupBy, setGroupBy] = useState<'device' | 'account' | 'operator'>('device')
  const params = { date_from: range[0], date_to: range[1] }
  const summary = useQuery({ queryKey: ['jijihong-reports', 'summary', params], queryFn: () => api.get<JijihongReportSummary>('/reports/jijihong/summary', { params }).then((res) => res.data) })
  const daily = useQuery({ queryKey: ['jijihong-reports', 'daily', params], queryFn: () => api.get<JijihongDailyRow[]>('/reports/jijihong/daily', { params }).then((res) => res.data) })
  const breakdown = useQuery({ queryKey: ['jijihong-reports', 'breakdown', params, groupBy], queryFn: () => api.get<JijihongBreakdownRow[]>('/reports/jijihong/breakdown', { params: { ...params, group_by: groupBy } }).then((res) => res.data) })

  const exportOrders = async () => {
    try {
      const response = await api.get('/reports/jijihong/orders/export', { params: { ...params, export_format: 'xlsx' }, responseType: 'blob' })
      const url = URL.createObjectURL(response.data)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `jijihong-orders-${dayjs().format('YYYYMMDD')}.xlsx`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      message.error(errorMessage(error, '报表导出失败'))
    }
  }

  return <div className="page-stack">
    <PageTitle title="报表中心" description="按客户实收、支付宝余额成本、真实付款成本和零成本优惠券统计季季红经营结果。" extra={<Button icon={<DownloadOutlined />} onClick={() => void exportOrders()}>导出季季红订单</Button>} />
    <Card><Space wrap>
      <RangePicker value={[dayjs(range[0]), dayjs(range[1])]} onChange={(value) => value && setRange([value[0]!.format('YYYY-MM-DD'), value[1]!.format('YYYY-MM-DD')])} />
      <Select value={groupBy} onChange={setGroupBy} options={[{ value: 'device', label: '按设备' }, { value: 'account', label: '按支付宝账号' }, { value: 'operator', label: '按操作员' }]} />
    </Space></Card>
    <div className="metric-grid">
      <Card><Statistic title="成功订单" value={summary.data?.order_count ?? 0} /></Card>
      <Card><Statistic title="客户实收" value={Number(summary.data?.customer_received ?? 0)} precision={2} prefix="¥" /></Card>
      <Card><Statistic title="订单利润" value={Number(summary.data?.profit ?? 0)} precision={2} prefix="¥" /></Card>
      <Card><Statistic title="期间净收益" value={Number(summary.data?.period_net_income ?? 0)} precision={2} prefix="¥" /></Card>
      <Card><Statistic title="优惠券使用" value={Number(summary.data?.coupon_used ?? 0)} precision={2} prefix="¥" /></Card>
      <Card><Statistic title="余额消耗" value={Number(summary.data?.balance_used ?? 0)} precision={2} prefix="¥" /></Card>
      <Card><Statistic title="真实付款" value={Number(summary.data?.external_cash ?? 0)} precision={2} prefix="¥" /></Card>
      <Card><Statistic title="盘盈盘亏" value={Number(summary.data?.reconciliation_gain_loss ?? 0)} precision={2} prefix="¥" /></Card>
      <Card><Statistic title="超限订单" value={summary.data?.soft_cap_exceeded_count ?? 0} /></Card>
      <Card><Statistic title="已耗尽账号" value={summary.data?.exhausted_account_count ?? 0} /></Card>
      <Card><Statistic title="当前资金池" value={Number(summary.data?.pool_balance ?? 0)} precision={2} prefix="¥" /></Card>
    </div>
    <Card title="每日趋势">
      <Table<JijihongDailyRow> rowKey="business_date" loading={daily.isLoading} dataSource={daily.data ?? []} pagination={false} columns={[
        { title: '日期', dataIndex: 'business_date' }, { title: '订单数', dataIndex: 'order_count' },
        { title: '订单金额', dataIndex: 'order_amount', align: 'right', render: (value) => <Money value={value} /> },
        { title: '客户实收', dataIndex: 'customer_received', align: 'right', render: (value) => <Money value={value} /> },
        { title: '优惠券', dataIndex: 'coupon_used', align: 'right', render: (value) => <Money value={value} /> },
        { title: '余额消耗', dataIndex: 'balance_used', align: 'right', render: (value) => <Money value={value} /> },
        { title: '真实付款', dataIndex: 'external_cash', align: 'right', render: (value) => <Money value={value} /> },
        { title: '利润', dataIndex: 'profit', align: 'right', render: (value) => <Money value={value} signed /> },
      ]} />
    </Card>
    <Card title={groupBy === 'device' ? '设备表现' : groupBy === 'account' ? '支付宝账号表现' : '操作员表现'}>
      <Table<JijihongBreakdownRow> rowKey="entity_id" loading={breakdown.isLoading} dataSource={breakdown.data ?? []} pagination={{ pageSize: 20 }} columns={[
        { title: '名称', dataIndex: 'entity_name' }, { title: '订单数', dataIndex: 'order_count' },
        { title: '订单金额', dataIndex: 'order_amount', align: 'right', render: (value) => <Money value={value} /> },
        { title: '客户实收', dataIndex: 'customer_received', align: 'right', render: (value) => <Money value={value} /> },
        { title: '优惠券', dataIndex: 'coupon_used', align: 'right', render: (value) => <Money value={value} /> },
        { title: '余额消耗', dataIndex: 'balance_used', align: 'right', render: (value) => <Money value={value} /> },
        { title: '真实付款', dataIndex: 'external_cash', align: 'right', render: (value) => <Money value={value} /> },
        { title: '利润', dataIndex: 'profit', align: 'right', render: (value) => <Money value={value} signed /> },
      ]} />
    </Card>
  </div>
}
