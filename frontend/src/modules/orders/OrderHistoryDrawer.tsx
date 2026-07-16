import { useQuery } from '@tanstack/react-query'
import { Drawer, Empty, Spin, Table, Tag, Typography } from 'antd'
import { api } from '../../shared/api'
import { dateTime } from '../../shared/format'
import type { OrderHistoryItem } from '../../shared/types'

const actionText: Record<string, string> = {
  'order.created': '创建订单',
  'order.updated': '修改订单',
  'order.status_changed': '变更订单状态',
}

export function OrderHistoryDrawer({
  open,
  orderId,
  orderNo,
  onClose,
}: {
  open: boolean
  orderId?: number
  orderNo?: string
  onClose: () => void
}) {
  const history = useQuery({
    queryKey: ['order-history', orderId],
    queryFn: () => api.get<OrderHistoryItem[]>(`/orders/${orderId}/history`).then((res) => res.data),
    enabled: open && Boolean(orderId),
  })

  return (
    <Drawer
      title={`订单历史 · ${orderNo ?? ''}`}
      width={560}
      open={open}
      onClose={onClose}
      destroyOnHidden
    >
      {history.isLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>
      ) : !history.data?.length ? (
        <Empty description="暂无创建或编辑记录" />
      ) : (
        <Table<OrderHistoryItem>
          rowKey="id"
          size="small"
          pagination={false}
          dataSource={history.data}
          columns={[
            { title: '时间', dataIndex: 'created_at', width: 150, render: dateTime },
            {
              title: '操作',
              dataIndex: 'action',
              width: 120,
              render: (value: string) => <Tag>{actionText[value] ?? value}</Tag>,
            },
            {
              title: '操作者',
              width: 100,
              render: (_, item) => item.user_name || (item.user_id ? `#${item.user_id}` : '系统'),
            },
            {
              title: '详情',
              dataIndex: 'payload',
              render: (value) => (
                value
                  ? <Typography.Text code className="audit-payload">{JSON.stringify(value)}</Typography.Text>
                  : '—'
              ),
            },
          ]}
        />
      )}
    </Drawer>
  )
}
