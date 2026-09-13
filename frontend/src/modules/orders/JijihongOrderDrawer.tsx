import { DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, DatePicker, Drawer, Form, Input, InputNumber, Select, Space, Statistic, Table, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, errorMessage } from '../../shared/api'
import { Money } from '../../shared/components'
import type {
  AlipayAccount,
  AlipayPoolSettings,
  JijihongOrderCreateResult,
  Order,
  PaymentPlan,
  RecommendationPreview,
  SuggestedAllocation,
} from '../../shared/types'

interface FormValues {
  business_date: Dayjs
  order_amount: number
  customer_received_amount: number
  external_cash_override_reason?: string
  note?: string
}

interface Props {
  open: boolean
  initialOrder?: Order | null
  onClose: () => void
  onCompleted: () => void | Promise<void>
}

const number = (value: string | number | undefined) => Number(value ?? 0)

export function JijihongOrderDrawer({ open, initialOrder, onClose, onCompleted }: Props) {
  const [form] = Form.useForm<FormValues>()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [allocations, setAllocations] = useState<SuggestedAllocation[]>([])
  const [preview, setPreview] = useState<RecommendationPreview | null>(null)
  const [saved, setSaved] = useState<JijihongOrderCreateResult | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [receivedTouched, setReceivedTouched] = useState(false)
  const requestId = useRef(0)
  const saveKey = useRef('')
  const orderAmount = Form.useWatch('order_amount', form)

  const accounts = useQuery({
    queryKey: ['alipay-accounts', 'order-selector'],
    queryFn: () => api.get<AlipayAccount[]>('/alipay-pool/accounts').then((res) => res.data),
    enabled: open,
  })
  const settings = useQuery({
    queryKey: ['alipay-settings'],
    queryFn: () => api.get<AlipayPoolSettings>('/alipay-pool/settings').then((res) => res.data),
    enabled: open,
  })
  const existingPlan = useQuery({
    queryKey: ['order-payment-plan', initialOrder?.id],
    queryFn: () => api.get<PaymentPlan | null>(`/alipay-pool/orders/${initialOrder!.id}/plan`).then((res) => res.data),
    enabled: open && Boolean(initialOrder?.id),
  })

  useEffect(() => {
    if (!open) return
    setSaved(null)
    setPreview(null)
    setAllocations([])
    setReceivedTouched(Boolean(initialOrder))
    if (!initialOrder) saveKey.current = crypto.randomUUID()
    form.setFieldsValue({
      business_date: dayjs(initialOrder?.business_date ?? dayjs()),
      order_amount: number(initialOrder?.order_amount) || undefined,
      customer_received_amount: number(initialOrder?.customer_received_amount ?? initialOrder?.order_amount) || undefined,
      note: initialOrder?.note,
      external_cash_override_reason: undefined,
    })
  }, [form, initialOrder, open])

  useEffect(() => {
    if (!open || !initialOrder || !existingPlan.data) return
    const plan = existingPlan.data
    setSaved({ order: initialOrder, payment_plan: plan })
    setAllocations(plan.allocations.map((item) => ({ ...item })))
    setPreview({
      order_amount: plan.order_amount,
      total_coupon: plan.total_coupon,
      total_balance: plan.total_balance,
      total_external_cash: plan.total_external_cash,
      soft_cap_exceeded: plan.soft_cap_exceeded,
      warning: plan.warning,
      allocations: plan.allocations.map((item) => ({ ...item })),
    })
  }, [existingPlan.data, initialOrder, open])

  useEffect(() => {
    if (!open || receivedTouched || !orderAmount) return
    form.setFieldValue('customer_received_amount', orderAmount)
  }, [form, open, orderAmount, receivedTouched])

  useEffect(() => {
    if (!open || saved || !orderAmount || orderAmount <= 0) return
    if (initialOrder && !existingPlan.isFetched) return
    const controller = new AbortController()
    const current = ++requestId.current
    const timer = window.setTimeout(async () => {
      setPreviewing(true)
      try {
        const response = await api.post<RecommendationPreview>(
          '/alipay-pool/recommendations/preview',
          { order_amount: orderAmount },
          { signal: controller.signal },
        )
        if (current !== requestId.current) return
        setPreview(response.data)
        setAllocations(response.data.allocations)
      } catch (error) {
        if (controller.signal.aborted || current !== requestId.current) return
        setPreview(null)
        setAllocations([])
        message.warning(errorMessage(error, '暂时无法生成支付方案'))
      } finally {
        if (current === requestId.current) setPreviewing(false)
      }
    }, 400)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [existingPlan.isFetched, initialOrder, message, open, orderAmount, saved])

  const accountGroups = useMemo(() => {
    const grouped = new Map<string, AlipayAccount[]>()
    for (const account of accounts.data ?? []) {
      if (account.status === 'EXHAUSTED') continue
      const rows = grouped.get(account.device_name) ?? []
      rows.push(account)
      grouped.set(account.device_name, rows)
    }
    return [...grouped.entries()].map(([label, rows]) => ({
      label,
      options: rows.map((account) => ({
        value: account.id,
        label: `${account.alias} · 可用 ¥${number(account.available_balance).toFixed(2)}${account.coupon_status === 'AVAILABLE' ? ' · 有券' : ''}`,
      })),
    }))
  }, [accounts.data])

  const totals = allocations.reduce(
    (result, item) => ({
      coupon: result.coupon + number(item.coupon_amount),
      balance: result.balance + number(item.balance_amount),
      cash: result.cash + number(item.external_cash_amount),
    }),
    { coupon: 0, balance: 0, cash: 0 },
  )
  const total = totals.coupon + totals.balance + totals.cash
  const softCap = number(settings.data?.external_cash_soft_cap || 8)
  const softCapExceeded = totals.cash > softCap

  const refreshPreview = async () => {
    const amount = Number(form.getFieldValue('order_amount'))
    if (!amount || amount <= 0) {
      message.warning('请先输入有效订单金额')
      return
    }
    const current = ++requestId.current
    setPreviewing(true)
    try {
      const response = await api.post<RecommendationPreview>('/alipay-pool/recommendations/preview', { order_amount: amount })
      if (current !== requestId.current) return
      setPreview(response.data)
      setAllocations(response.data.allocations)
    } catch (error) {
      message.warning(errorMessage(error, '暂时无法生成支付方案'))
    } finally {
      if (current === requestId.current) setPreviewing(false)
    }
  }

  const updateAllocation = (index: number, changes: Partial<SuggestedAllocation>) => {
    setAllocations((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, ...changes } : row))
  }

  const replaceAccount = (index: number, accountId: number) => {
    const account = accounts.data?.find((item) => item.id === accountId)
    if (!account) return
    updateAllocation(index, {
      account_id: account.id,
      account_alias: account.alias,
      device_name: account.device_name,
      coupon_amount: '0',
      balance_amount: '0',
      external_cash_amount: '0',
      balance_before: account.available_balance,
      balance_after: account.available_balance,
    })
  }

  const addAccount = () => {
    const used = new Set(allocations.map((item) => item.account_id))
    const account = accounts.data?.find((item) => item.status !== 'EXHAUSTED' && !used.has(item.id))
    if (!account) {
      message.warning('没有可添加的支付宝账号')
      return
    }
    setAllocations((rows) => [...rows, {
      account_id: account.id,
      account_alias: account.alias,
      device_name: account.device_name,
      coupon_amount: '0',
      balance_amount: '0',
      external_cash_amount: '0',
      balance_before: account.available_balance,
      balance_after: account.available_balance,
    }])
  }

  const reservationBody = async () => {
    const values = await form.validateFields()
    if (!allocations.length) throw new Error('请至少选择一个支付宝账号')
    if (Math.abs(total - Number(values.order_amount)) > 0.005) {
      throw new Error(`付款方案合计 ¥${total.toFixed(2)}，必须等于订单金额`)
    }
    if (softCapExceeded && !values.external_cash_override_reason?.trim()) {
      throw new Error(`真实付款超过 ¥${softCap.toFixed(2)}，请填写超限原因`)
    }
    return {
      business_date: values.business_date.format('YYYY-MM-DD'),
      order_amount: values.order_amount,
      customer_received_amount: values.customer_received_amount,
      external_cash_override_reason: values.external_cash_override_reason?.trim() || null,
      note: values.note?.trim() || null,
      allocations: allocations.map((item) => ({
        account_id: item.account_id,
        coupon_amount: number(item.coupon_amount),
        balance_amount: number(item.balance_amount),
        external_cash_amount: number(item.external_cash_amount),
      })),
    }
  }

  const saveReservation = async () => {
    setSaving(true)
    try {
      const body = await reservationBody()
      const response = saved || initialOrder
        ? await api.put<JijihongOrderCreateResult>(`/alipay-pool/orders/${saved?.order.id ?? initialOrder!.id}/reservation`, body)
        : await api.post<JijihongOrderCreateResult>('/alipay-pool/orders', { ...body, idempotency_key: saveKey.current })
      setSaved(response.data)
      setAllocations(response.data.payment_plan.allocations.map((item) => ({ ...item })))
      setPreview({
        order_amount: response.data.payment_plan.order_amount,
        total_coupon: response.data.payment_plan.total_coupon,
        total_balance: response.data.payment_plan.total_balance,
        total_external_cash: response.data.payment_plan.total_external_cash,
        soft_cap_exceeded: response.data.payment_plan.soft_cap_exceeded,
        warning: response.data.payment_plan.warning,
        allocations: response.data.payment_plan.allocations.map((item) => ({ ...item })),
      })
      message.success(saved || initialOrder ? '预占方案已更新' : '订单已保存，余额与优惠券已预占')
      await queryClient.invalidateQueries({ queryKey: ['orders'] })
      await queryClient.invalidateQueries({ queryKey: ['alipay-accounts'] })
    } catch (error) {
      message.error(error instanceof Error && !('response' in error) ? error.message : errorMessage(error, '订单预占失败，请重新推荐'))
      const status = (error as { response?: { status?: number } })?.response?.status
      if (status === 409) {
        if (!saved && !initialOrder) setSaved(null)
        await refreshPreview()
      }
    } finally {
      setSaving(false)
    }
  }

  const confirmPayment = async () => {
    if (!saved) return
    setConfirming(true)
    try {
      await api.post(`/alipay-pool/payment-plans/${saved.payment_plan.id}/confirm`, {})
      message.success('付款已确认，余额、优惠券、订单收支已同步入账')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['orders'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['alipay-accounts'] }),
        queryClient.invalidateQueries({ queryKey: ['jijihong-funds'] }),
      ])
      await onCompleted()
      onClose()
    } catch (error) {
      message.error(errorMessage(error, '付款确认失败'))
    } finally {
      setConfirming(false)
    }
  }

  return (
    <Drawer
      title={initialOrder ? `订单与付款方案 · ${initialOrder.order_no}` : '登记季季红订单'}
      width={900}
      open={open}
      onClose={onClose}
      destroyOnHidden
      extra={<Space>
        <Button icon={<ReloadOutlined />} loading={previewing} onClick={() => void refreshPreview()}>重新推荐</Button>
        <Button disabled={Boolean(initialOrder && !['DRAFT', 'DISPATCHED'].includes(initialOrder.status))} loading={saving} onClick={() => void saveReservation()}>{saved ? '更新预占' : '保存并预占'}</Button>
        <Button type="primary" disabled={saved?.payment_plan.status !== 'RESERVED'} loading={confirming} onClick={() => void confirmPayment()}>确认已付款</Button>
      </Space>}
    >
      <Space direction="vertical" size="middle" className="full-width">
        <Alert
          type={saved ? 'success' : 'info'}
          showIcon
          message={saved ? `订单已保存，方案预占至 ${dayjs(saved.payment_plan.expires_at).format('YYYY-MM-DD HH:mm:ss')}` : '输入订单金额后自动推荐，预览不会占用账号余额'}
          description="可跨设备增删、替换账号并修改拆分金额；只有保存才预占，确认付款后才正式扣减。"
        />
        <Form<FormValues> form={form} layout="vertical">
          <Space align="start" wrap>
            <Form.Item name="business_date" label="业务日期" rules={[{ required: true }]}><DatePicker /></Form.Item>
            <Form.Item name="order_amount" label="订单金额" rules={[{ required: true }]}><InputNumber min={0.01} precision={2} prefix="¥" /></Form.Item>
            <Form.Item name="customer_received_amount" label="客户实收" rules={[{ required: true }]}>
              <InputNumber min={0} precision={2} prefix="¥" onChange={() => setReceivedTouched(true)} />
            </Form.Item>
          </Space>
          {softCapExceeded && (
            <Form.Item name="external_cash_override_reason" label="真实付款超限原因" rules={[{ required: true }]}>
              <Input placeholder={`真实付款 ¥${totals.cash.toFixed(2)} 已超过软上限 ¥${softCap.toFixed(2)}`} />
            </Form.Item>
          )}
          <Form.Item name="note" label="备注"><Input.TextArea autoSize={{ minRows: 2, maxRows: 4 }} /></Form.Item>
        </Form>
        {(preview?.warning || softCapExceeded) && <Alert type="warning" showIcon message={preview?.warning ?? `真实付款超过 ¥${softCap.toFixed(2)}`} />}
        <div className="calculation-strip">
          <Statistic title="优惠券" value={totals.coupon} precision={2} prefix="¥" />
          <Statistic title="余额抵扣" value={totals.balance} precision={2} prefix="¥" />
          <Statistic title="真实付款" value={totals.cash} precision={2} prefix="¥" valueStyle={{ color: softCapExceeded ? '#b7473a' : undefined }} />
          <Statistic title="方案合计" value={total} precision={2} prefix="¥" />
        </div>
        <Table<SuggestedAllocation>
          rowKey={(row) => `${row.account_id}-${allocations.indexOf(row)}`}
          loading={previewing || accounts.isLoading}
          pagination={false}
          dataSource={allocations}
          locale={{ emptyText: '输入有效订单金额后自动推荐' }}
          columns={[
            {
              title: '设备 / 支付宝账号', width: 280,
              render: (_, row, index) => <Select className="full-width" showSearch optionFilterProp="label" value={row.account_id} options={accountGroups} onChange={(value) => replaceAccount(index, value)} />,
            },
            { title: '优惠券', render: (_, row, index) => <InputNumber min={0} precision={2} value={number(row.coupon_amount)} onChange={(value) => updateAllocation(index, { coupon_amount: String(value ?? 0) })} /> },
            { title: '余额抵扣', render: (_, row, index) => <InputNumber min={0} max={number(row.balance_before)} precision={2} value={number(row.balance_amount)} onChange={(value) => updateAllocation(index, { balance_amount: String(value ?? 0), balance_after: String(Math.max(0, number(row.balance_before) - number(value ?? 0))) })} /> },
            { title: '真实付款', render: (_, row, index) => <InputNumber min={0} precision={2} value={number(row.external_cash_amount)} onChange={(value) => updateAllocation(index, { external_cash_amount: String(value ?? 0) })} /> },
            { title: '余额后', dataIndex: 'balance_after', render: (value) => <Money value={value} /> },
            { title: '', width: 48, render: (_, __, index) => <Button danger type="text" icon={<DeleteOutlined />} onClick={() => setAllocations((rows) => rows.filter((_, rowIndex) => rowIndex !== index))} /> },
          ]}
        />
        <Button type="dashed" icon={<PlusOutlined />} disabled={allocations.length >= Number(settings.data?.max_split_accounts ?? 5)} onClick={addAccount}>添加支付宝账号</Button>
        <Typography.Text type="secondary">设备不参与推荐评分，方案允许跨设备拆单。真实付款超限是警告，不会禁止业务提交，但必须填写原因。</Typography.Text>
      </Space>
    </Drawer>
  )
}
