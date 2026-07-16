import { DownloadOutlined, MoreOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Dropdown, Input, Select, Space, Table, Tag } from 'antd'
import dayjs from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '../../shared/api'
import { Money, PageTitle, StatusTag } from '../../shared/components'
import type { Contractor, Order, OrderStatus, Source } from '../../shared/types'
import { OrderFormDrawer, type OrderFormValues } from './OrderFormDrawer'

export function OrdersPage() {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [open, setOpen] = useState(searchParams.get('new') === '1')
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<string>()
  const [sourceId, setSourceId] = useState<number>()
  const [contractorType, setContractorType] = useState<string>()
  const [keyword, setKeyword] = useState('')
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
  const filters = useMemo(() => ({ page, page_size: 20, status, source_id: sourceId, contractor_type: contractorType }), [page, status, sourceId, contractorType])
  const orders = useQuery({
    queryKey: ['orders', filters],
    queryFn: () => api.get<{ items: Order[]; total: number }>('/orders', { params: filters }).then((res) => res.data),
  })
  const filteredItems = useMemo(() => {
    const value = keyword.trim().toLowerCase()
    if (!value) return orders.data?.items ?? []
    return (orders.data?.items ?? []).filter((order) =>
      [order.order_no, order.source_name, order.contractor_name, order.student_name]
        .filter(Boolean)
        .some((item) => String(item).toLowerCase().includes(value)),
    )
  }, [orders.data?.items, keyword])

  const createMutation = useMutation({
    mutationFn: (values: OrderFormValues) => api.post('/orders', {
      ...values,
      business_date: dayjs(values.business_date).format('YYYY-MM-DD'),
    }),
    onSuccess: async () => {
      message.success('订单已保存')
      setOpen(false)
      setSearchParams({})
      await queryClient.invalidateQueries({ queryKey: ['orders'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error) => message.error(errorMessage(error, '订单保存失败')),
  })
  const statusMutation = useMutation({
    mutationFn: ({ id, target, reason }: { id: number; target: OrderStatus; reason?: string }) =>
      api.post(`/orders/${id}/status`, { status: target, reason }),
    onSuccess: async () => {
      message.success('订单状态已更新')
      await queryClient.invalidateQueries({ queryKey: ['orders'] })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error) => message.error(errorMessage(error, '状态更新失败')),
  })

  const closeDrawer = () => {
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
          <Input allowClear prefix={<SearchOutlined />} placeholder="当前页搜索订单号、人员" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
          <Select allowClear placeholder="订单状态" value={status} onChange={(value) => { setStatus(value); setPage(1) }} options={[
            { value: 'DRAFT', label: '草稿' }, { value: 'DISPATCHED', label: '已派单' }, { value: 'SUCCESS', label: '成功' }, { value: 'CANCELLED', label: '已取消' }, { value: 'REVERSED', label: '已冲正' },
          ]} />
          <Select allowClear showSearch optionFilterProp="label" placeholder="放单人员" value={sourceId} onChange={(value) => { setSourceId(value); setPage(1) }} options={sources.data?.map((item) => ({ value: item.id, label: item.name }))} />
          <Select allowClear placeholder="做单方式" value={contractorType} onChange={(value) => { setContractorType(value); setPage(1) }} options={[{ value: 'LEADER', label: '学生头子' }, { value: 'RETAIL', label: '散户' }]} />
          {selectedIds.length > 0 && <Button icon={<DownloadOutlined />} onClick={() => void exportSelected()}>导出已选 {selectedIds.length} 单</Button>}
        </div>
        <Table<Order>
          rowKey="id"
          loading={orders.isLoading}
          dataSource={filteredItems}
          scroll={{ x: 1200 }}
          rowSelection={{ selectedRowKeys: selectedIds, onChange: setSelectedIds }}
          pagination={{ current: page, pageSize: 20, total: orders.data?.total, showSizeChanger: false, onChange: setPage }}
          columns={[
            { title: '业务日期', dataIndex: 'business_date', width: 110 },
            { title: '订单号', dataIndex: 'order_no', width: 180, render: (value) => <span className="mono">{value}</span> },
            { title: '放单人员', dataIndex: 'source_name', width: 130 },
            { title: '做单方', width: 170, render: (_, order) => <Space size={4}><StatusTag value={order.contractor_type} /><span>{order.contractor_name}</span></Space> },
            { title: '学生', dataIndex: 'student_name', width: 100, render: (value) => value || '—' },
            { title: '状态', dataIndex: 'status', width: 90, render: (value) => <StatusTag value={value} /> },
            { title: '标价', dataIndex: 'order_amount', align: 'right', width: 110, render: (value) => <Money value={value} /> },
            { title: '实付', dataIndex: 'actual_paid', align: 'right', width: 110, render: (value) => <Money value={value} /> },
            { title: '佣金', dataIndex: 'commission', align: 'right', width: 100, render: (value, order) => <Space size={2}><Money value={value} />{order.commission_overridden && <Tag>覆盖</Tag>}</Space> },
            { title: '利润', dataIndex: 'profit', align: 'right', width: 120, render: (value) => <Money value={value} signed /> },
            {
              title: '', fixed: 'right', width: 54,
              render: (_, order) => {
                const items = []
                if (order.status === 'DRAFT') items.push({ key: 'dispatch', label: '标记已派单', onClick: () => statusMutation.mutate({ id: order.id, target: 'DISPATCHED' }) })
                if (order.status === 'DRAFT' || order.status === 'DISPATCHED') {
                  items.push({ key: 'success', label: '标记成功并入账', onClick: () => statusMutation.mutate({ id: order.id, target: 'SUCCESS' }) })
                  items.push({ key: 'cancel', danger: true, label: '取消订单', onClick: () => transitionWithReason(order, 'CANCELLED') })
                }
                if (order.status === 'SUCCESS') items.push({ key: 'reverse', danger: true, label: '冲正订单', onClick: () => transitionWithReason(order, 'REVERSED') })
                return <Dropdown menu={{ items }} disabled={!items.length}><Button type="text" icon={<MoreOutlined />} /></Dropdown>
              },
            },
          ]}
        />
      </Card>
      <OrderFormDrawer
        open={open}
        sources={sources.data ?? []}
        leaders={leaders.data ?? []}
        submitting={createMutation.isPending}
        onClose={closeDrawer}
        onSubmit={async (values) => { await createMutation.mutateAsync(values) }}
      />
    </div>
  )
}