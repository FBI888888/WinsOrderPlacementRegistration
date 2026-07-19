import { FileSearchOutlined, PlusOutlined, WalletOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Col, DatePicker, Drawer, Form, Input, Modal, Row, Select, Space, Statistic, Switch, Table, Tag, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { api, errorMessage } from '../../shared/api'
import { Money, MoneyInput, PageTitle } from '../../shared/components'
import { dateTime, statusText } from '../../shared/format'
import type { Balance, ClearingPreviewItem, Contractor, LedgerEntry, Source } from '../../shared/types'

const entryText: Record<string, string> = {
  ADVANCE_TOPUP: '垫资/补款', ORDER_PAYMENT: '订单实付', ADVANCE_RETURN: '退回垫资',
  COMMISSION_ACCRUAL: '佣金计提', COMMISSION_PAYMENT: '支付佣金', SOURCE_ACCRUAL: '放单应收',
  SOURCE_RECEIPT: '放单收款', REVERSAL: '冲正流水',
}

type PartyKind = 'contractor' | 'source'

export function FundsPage() {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()
  const transactionType = Form.useWatch('transaction_type', form)
  const [partyKind, setPartyKind] = useState<PartyKind>('contractor')
  const [partyId, setPartyId] = useState<number>()
  const [showAllBalances, setShowAllBalances] = useState(false)
  const [clearingDate, setClearingDate] = useState<Dayjs>(dayjs())
  const [batchClearingOpen, setBatchClearingOpen] = useState(false)
  const [logTarget, setLogTarget] = useState<Balance>()

  const balances = useQuery({ queryKey: ['fund-balances'], queryFn: () => api.get<Balance[]>('/funds/balances').then((res) => res.data) })
  const clearingDateValue = clearingDate.format('YYYY-MM-DD')
  const clearingPreviewQuery = useQuery({
    queryKey: ['clearing-preview', clearingDateValue],
    queryFn: () => api.get<ClearingPreviewItem[]>('/settlements/clearing-preview', {
      params: { business_date: clearingDateValue },
    }).then((res) => res.data),
  })
  const contractors = useQuery({ queryKey: ['contractors', 'all'], queryFn: () => api.get<Contractor[]>('/partners/contractors').then((res) => res.data) })
  const sources = useQuery({ queryKey: ['sources'], queryFn: () => api.get<Source[]>('/partners/sources').then((res) => res.data) })

  const activeContractors = useMemo(
    () => (contractors.data ?? []).filter((item) => item.is_active),
    [contractors.data],
  )
  const activeSources = useMemo(
    () => (sources.data ?? []).filter((item) => item.is_active),
    [sources.data],
  )

  useEffect(() => {
    if (partyId !== undefined) return
    if (activeContractors.length > 0) {
      setPartyKind('contractor')
      setPartyId(activeContractors[0].id)
      return
    }
    if (activeSources.length > 0) {
      setPartyKind('source')
      setPartyId(activeSources[0].id)
    }
  }, [activeContractors, activeSources, partyId])

  const entryParams = useMemo(() => {
    if (!partyId) return undefined
    return partyKind === 'contractor' ? { contractor_id: partyId } : { source_id: partyId }
  }, [partyKind, partyId])

  const entries = useQuery({
    queryKey: ['fund-entries', entryParams],
    queryFn: () => api.get<LedgerEntry[]>('/funds/entries', { params: entryParams }).then((res) => res.data),
    enabled: Boolean(entryParams),
  })

  const logParams = useMemo(() => {
    if (!logTarget) return undefined
    return logTarget.account === 'SOURCE_RECEIVABLE'
      ? { account: logTarget.account, source_id: logTarget.counterparty_id }
      : { account: logTarget.account, contractor_id: logTarget.counterparty_id }
  }, [logTarget])

  const logEntries = useQuery({
    queryKey: ['fund-balance-log', logParams],
    queryFn: () => api.get<LedgerEntry[]>('/funds/entries', { params: logParams }).then((res) => res.data),
    enabled: Boolean(logParams),
  })

  const names = useMemo(() => ({
    contractors: new Map(contractors.data?.map((item) => [item.id, item.name])),
    sources: new Map(sources.data?.map((item) => [item.id, item.name])),
  }), [contractors.data, sources.data])

  const personBalances = useMemo(() => {
    if (!partyId || !balances.data) return []
    return balances.data.filter((item) => {
      if (item.counterparty_id !== partyId) return false
      return partyKind === 'contractor'
        ? item.account !== 'SOURCE_RECEIVABLE'
        : item.account === 'SOURCE_RECEIVABLE'
    })
  }, [balances.data, partyId, partyKind])

  const totals = useMemo(() => {
    const result = { ADVANCE: 0, COMMISSION_PAYABLE: 0, SOURCE_RECEIVABLE: 0 }
    personBalances.forEach((item) => { result[item.account] += Number(item.balance) })
    return result
  }, [personBalances])

  const commissionBalanceByContractor = useMemo(
    () => new Map(
      (balances.data ?? [])
        .filter((item) => item.account === 'COMMISSION_PAYABLE')
        .map((item) => [item.counterparty_id, Number(item.balance)]),
    ),
    [balances.data],
  )

  const selectedClearingBalance = Number(
    clearingPreviewQuery.data?.find((item) => (
      item.counterparty_id === partyId
      && item.settlement_type === (partyKind === 'contractor' ? 'CONTRACTOR' : 'SOURCE')
    ))?.balance ?? 0,
  )
  const netSettlement = totals.ADVANCE - totals.COMMISSION_PAYABLE
  const balanceTableData = showAllBalances ? (balances.data ?? []) : personBalances

  const selectedName = partyKind === 'contractor'
    ? names.contractors.get(partyId ?? -1)
    : names.sources.get(partyId ?? -1)

  const mutation = useMutation({
    mutationFn: (values: Record<string, unknown>) => api.post('/funds/transactions', { ...values, business_date: dayjs(values.business_date as string).format('YYYY-MM-DD') }),
    onSuccess: async () => {
      message.success('资金流水已登记')
      setOpen(false)
      form.resetFields()
      await queryClient.invalidateQueries({ queryKey: ['fund-entries'] })
      await queryClient.invalidateQueries({ queryKey: ['fund-balances'] })
      await queryClient.invalidateQueries({ queryKey: ['clearing-preview'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const clearMutation = useMutation({
    mutationFn: () => api.post('/settlements/clear', {
      settlement_type: partyKind === 'contractor' ? 'CONTRACTOR' : 'SOURCE',
      counterparty_id: partyId,
      business_date: clearingDateValue,
    }),
    onSuccess: async () => {
      message.success('当前往来对象已结清')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['fund-entries'] }),
        queryClient.invalidateQueries({ queryKey: ['fund-balances'] }),
        queryClient.invalidateQueries({ queryKey: ['clearing-preview'] }),
        queryClient.invalidateQueries({ queryKey: ['settlements'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      ])
    },
    onError: (error) => message.error(errorMessage(error, '结清失败')),
  })

  const batchClearMutation = useMutation({
    mutationFn: () => api.post('/settlements/clear-batch', { business_date: clearingDateValue }),
    onSuccess: async () => {
      message.success('批量结清已完成')
      setBatchClearingOpen(false)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['fund-entries'] }),
        queryClient.invalidateQueries({ queryKey: ['fund-balances'] }),
        queryClient.invalidateQueries({ queryKey: ['clearing-preview'] }),
        queryClient.invalidateQueries({ queryKey: ['settlements'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      ])
    },
    onError: (error) => message.error(errorMessage(error, '批量结清失败')),
  })

  const mutedStyle = { opacity: 0.45 }

  return (
    <div className="page-stack">
      <PageTitle
        title="资金流水"
        description="垫资余额、佣金应付和放单应收分别核算；结清通过追加反向流水完成，历史记录不会删除。"
        extra={(
          <Space>
            <Button onClick={() => setBatchClearingOpen(true)}>按日期批量结清</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>登记资金</Button>
          </Space>
        )}
      />
      <Card size="small">
        <Space wrap>
          <span>往来对象</span>
          <Select
            value={partyKind}
            style={{ width: 120 }}
            onChange={(value: PartyKind) => {
              setPartyKind(value)
              const nextId = value === 'contractor' ? activeContractors[0]?.id : activeSources[0]?.id
              setPartyId(nextId)
            }}
            options={[
              { value: 'contractor', label: '做单方' },
              { value: 'source', label: '放单人员' },
            ]}
          />
          <Select
            showSearch
            optionFilterProp="label"
            placeholder="选择人员"
            value={partyId}
            style={{ minWidth: 200 }}
            onChange={setPartyId}
            options={
              partyKind === 'contractor'
                ? (contractors.data ?? []).map((item) => ({
                  value: item.id,
                  label: `${item.name} · ${statusText[item.contractor_type]}${item.is_active ? '' : '（停用）'}`,
                }))
                : (sources.data ?? []).map((item) => ({
                  value: item.id,
                  label: `${item.name}${item.is_active ? '' : '（停用）'}`,
                }))
            }
          />
          <span>结清截至</span>
          <DatePicker
            value={clearingDate}
            allowClear={false}
            disabledDate={(current) => current.startOf('day').isAfter(dayjs().startOf('day'))}
            onChange={(value) => value && setClearingDate(value)}
          />
          {selectedName && <Tag>{selectedName}</Tag>}
          <Button
            disabled={!partyId || clearingPreviewQuery.isLoading || selectedClearingBalance <= 0}
            loading={clearMutation.isPending}
            onClick={() => modal.confirm({
              title: `结清「${selectedName ?? ''}」截至 ${clearingDateValue} 的余额？`,
              content: `本次将结清截至 ${clearingDateValue} 的${partyKind === 'contractor' ? '待付佣金' : '放单应收'} ¥${selectedClearingBalance.toFixed(2)}，所选日期之后的流水不会受到影响。`,
              okText: '确认结清',
              onOk: () => clearMutation.mutateAsync(),
            })}
          >立即结清</Button>
        </Space>
      </Card>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={6}>
          <Card className="metric-card" style={partyKind === 'source' ? mutedStyle : undefined}>
            <Statistic
              title="垫资可用余额"
              value={partyKind === 'contractor' ? totals.ADVANCE : 0}
              prefix={<WalletOutlined />}
              formatter={(value) => partyKind === 'contractor' ? <Money value={Number(value)} signed /> : '—'}
            />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card className="metric-card" style={partyKind === 'source' ? mutedStyle : undefined}>
            <Statistic
              title="待付佣金"
              value={partyKind === 'contractor' ? totals.COMMISSION_PAYABLE : 0}
              formatter={(value) => partyKind === 'contractor' ? <Money value={Number(value)} /> : '—'}
            />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card className="metric-card" style={partyKind === 'contractor' ? mutedStyle : undefined}>
            <Statistic
              title="放单应收"
              value={partyKind === 'source' ? totals.SOURCE_RECEIVABLE : 0}
              formatter={(value) => partyKind === 'source' ? <Money value={Number(value)} /> : '—'}
            />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card className="metric-card" style={partyKind === 'source' ? mutedStyle : undefined}>
            <Statistic
              title="扣佣待结算"
              value={partyKind === 'contractor' ? netSettlement : 0}
              formatter={(value) => partyKind === 'contractor' ? <Money value={Number(value)} signed /> : '—'}
            />
          </Card>
        </Col>
      </Row>
      <Card
        title="往来余额"
        extra={(
          <Space>
            <span>显示全部</span>
            <Switch checked={showAllBalances} onChange={setShowAllBalances} />
          </Space>
        )}
      >
        <Table<Balance> rowKey={(item) => `${item.account}-${item.counterparty_id}`} dataSource={balanceTableData} loading={balances.isLoading} pagination={{ pageSize: 10 }} columns={[
          { title: '账户', dataIndex: 'account', render: (value) => ({ ADVANCE: '垫资余额', COMMISSION_PAYABLE: '佣金应付', SOURCE_RECEIVABLE: '放单应收' }[value as string]) },
          { title: '往来对象', dataIndex: 'counterparty_name' },
          { title: '余额', dataIndex: 'balance', align: 'right', render: (value, item) => <Money value={value} signed={item.account === 'ADVANCE'} /> },
          {
            title: '扣佣待结算', align: 'right',
            render: (_, item) => item.account === 'ADVANCE'
              ? <Money value={Number(item.balance) - (commissionBalanceByContractor.get(item.counterparty_id) ?? 0)} signed />
              : '—',
          },
          {
            title: '日志', width: 90,
            render: (_, item) => (
              <Button type="link" icon={<FileSearchOutlined />} onClick={() => setLogTarget(item)}>查看</Button>
            ),
          },
        ]} />
      </Card>
      <Card title={selectedName ? `最近流水 · ${selectedName}` : '最近流水'}>
        <Table<LedgerEntry>
          rowKey="id"
          dataSource={entries.data}
          loading={entries.isLoading}
          scroll={{ x: partyKind === 'source' ? 1050 : 1200 }}
          pagination={{ pageSize: 15 }}
          columns={[
            { title: '业务日期', dataIndex: 'business_date', width: 110 },
            { title: '记录时间', dataIndex: 'created_at', width: 170, render: dateTime },
            { title: '类型', dataIndex: 'entry_type', width: 130, render: (value) => <Tag>{entryText[value] ?? value}</Tag> },
            { title: '往来对象', render: (_, item) => item.contractor_id ? names.contractors.get(item.contractor_id) : item.source_id ? names.sources.get(item.source_id) : '—' },
            { title: '关联订单', dataIndex: 'order_id', render: (value) => value ? `#${value}` : '—' },
            ...(partyKind === 'source'
              ? [{
                title: '放单应收', width: 140, align: 'right' as const,
                render: (_: unknown, item: LedgerEntry) => item.source_receivable_snapshot == null
                  ? '—'
                  : <Money value={item.source_receivable_snapshot} signed />,
              }]
              : [
                {
                  title: '垫资可用余额', width: 140, align: 'right' as const,
                  render: (_: unknown, item: LedgerEntry) => item.advance_balance_snapshot == null
                    ? '—'
                    : <Money value={item.advance_balance_snapshot} signed />,
                },
                {
                  title: '待付佣金', width: 130, align: 'right' as const,
                  render: (_: unknown, item: LedgerEntry) => item.commission_payable_snapshot == null
                    ? '—'
                    : <Money value={item.commission_payable_snapshot} />,
                },
                {
                  title: '扣佣待结算', width: 140, align: 'right' as const,
                  render: (_: unknown, item: LedgerEntry) => item.net_settlement_snapshot == null
                    ? '—'
                    : <Money value={item.net_settlement_snapshot} signed />,
                },
              ]),
            { title: '备注', dataIndex: 'note', render: (value) => value || '—' },
            { title: '变动金额', dataIndex: 'amount', align: 'right' as const, width: 140, render: (value) => <Money value={value} signed /> },
          ]}
        />
      </Card>

      <Drawer
        title={logTarget ? `余额日志 · ${logTarget.counterparty_name}` : '余额日志'}
        width={720}
        open={Boolean(logTarget)}
        onClose={() => setLogTarget(undefined)}
        destroyOnHidden
      >
        <Typography.Paragraph type="secondary">
          {logTarget ? `账户：${logTarget.account === 'ADVANCE' ? '垫资余额' : logTarget.account === 'COMMISSION_PAYABLE' ? '佣金应付' : '放单应收'} · 当前余额：${logTarget.balance}` : ''}
        </Typography.Paragraph>
        <Table<LedgerEntry>
          rowKey="id"
          dataSource={logEntries.data ?? []}
          loading={logEntries.isLoading}
          pagination={{ pageSize: 15 }}
          scroll={{ x: 700 }}
          locale={{ emptyText: '暂无流水日志' }}
          columns={[
            { title: '业务日期', dataIndex: 'business_date', width: 110 },
            { title: '记录时间', dataIndex: 'created_at', width: 170, render: dateTime },
            { title: '类型', dataIndex: 'entry_type', width: 130, render: (value) => <Tag>{entryText[value] ?? value}</Tag> },
            { title: '关联订单', dataIndex: 'order_id', width: 110, render: (value) => value ? `#${value}` : '—' },
            { title: '备注', dataIndex: 'note', render: (value) => value || '—' },
            { title: '变动金额', dataIndex: 'amount', align: 'right', width: 130, render: (value) => <Money value={value} signed /> },
          ]}
        />
      </Drawer>

      <Modal
        title={`确认批量结清 · 截至 ${clearingDateValue}`}
        open={batchClearingOpen}
        onCancel={() => setBatchClearingOpen(false)}
        onOk={() => batchClearMutation.mutate()}
        confirmLoading={batchClearMutation.isPending}
        okText="确认全部结清"
        okButtonProps={{
          disabled: clearingPreviewQuery.isLoading || (clearingPreviewQuery.data?.length ?? 0) === 0,
        }}
      >
        <Typography.Paragraph type="secondary">
          系统将按往来对象分别结清截至 {clearingDateValue} 的余额，所选日期之后的流水不受影响；垫资可用余额不会被清空。
        </Typography.Paragraph>
        <Table<ClearingPreviewItem>
          rowKey={(item) => `${item.account}-${item.counterparty_id}`}
          dataSource={clearingPreviewQuery.data ?? []}
          loading={clearingPreviewQuery.isLoading}
          pagination={false}
          locale={{ emptyText: `截至 ${clearingDateValue} 没有待结清余额` }}
          columns={[
            { title: '对象', dataIndex: 'counterparty_name' },
            { title: '账户', dataIndex: 'account', render: (value) => value === 'COMMISSION_PAYABLE' ? '待付佣金' : '放单应收' },
            { title: '待结清', dataIndex: 'balance', align: 'right', render: (value) => <Money value={value} /> },
          ]}
        />
      </Modal>

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
