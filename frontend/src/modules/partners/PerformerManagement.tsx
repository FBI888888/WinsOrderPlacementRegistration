import { EditOutlined, EyeOutlined, GiftOutlined, PlusOutlined, StopOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Drawer, Form, Input, Modal, Select, Space, Table, Tabs, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../../shared/api'
import { Money } from '../../shared/components'
import { dateTime } from '../../shared/format'
import type { Contractor, Order, Performer, PerformerOrderStat, PointAccount } from '../../shared/types'

interface PendingPointOrder {
  id: number
  order_no: string
  business_date: string
  contractor_id: number
  contractor_name: string
  order_amount: string
  created_at: string
}

type PerformerStatusFilter = 'active' | 'inactive' | 'all'

const performerStatusFilterOptions = [
  { value: 'active', label: '正常' },
  { value: 'inactive', label: '停用' },
  { value: 'all', label: '全部' },
]

const matchesStatusFilter = (isActive: boolean, filter: PerformerStatusFilter) =>
  filter === 'all' || isActive === (filter === 'active')

type EditTarget =
  | { kind: 'retail'; contractor: Contractor }
  | { kind: 'student'; performer: Performer }

export function PerformerManagement() {
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [retailOpen, setRetailOpen] = useState(false)
  const [studentOpen, setStudentOpen] = useState(false)
  const [selectedLeaderId, setSelectedLeaderId] = useState<number>()
  const [detailTarget, setDetailTarget] = useState<Performer>()
  const [editTarget, setEditTarget] = useState<EditTarget>()
  const [retailStatusFilter, setRetailStatusFilter] = useState<PerformerStatusFilter>('active')
  const [studentStatusFilter, setStudentStatusFilter] = useState<PerformerStatusFilter>('active')
  const [retailForm] = Form.useForm()
  const [studentForm] = Form.useForm()
  const [editForm] = Form.useForm()

  const leaders = useQuery({
    queryKey: ['contractors', 'leaders', 'people-management'],
    queryFn: () => api.get<Contractor[]>('/partners/contractors', {
      params: { contractor_type: 'LEADER' },
    }).then((res) => res.data),
  })
  const retails = useQuery({
    queryKey: ['contractors', 'retail', 'people-management'],
    queryFn: () => api.get<Contractor[]>('/partners/contractors', {
      params: { contractor_type: 'RETAIL' },
    }).then((res) => res.data),
  })
  const performers = useQuery({
    queryKey: ['performers', 'people-management'],
    queryFn: () => api.get<Performer[]>('/partners/performers').then((res) => res.data),
  })
  const accounts = useQuery({
    queryKey: ['point-accounts'],
    queryFn: () => api.get<PointAccount[]>('/points/accounts').then((res) => res.data),
  })
  const orderStats = useQuery({
    queryKey: ['performer-order-stats'],
    queryFn: () => api.get<PerformerOrderStat[]>('/orders/performer-stats').then((res) => res.data),
  })
  const detailOrders = useQuery({
    queryKey: ['performer-orders', detailTarget?.id],
    queryFn: () => api.get<{ items: Order[] }>('/orders', {
      params: { performer_id: detailTarget!.id, status: 'SUCCESS', page_size: 200 },
    }).then((res) => res.data.items),
    enabled: Boolean(detailTarget),
  })
  const pendingOrders = useQuery({
    queryKey: ['point-pending-orders'],
    queryFn: () => api.get<PendingPointOrder[]>('/points/pending-orders').then((res) => res.data),
  })

  useEffect(() => {
    if (selectedLeaderId == null) {
      const firstActive = leaders.data?.find((item) => item.is_active)
      if (firstActive) setSelectedLeaderId(firstActive.id)
    }
  }, [leaders.data, selectedLeaderId])

  const accountByPerformer = useMemo(
    () => new Map((accounts.data ?? []).map((item) => [item.performer_id, item])),
    [accounts.data],
  )
  const orderCountByPerformer = useMemo(
    () => new Map((orderStats.data ?? []).map((item) => [item.performer_id, item.success_count])),
    [orderStats.data],
  )
  const retailPerformerByContractor = useMemo(
    () => new Map(
      (performers.data ?? [])
        .filter((item) => item.performer_type === 'RETAIL')
        .map((item) => [item.contractor_id, item]),
    ),
    [performers.data],
  )
  const retailRows = useMemo(
    () => (retails.data ?? [])
      .filter((item) => matchesStatusFilter(item.is_active, retailStatusFilter))
      .sort((left, right) => {
        const leftPerformer = retailPerformerByContractor.get(left.id)
        const rightPerformer = retailPerformerByContractor.get(right.id)
        const countDifference = (orderCountByPerformer.get(leftPerformer?.id ?? -1) ?? 0)
          - (orderCountByPerformer.get(rightPerformer?.id ?? -1) ?? 0)
        return countDifference || left.name.localeCompare(right.name, 'zh-CN')
      }),
    [retails.data, retailPerformerByContractor, retailStatusFilter, orderCountByPerformer],
  )
  const students = useMemo(
    () => (performers.data ?? [])
      .filter(
        (item) => item.performer_type === 'STUDENT'
          && item.contractor_id === selectedLeaderId
          && item.is_listed
          && matchesStatusFilter(item.is_active, studentStatusFilter),
      )
      .sort((left, right) => {
        const countDifference = (orderCountByPerformer.get(left.id) ?? 0)
          - (orderCountByPerformer.get(right.id) ?? 0)
        return countDifference || left.name.localeCompare(right.name, 'zh-CN')
      }),
    [performers.data, selectedLeaderId, studentStatusFilter, orderCountByPerformer],
  )

  const refreshPeople = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['contractors'] }),
      queryClient.invalidateQueries({ queryKey: ['performers'] }),
      queryClient.invalidateQueries({ queryKey: ['point-accounts'] }),
      queryClient.invalidateQueries({ queryKey: ['point-pending-orders'] }),
    ])
  }

  const createRetail = useMutation({
    mutationFn: (values: { name: string; contact?: string; note?: string }) => api.post('/partners/contractors', {
      ...values,
      contractor_type: 'RETAIL',
      default_commission: 0,
      effective_date: dayjs().format('YYYY-MM-DD'),
    }),
    onSuccess: async () => {
      message.success('散户已添加')
      setRetailOpen(false)
      retailForm.resetFields()
      await refreshPeople()
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const createStudent = useMutation({
    mutationFn: (values: { name: string; note?: string }) => {
      if (selectedLeaderId == null) throw new Error('missing leader')
      return api.post('/partners/performers', {
        ...values,
        performer_type: 'STUDENT',
        contractor_id: selectedLeaderId,
        is_listed: true,
      })
    },
    onSuccess: async () => {
      message.success('实际做单学生已添加')
      setStudentOpen(false)
      studentForm.resetFields()
      await refreshPeople()
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const updatePerson = useMutation({
    mutationFn: (values: { name: string; contact?: string; note?: string }) => {
      if (!editTarget) throw new Error('missing edit target')
      if (editTarget.kind === 'retail') {
        return api.patch(`/partners/contractors/${editTarget.contractor.id}`, values)
      }
      return api.patch(`/partners/performers/${editTarget.performer.id}`, {
        name: values.name,
        note: values.note,
      })
    },
    onSuccess: async () => {
      message.success('人员信息已更新')
      setEditTarget(undefined)
      editForm.resetFields()
      await refreshPeople()
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const toggleRetail = (contractor: Contractor) => {
    const nextActive = !contractor.is_active
    modal.confirm({
      title: `${nextActive ? '启用' : '停用'}散户「${contractor.name}」？`,
      content: nextActive ? '启用后可在新订单中选择。' : '停用后不能用于新订单，历史订单和积分不受影响。',
      okText: nextActive ? '启用' : '停用',
      okButtonProps: nextActive ? undefined : { danger: true },
      onOk: async () => {
        await api.patch(`/partners/contractors/${contractor.id}`, { is_active: nextActive })
        message.success(nextActive ? '散户已启用' : '散户已停用')
        await refreshPeople()
      },
    })
  }

  const toggleStudent = (performer: Performer) => {
    const nextActive = !performer.is_active
    modal.confirm({
      title: `${nextActive ? '启用' : '停用'}学生「${performer.name}」？`,
      content: nextActive ? '启用后可在新订单中选择。' : '停用后不能用于新订单，历史订单和积分不受影响。',
      okText: nextActive ? '启用' : '停用',
      okButtonProps: nextActive ? undefined : { danger: true },
      onOk: async () => {
        await api.patch(`/partners/performers/${performer.id}`, { is_active: nextActive })
        message.success(nextActive ? '学生已启用' : '学生已停用')
        await refreshPeople()
      },
    })
  }

  const redeem = (performerId: number, name: string, account?: PointAccount) => {
    if (!account || account.available_coupons < 1) {
      message.warning('当前积分不足 600，不能兑换')
      return
    }
    modal.confirm({
      title: `为「${name}」兑换 30 元优惠券？`,
      content: `将扣除 600 积分，兑换后预计剩余 ${Number(account.balance) - 600} 积分。请确认已提醒做单人员并完成手动兑换。`,
      okText: '确认已兑换',
      onOk: async () => {
        try {
          const response = await api.post<{ balance: string }>(`/points/performers/${performerId}/redeem`, {})
          message.success(`兑换已记录，剩余 ${response.data.balance} 积分`)
          await refreshPeople()
        } catch (error) {
          message.error(errorMessage(error))
          throw error
        }
      },
    })
  }

  const pointsCell = (performerId?: number) => {
    const account = performerId == null ? undefined : accountByPerformer.get(performerId)
    if (!account) return '0'
    return (
      <Space size={6}>
        <Typography.Text strong>{account.balance}</Typography.Text>
        {account.available_coupons > 0 && <Tag color="warning">可兑 {account.available_coupons} 张</Tag>}
      </Space>
    )
  }

  const openEditRetail = (contractor: Contractor) => {
    setEditTarget({ kind: 'retail', contractor })
    editForm.setFieldsValue({ name: contractor.name, contact: contractor.contact, note: contractor.note })
  }

  const openEditStudent = (performer: Performer) => {
    setEditTarget({ kind: 'student', performer })
    editForm.setFieldsValue({ name: performer.name, note: performer.note })
  }

  return (
    <Card title="实际做单人员与积分">
      <Tabs items={[
        {
          key: 'retail',
          label: `散户 ${retailRows.length}`,
          children: (
            <>
              <div className="table-toolbar">
                <Space wrap>
                  <Select
                    value={retailStatusFilter}
                    onChange={setRetailStatusFilter}
                    options={performerStatusFilterOptions}
                    style={{ width: 120 }}
                  />
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => setRetailOpen(true)}>新增散户</Button>
                </Space>
              </div>
              <Table<Contractor>
                rowKey="id"
                loading={retails.isLoading || performers.isLoading || accounts.isLoading || orderStats.isLoading}
                dataSource={retailRows}
                pagination={false}
                columns={[
                  { title: '姓名', dataIndex: 'name', render: (value) => <strong>{value}</strong> },
                  { title: '记录时间', dataIndex: 'created_at', width: 170, render: dateTime },
                  { title: '联系方式', dataIndex: 'contact', render: (value) => value || '—' },
                  {
                    title: '状态', dataIndex: 'is_active', width: 90,
                    render: (value) => value ? <Tag color="success">正常</Tag> : <Tag>停用</Tag>,
                  },
                  {
                    title: '当前积分', width: 180,
                    render: (_, contractor) => pointsCell(retailPerformerByContractor.get(contractor.id)?.id),
                  },
                  {
                    title: '做单次数', width: 100, align: 'right',
                    render: (_, contractor) => {
                      const performer = retailPerformerByContractor.get(contractor.id)
                      return performer ? orderCountByPerformer.get(performer.id) ?? 0 : 0
                    },
                  },
                  { title: '备注', dataIndex: 'note', render: (value) => value || '—' },
                  {
                    title: '操作', width: 380,
                    render: (_, contractor) => {
                      const performer = retailPerformerByContractor.get(contractor.id)
                      const account = performer ? accountByPerformer.get(performer.id) : undefined
                      return (
                        <Space wrap>
                          <Button icon={<EyeOutlined />} disabled={!performer} onClick={() => performer && setDetailTarget(performer)}>详情</Button>
                          <Button icon={<EditOutlined />} onClick={() => openEditRetail(contractor)}>编辑</Button>
                          <Button
                            icon={<GiftOutlined />}
                            disabled={!account?.available_coupons}
                            onClick={() => performer && redeem(performer.id, performer.name, account)}
                          >兑换</Button>
                          <Button danger={contractor.is_active} icon={<StopOutlined />} onClick={() => toggleRetail(contractor)}>
                            {contractor.is_active ? '停用' : '启用'}
                          </Button>
                        </Space>
                      )
                    },
                  },
                ]}
              />
            </>
          ),
        },
        {
          key: 'students',
          label: `实际学生 ${students.length}`,
          children: (
            <>
              <div className="table-toolbar">
                <Space wrap>
                  <Select
                    showSearch
                    optionFilterProp="label"
                    value={selectedLeaderId}
                    onChange={setSelectedLeaderId}
                    placeholder="选择学生头子"
                    style={{ width: 220 }}
                    options={(leaders.data ?? []).map((item) => ({
                      value: item.id,
                      label: `${item.name}${!item.is_active ? '（停用）' : ''}`,
                    }))}
                  />
                  <Select
                    value={studentStatusFilter}
                    onChange={setStudentStatusFilter}
                    options={performerStatusFilterOptions}
                    style={{ width: 120 }}
                  />
                  <Button type="primary" icon={<PlusOutlined />} disabled={!selectedLeaderId} onClick={() => setStudentOpen(true)}>
                    添加实际学生
                  </Button>
                </Space>
              </div>
              <Table<Performer>
                rowKey="id"
                loading={performers.isLoading || accounts.isLoading || orderStats.isLoading}
                dataSource={students}
                pagination={false}
                locale={{ emptyText: selectedLeaderId ? '该学生头子名下暂无学生' : '请先选择学生头子' }}
                columns={[
                  { title: '学生姓名', dataIndex: 'name', render: (value) => <strong>{value}</strong> },
                  { title: '记录时间', dataIndex: 'created_at', width: 170, render: dateTime },
                  {
                    title: '状态', dataIndex: 'is_active', width: 90,
                    render: (value) => value ? <Tag color="success">正常</Tag> : <Tag>停用</Tag>,
                  },
                  { title: '当前积分', width: 180, render: (_, performer) => pointsCell(performer.id) },
                  { title: '做单次数', width: 100, align: 'right', render: (_, performer) => orderCountByPerformer.get(performer.id) ?? 0 },
                  { title: '备注', dataIndex: 'note', render: (value) => value || '—' },
                  {
                    title: '操作', width: 380,
                    render: (_, performer) => {
                      const account = accountByPerformer.get(performer.id)
                      return (
                        <Space wrap>
                          <Button icon={<EyeOutlined />} onClick={() => setDetailTarget(performer)}>详情</Button>
                          <Button icon={<EditOutlined />} onClick={() => openEditStudent(performer)}>编辑</Button>
                          <Button
                            icon={<GiftOutlined />}
                            disabled={!account?.available_coupons}
                            onClick={() => redeem(performer.id, performer.name, account)}
                          >兑换</Button>
                          <Button danger={performer.is_active} icon={<StopOutlined />} onClick={() => toggleStudent(performer)}>
                            {performer.is_active ? '停用' : '启用'}
                          </Button>
                        </Space>
                      )
                    },
                  },
                ]}
              />
            </>
          ),
        },
        {
          key: 'pending',
          label: `待补做单人 ${pendingOrders.data?.length ?? 0}`,
          children: (
            <Table<PendingPointOrder>
              rowKey="id"
              loading={pendingOrders.isLoading}
              dataSource={pendingOrders.data ?? []}
              pagination={false}
              locale={{ emptyText: '没有缺少实际做单人的成功订单' }}
              columns={[
                { title: '业务日期', dataIndex: 'business_date' },
                { title: '记录时间', dataIndex: 'created_at', width: 170, render: dateTime },
                { title: '订单号', dataIndex: 'order_no', render: (value) => <span className="mono">{value}</span> },
                { title: '学生头子', dataIndex: 'contractor_name' },
                { title: '订单原价', dataIndex: 'order_amount' },
                {
                  title: '处理', width: 120,
                  render: () => <Button onClick={() => navigate('/orders')}>前往补充</Button>,
                },
              ]}
            />
          ),
        },
      ]} />

      <Modal
        title="新增散户"
        open={retailOpen}
        onCancel={() => setRetailOpen(false)}
        onOk={() => retailForm.submit()}
        confirmLoading={createRetail.isPending}
      >
        <Form form={retailForm} layout="vertical" requiredMark={false} onFinish={(values) => createRetail.mutate(values)}>
          <Form.Item name="name" label="姓名" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
          <Form.Item name="contact" label="联系方式"><Input /></Form.Item>
          <Form.Item name="note" label="备注"><Input.TextArea /></Form.Item>
        </Form>
      </Modal>

      <Modal
        title="添加实际做单学生"
        open={studentOpen}
        onCancel={() => setStudentOpen(false)}
        onOk={() => studentForm.submit()}
        confirmLoading={createStudent.isPending}
      >
        <Form form={studentForm} layout="vertical" requiredMark={false} onFinish={(values) => createStudent.mutate(values)}>
          <Form.Item name="name" label="学生姓名" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
          <Form.Item name="note" label="备注"><Input.TextArea /></Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editTarget?.kind === 'retail' ? '编辑散户' : '编辑实际学生'}
        open={Boolean(editTarget)}
        onCancel={() => { setEditTarget(undefined); editForm.resetFields() }}
        onOk={() => editForm.submit()}
        confirmLoading={updatePerson.isPending}
      >
        <Form form={editForm} layout="vertical" requiredMark={false} onFinish={(values) => updatePerson.mutate(values)}>
          <Form.Item name="name" label="姓名" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
          {editTarget?.kind === 'retail' && <Form.Item name="contact" label="联系方式"><Input /></Form.Item>}
          <Form.Item name="note" label="备注"><Input.TextArea /></Form.Item>
        </Form>
      </Modal>
      <Drawer
        title={detailTarget ? `做单记录 · ${detailTarget.name}` : '做单记录'}
        width={860}
        open={Boolean(detailTarget)}
        onClose={() => setDetailTarget(undefined)}
        destroyOnHidden
      >
        <Table<Order>
          rowKey="id"
          loading={detailOrders.isLoading}
          dataSource={detailOrders.data ?? []}
          pagination={{ pageSize: 15 }}
          scroll={{ x: 900 }}
          locale={{ emptyText: '暂无成功做单记录' }}
          columns={[
            { title: '业务日期', dataIndex: 'business_date', width: 110 },
            { title: '记录时间', dataIndex: 'created_at', width: 170, render: dateTime },
            { title: '订单号', dataIndex: 'order_no', width: 180, render: (value) => <span className="mono">{value}</span> },
            { title: '做单方', dataIndex: 'contractor_name', width: 130 },
            { title: '放单人员', dataIndex: 'source_name', width: 130 },
            { title: '标价', dataIndex: 'order_amount', align: 'right', width: 110, render: (value) => <Money value={value} /> },
            { title: '优惠金额', dataIndex: 'coupon_amount', align: 'right', width: 110, render: (value) => <Money value={value} /> },
            { title: '实付', dataIndex: 'actual_paid', align: 'right', width: 110, render: (value) => <Money value={value} /> },
            { title: '佣金', dataIndex: 'commission', align: 'right', width: 100, render: (value) => <Money value={value} /> },
            { title: '利润', dataIndex: 'profit', align: 'right', width: 110, render: (value) => <Money value={value} signed /> },
          ]}
        />
      </Drawer>
    </Card>
  )
}
