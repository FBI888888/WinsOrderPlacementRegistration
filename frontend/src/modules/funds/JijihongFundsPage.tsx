import { useQuery } from '@tanstack/react-query'
import { Card, DatePicker, Select, Space, Statistic, Table, Tabs } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { api } from '../../shared/api'
import { Money, PageTitle } from '../../shared/components'
import { dateTime } from '../../shared/format'
import type { AlipayAccount, AlipayBalanceEntryView, JijihongFinancialEntry, JijihongFundsSummary } from '../../shared/types'

const { RangePicker } = DatePicker
const financialTypeText: Record<string, string> = {
  CUSTOMER_RECEIPT: '客户实收',
  BALANCE_COST: '支付宝余额成本',
  EXTERNAL_CASH_COST: '真实付款成本',
  RECONCILIATION_GAIN_LOSS: '盘盈盘亏',
  REVERSAL: '冲正',
}
const balanceTypeText: Record<string, string> = {
  IMPORT_OPENING: '期初登记', RESERVE: '预占', RELEASE: '释放', CONFIRM: '确认扣款',
  MANUAL_ADJUSTMENT: '人工调整', RECONCILIATION_ADJUSTMENT: '盘点调整', REVERSAL: '冲正',
}

export function JijihongFundsPage() {
  const [range, setRange] = useState<[string, string]>([dayjs().startOf('month').format('YYYY-MM-DD'), dayjs().format('YYYY-MM-DD')])
  const [deviceId, setDeviceId] = useState<number>()
  const [accountId, setAccountId] = useState<number>()
  const [entryType, setEntryType] = useState<string>()
  const accounts = useQuery({ queryKey: ['alipay-accounts', 'funds'], queryFn: () => api.get<AlipayAccount[]>('/alipay-pool/accounts').then((res) => res.data) })
  const summary = useQuery({
    queryKey: ['jijihong-funds', 'summary', range],
    queryFn: () => api.get<JijihongFundsSummary>('/alipay-pool/funds/summary', { params: { date_from: range[0], date_to: range[1] } }).then((res) => res.data),
  })
  const queryParams = { page: 1, page_size: 200, device_id: deviceId, account_id: accountId, entry_type: entryType }
  const balanceEntries = useQuery({
    queryKey: ['jijihong-funds', 'balance', queryParams],
    queryFn: () => api.get<{ items: AlipayBalanceEntryView[] }>('/alipay-pool/funds/account-entries', { params: queryParams }).then((res) => res.data),
  })
  const financialEntries = useQuery({
    queryKey: ['jijihong-funds', 'financial', queryParams, range],
    queryFn: () => api.get<{ items: JijihongFinancialEntry[] }>('/alipay-pool/funds/financial-entries', {
      params: { ...queryParams, date_from: range[0], date_to: range[1] },
    }).then((res) => res.data),
  })
  const deviceOptions = [...new Map((accounts.data ?? []).map((item) => [item.device_id, item.device_name])).entries()].map(([value, label]) => ({ value, label }))
  const accountOptions = (accounts.data ?? []).filter((item) => !deviceId || item.device_id === deviceId).map((item) => ({ value: item.id, label: `${item.device_name} · ${item.alias}` }))

  return <div className="page-stack">
    <PageTitle title="资金流水" description="支付宝账号余额账本与订单经营收支账本相互独立，所有调整和冲正都以追加流水记录。" />
    <Card>
      <Space wrap>
        <RangePicker value={[dayjs(range[0]), dayjs(range[1])]} onChange={(value) => value && setRange([value[0]!.format('YYYY-MM-DD'), value[1]!.format('YYYY-MM-DD')])} />
        <Select allowClear placeholder="设备" value={deviceId} options={deviceOptions} onChange={(value) => { setDeviceId(value); setAccountId(undefined) }} />
        <Select allowClear showSearch optionFilterProp="label" placeholder="支付宝账号" value={accountId} options={accountOptions} onChange={setAccountId} />
        <Select allowClear placeholder="流水类型" value={entryType} onChange={setEntryType} options={Object.entries({ ...financialTypeText, ...balanceTypeText }).map(([value, label]) => ({ value, label }))} />
      </Space>
    </Card>
    <div className="metric-grid">
      <Card><Statistic title="资金池余额" value={Number(summary.data?.current_balance ?? 0)} precision={2} prefix="¥" /></Card>
      <Card><Statistic title="已预占" value={Number(summary.data?.reserved_balance ?? 0)} precision={2} prefix="¥" /></Card>
      <Card><Statistic title="客户实收" value={Number(summary.data?.customer_receipts ?? 0)} precision={2} prefix="¥" /></Card>
      <Card><Statistic title="期间净收益" value={Number(summary.data?.period_net_income ?? 0)} precision={2} prefix="¥" /></Card>
    </div>
    <Card>
      <Tabs items={[
        {
          key: 'balance', label: '支付宝余额流水', children: <Table<AlipayBalanceEntryView> rowKey="id" loading={balanceEntries.isLoading} dataSource={balanceEntries.data?.items ?? []} pagination={{ pageSize: 50 }} columns={[
            { title: '时间', dataIndex: 'created_at', width: 170, render: dateTime },
            { title: '设备', dataIndex: 'device_name' }, { title: '账号', dataIndex: 'account_alias' },
            { title: '订单ID', dataIndex: 'order_id', render: (value) => value ?? '—' },
            { title: '类型', dataIndex: 'entry_type', render: (value) => balanceTypeText[value] ?? value },
            { title: '余额变化', dataIndex: 'balance_delta', align: 'right', render: (value) => <Money value={value} signed /> },
            { title: '预占变化', dataIndex: 'reserved_delta', align: 'right', render: (value) => <Money value={value} signed /> },
            { title: '余额后', dataIndex: 'balance_after', align: 'right', render: (value) => <Money value={value} /> },
            { title: '说明', dataIndex: 'reason' },
          ]} />,
        },
        {
          key: 'financial', label: '订单收支流水', children: <Table<JijihongFinancialEntry> rowKey="id" loading={financialEntries.isLoading} dataSource={financialEntries.data?.items ?? []} pagination={{ pageSize: 50 }} columns={[
            { title: '业务日期', dataIndex: 'business_date', width: 110 }, { title: '订单ID', dataIndex: 'order_id', render: (value) => value ?? '—' },
            { title: '设备', dataIndex: 'device_name', render: (value) => value ?? '—' }, { title: '账号', dataIndex: 'account_alias', render: (value) => value ?? '—' },
            { title: '类型', dataIndex: 'entry_type', render: (value) => financialTypeText[value] ?? value },
            { title: '金额', dataIndex: 'amount', align: 'right', render: (value) => <Money value={value} signed /> },
            { title: '说明', dataIndex: 'note' },
          ]} />,
        },
      ]} />
    </Card>
  </div>
}
