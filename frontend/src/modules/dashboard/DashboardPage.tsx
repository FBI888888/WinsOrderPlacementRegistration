import { PlusOutlined, WarningOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Col, DatePicker, Empty, Row, Space, Statistic, Table, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../shared/api'
import { Money, PageTitle, StatusTag } from '../../shared/components'
import { currency } from '../../shared/format'
import type { DashboardSummary, Order } from '../../shared/types'

const { RangePicker } = DatePicker

export function DashboardPage() {
  const navigate = useNavigate()
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs(), dayjs()])
  const params = { date_from: range[0].format('YYYY-MM-DD'), date_to: range[1].format('YYYY-MM-DD') }
  const summary = useQuery({
    queryKey: ['dashboard', params],
    queryFn: () => api.get<DashboardSummary>('/reports/dashboard', { params }).then((res) => res.data),
  })
  const recent = useQuery({
    queryKey: ['orders', 'dashboard'],
    queryFn: () => api.get<{ items: Order[] }>('/orders', { params: { page_size: 8 } }).then((res) => res.data.items),
  })
  const data = summary.data

  return (
    <div className="page-stack">
      <PageTitle
        title="经营概览"
        description="收入与利润按成功订单确认；垫资只反映现金余额，不重复计入成本。"
        extra={
          <Space wrap>
            <RangePicker value={range} onChange={(value) => value && setRange(value as [Dayjs, Dayjs])} />
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/orders?new=1')}>快速录单</Button>
          </Space>
        }
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} xl={6}>
          <Card className="metric-card"><Statistic title="成功订单" value={data?.success_count ?? 0} suffix={`/ ${data?.order_count ?? 0} 单`} /></Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card className="metric-card"><Statistic title="结算收入" value={data?.settlement_income ?? 0} formatter={(value) => currency(Number(value))} /></Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card className="metric-card"><Statistic title="订单成本" value={data?.cost ?? 0} formatter={(value) => currency(Number(value))} /></Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card className="metric-card accent"><Statistic title="期间利润" value={data?.profit ?? 0} valueStyle={{ color: Number(data?.profit ?? 0) < 0 ? '#b7473a' : '#315c4c' }} formatter={(value) => currency(Number(value))} /></Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card title="最近订单" extra={<Button type="link" onClick={() => navigate('/orders')}>查看全部</Button>}>
            <Table<Order>
              rowKey="id"
              size="middle"
              loading={recent.isLoading}
              dataSource={recent.data}
              pagination={false}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有订单" /> }}
              columns={[
                { title: '日期', dataIndex: 'business_date', width: 110 },
                { title: '放单人员', dataIndex: 'source_name' },
                { title: '做单方', dataIndex: 'contractor_name' },
                { title: '状态', dataIndex: 'status', render: (value) => <StatusTag value={value} /> },
                { title: '利润', dataIndex: 'profit', align: 'right', render: (value) => <Money value={value} signed /> },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="当前往来余额" className="balance-card">
            <div><Typography.Text>可用垫资</Typography.Text><Money value={data?.advance_balance ?? 0} signed /></div>
            <div><Typography.Text>待付佣金</Typography.Text><Money value={data?.commission_payable ?? 0} /></div>
            <div><Typography.Text>放单应收</Typography.Text><Money value={data?.source_receivable ?? 0} /></div>
            <div className="warning-line">
              <WarningOutlined />
              <span>期间负利润订单</span>
              <strong>{data?.negative_profit_count ?? 0} 单</strong>
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  )
}