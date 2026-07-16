import { PercentageOutlined, PlusOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, DatePicker, Form, Input, InputNumber, Modal, Select, Space, Table, Tabs, Tag } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { api, errorMessage } from '../../shared/api'
import { Money, MoneyInput, PageTitle } from '../../shared/components'
import type { Contractor, Source } from '../../shared/types'

export function PartnersPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [sourceOpen, setSourceOpen] = useState(false)
  const [leaderOpen, setLeaderOpen] = useState(false)
  const [rateTarget, setRateTarget] = useState<{ type: 'source' | 'leader'; id: number; name: string }>()
  const [sourceForm] = Form.useForm()
  const [leaderForm] = Form.useForm()
  const [rateForm] = Form.useForm()

  const sources = useQuery({ queryKey: ['sources'], queryFn: () => api.get<Source[]>('/partners/sources').then((res) => res.data) })
  const leaders = useQuery({ queryKey: ['contractors', 'leaders'], queryFn: () => api.get<Contractor[]>('/partners/contractors', { params: { contractor_type: 'LEADER' } }).then((res) => res.data) })

  const createSource = useMutation({
    mutationFn: (values: Record<string, unknown>) => api.post('/partners/sources', { ...values, effective_date: dayjs(values.effective_date as string).format('YYYY-MM-DD'), default_discount: Number(values.default_discount) / 10 }),
    onSuccess: async () => { message.success('放单人员已创建'); setSourceOpen(false); sourceForm.resetFields(); await queryClient.invalidateQueries({ queryKey: ['sources'] }) },
    onError: (error) => message.error(errorMessage(error)),
  })
  const createLeader = useMutation({
    mutationFn: (values: Record<string, unknown>) => api.post('/partners/contractors', { ...values, contractor_type: 'LEADER', effective_date: dayjs(values.effective_date as string).format('YYYY-MM-DD') }),
    onSuccess: async () => { message.success('学生头子已创建'); setLeaderOpen(false); leaderForm.resetFields(); await queryClient.invalidateQueries({ queryKey: ['contractors'] }) },
    onError: (error) => message.error(errorMessage(error)),
  })
  const createRate = useMutation({
    mutationFn: (values: Record<string, unknown>) => {
      if (!rateTarget) throw new Error('missing target')
      const effectiveDate = dayjs(values.effective_date as string).format('YYYY-MM-DD')
      if (rateTarget.type === 'source') {
        return api.post(`/partners/sources/${rateTarget.id}/rates`, {
          effective_date: effectiveDate,
          settlement_basis: values.settlement_basis,
          discount: Number(values.discount) / 10,
        })
      }
      return api.post(`/partners/contractors/${rateTarget.id}/rates`, {
        effective_date: effectiveDate,
        commission_per_order: values.commission_per_order,
      })
    },
    onSuccess: async () => {
      message.success('新费率已保存')
      setRateTarget(undefined)
      rateForm.resetFields()
      await queryClient.invalidateQueries({ queryKey: ['sources'] })
      await queryClient.invalidateQueries({ queryKey: ['contractors'] })
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  return (
    <div className="page-stack">
      <PageTitle title="合作方与费率" description="费率按生效日期追加，不覆盖历史订单快照。散户在录单时直接填写，无需维护名单。" />
      <Card>
        <Tabs items={[
          {
            key: 'sources',
            label: `放单人员 ${sources.data?.length ?? 0}`,
            children: (
              <>
                <div className="table-toolbar"><Button type="primary" icon={<PlusOutlined />} onClick={() => setSourceOpen(true)}>新增放单人员</Button></div>
                <Table<Source> rowKey="id" loading={sources.isLoading} dataSource={sources.data} pagination={false} columns={[
                  { title: '名称', dataIndex: 'name', render: (value, item) => <Space><strong>{value}</strong>{!item.is_active && <Tag>停用</Tag>}</Space> },
                  { title: '联系方式', dataIndex: 'contact', render: (value) => value || '—' },
                  { title: '默认结算基数', dataIndex: 'default_basis', render: (value) => value === 'ORDER_AMOUNT' ? '订单标价' : '券后价' },
                  { title: '当前折扣', dataIndex: 'default_discount', render: (value) => `${(Number(value) * 10).toFixed(2)} 折` },
                  { title: '备注', dataIndex: 'note', render: (value) => value || '—' },
                  { title: '', width: 130, render: (_, item) => <Button icon={<PercentageOutlined />} onClick={() => setRateTarget({ type: 'source', id: item.id, name: item.name })}>调整费率</Button> },
                ]} />
              </>
            ),
          },
          {
            key: 'leaders',
            label: `学生头子 ${leaders.data?.length ?? 0}`,
            children: (
              <>
                <div className="table-toolbar"><Button type="primary" icon={<PlusOutlined />} onClick={() => setLeaderOpen(true)}>新增学生头子</Button></div>
                <Table<Contractor> rowKey="id" loading={leaders.isLoading} dataSource={leaders.data} pagination={false} columns={[
                  { title: '姓名', dataIndex: 'name', render: (value, item) => <Space><strong>{value}</strong>{!item.is_active && <Tag>停用</Tag>}</Space> },
                  { title: '联系方式', dataIndex: 'contact', render: (value) => value || '—' },
                  { title: '当前每单佣金', dataIndex: 'default_commission', render: (value) => <Money value={value} /> },
                  { title: '备注', dataIndex: 'note', render: (value) => value || '—' },
                  { title: '', width: 130, render: (_, item) => <Button icon={<PercentageOutlined />} onClick={() => setRateTarget({ type: 'leader', id: item.id, name: item.name })}>调整佣金</Button> },
                ]} />
              </>
            ),
          },
        ]} />
      </Card>

      <Modal title="新增放单人员" open={sourceOpen} onCancel={() => setSourceOpen(false)} onOk={() => sourceForm.submit()} confirmLoading={createSource.isPending}>
        <Form form={sourceForm} layout="vertical" requiredMark={false} onFinish={(values) => createSource.mutate(values)} initialValues={{ default_basis: 'ORDER_AMOUNT', default_discount: 9, effective_date: dayjs() }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="contact" label="联系方式"><Input /></Form.Item>
          <Form.Item name="default_basis" label="默认结算基数" rules={[{ required: true }]}><Select options={[{ value: 'ORDER_AMOUNT', label: '订单标价' }, { value: 'AFTER_COUPON', label: '券后价' }]} /></Form.Item>
          <Form.Item name="default_discount" label="默认折扣" rules={[{ required: true }]}><InputNumber min={0.01} max={10} precision={2} addonAfter="折" className="full-width" /></Form.Item>
          <Form.Item name="effective_date" label="生效日期" rules={[{ required: true }]}><DatePicker className="full-width" /></Form.Item>
          <Form.Item name="note" label="备注"><Input.TextArea /></Form.Item>
        </Form>
      </Modal>
      <Modal title="新增学生头子" open={leaderOpen} onCancel={() => setLeaderOpen(false)} onOk={() => leaderForm.submit()} confirmLoading={createLeader.isPending}>
        <Form form={leaderForm} layout="vertical" requiredMark={false} onFinish={(values) => createLeader.mutate(values)} initialValues={{ default_commission: 0, effective_date: dayjs() }}>
          <Form.Item name="name" label="姓名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="contact" label="联系方式"><Input /></Form.Item>
          <Form.Item name="default_commission" label="每日每单佣金" rules={[{ required: true }]}><MoneyInput /></Form.Item>
          <Form.Item name="effective_date" label="生效日期" rules={[{ required: true }]}><DatePicker className="full-width" /></Form.Item>
          <Form.Item name="note" label="备注"><Input.TextArea /></Form.Item>
        </Form>
      </Modal>
      <Modal title={`调整费率 · ${rateTarget?.name ?? ''}`} open={Boolean(rateTarget)} onCancel={() => setRateTarget(undefined)} onOk={() => rateForm.submit()} confirmLoading={createRate.isPending}>
        <Form form={rateForm} layout="vertical" requiredMark={false} onFinish={(values) => createRate.mutate(values)} initialValues={{ effective_date: dayjs() }}>
          <Form.Item name="effective_date" label="生效日期" rules={[{ required: true }]}><DatePicker className="full-width" /></Form.Item>
          {rateTarget?.type === 'source' ? (
            <>
              <Form.Item name="settlement_basis" label="结算基数" rules={[{ required: true }]}><Select options={[{ value: 'ORDER_AMOUNT', label: '订单标价' }, { value: 'AFTER_COUPON', label: '券后价' }]} /></Form.Item>
              <Form.Item name="discount" label="折扣" rules={[{ required: true }]}><InputNumber min={0.01} max={10} precision={2} addonAfter="折" className="full-width" /></Form.Item>
            </>
          ) : (
            <Form.Item name="commission_per_order" label="每单佣金" rules={[{ required: true }]}><MoneyInput /></Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  )
}