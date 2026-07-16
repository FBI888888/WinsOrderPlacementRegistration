import { PlusOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Form, Input, Modal, Select, Space, Switch, Table, Tag } from 'antd'
import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { api, errorMessage } from '../../shared/api'
import { useAuth } from '../../shared/auth-context'
import { PageTitle } from '../../shared/components'
import { dateTime, roleText } from '../../shared/format'
import type { Member, Role } from '../../shared/types'

export function TeamPage() {
  const { me } = useAuth()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()
  const members = useQuery({ queryKey: ['members'], queryFn: () => api.get<Member[]>('/auth/members').then((res) => res.data), enabled: me?.role === 'OWNER' })
  const createMutation = useMutation({
    mutationFn: (values: Record<string, unknown>) => api.post('/auth/members', values),
    onSuccess: async () => { message.success('成员已加入账套'); setOpen(false); form.resetFields(); await queryClient.invalidateQueries({ queryKey: ['members'] }) },
    onError: (error) => message.error(errorMessage(error)),
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, values }: { id: number; values: Record<string, unknown> }) => api.patch(`/auth/members/${id}`, values),
    onSuccess: async () => { message.success('成员权限已更新'); await queryClient.invalidateQueries({ queryKey: ['members'] }) },
    onError: (error) => message.error(errorMessage(error)),
  })

  if (me?.role !== 'OWNER') return <Navigate to="/" replace />

  return (
    <div className="page-stack">
      <PageTitle title="成员权限" description="成员在当前账套内协作，不同账套之间的数据始终隔离。" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>添加成员</Button>} />
      <Card>
        <Table<Member> rowKey="id" dataSource={members.data} loading={members.isLoading} pagination={false} columns={[
          { title: '成员', render: (_, item) => <Space direction="vertical" size={0}><strong>{item.name}</strong><span className="subtle">{item.email}</span></Space> },
          { title: '角色', dataIndex: 'role', render: (value: Role, item) => item.user_id === me.user_id ? <Tag color="green">{roleText[value]} · 当前账号</Tag> : <Select value={value} style={{ width: 120 }} onChange={(role) => updateMutation.mutate({ id: item.id, values: { role } })} options={[{ value: 'OWNER', label: '负责人' }, { value: 'BOOKKEEPER', label: '记账员' }, { value: 'VIEWER', label: '只读成员' }]} /> },
          { title: '状态', dataIndex: 'is_active', render: (value, item) => <Switch checked={value} disabled={item.user_id === me.user_id} checkedChildren="启用" unCheckedChildren="停用" onChange={(is_active) => updateMutation.mutate({ id: item.id, values: { is_active } })} /> },
          { title: '加入时间', dataIndex: 'created_at', render: dateTime },
        ]} />
      </Card>
      <Modal title="添加账套成员" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={createMutation.isPending}>
        <Form form={form} layout="vertical" requiredMark={false} onFinish={(values) => createMutation.mutate(values)} initialValues={{ role: 'BOOKKEEPER' }}>
          <Form.Item name="name" label="姓名" rules={[{ required: true, min: 2 }]}><Input /></Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email' }]}><Input /></Form.Item>
          <Form.Item name="password" label="初始密码" rules={[{ required: true, min: 8 }]}><Input.Password placeholder="成员首次登录使用" /></Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}><Select options={[{ value: 'BOOKKEEPER', label: '记账员：可录单、记资金和结算' }, { value: 'VIEWER', label: '只读成员：只查看和导出' }, { value: 'OWNER', label: '负责人：全部权限' }]} /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}