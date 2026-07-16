import { EditOutlined, PercentageOutlined, PlusOutlined, StopOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, DatePicker, Form, Input, InputNumber, Modal, Select, Space, Table, Tabs, Tag } from 'antd'
import dayjs from 'dayjs'
import { useMemo, useState } from 'react'
import { api, errorMessage } from '../../shared/api'
import { Money, MoneyInput, PageTitle } from '../../shared/components'
import type { Contractor, Source } from '../../shared/types'
import { PerformerManagement } from './PerformerManagement'

type StatusFilter = 'active' | 'inactive' | 'all'

export function PartnersPage() {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [sourceOpen, setSourceOpen] = useState(false)
  const [leaderOpen, setLeaderOpen] = useState(false)
  const [editingSource, setEditingSource] = useState<Source>()
  const [editingLeader, setEditingLeader] = useState<Contractor>()
  const [rateTarget, setRateTarget] = useState<{ type: 'source' | 'leader'; id: number; name: string }>()
  const [sourceStatusFilter, setSourceStatusFilter] = useState<StatusFilter>('active')
  const [leaderStatusFilter, setLeaderStatusFilter] = useState<StatusFilter>('active')
  const [sourceForm] = Form.useForm()
  const [leaderForm] = Form.useForm()
  const [editSourceForm] = Form.useForm()
  const [editLeaderForm] = Form.useForm()
  const [rateForm] = Form.useForm()

  const sources = useQuery({
    queryKey: ['sources', 'manage', sourceStatusFilter],
    queryFn: () => api.get<Source[]>('/partners/sources', {
      params: sourceStatusFilter === 'active' ? { active_only: true } : undefined,
    }).then((res) => res.data),
  })
  const leaders = useQuery({
    queryKey: ['contractors', 'leaders', 'manage', leaderStatusFilter],
    queryFn: () => api.get<Contractor[]>('/partners/contractors', {
      params: {
        contractor_type: 'LEADER',
        ...(leaderStatusFilter === 'active' ? { active_only: true } : {}),
      },
    }).then((res) => res.data),
  })

  const filteredSources = useMemo(() => {
    if (sourceStatusFilter === 'inactive') return (sources.data ?? []).filter((item) => !item.is_active)
    return sources.data ?? []
  }, [sources.data, sourceStatusFilter])

  const filteredLeaders = useMemo(() => {
    if (leaderStatusFilter === 'inactive') return (leaders.data ?? []).filter((item) => !item.is_active)
    return leaders.data ?? []
  }, [leaders.data, leaderStatusFilter])

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
  const updateSource = useMutation({
    mutationFn: ({ id, values }: { id: number; values: Record<string, unknown> }) => api.patch(`/partners/sources/${id}`, values),
    onSuccess: async () => {
      message.success('放单人员已更新')
      setEditingSource(undefined)
      editSourceForm.resetFields()
      await queryClient.invalidateQueries({ queryKey: ['sources'] })
    },
    onError: (error) => message.error(errorMessage(error)),
  })
  const updateLeader = useMutation({
    mutationFn: ({ id, values }: { id: number; values: Record<string, unknown> }) => api.patch(`/partners/contractors/${id}`, values),
    onSuccess: async () => {
      message.success('学生头子已更新')
      setEditingLeader(undefined)
      editLeaderForm.resetFields()
      await queryClient.invalidateQueries({ queryKey: ['contractors'] })
    },
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

  const toggleSourceActive = (item: Source) => {
    const nextActive = !item.is_active
    modal.confirm({
      title: nextActive ? `启用「${item.name}」？` : `停用「${item.name}」？`,
      content: nextActive ? '启用后可在录单时选择该放单人员。' : '停用后将无法用于新订单，历史订单不受影响。',
      okText: nextActive ? '启用' : '停用',
      okButtonProps: nextActive ? undefined : { danger: true },
      onOk: async () => {
        try {
          await api.patch(`/partners/sources/${item.id}`, { is_active: nextActive })
          message.success(nextActive ? '已启用' : '已停用')
          await queryClient.invalidateQueries({ queryKey: ['sources'] })
        } catch (error) {
          message.error(errorMessage(error))
          throw error
        }
      },
    })
  }

  const toggleLeaderActive = (item: Contractor) => {
    const nextActive = !item.is_active
    modal.confirm({
      title: nextActive ? `启用「${item.name}」？` : `停用「${item.name}」？`,
      content: nextActive ? '启用后可在录单时选择该学生头子。' : '停用后将无法用于新订单，历史订单不受影响。',
      okText: nextActive ? '启用' : '停用',
      okButtonProps: nextActive ? undefined : { danger: true },
      onOk: async () => {
        try {
          await api.patch(`/partners/contractors/${item.id}`, { is_active: nextActive })
          message.success(nextActive ? '已启用' : '已停用')
          await queryClient.invalidateQueries({ queryKey: ['contractors'] })
        } catch (error) {
          message.error(errorMessage(error))
          throw error
        }
      },
    })
  }

  const openEditSource = (item: Source) => {
    setEditingSource(item)
    editSourceForm.setFieldsValue({ name: item.name, contact: item.contact, note: item.note })
  }

  const openEditLeader = (item: Contractor) => {
    setEditingLeader(item)
    editLeaderForm.setFieldsValue({ name: item.name, contact: item.contact, note: item.note })
  }

  const statusFilterOptions = [
    { value: 'active', label: '正常' },
    { value: 'inactive', label: '停用' },
    { value: 'all', label: '全部' },
  ]

  return (
    <div className="page-stack">
      <PageTitle title="合作方与费率" description="维护放单人员、学生头子、散户与实际做单学生；费率按生效日期留存历史快照。" />
      <Card>
        <Tabs items={[
          {
            key: 'sources',
            label: `放单人员 ${filteredSources.length}`,
            children: (
              <>
                <div className="table-toolbar">
                  <Space wrap>
                    <Select
                      value={sourceStatusFilter}
                      onChange={setSourceStatusFilter}
                      options={statusFilterOptions}
                      style={{ width: 120 }}
                    />
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => setSourceOpen(true)}>新增放单人员</Button>
                  </Space>
                </div>
                <Table<Source> rowKey="id" loading={sources.isLoading} dataSource={filteredSources} pagination={false} columns={[
                  { title: '名称', dataIndex: 'name', render: (value) => <strong>{value}</strong> },
                  { title: '联系方式', dataIndex: 'contact', render: (value) => value || '—' },
                  { title: '状态', dataIndex: 'is_active', width: 90, render: (value) => value ? <Tag color="success">正常</Tag> : <Tag>停用</Tag> },
                  { title: '默认结算基数', dataIndex: 'default_basis', render: (value) => value === 'ORDER_AMOUNT' ? '订单标价' : '券后价' },
                  { title: '当前折扣', dataIndex: 'default_discount', render: (value) => `${(Number(value) * 10).toFixed(2)} 折` },
                  { title: '备注', dataIndex: 'note', render: (value) => value || '—' },
                  {
                    title: '操作',
                    width: 280,
                    render: (_, item) => (
                      <Space wrap>
                        <Button icon={<EditOutlined />} onClick={() => openEditSource(item)}>编辑</Button>
                        <Button icon={<PercentageOutlined />} onClick={() => setRateTarget({ type: 'source', id: item.id, name: item.name })}>调整费率</Button>
                        <Button
                          danger={item.is_active}
                          icon={<StopOutlined />}
                          onClick={() => toggleSourceActive(item)}
                        >
                          {item.is_active ? '停用' : '启用'}
                        </Button>
                      </Space>
                    ),
                  },
                ]} />
              </>
            ),
          },
          {
            key: 'leaders',
            label: `学生头子 ${filteredLeaders.length}`,
            children: (
              <>
                <div className="table-toolbar">
                  <Space wrap>
                    <Select
                      value={leaderStatusFilter}
                      onChange={setLeaderStatusFilter}
                      options={statusFilterOptions}
                      style={{ width: 120 }}
                    />
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => setLeaderOpen(true)}>新增学生头子</Button>
                  </Space>
                </div>
                <Table<Contractor> rowKey="id" loading={leaders.isLoading} dataSource={filteredLeaders} pagination={false} columns={[
                  { title: '姓名', dataIndex: 'name', render: (value) => <strong>{value}</strong> },
                  { title: '联系方式', dataIndex: 'contact', render: (value) => value || '—' },
                  { title: '状态', dataIndex: 'is_active', width: 90, render: (value) => value ? <Tag color="success">正常</Tag> : <Tag>停用</Tag> },
                  { title: '当前每单佣金', dataIndex: 'default_commission', render: (value) => <Money value={value} /> },
                  { title: '备注', dataIndex: 'note', render: (value) => value || '—' },
                  {
                    title: '操作',
                    width: 280,
                    render: (_, item) => (
                      <Space wrap>
                        <Button icon={<EditOutlined />} onClick={() => openEditLeader(item)}>编辑</Button>
                        <Button icon={<PercentageOutlined />} onClick={() => setRateTarget({ type: 'leader', id: item.id, name: item.name })}>调整佣金</Button>
                        <Button
                          danger={item.is_active}
                          icon={<StopOutlined />}
                          onClick={() => toggleLeaderActive(item)}
                        >
                          {item.is_active ? '停用' : '启用'}
                        </Button>
                      </Space>
                    ),
                  },
                ]} />
              </>
            ),
          },
        ]} />
      </Card>

      <PerformerManagement />

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
      <Modal
        title="编辑放单人员"
        open={Boolean(editingSource)}
        onCancel={() => { setEditingSource(undefined); editSourceForm.resetFields() }}
        onOk={() => editSourceForm.submit()}
        confirmLoading={updateSource.isPending}
      >
        <Form
          form={editSourceForm}
          layout="vertical"
          requiredMark={false}
          onFinish={(values) => editingSource && updateSource.mutate({ id: editingSource.id, values })}
        >
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="contact" label="联系方式"><Input /></Form.Item>
          <Form.Item name="note" label="备注"><Input.TextArea /></Form.Item>
        </Form>
      </Modal>
      <Modal
        title="编辑学生头子"
        open={Boolean(editingLeader)}
        onCancel={() => { setEditingLeader(undefined); editLeaderForm.resetFields() }}
        onOk={() => editLeaderForm.submit()}
        confirmLoading={updateLeader.isPending}
      >
        <Form
          form={editLeaderForm}
          layout="vertical"
          requiredMark={false}
          onFinish={(values) => editingLeader && updateLeader.mutate({ id: editingLeader.id, values })}
        >
          <Form.Item name="name" label="姓名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="contact" label="联系方式"><Input /></Form.Item>
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
