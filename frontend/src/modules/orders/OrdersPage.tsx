import { DownloadOutlined, MoreOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Drawer, Dropdown, Input, Select, Space, Table, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { useDeferredValue, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '../../shared/api'
import { Money, PageTitle, StatusTag } from '../../shared/components'
import { dateTime } from '../../shared/format'
import type { Contractor, Order, OrderHistoryItem, OrderStatus, Performer, Source } from '../../shared/types'
import { OrderFormDrawer, type OrderFormValues } from './OrderFormDrawer'

const historyActionText: Record<string, string> = {
  'order.created': '创建订单',
  'order.updated': '修改订单',
  'order.status_changed': '变更订单状态',
}

export function OrdersPage() {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [open, setOpen] = useState(searchParams.get('new') === '1')
  const [editingOrder, setEditingOrder] = useState<Order | null>(null)
  const [historyOrder, setHistoryOrder] = useState<Order | null>(null)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<string>()
  const [sourceId, setSourceId] = useState<number>()
  const [leaderId, setLeaderId] = useState<number>()
  const [contractorType, setContractorType] = useState<string>()
  const [keyword, setKeyword] = useState('')
  const deferredKeyword = useDeferredValue(keyword)
  const [selectedIds, setSelectedIds] = useState<React.Key[]>([])

  useEffect(() => {
    if (searchParams.get('new') === '1') setOpen(true)
  }, [searchParams])

  const sources = useQuery({
    queryKey: ['sources'],
    queryFn: () => api.get<Source[]>('/partners/sources').then((res) => res.data),
  })
  const leaders = useQuery({
    queryKey: ['contractors', 'leaders'],
    queryFn: () => api.get<Contractor[]>('/partners/contractors', { params: { contractor_type: 'LEADER' } }).then((res) => res.data),
  })
  const performers = useQuery({
    queryKey: ['performers', 'orders'],
    queryFn: () => api.get<Performer[]>('/partners/performers').then((res) => res.data),
  })
  const filters = useMemo(() => ({
    page,
    page_size: 20,
    status,
    source_id: sourceId,
    contractor_id: leaderId,
    contractor_type: contractorType,
    keyword: deferredKeyword.trim() || undefined,
  }), [page, status, sourceId, leaderId, contractorType, deferredKeyword])
  const orders = useQuery({
    queryKey: ['orders', filters],
    queryFn: () => api.get<{ items: Order[]; total: number }>('/orders', { params: filters }).then((res) => res.data),
  })
  const history = useQuery({
    queryKey: ['order-history', historyOrder?.id],
    queryFn: () => api.get<OrderHistoryItem[]>(`/orders/${historyOrder!.id}/history`).then((res) => res.data),
    enabled: Boolean(historyOrder?.id),
  })

  const notifyCouponEligibility = (order: Order) => {
    if (order.available_coupons > 0 && order.performer_name) {
      message.warning(`${order.performer_name} 当前有 ${order.point_balance ?? 0} 积分，可提醒其兑换 ${order.available_coupons} 张 30 元优惠券`)
    }
  }

  const createMutation = useMutation({
    mutationFn: (values: OrderFormValues) => api.post<Order>('/orders', {
      ...values,
      business_date: dayjs(values.business_date).format('YYYY-MM-DD'),
    }),
    onSuccess: async (response) => {
      message.success('订单已保存')
      notifyCouponEligibility(response.data)
      setOpen(false)
      setSearchParams({})
      await queryClient.invalidateQueries({ queryKey: ['orders'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      await queryClient.invalidateQueries({ queryKey: ['performers'] })
      await queryClient.invalidateQueries({ queryKey: ['point-accounts'] })
      await queryClient.invalidateQueries({ queryKey: ['performer-order-stats'] })
    },
    onError: (error) => message.error(errorMessage(error, '订单保存失败')),
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, values }: { id: number; values: OrderFormValues }) => api.patch<Order>(`/orders/${id}`, {
      business_date: dayjs(values.business_date).format('YYYY-MM-DD'),
      source_id: values.source_id,
      contractor_type: values.contractor_type,
      contractor_id: values.contractor_type === 'LEADER' ? values.contractor_id : null,
      performer_id: values.performer_id ?? null,
      performer_name: values.performer_name?.trim() || null,
      save_performer: values.save_performer,
      order_amount: values.order_amount,
      coupon_amount: values.coupon_amount,
      actual_paid: values.actual_paid,
      settlement_income_override: values.settlement_income_override ?? null,
      income_override_reason: values.settlement_income_override == null
        ? null
        : values.income_override_reason?.trim() || null,
      commission_override: values.commission_override ?? null,
      commission_override_reason: values.commission_override == null
        ? null
        : values.commission_override_reason?.trim() || null,
      note: values.note?.trim() || null,
    }),
    onSuccess: async (response) => {
      message.success('订单已更新')
      notifyCouponEligibility(response.data)
      setEditingOrder(null)
      await queryClient.invalidateQueries({ queryKey: ['orders'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      await queryClient.invalidateQueries({ queryKey: ['performers'] })
      await queryClient.invalidateQueries({ queryKey: ['point-accounts'] })
      await queryClient.invalidateQueries({ queryKey: ['performer-order-stats'] })
    },
    onError: (error) => message.error(errorMessage(error, '订单更新失败')),
  })
  const statusMutation = useMutation({
    mutationFn: ({ id, target, reason }: { id: number; target: OrderStatus; reason?: string }) =>
      api.post<Order>(`/orders/${id}/status`, { status: target, reason }),
    onSuccess: async (response) => {
      message.success('订单状态已更新')
      notifyCouponEligibility(response.data)
      await queryClient.invalidateQueries({ queryKey: ['orders'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      await queryClient.invalidateQueries({ queryKey: ['performers'] })
      await queryClient.invalidateQueries({ queryKey: ['point-accounts'] })
      await queryClient.invalidateQueries({ queryKey: ['performer-order-stats'] })
    },
    onError: (error) => message.error(errorMessage(error, '状态更新失败')),
  })

  const closeCreateDrawer = () => {
    setOpen(false)
    setSearchParams({})
  }

  const transitionWithReason = (order: Order, target: 'CANCELLED' | 'REVERSED') => {
    let reason = ''
    modal.confirm({
      title: target === 'REVERSED' ? '冲正成功订单' : '取消订单',
      content: <Input.TextArea placeholder="请输入原因，操作会写入审计日志" onChange={(event) => { reason = event.target.value }} />,
      okText: '确认',
      okButtonProps: { danger: true },
      onOk: async () => {
        if (!reason.trim()) {
          message.warning('必须填写原因')
          throw new Error('reason required')
        }
        await statusMutation.mutateAsync({ id: order.id, target, reason })
      },
    })
  }

  const exportSelected = async () => {
    const params = new URLSearchParams({ export_format: 'xlsx' })
    selectedIds.forEach((id) => params.append('order_ids', String(id)))
    const response = await api.get('/reports/orders/export', { params, responseType: 'blob' })
    const url = URL.createObjectURL(response.data)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `orders-${dayjs().format('YYYYMMDD')}.xlsx`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="page-stack">
      <PageTitle
        title="订单登记"
        description="成功订单自动生成账务流水；历史费率在订单上固化，不随当前配置变化。"
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>登记订单</Button>}
      />
      <Card>
        <div className="filter-bar">
          <Input allowClear prefix={<SearchOutlined />} placeholder="搜索订单号或人员" value={keyword} onChange={(event) => { setKeyword(event.target.value); setPage(1) }} />
          <Select allowClear placeholder="订单状态" value={status} onChange={(value) => { setStatus(value); setPage(1) }} options={[
            { value: 'DRAFT', label: '草稿' }, { value: 'DISPATCHED', label: '已派单' }, { value: 'SUCCESS', label: '成功' }, { value: 'CANCELLED', label: '已取消' }, { value: 'REVERSED', label: '已冲正' },
          ]} />
          <Select allowClear showSearch optionFilterProp="label" placeholder="放单人员" value={sourceId} onChange={(value) => { setSourceId(value); setPage(1) }} options={sources.data?.map((item) => ({ value: item.id, label: item.name }))} />
          <Select allowClear showSearch optionFilterProp="label" placeholder="学生头子" value={leaderId} onChange={(value) => { setLeaderId(value); setPage(1) }} options={leaders.data?.map((item) => ({ value: item.id, label: item.name }))} />
          <Select allowClear placeholder="做单方式" value={contractorType} onChange={(value) => { setContractorType(value); setPage(1) }} options={[{ value: 'LEADER', label: '学生头子' }, { value: 'RETAIL', label: '散户' }]} />
          {selectedIds.length > 0 && <Button icon={<DownloadOutlined />} onClick={() => void exportSelected()}>导出已选 {selectedIds.length} 单</Button>}
        </div>
        <Table<Order>
          rowKey="id"
          loading={orders.isLoading}
          dataSource={orders.data?.items ?? []}
          scroll={{ x: 1200 }}
          rowSelection={{ selectedRowKeys: selectedIds, onChange: setSelectedIds }}
          pagination={{ current: page, pageSize: 20, total: orders.data?.total, showSizeChanger: false, onChange: setPage }}
          columns={[
            { title: '业务日期', dataIndex: 'business_date', width: 110 },
            { title: '订单号', dataIndex: 'order_no', width: 180, render: (value) => <span className="mono">{value}</span> },
            { title: '放单人员', dataIndex: 'source_name', width: 130 },
            { title: '做单方', width: 170, render: (_, order) => <Space size={4}><StatusTag value={order.contractor_type} /><span>{order.contractor_name}</span></Space> },
            { title: '实际做单人', dataIndex: 'performer_name', width: 120, render: (value) => value || '待补' },
            { title: '状态', dataIndex: 'status', width: 90, render: (value) => <StatusTag value={value} /> },
            { title: '标价', dataIndex: 'order_amount', align: 'right', width: 110, render: (value) => <Money value={value} /> },
            { title: '实付', dataIndex: 'actual_paid', align: 'right', width: 110, render: (value) => <Money value={value} /> },
            { title: '佣金', dataIndex: 'commission', align: 'right', width: 100, render: (value, order) => <Space size={2}><Money value={value} />{order.commission_overridden && <Tag>覆盖</Tag>}</Space> },
            { title: '利润', dataIndex: 'profit', align: 'right', width: 120, render: (value) => <Money value={value} signed /> },
            {
              title: '操作', fixed: 'right', width: 100,
              render: (_, order) => {
                const items = []
                items.push({ key: 'edit', label: '编辑', onClick: () => setEditingOrder(order) })
                items.push({ key: 'history', label: '历史', onClick: () => setHistoryOrder(order) })
                if (order.status === 'DRAFT') items.push({ key: 'dispatch', label: '标记已派单', onClick: () => statusMutation.mutate({ id: order.id, target: 'DISPATCHED' }) })
                if (order.status === 'DRAFT' || order.status === 'DISPATCHED') {
                  items.push({ key: 'success', label: '标记成功并入账', onClick: () => statusMutation.mutate({ id: order.id, target: 'SUCCESS' }) })
                  items.push({ key: 'cancel', danger: true, label: '取消订单', onClick: () => transitionWithReason(order, 'CANCELLED') })
                }
                if (order.status === 'SUCCESS') items.push({ key: 'reverse', danger: true, label: '冲正订单', onClick: () => transitionWithReason(order, 'REVERSED') })
                return <Dropdown menu={{ items }}><Button type="text" icon={<MoreOutlined />}>操作</Button></Dropdown>
              },
            },
          ]}
        />
      </Card>
      <OrderFormDrawer
        open={open}
        mode="create"
        sources={sources.data ?? []}
        leaders={leaders.data ?? []}
        performers={performers.data ?? []}
        submitting={createMutation.isPending}
        onClose={closeCreateDrawer}
        onSubmit={async (values) => { await createMutation.mutateAsync(values) }}
      />
      <OrderFormDrawer
        open={Boolean(editingOrder)}
        mode="edit"
        initialOrder={editingOrder}
        sources={sources.data ?? []}
        leaders={leaders.data ?? []}
        performers={performers.data ?? []}
        submitting={updateMutation.isPending}
        onClose={() => setEditingOrder(null)}
        onSubmit={async (values) => {
          if (!editingOrder) return
          await updateMutation.mutateAsync({ id: editingOrder.id, values })
        }}
      />
      <Drawer
        title={historyOrder ? `订单历史 · ${historyOrder.order_no}` : '订单历史'}
        width={480}
        open={Boolean(historyOrder)}
        onClose={() => setHistoryOrder(null)}
        destroyOnHidden
      >
        <Table<OrderHistoryItem>
          rowKey="id"
          loading={history.isLoading}
          dataSource={history.data}
          pagination={false}
          locale={{ emptyText: '暂无创建或编辑记录' }}
          columns={[
            { title: '时间', dataIndex: 'created_at', width: 150, render: dateTime },
            {
              title: '操作',
              dataIndex: 'action',
              width: 110,
              render: (value) => <Tag>{historyActionText[value] ?? value}</Tag>,
            },
            { title: '操作者', dataIndex: 'user_name', width: 90, render: (value) => value || '系统' },
            {
              title: '详情',
              dataIndex: 'payload',
              render: (value) => value
                ? <Typography.Text code className="audit-payload">{JSON.stringify(value)}</Typography.Text>
                : '—',
            },
          ]}
        />
      </Drawer>
    </div>
  )
}
