import { CheckOutlined, PlusOutlined, RollbackOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, DatePicker, Form, Input, Modal, Popconfirm, Radio, Select, Space, Table } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { api, errorMessage } from '../../shared/api'
import { Money, PageTitle, StatusTag } from '../../shared/components'
import { dateTime } from '../../shared/format'
import type { Contractor, Settlement, Source } from '../../shared/types'

const { RangePicker } = DatePicker

export function SettlementsPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [reverseTarget, setReverseTarget] = useState<Settlement>()
  const [form] = Form.useForm()
  const [reverseForm] = Form.useForm()
  const settlementType = Form.useWatch('settlement_type', form) ?? 'SOURCE'
  const settlements = useQuery({ queryKey: ['settlements'], queryFn: () => api.get<Settlement[]>('/settlements').then((res) => res.data) })
  const sources = useQuery({ queryKey: ['sources'], queryFn: () => api.get<Source[]>('/partners/sources').then((res) => res.data) })
  const contractors = useQuery({ queryKey: ['contractors', 'all'], queryFn: () => api.get<Contractor[]>('/partners/contractors').then((res) => res.data) })

  const createMutation = useMutation({
    mutationFn: (values: Record<string, unknown>) => {
      const range = values.range as [ReturnType<typeof dayjs>, ReturnType<typeof dayjs>]
      return api.post('/settlements', { ...values, range: undefined, date_from: range[0].format('YYYY-MM-DD'), date_to: range[1].format('YYYY-MM-DD') })
    },
    onSuccess: async () => { message.success('结算草稿已生成，请核对后确认'); setOpen(false); form.resetFields(); await queryClient.invalidateQueries({ queryKey: ['settlements'] }) },
    onError: (error) => message.error(errorMessage(error, '生成结算单失败')),
  })
  const confirmMutation = useMutation({
    mutationFn: (id: number) => api.post(`/settlements/${id}/confirm`),
    onSuccess: async () => { message.success('结算单已确认并锁账'); await queryClient.invalidateQueries({ queryKey: ['settlements'] }) },
    onError: (error) => message.error(errorMessage(error)),
  })
  const reverseMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => api.post(`/settlements/${id}/reverse`, { reason }),
    onSuccess: async () => { message.success('结算单已冲正，关联订单已解锁'); setReverseTarget(undefined); reverseForm.resetFields(); await queryClient.invalidateQueries({ queryKey: ['settlements'] }) },
    onError: (error) => message.error(errorMessage(error)),
  })

  return (
    <div className="page-stack">
      <PageTitle title="结算中心" description="结算确认后会锁定关联订单，并追加资金清账流水；冲正会恢复余额并解锁订单。" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>生成结算单</Button>} />
      <Card>
        <Table<Settlement> rowKey="id" loading={settlements.isLoading} dataSource={settlements.data} scroll={{ x: 1200 }} pagination={{ pageSize: 15 }} columns={[
          { title: '结算单号', dataIndex: 'settlement_no', width: 190, render: (value) => <span className="mono">{value}</span> },
          { title: '记录时间', dataIndex: 'created_at', width: 170, render: dateTime },
          { title: '类型', dataIndex: 'settlement_type', width: 110, render: (value) => <StatusTag value={value} /> },
          { title: '往来对象', dataIndex: 'counterparty_name_snapshot', width: 140 },
          { title: '期间', width: 210, render: (_, item) => `${item.date_from} 至 ${item.date_to}` },
          { title: '订单数', dataIndex: 'order_count', width: 90, align: 'right' },
          { title: '清账账户', dataIndex: 'account', width: 110, render: (value) => value === 'COMMISSION_PAYABLE' ? '待付佣金' : value === 'SOURCE_RECEIVABLE' ? '放单应收' : '历史记录' },
          { title: '结清金额', dataIndex: 'settled_amount', width: 120, align: 'right', render: (value) => <Money value={value} /> },
          { title: '结算收入', dataIndex: 'settlement_income_total', width: 120, align: 'right', render: (value) => <Money value={value} /> },
          { title: '实付', dataIndex: 'actual_paid_total', width: 110, align: 'right', render: (value) => <Money value={value} /> },
          { title: '佣金', dataIndex: 'commission_total', width: 100, align: 'right', render: (value) => <Money value={value} /> },
          { title: '利润', dataIndex: 'profit_total', width: 120, align: 'right', render: (value) => <Money value={value} signed /> },
          { title: '状态', dataIndex: 'status', width: 100, render: (value) => <StatusTag value={value} /> },
          { title: '确认时间', dataIndex: 'confirmed_at', width: 170, render: (value) => value ? dateTime(value) : '—' },
          {
            title: '', fixed: 'right', width: 170,
            render: (_, item) => (
              <Space>
                {item.status === 'DRAFT' && <Popconfirm title="确认后关联订单将锁定，是否继续？" onConfirm={() => confirmMutation.mutate(item.id)}><Button type="primary" ghost icon={<CheckOutlined />}>确认</Button></Popconfirm>}
                {item.status === 'CONFIRMED' && <Button danger icon={<RollbackOutlined />} onClick={() => setReverseTarget(item)}>冲正</Button>}
              </Space>
            ),
          },
        ]} />
      </Card>

      <Modal title="生成结算草稿" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={createMutation.isPending}>
        <Form form={form} layout="vertical" requiredMark={false} onFinish={(values) => createMutation.mutate(values)} initialValues={{ settlement_type: 'SOURCE', range: [dayjs(), dayjs()] }}>
          <Form.Item name="settlement_type" label="结算类型"><Radio.Group optionType="button" buttonStyle="solid" options={[{ value: 'SOURCE', label: '放单人员结算' }, { value: 'CONTRACTOR', label: '做单方结算' }]} /></Form.Item>
          <Form.Item name="range" label="结算期间" rules={[{ required: true }]}><RangePicker className="full-width" /></Form.Item>
          {settlementType === 'SOURCE' ? (
            <Form.Item name="source_id" label="放单人员" rules={[{ required: true }]}><Select showSearch optionFilterProp="label" options={sources.data?.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item>
          ) : (
            <Form.Item name="contractor_id" label="学生头子或散户" rules={[{ required: true }]}><Select showSearch optionFilterProp="label" options={contractors.data?.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item>
          )}
          <Form.Item name="note" label="备注"><Input.TextArea /></Form.Item>
        </Form>
      </Modal>
      <Modal title={`冲正结算 · ${reverseTarget?.settlement_no ?? ''}`} open={Boolean(reverseTarget)} onCancel={() => setReverseTarget(undefined)} onOk={() => reverseForm.submit()} confirmLoading={reverseMutation.isPending} okButtonProps={{ danger: true }}>
        <Form form={reverseForm} layout="vertical" onFinish={(values) => reverseTarget && reverseMutation.mutate({ id: reverseTarget.id, reason: values.reason })}>
          <Form.Item name="reason" label="冲正原因" rules={[{ required: true }]}><Input.TextArea placeholder="原因会写入审计日志" /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}