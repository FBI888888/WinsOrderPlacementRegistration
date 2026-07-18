import { DownloadOutlined, EyeOutlined, FileExcelOutlined, SaveOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Checkbox, Col, DatePicker, Drawer, Form, Input, Radio, Row, Space, Statistic, Table, Tabs, Tag, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { api, errorMessage } from '../../shared/api'
import { Money, PageTitle } from '../../shared/components'
import { currency, dateTime } from '../../shared/format'
import type { Order, PerformanceDailyRow, PerformanceGroupRow, PerformanceReport } from '../../shared/types'

interface ExportField { value: string; label: string }
interface ExportTemplate { id: number; name: string; fields: string[]; filters?: Record<string, unknown>; created_at: string }
interface ExportLog { id: number; export_format: string; fields: string[]; row_count: number; file_hash: string; created_at: string }
interface DetailTarget { row: PerformanceGroupRow; filterKey: 'source_id' | 'contractor_id' | 'performer_id' }

type GroupRows = PerformanceGroupRow[]

const groupColumns = (onDetail: (row: PerformanceGroupRow) => void) => [
  { title: '名称', dataIndex: 'entity_name', width: 150, render: (value: string) => <strong>{value}</strong> },
  { title: '成功单量', dataIndex: 'order_count', width: 100, align: 'right' as const },
  { title: '营业额', dataIndex: 'order_amount', width: 120, align: 'right' as const, render: (value: string) => <Money value={value} /> },
  { title: '优惠总额', dataIndex: 'coupon_amount', width: 120, align: 'right' as const, render: (value: string) => <Money value={value} /> },
  { title: '实付总额', dataIndex: 'actual_paid', width: 120, align: 'right' as const, render: (value: string) => <Money value={value} /> },
  { title: '结算收入', dataIndex: 'settlement_income', width: 120, align: 'right' as const, render: (value: string) => <Money value={value} /> },
  { title: '成本', dataIndex: 'cost', width: 110, align: 'right' as const, render: (value: string) => <Money value={value} /> },
  { title: '佣金', dataIndex: 'commission', width: 100, align: 'right' as const, render: (value: string) => <Money value={value} /> },
  { title: '利润', dataIndex: 'profit', width: 120, align: 'right' as const, render: (value: string) => <Money value={value} signed /> },
  {
    title: '操作', fixed: 'right' as const, width: 90,
    render: (_: unknown, row: PerformanceGroupRow) => <Button type="link" icon={<EyeOutlined />} onClick={() => onDetail(row)}>详情</Button>,
  },
]

const dailyColumns = (onDetail: (row: PerformanceDailyRow) => void) => [
  { title: '日期', dataIndex: 'business_date', width: 120, fixed: 'left' as const },
  { title: '成功单量', dataIndex: 'order_count', width: 100, align: 'right' as const },
  { title: '营业额', dataIndex: 'order_amount', width: 120, align: 'right' as const, render: (value: string) => <Money value={value} /> },
  { title: '优惠总额', dataIndex: 'coupon_amount', width: 120, align: 'right' as const, render: (value: string) => <Money value={value} /> },
  { title: '实付总额', dataIndex: 'actual_paid', width: 120, align: 'right' as const, render: (value: string) => <Money value={value} /> },
  { title: '结算收入', dataIndex: 'settlement_income', width: 120, align: 'right' as const, render: (value: string) => <Money value={value} /> },
  { title: '成本', dataIndex: 'cost', width: 110, align: 'right' as const, render: (value: string) => <Money value={value} /> },
  { title: '佣金', dataIndex: 'commission', width: 100, align: 'right' as const, render: (value: string) => <Money value={value} /> },
  { title: '利润', dataIndex: 'profit', width: 120, align: 'right' as const, render: (value: string) => <Money value={value} signed /> },
  { title: '负利润单量', dataIndex: 'negative_profit_count', width: 110, align: 'right' as const },
  {
    title: '操作', fixed: 'right' as const, width: 90,
    render: (_: unknown, row: PerformanceDailyRow) => <Button type="link" icon={<EyeOutlined />} onClick={() => onDetail(row)}>详情</Button>,
  },
]

function PerformanceGroupTable({ rows, onDetail }: { rows: GroupRows; onDetail: (row: PerformanceGroupRow) => void }) {
  return (
    <Table<PerformanceGroupRow>
      rowKey={(row) => `${row.group_type}-${row.entity_id}`}
      dataSource={rows}
      pagination={{ pageSize: 10 }}
      scroll={{ x: 1200 }}
      locale={{ emptyText: '当前期间暂无成功订单' }}
      columns={groupColumns(onDetail)}
    />
  )
}

function OrderDetailTable({ orders, loading }: { orders: Order[]; loading: boolean }) {
  return (
    <Table<Order>
      rowKey="id"
      dataSource={orders}
      loading={loading}
      pagination={{ pageSize: 15 }}
      scroll={{ x: 1250 }}
      locale={{ emptyText: '暂无订单明细' }}
      columns={[
        { title: '日期', dataIndex: 'business_date', width: 110 },
        { title: '订单号', dataIndex: 'order_no', width: 180, render: (value) => <span className="mono">{value}</span> },
        { title: '放单人员', dataIndex: 'source_name', width: 130 },
        { title: '做单方', dataIndex: 'contractor_name', width: 140 },
        { title: '实际做单人', dataIndex: 'performer_name', width: 130, render: (value) => value || '待补' },
        { title: '标价', dataIndex: 'order_amount', align: 'right', width: 110, render: (value) => <Money value={value} /> },
        { title: '优惠金额', dataIndex: 'coupon_amount', align: 'right', width: 110, render: (value) => <Money value={value} /> },
        { title: '实付', dataIndex: 'actual_paid', align: 'right', width: 110, render: (value) => <Money value={value} /> },
        { title: '结算收入', dataIndex: 'settlement_income', align: 'right', width: 120, render: (value) => <Money value={value} /> },
        { title: '佣金', dataIndex: 'commission', align: 'right', width: 100, render: (value) => <Money value={value} /> },
        { title: '利润', dataIndex: 'profit', align: 'right', width: 110, render: (value) => <Money value={value} signed /> },
      ]}
    />
  )
}

export function ReportsPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs(), dayjs()])
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailTarget, setDetailTarget] = useState<DetailTarget>()
  const [dailyDate, setDailyDate] = useState<string>()
  const [exportOpen, setExportOpen] = useState(false)
  const [format, setFormat] = useState('xlsx')
  const [fields, setFields] = useState<string[]>([])
  const [templateName, setTemplateName] = useState('')
  const [downloading, setDownloading] = useState(false)

  const params = useMemo(() => ({
    date_from: range[0].format('YYYY-MM-DD'),
    date_to: range[1].format('YYYY-MM-DD'),
  }), [range])
  const report = useQuery({
    queryKey: ['performance-report', params],
    queryFn: () => api.get<PerformanceReport>('/reports/performance', { params }).then((res) => res.data),
  })
  const dailyReport = useQuery({
    queryKey: ['daily-performance-report'],
    queryFn: () => api.get<PerformanceDailyRow[]>('/reports/performance/daily').then((res) => res.data),
  })
  const detailParams = useMemo(() => {
    if (!detailTarget) return undefined
    return {
      ...params,
      status: 'SUCCESS',
      page_size: 200,
      [detailTarget.filterKey]: detailTarget.row.entity_id,
    }
  }, [detailTarget, params])
  const detailOrders = useQuery({
    queryKey: ['performance-detail-orders', detailParams],
    queryFn: () => api.get<{ items: Order[] }>('/orders', { params: detailParams }).then((res) => res.data.items),
    enabled: Boolean(detailParams),
  })
  const dailyDetailParams = useMemo(() => dailyDate ? {
    date_from: dailyDate,
    date_to: dailyDate,
    status: 'SUCCESS',
    page_size: 200,
  } : undefined, [dailyDate])
  const dailyDetailOrders = useQuery({
    queryKey: ['daily-performance-detail-orders', dailyDetailParams],
    queryFn: () => api.get<{ items: Order[] }>('/orders', { params: dailyDetailParams }).then((res) => res.data.items),
    enabled: Boolean(dailyDetailParams),
  })

  const fieldOptions = useQuery({
    queryKey: ['export-fields'],
    queryFn: () => api.get<ExportField[]>('/reports/export-fields').then((res) => res.data),
  })
  const templates = useQuery({
    queryKey: ['export-templates'],
    queryFn: () => api.get<ExportTemplate[]>('/reports/templates').then((res) => res.data),
  })
  const logs = useQuery({
    queryKey: ['export-logs'],
    queryFn: () => api.get<ExportLog[]>('/reports/export-logs').then((res) => res.data),
    enabled: exportOpen,
  })

  useEffect(() => {
    if (fields.length === 0 && fieldOptions.data?.length) {
      setFields(fieldOptions.data.map((item) => item.value))
    }
  }, [fieldOptions.data, fields.length])

  const saveTemplate = useMutation({
    mutationFn: () => api.post('/reports/templates', { name: templateName, fields, filters: { status: 'SUCCESS' } }),
    onSuccess: async () => {
      message.success('导出模板已保存')
      setTemplateName('')
      await queryClient.invalidateQueries({ queryKey: ['export-templates'] })
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const download = async () => {
    if (!fields.length) {
      message.warning('至少选择一个导出字段')
      return
    }
    setDownloading(true)
    try {
      const exportParams = new URLSearchParams({
        export_format: format,
        date_from: params.date_from,
        date_to: params.date_to,
        status: 'SUCCESS',
      })
      fields.forEach((field) => exportParams.append('fields', field))
      const response = await api.get('/reports/orders/export', { params: exportParams, responseType: 'blob' })
      const url = URL.createObjectURL(response.data)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `业绩报表-${dayjs().format('YYYYMMDD-HHmm')}.${format}`
      anchor.click()
      URL.revokeObjectURL(url)
      message.success('报表已生成')
      await queryClient.invalidateQueries({ queryKey: ['export-logs'] })
    } catch (error) {
      message.error(errorMessage(error, '导出失败'))
    } finally {
      setDownloading(false)
    }
  }

  const openDetail = (row: PerformanceGroupRow) => {
    const filterKey = row.group_type === 'source'
      ? 'source_id'
      : row.group_type === 'performer' ? 'performer_id' : 'contractor_id'
    setDetailTarget({ row, filterKey })
  }
  const data = report.data
  const summary = data?.summary
  const groupTabs = [
    { key: 'sources', label: '放单人员', children: <PerformanceGroupTable rows={data?.sources ?? []} onDetail={openDetail} /> },
    { key: 'leaders', label: '学生头子', children: <PerformanceGroupTable rows={data?.leaders ?? []} onDetail={openDetail} /> },
    { key: 'retails', label: '散户', children: <PerformanceGroupTable rows={data?.retails ?? []} onDetail={openDetail} /> },
    { key: 'performers', label: '实际做单人', children: <PerformanceGroupTable rows={data?.performers ?? []} onDetail={openDetail} /> },
  ]

  return (
    <div className="page-stack">
      <PageTitle
        title="报表中心"
        description={`业绩报表 · ${params.date_from === params.date_to ? params.date_from : `${params.date_from} 至 ${params.date_to}`} · 仅统计成功订单`}
        extra={(
          <Space wrap>
            <DatePicker.RangePicker value={range} onChange={(value) => value && setRange(value as [Dayjs, Dayjs])} />
            <Button onClick={() => setDetailOpen(true)} disabled={!data}>详情</Button>
            <Button type="primary" icon={<DownloadOutlined />} onClick={() => setExportOpen(true)}>导出</Button>
          </Space>
        )}
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} xl={6}><Card className="metric-card"><Statistic title="成功单量" value={summary?.order_count ?? 0} suffix="单" loading={report.isLoading} /></Card></Col>
        <Col xs={24} sm={12} xl={6}><Card className="metric-card"><Statistic title="营业额" value={summary?.order_amount ?? 0} formatter={(value) => currency(Number(value))} loading={report.isLoading} /></Card></Col>
        <Col xs={24} sm={12} xl={6}><Card className="metric-card"><Statistic title="优惠总额" value={summary?.coupon_amount ?? 0} formatter={(value) => currency(Number(value))} loading={report.isLoading} /></Card></Col>
        <Col xs={24} sm={12} xl={6}><Card className="metric-card accent"><Statistic title="总利润" value={summary?.profit ?? 0} valueStyle={{ color: Number(summary?.profit ?? 0) < 0 ? '#b7473a' : '#315c4c' }} formatter={(value) => currency(Number(value))} loading={report.isLoading} /></Card></Col>
      </Row>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} xl={6}><Card className="metric-card"><Statistic title="实付总额" value={summary?.actual_paid ?? 0} formatter={(value) => currency(Number(value))} loading={report.isLoading} /></Card></Col>
        <Col xs={24} sm={12} xl={6}><Card className="metric-card"><Statistic title="结算收入" value={summary?.settlement_income ?? 0} formatter={(value) => currency(Number(value))} loading={report.isLoading} /></Card></Col>
        <Col xs={24} sm={12} xl={6}><Card className="metric-card"><Statistic title="成本" value={summary?.cost ?? 0} formatter={(value) => currency(Number(value))} loading={report.isLoading} /></Card></Col>
        <Col xs={24} sm={12} xl={6}><Card className="metric-card"><Statistic title="佣金" value={summary?.commission ?? 0} formatter={(value) => currency(Number(value))} loading={report.isLoading} /></Card></Col>
      </Row>
      <Card>
        <Space wrap>
          <Tag color={Number(summary?.profit ?? 0) < 0 ? 'error' : 'success'}>负利润订单：{summary?.negative_profit_count ?? 0} 单</Tag>
          <Typography.Text type="secondary">数据按成功订单实时聚合，可点击详情查看分组业绩和订单明细。</Typography.Text>
        </Space>
      </Card>
      <Card
        title="每日业绩"
        extra={dailyReport.isError ? <Typography.Text type="danger">加载失败，请刷新重试</Typography.Text> : '全部历史日期'}
      >
        <Table<PerformanceDailyRow>
          rowKey="business_date"
          dataSource={dailyReport.data ?? []}
          loading={dailyReport.isLoading}
          pagination={{ pageSize: 10 }}
          scroll={{ x: 1250 }}
          locale={{ emptyText: '暂无成功订单' }}
          columns={dailyColumns((row) => setDailyDate(row.business_date))}
        />
      </Card>

      <Drawer title="业绩详情" width={1280} open={detailOpen} onClose={() => setDetailOpen(false)} destroyOnHidden>
        <Tabs items={groupTabs} />
      </Drawer>
      <Drawer title={detailTarget ? `订单明细 · ${detailTarget.row.entity_name}` : '订单明细'} width={1180} open={Boolean(detailTarget)} onClose={() => setDetailTarget(undefined)} destroyOnHidden>
        <Typography.Paragraph type="secondary">当前期间：{params.date_from} 至 {params.date_to}，仅显示成功订单。</Typography.Paragraph>
        <Table<Order>
          rowKey="id"
          dataSource={detailOrders.data ?? []}
          loading={detailOrders.isLoading}
          pagination={{ pageSize: 15 }}
          scroll={{ x: 1250 }}
          locale={{ emptyText: '暂无订单明细' }}
          columns={[
            { title: '日期', dataIndex: 'business_date', width: 110 },
            { title: '订单号', dataIndex: 'order_no', width: 180, render: (value) => <span className="mono">{value}</span> },
            { title: '放单人员', dataIndex: 'source_name', width: 130 },
            { title: '做单方', dataIndex: 'contractor_name', width: 140 },
            { title: '实际做单人', dataIndex: 'performer_name', width: 130, render: (value) => value || '待补' },
            { title: '标价', dataIndex: 'order_amount', align: 'right', width: 110, render: (value) => <Money value={value} /> },
            { title: '优惠金额', dataIndex: 'coupon_amount', align: 'right', width: 110, render: (value) => <Money value={value} /> },
            { title: '实付', dataIndex: 'actual_paid', align: 'right', width: 110, render: (value) => <Money value={value} /> },
            { title: '结算收入', dataIndex: 'settlement_income', align: 'right', width: 120, render: (value) => <Money value={value} /> },
            { title: '佣金', dataIndex: 'commission', align: 'right', width: 100, render: (value) => <Money value={value} /> },
            { title: '利润', dataIndex: 'profit', align: 'right', width: 110, render: (value) => <Money value={value} signed /> },
          ]}
        />
      </Drawer>
      <Drawer
        title={dailyDate ? `每日订单明细 · ${dailyDate}` : '每日订单明细'}
        width={1180}
        open={Boolean(dailyDate)}
        onClose={() => setDailyDate(undefined)}
        destroyOnHidden
      >
        <Typography.Paragraph type="secondary">仅显示该日成功订单。</Typography.Paragraph>
        <OrderDetailTable orders={dailyDetailOrders.data ?? []} loading={dailyDetailOrders.isLoading} />
      </Drawer>

      <Drawer title="导出业绩报表" width={720} open={exportOpen} onClose={() => setExportOpen(false)} destroyOnHidden>
        <Card title="导出设置" size="small">
          <Form layout="vertical" requiredMark={false}>
            <Form.Item label="文件格式"><Radio.Group value={format} onChange={(event) => setFormat(event.target.value)} options={[{ value: 'xlsx', label: 'Excel (.xlsx)' }, { value: 'csv', label: 'CSV (.csv)' }]} /></Form.Item>
            <Form.Item label="导出字段">
              <Checkbox.Group value={fields} onChange={(value) => setFields(value as string[])} className="field-grid">
                {fieldOptions.data?.map((field) => <Checkbox key={field.value} value={field.value}>{field.label}</Checkbox>)}
              </Checkbox.Group>
            </Form.Item>
            <Button type="primary" block icon={<DownloadOutlined />} loading={downloading} onClick={() => void download()}>导出当前期间成功订单</Button>
          </Form>
        </Card>
        <Card title="保存为个人模板" size="small">
          <Space.Compact block><Input value={templateName} onChange={(event) => setTemplateName(event.target.value)} placeholder="例如：每日利润明细" /><Button icon={<SaveOutlined />} disabled={!templateName.trim()} loading={saveTemplate.isPending} onClick={() => saveTemplate.mutate()}>保存</Button></Space.Compact>
          <div className="template-list">
            {templates.data?.map((template) => <button key={template.id} type="button" onClick={() => setFields(template.fields)}><FileExcelOutlined /><span><strong>{template.name}</strong><small>{template.fields.length} 个字段</small></span></button>)}
            {!templates.data?.length && <Typography.Text type="secondary">暂无模板</Typography.Text>}
          </div>
        </Card>
        <Card title="最近导出记录" size="small">
          <Table<ExportLog> rowKey="id" dataSource={logs.data} loading={logs.isLoading} pagination={{ pageSize: 8 }} columns={[
            { title: '导出时间', dataIndex: 'created_at', render: dateTime },
            { title: '格式', dataIndex: 'export_format', render: (value) => value.toUpperCase() },
            { title: '行数', dataIndex: 'row_count' },
            { title: '摘要', dataIndex: 'file_hash', render: (value) => <span className="mono">{value.slice(0, 12)}…</span> },
          ]} />
        </Card>
      </Drawer>
    </div>
  )
}