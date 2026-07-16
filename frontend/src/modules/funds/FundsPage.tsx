import { PlusOutlined, WalletOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Col, DatePicker, Form, Input, Modal, Row, Select, Space, Statistic, Table, Tag } from 'antd'
import dayjs from 'dayjs'
import { useMemo, useState } from 'react'
import { api, errorMessage } from '../../shared/api'
import { Money, MoneyInput, PageTitle } from '../../shared/components'
import { statusText } from '../../shared/format'
import type { Balance, Contractor, LedgerEntry, Source } from '../../shared/types'

const entryText: Record<string, string> = {
  ADVANCE_TOPUP: '垫资/补款', ORDER_PAYMENT: '订单实付', ADVANCE_RETURN: '退回垫资',
  COMMISSION_ACCRUAL: '佣金计提', COMMISSION_PAYMENT: '支付佣金', SOURCE_ACCRUAL: '放单应收',
  SOURCE_RECEIPT: '放单收款', REVERSAL: '冲正流水',
}

export function FundsPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()
  const transactionType = Form.useWatch('transaction_type', form)
  const balances = useQuery({ queryKey: ['fund-balances'], queryFn: () => api.get<Balance[]>('/funds/balances').then((res) => res.data) })
  const entries = useQuery({ queryKey: ['fund-entries'], queryFn: () => api.get<LedgerEntry[]>('/funds/entries').then((res) => res.data) })
  const contractors = useQuery({ queryKey: ['contractors', 'all'], queryFn: () => api.get<Contractor[]>('/partners/contractors').then((res) => res.data) })
  const sources = useQuery({ queryKey: ['sources'], queryFn: () => api.get<Source[]>('/partners/sources').then((res) => res.data) })
  const names = useMemo(() => ({
    contractors: new Map(contractors.data?.map((item) => [item.id, item.name])),
    sources: new Map(sources.data?.map((item) => [item.id, item.name])),
  }), [contractors.data, sources.data])
  const totals = useMemo(() => {
    const result = { ADVANCE: 0, COMMISSION_PAYABLE: 0, SOURCE_RECEIVABLE: 0 }
    balances.data?.forEach((item) => { result[item.account] += Number(item.balance) })
    return result
  }, [balances.data])

  const mutation = useMutation({
    mutationFn: (values: Record<string, unknown>) => api.post('/funds/transactions', { ...values, business_date: dayjs(values.business_date as string).format('YYYY-MM-DD') }),
    onSuccess: async () => {
      message.success('资金流水已登记')
      setOpen(false)
      form.resetFields()
      await queryClient.invalidateQueries({ queryKey: ['fund-entries'] })
      await queryClient.invalidateQueries({ queryKey: ['fund-balances'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  return (
    <div className="page-stack">
      <PageTitle title="资金流水" description="垫资余额、佣金应付和放单应收分别核算；资金进出不会直接改变订单利润。" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>登记资金</Button>} />
      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}><Card className="metric-card"><Statistic title="垫资可用余额" value={totals.ADVANCE} prefix={<WalletOutlined />} formatter={(value) => <Money value={Number(value)} signed />} /></Card></Col>
        <Col xs={24} md={8}><Card className="metric-card"><Statistic title="待付佣金" value={totals.COMMISSION_PAYABLE} formatter={(value) => <Money value={Number(value)} />} /></Card></Col>
        <Col xs={24} md={8}><Card className="metric-card"><Statistic title="放单应收" value={totals.SOURCE_RECEIVABLE} formatter={(value) => <Money value={Number(value)} />} /></Card></Col>
      </Row>
      <Card title="往来余额">
        <Table<Balance> rowKey={(item) => `${item.account}-${item.counterparty_id}`} dataSource={balances.data} loading={balances.isLoading} pagination={{ pageSize: 10 }} columns={[
          { title: '账户', dataIndex: 'account', render: (value) => ({ ADVANCE: '垫资余额', COMMISSION_PAYABLE: '佣金应付', SOURCE_RECEIVABLE: '放单应收' }[value as string]) },
          { title: '往来对象', dataIndex: 'counterparty_name' },
          { title: '余额', dataIndex: 'balance', align: 'right', render: (value, item) => <Money value={value} signed={item.account === 'ADVANCE'} /> },
        ]} />
      </Card>
      <Card title="最近流水">
        <Table<LedgerEntry> rowKey="id" dataSource={entries.data} loading={entries.isLoading} scroll={{ x: 900 }} pagination={{ pageSize: 15 }} columns={[
          { title: '日期', dataIndex: 'business_date', width: 110 },
          { title: '类型', dataIndex: 'entry_type', width: 130, render: (value) => <Tag>{entryText[value] ?? value}</Tag> },
          { title: '往来对象', render: (_, item) => item.contractor_id ? names.contractors.get(item.contractor_id) : item.source_id ? names.sources.get(item.source_id) : '—' },
          { title: '关联订单', dataIndex: 'order_id', render: (value) => value ? `#${value}` : '—' },
          { title: '备注', dataIndex: 'note', render: (value) => value || '—' },
          { title: '变动金额', dataIndex: 'amount', align: 'right', width: 140, render: (value) => <Money value={value} signed /> },
        ]} />
      </Card>

      <Modal title="登记资金流水" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={mutation.isPending}>
        <Form form={form} layout="vertical" requiredMark={false} onFinish={(values) => mutation.mutate(values)} initialValues={{ business_date: dayjs(), transaction_type: 'ADVANCE_TOPUP' }}>
          <Form.Item name="business_date" label="业务日期" rules={[{ required: true }]}><DatePicker className="full-width" /></Form.Item>
          <Form.Item name="transaction_type" label="流水类型" rules={[{ required: true }]}><Select options={[
            { value: 'ADVANCE_TOPUP', label: '给做单方垫资/补款' }, { value: 'ADVANCE_RETURN', label: '做单方退回垫资' },
            { value: 'COMMISSION_PAYMENT', label: '支付做单佣金' }, { value: 'SOURCE_RECEIPT', label: '收到放单结算款' },
          ]} /></Form.Item>
          {transactionType === 'SOURCE_RECEIPT' ? (
            <Form.Item name="source_id" label="放单人员" rules={[{ required: true }]}><Select showSearch optionFilterProp="label" options={sources.data?.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item>
          ) : (
            <Form.Item name="contractor_id" label="做单方" rules={[{ required: true }]}><Select showSearch optionFilterProp="label" options={contractors.data?.map((item) => ({ value: item.id, label: `${item.name} · ${statusText[item.contractor_type]}` }))} /></Form.Item>
          )}
          <Form.Item name="amount" label="金额" rules={[{ required: true }]}><MoneyInput min={0.01} /></Form.Item>
          <Form.Item name="note" label="备注"><Input.TextArea placeholder="例如：7月15日第二次补款" /></Form.Item>
          <Space size={6} className="form-tip"><span>系统会根据流水类型自动确定余额增减方向。</span></Space>
        </Form>
      </Modal>
    </div>
  )
}