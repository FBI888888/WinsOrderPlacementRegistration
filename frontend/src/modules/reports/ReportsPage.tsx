import { DownloadOutlined, FileExcelOutlined, SaveOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Checkbox, Col, DatePicker, Form, Input, Radio, Row, Select, Space, Table, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'
import { api, errorMessage } from '../../shared/api'
import { PageTitle } from '../../shared/components'
import { dateTime } from '../../shared/format'
import type { Contractor, Source } from '../../shared/types'

interface ExportField { value: string; label: string }
interface ExportTemplate { id: number; name: string; fields: string[]; filters?: Record<string, unknown>; created_at: string }
interface ExportLog { id: number; export_format: string; fields: string[]; row_count: number; file_hash: string; created_at: string }

export function ReportsPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().startOf('month'), dayjs()])
  const [format, setFormat] = useState('xlsx')
  const [fields, setFields] = useState<string[]>([])
  const [sourceId, setSourceId] = useState<number>()
  const [contractorId, setContractorId] = useState<number>()
  const [status, setStatus] = useState<string>()
  const [templateName, setTemplateName] = useState('')
  const [downloading, setDownloading] = useState(false)

  const fieldOptions = useQuery({
    queryKey: ['export-fields'],
    queryFn: () => api.get<ExportField[]>('/reports/export-fields').then((res) => { setFields((current) => current.length ? current : res.data.map((item) => item.value)); return res.data }),
  })
  const templates = useQuery({ queryKey: ['export-templates'], queryFn: () => api.get<ExportTemplate[]>('/reports/templates').then((res) => res.data) })
  const logs = useQuery({ queryKey: ['export-logs'], queryFn: () => api.get<ExportLog[]>('/reports/export-logs').then((res) => res.data) })
  const sources = useQuery({ queryKey: ['sources'], queryFn: () => api.get<Source[]>('/partners/sources').then((res) => res.data) })
  const contractors = useQuery({ queryKey: ['contractors', 'all'], queryFn: () => api.get<Contractor[]>('/partners/contractors').then((res) => res.data) })

  const saveTemplate = useMutation({
    mutationFn: () => api.post('/reports/templates', { name: templateName, fields, filters: { source_id: sourceId, contractor_id: contractorId, status } }),
    onSuccess: async () => { message.success('导出模板已保存'); setTemplateName(''); await queryClient.invalidateQueries({ queryKey: ['export-templates'] }) },
    onError: (error) => message.error(errorMessage(error)),
  })

  const download = async () => {
    if (!fields.length) return message.warning('至少选择一个导出字段')
    setDownloading(true)
    try {
      const params = new URLSearchParams({
        export_format: format,
        date_from: range[0].format('YYYY-MM-DD'),
        date_to: range[1].format('YYYY-MM-DD'),
      })
      fields.forEach((field) => params.append('fields', field))
      if (sourceId) params.set('source_id', String(sourceId))
      if (contractorId) params.set('contractor_id', String(contractorId))
      if (status) params.set('status', status)
      const response = await api.get('/reports/orders/export', { params, responseType: 'blob' })
      const url = URL.createObjectURL(response.data)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `订单报表-${dayjs().format('YYYYMMDD-HHmm')}.${format}`
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

  return (
    <div className="page-stack">
      <PageTitle title="报表导出" description="选择范围、对象与字段后由后端统一生成，导出行为保留审计摘要。" extra={<Button type="primary" icon={<DownloadOutlined />} loading={downloading} onClick={() => void download()}>生成并下载</Button>} />
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <Card title="导出设置">
            <Form layout="vertical" requiredMark={false}>
              <Row gutter={16}>
                <Col xs={24} md={12}><Form.Item label="业务日期"><DatePicker.RangePicker value={range} onChange={(value) => value && setRange(value as [Dayjs, Dayjs])} className="full-width" /></Form.Item></Col>
                <Col xs={24} md={12}><Form.Item label="文件格式"><Radio.Group value={format} onChange={(event) => setFormat(event.target.value)} options={[{ value: 'xlsx', label: 'Excel (.xlsx)' }, { value: 'csv', label: 'CSV (.csv)' }]} /></Form.Item></Col>
                <Col xs={24} md={8}><Form.Item label="订单状态"><Select allowClear value={status} onChange={setStatus} options={[{ value: 'SUCCESS', label: '成功' }, { value: 'DRAFT', label: '草稿' }, { value: 'DISPATCHED', label: '已派单' }, { value: 'CANCELLED', label: '已取消' }, { value: 'REVERSED', label: '已冲正' }]} /></Form.Item></Col>
                <Col xs={24} md={8}><Form.Item label="放单人员"><Select allowClear showSearch optionFilterProp="label" value={sourceId} onChange={setSourceId} options={sources.data?.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item></Col>
                <Col xs={24} md={8}><Form.Item label="做单方"><Select allowClear showSearch optionFilterProp="label" value={contractorId} onChange={setContractorId} options={contractors.data?.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item></Col>
              </Row>
              <Form.Item label="导出字段">
                <Checkbox.Group value={fields} onChange={(value) => setFields(value as string[])} className="field-grid">
                  {fieldOptions.data?.map((field) => <Checkbox key={field.value} value={field.value}>{field.label}</Checkbox>)}
                </Checkbox.Group>
              </Form.Item>
            </Form>
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="保存为个人模板">
            <Space.Compact block><Input value={templateName} onChange={(event) => setTemplateName(event.target.value)} placeholder="例如：每日利润明细" /><Button icon={<SaveOutlined />} disabled={!templateName.trim()} loading={saveTemplate.isPending} onClick={() => saveTemplate.mutate()}>保存</Button></Space.Compact>
            <div className="template-list">
              {templates.data?.map((template) => (
                <button key={template.id} type="button" onClick={() => { setFields(template.fields); setSourceId(template.filters?.source_id as number | undefined); setContractorId(template.filters?.contractor_id as number | undefined); setStatus(template.filters?.status as string | undefined) }}>
                  <FileExcelOutlined /><span><strong>{template.name}</strong><small>{template.fields.length} 个字段</small></span>
                </button>
              ))}
              {!templates.data?.length && <Typography.Text type="secondary">暂无模板</Typography.Text>}
            </div>
          </Card>
        </Col>
      </Row>
      <Card title="最近导出记录">
        <Table<ExportLog> rowKey="id" dataSource={logs.data} loading={logs.isLoading} pagination={{ pageSize: 10 }} columns={[
          { title: '导出时间', dataIndex: 'created_at', render: dateTime },
          { title: '格式', dataIndex: 'export_format', render: (value) => value.toUpperCase() },
          { title: '数据行数', dataIndex: 'row_count' },
          { title: '字段数', dataIndex: 'fields', render: (value: string[]) => value.length },
          { title: '文件摘要', dataIndex: 'file_hash', render: (value) => <span className="mono">{value.slice(0, 16)}…</span> },
        ]} />
      </Card>
    </div>
  )
}