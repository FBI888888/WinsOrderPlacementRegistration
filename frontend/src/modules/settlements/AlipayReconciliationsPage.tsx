import { PlusOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, DatePicker, Input, InputNumber, Modal, Space, Table, Tag } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { api, errorMessage } from '../../shared/api'
import { useAuth } from '../../shared/auth-context'
import { Money, PageTitle } from '../../shared/components'
import { dateTime } from '../../shared/format'
import type { AlipayAccount, AlipayReconciliation, ReconciliationItem } from '../../shared/types'

const statusText = { DRAFT: '草稿', CONFIRMED: '已确认', REVERSED: '已冲正' }

export function AlipayReconciliationsPage() {
  const { message } = App.useApp()
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [businessDate, setBusinessDate] = useState(dayjs())
  const [note, setNote] = useState('')
  const [actual, setActual] = useState<Record<number, number>>({})
  const accounts = useQuery({ queryKey: ['alipay-accounts', 'reconciliation'], queryFn: () => api.get<AlipayAccount[]>('/alipay-pool/accounts').then((res) => res.data) })
  const reconciliations = useQuery({ queryKey: ['alipay-reconciliations'], queryFn: () => api.get<AlipayReconciliation[]>('/alipay-pool/reconciliations').then((res) => res.data) })
  const canWrite = me?.role === 'OWNER' || me?.role === 'BOOKKEEPER'

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['alipay-reconciliations'] }),
      queryClient.invalidateQueries({ queryKey: ['alipay-accounts'] }),
      queryClient.invalidateQueries({ queryKey: ['jijihong-funds'] }),
      queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
    ])
  }
  const createMutation = useMutation({
    mutationFn: () => api.post('/alipay-pool/reconciliations', {
      business_date: businessDate.format('YYYY-MM-DD'),
      note: note.trim() || null,
      items: (accounts.data ?? []).map((account) => ({ account_id: account.id, actual_balance: actual[account.id] ?? Number(account.current_balance) })),
    }),
    onSuccess: async () => { message.success('盘点草稿已创建'); setOpen(false); await refresh() },
    onError: (error) => message.error(errorMessage(error, '盘点草稿创建失败')),
  })
  const confirmMutation = useMutation({
    mutationFn: (id: number) => api.post(`/alipay-pool/reconciliations/${id}/confirm`),
    onSuccess: async () => { message.success('盘点已确认，差异流水已追加'); await refresh() },
    onError: (error) => message.error(errorMessage(error, '确认失败；如系统余额已变化，请重新创建盘点草稿')),
  })
  const reverseMutation = useMutation({
    mutationFn: (id: number) => api.post(`/alipay-pool/reconciliations/${id}/reverse`),
    onSuccess: async () => { message.success('盘点已冲正'); await refresh() },
    onError: (error) => message.error(errorMessage(error, '盘点冲正失败')),
  })

  const openCreate = () => {
    setBusinessDate(dayjs())
    setNote('')
    setActual(Object.fromEntries((accounts.data ?? []).map((account) => [account.id, Number(account.current_balance)])))
    setOpen(true)
  }

  return <div className="page-stack">
    <PageTitle
      title="账号对账"
      description="先保存盘点草稿，再锁定账号确认差异；确认和冲正只追加账本流水，不覆盖历史。"
      extra={canWrite && <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>创建盘点</Button>}
    />
    <Card>
      <Table<AlipayReconciliation>
        rowKey="id"
        loading={reconciliations.isLoading}
        dataSource={reconciliations.data ?? []}
        expandable={{
          expandedRowRender: (row) => <Table<ReconciliationItem> rowKey="id" pagination={false} dataSource={row.items} columns={[
            { title: '设备', dataIndex: 'device_name' }, { title: '账号', dataIndex: 'account_alias' },
            { title: '系统余额快照', dataIndex: 'system_balance_snapshot', align: 'right', render: (value) => <Money value={value} /> },
            { title: '实际余额', dataIndex: 'actual_balance', align: 'right', render: (value) => <Money value={value} /> },
            { title: '差异', dataIndex: 'difference', align: 'right', render: (value) => <Money value={value} signed /> },
            { title: '原因', dataIndex: 'reason', render: (value) => value || '—' },
          ]} />,
        }}
        columns={[
          { title: '业务日期', dataIndex: 'business_date' },
          { title: '创建时间', dataIndex: 'created_at', render: dateTime },
          { title: '账号数', dataIndex: 'items', render: (items: ReconciliationItem[]) => items.length },
          { title: '总差异', dataIndex: 'items', align: 'right', render: (items: ReconciliationItem[]) => <Money value={items.reduce((sum, item) => sum + Number(item.difference), 0)} signed /> },
          { title: '状态', dataIndex: 'status', render: (value: keyof typeof statusText) => <Tag>{statusText[value]}</Tag> },
          { title: '备注', dataIndex: 'note', render: (value) => value || '—' },
          {
            title: '操作', render: (_, row) => canWrite && <Space>
              {row.status === 'DRAFT' && <Button type="link" loading={confirmMutation.isPending} onClick={() => confirmMutation.mutate(row.id)}>确认盘点</Button>}
              {row.status === 'CONFIRMED' && <Button danger type="link" loading={reverseMutation.isPending} onClick={() => reverseMutation.mutate(row.id)}>冲正</Button>}
            </Space>,
          },
        ]}
      />
    </Card>
    <Modal title="创建账号盘点草稿" width={760} open={open} onCancel={() => setOpen(false)} onOk={() => createMutation.mutate()} confirmLoading={createMutation.isPending} okText="保存草稿">
      <Space direction="vertical" className="full-width" size="middle">
        <Space><span>业务日期</span><DatePicker value={businessDate} onChange={(value) => value && setBusinessDate(value)} /></Space>
        <Input.TextArea placeholder="盘点备注（可选）" value={note} onChange={(event) => setNote(event.target.value)} />
        <Table<AlipayAccount> rowKey="id" pagination={{ pageSize: 10 }} dataSource={accounts.data ?? []} columns={[
          { title: '设备', dataIndex: 'device_name' }, { title: '账号', dataIndex: 'alias' },
          { title: '系统余额', dataIndex: 'current_balance', align: 'right', render: (value) => <Money value={value} /> },
          { title: '实际余额', render: (_, account) => <InputNumber min={0} precision={2} value={actual[account.id]} onChange={(value) => setActual((rows) => ({ ...rows, [account.id]: Number(value ?? 0) }))} /> },
          { title: '差异', align: 'right', render: (_, account) => <Money value={(actual[account.id] ?? Number(account.current_balance)) - Number(account.current_balance)} signed /> },
        ]} />
      </Space>
    </Modal>
  </div>
}
