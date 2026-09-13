import {
  EditOutlined,
  PlusOutlined,
  SettingOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Upload,
} from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { api, errorMessage } from '../../shared/api'
import { useAuth } from '../../shared/auth-context'
import { Money, PageTitle } from '../../shared/components'
import type {
  AlipayAccount,
  AlipayDevice,
  AlipayImportBatch,
  AlipayImportRow,
  AlipayPoolSettings,
} from '../../shared/types'

const phaseText: Record<string, string> = {
  NOT_STARTED: '未开始',
  DAY1_ACTIVE: '首日使用',
  WAITING_COUPON: '等待次日券',
  DAY2_ACTIVE: '次日清空',
  EXHAUSTED: '已耗尽',
}

const couponText: Record<string, string> = {
  PENDING: '待生效',
  AVAILABLE: '可用',
  RESERVED: '已预占',
  USED: '已使用',
  EXPIRED: '已过期',
}

interface AccountFormValues {
  device_id: number
  alias: string
  initial_recharge_amount?: number
  login_identifier_masked?: string
  current_balance: number
  phase: string
  birthday_set_date?: string
  note?: string
}

export function AlipayPoolPage() {
  const { message } = App.useApp()
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [deviceOpen, setDeviceOpen] = useState(false)
  const [accountOpen, setAccountOpen] = useState(false)
  const [importBatch, setImportBatch] = useState<AlipayImportBatch | null>(null)
  const [selectedRows, setSelectedRows] = useState<React.Key[]>([])
  const [editingImportRow, setEditingImportRow] = useState<AlipayImportRow | null>(null)
  const [settingsForm] = Form.useForm()
  const [deviceForm] = Form.useForm()
  const [accountForm] = Form.useForm<AccountFormValues>()
  const [importRowForm] = Form.useForm()

  const settings = useQuery({
    queryKey: ['alipay-pool-settings'],
    queryFn: () => api.get<AlipayPoolSettings>('/alipay-pool/settings').then((res) => res.data),
  })
  const devices = useQuery({
    queryKey: ['alipay-devices'],
    queryFn: () => api.get<AlipayDevice[]>('/alipay-pool/devices').then((res) => res.data),
  })
  const accounts = useQuery({
    queryKey: ['alipay-accounts'],
    queryFn: () => api.get<AlipayAccount[]>('/alipay-pool/accounts').then((res) => res.data),
  })

  const refreshPool = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['alipay-pool-settings'] }),
      queryClient.invalidateQueries({ queryKey: ['alipay-devices'] }),
      queryClient.invalidateQueries({ queryKey: ['alipay-accounts'] }),
    ])
  }

  const settingsMutation = useMutation({
    mutationFn: (values: Record<string, number>) => api.patch('/alipay-pool/settings', values),
    onSuccess: async () => {
      message.success('资金池参数已更新')
      setSettingsOpen(false)
      await refreshPool()
    },
    onError: (error) => message.error(errorMessage(error)),
  })
  const deviceMutation = useMutation({
    mutationFn: (values: { name: string; account_category?: string; note?: string }) =>
      api.post('/alipay-pool/devices', values),
    onSuccess: async () => {
      message.success('设备已添加')
      setDeviceOpen(false)
      deviceForm.resetFields()
      await refreshPool()
    },
    onError: (error) => message.error(errorMessage(error)),
  })
  const accountMutation = useMutation({
    mutationFn: (values: AccountFormValues) => api.post('/alipay-pool/accounts', {
      ...values,
      status: 'ACTIVE',
      create_coupon: true,
      birthday_set_date: values.birthday_set_date || null,
    }),
    onSuccess: async () => {
      message.success('支付宝账号已登记')
      setAccountOpen(false)
      accountForm.resetFields()
      await refreshPool()
    },
    onError: (error) => message.error(errorMessage(error)),
  })
  const importMutation = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api.post<AlipayImportBatch>('/alipay-pool/imports/preview', form)
    },
    onSuccess: (response) => {
      setImportBatch(response.data)
      setSelectedRows(
        response.data.rows.filter((row) => row.status === 'READY').map((row) => row.id),
      )
      message.success('Excel 已解析，请确认预览')
    },
    onError: (error) => message.error(errorMessage(error, 'Excel 解析失败')),
  })
  const commitMutation = useMutation({
    mutationFn: () => api.post<AlipayImportBatch>(
      '/alipay-pool/imports/' + importBatch?.id + '/commit',
      { row_ids: selectedRows },
    ),
    onSuccess: async (response) => {
      setImportBatch(response.data)
      message.success('已导入 ' + response.data.imported_rows + ' 个账号')
      await refreshPool()
    },
    onError: (error) => message.error(errorMessage(error, '导入失败')),
  })
  const importRowMutation = useMutation({
    mutationFn: (values: Record<string, string>) => {
      const parsed = { ...(editingImportRow?.parsed_data ?? {}), ...values }
      return api.patch<AlipayImportRow>(
        '/alipay-pool/imports/' + importBatch?.id + '/rows/' + editingImportRow?.id,
        { parsed_data: parsed },
      )
    },
    onSuccess: (response) => {
      if (!importBatch) return
      setImportBatch({
        ...importBatch,
        rows: importBatch.rows.map((row) => row.id === response.data.id ? response.data : row),
      })
      setSelectedRows((rows) => [...new Set([...rows, response.data.id])])
      setEditingImportRow(null)
      message.success('导入行已修正')
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  useEffect(() => {
    if (settingsOpen && settings.data) {
      settingsForm.setFieldsValue({
        external_cash_soft_cap: Number(settings.data.external_cash_soft_cap),
        first_day_target_balance: Number(settings.data.first_day_target_balance),
        first_day_target_tolerance: Number(settings.data.first_day_target_tolerance),
        max_split_accounts: settings.data.max_split_accounts,
        reservation_minutes: settings.data.reservation_minutes,
        default_coupon_amount: Number(settings.data.default_coupon_amount),
      })
    }
  }, [settingsOpen, settings.data, settingsForm])

  useEffect(() => {
    if (editingImportRow) {
      importRowForm.setFieldsValue(editingImportRow.parsed_data)
    }
  }, [editingImportRow, importRowForm])

  const totals = useMemo(() => {
    const rows = accounts.data ?? []
    return {
      balance: rows.reduce((sum, item) => sum + Number(item.current_balance), 0),
      reserved: rows.reduce((sum, item) => sum + Number(item.reserved_balance), 0),
      availableCoupons: rows.filter((item) => item.coupon_status === 'AVAILABLE').length,
      active: rows.filter((item) => item.status === 'ACTIVE').length,
    }
  }, [accounts.data])

  if (me?.business_mode !== 'JIJIHONG') return <Navigate to="/" replace />

  return (
    <div className="page-stack">
      <PageTitle
        title="支付宝资金池"
        description="余额与20元优惠券分开核算；推荐只预占，人工确认后才扣减。"
        extra={(
          <Space wrap>
            <Button icon={<SettingOutlined />} onClick={() => setSettingsOpen(true)}>参数</Button>
            <Button icon={<PlusOutlined />} onClick={() => setDeviceOpen(true)}>添加设备</Button>
            <Button icon={<PlusOutlined />} onClick={() => setAccountOpen(true)}>登记账号</Button>
            <Upload
              accept=".xlsx"
              showUploadList={false}
              beforeUpload={(file) => {
                importMutation.mutate(file)
                return Upload.LIST_IGNORE
              }}
            >
              <Button type="primary" icon={<UploadOutlined />} loading={importMutation.isPending}>
                导入 Excel
              </Button>
            </Upload>
          </Space>
        )}
      />

      <Row gutter={[16, 16]}>
        <Col xs={12} lg={6}><Card><Statistic title="账号余额" value={totals.balance} precision={2} prefix="¥" /></Card></Col>
        <Col xs={12} lg={6}><Card><Statistic title="已预占" value={totals.reserved} precision={2} prefix="¥" /></Card></Col>
        <Col xs={12} lg={6}><Card><Statistic title="可用20元券" value={totals.availableCoupons} suffix="张" /></Card></Col>
        <Col xs={12} lg={6}><Card><Statistic title="在用账号" value={totals.active} suffix="个" /></Card></Col>
      </Row>

      {(devices.data ?? []).some((item) => item.capacity_warning) && (
        <Alert
          type="warning"
          showIcon
          message="部分手机登记了超过5个在用账号"
          description="这是容量提醒，不会阻止继续登记或推荐。"
        />
      )}

      <Card title="设备">
        <Table<AlipayDevice>
          rowKey="id"
          size="small"
          loading={devices.isLoading}
          dataSource={devices.data ?? []}
          pagination={false}
          columns={[
            { title: '设备', dataIndex: 'name' },
            { title: '账号类别', dataIndex: 'account_category', render: (value) => value || '—' },
            {
              title: '在用账号',
              dataIndex: 'active_account_count',
              render: (value, row) => <Tag color={row.capacity_warning ? 'orange' : 'green'}>{value} / 5</Tag>,
            },
            { title: '备注', dataIndex: 'note', render: (value) => value || '—' },
          ]}
        />
      </Card>

      <Card title="支付宝账号">
        <Table<AlipayAccount>
          rowKey="id"
          loading={accounts.isLoading}
          dataSource={accounts.data ?? []}
          scroll={{ x: 1100 }}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          columns={[
            { title: '设备', dataIndex: 'device_name', width: 120 },
            { title: '账号别名', dataIndex: 'alias', width: 120 },
            { title: '阶段', dataIndex: 'phase', width: 110, render: (value) => <Tag>{phaseText[value] ?? value}</Tag> },
            { title: '当前余额', dataIndex: 'current_balance', align: 'right', width: 110, render: (value) => <Money value={value} /> },
            { title: '预占', dataIndex: 'reserved_balance', align: 'right', width: 100, render: (value) => <Money value={value} /> },
            { title: '可用余额', dataIndex: 'available_balance', align: 'right', width: 110, render: (value) => <Money value={value} /> },
            {
              title: '20元券',
              dataIndex: 'coupon_status',
              width: 100,
              render: (value) => value ? <Tag color={value === 'AVAILABLE' ? 'green' : undefined}>{couponText[value] ?? value}</Tag> : '—',
            },
            { title: '生日设置', dataIndex: 'birthday_set_date', width: 110, render: (value) => value || '—' },
            { title: '状态', dataIndex: 'status', width: 90, render: (value) => <Tag>{value === 'ACTIVE' ? '在用' : value === 'PAUSED' ? '暂停' : '耗尽'}</Tag> },
            { title: '备注', dataIndex: 'note', render: (value) => value || '—' },
          ]}
        />
      </Card>

      <Modal
        title="资金池参数"
        open={settingsOpen}
        onCancel={() => setSettingsOpen(false)}
        onOk={() => settingsForm.submit()}
        confirmLoading={settingsMutation.isPending}
      >
        <Form form={settingsForm} layout="vertical" onFinish={(values) => settingsMutation.mutate(values)}>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="external_cash_soft_cap" label="真实付款软上限"><InputNumber min={0} precision={2} className="full-width" /></Form.Item></Col>
            <Col span={12}><Form.Item name="max_split_accounts" label="最多拆分账号"><InputNumber min={1} max={5} className="full-width" /></Form.Item></Col>
            <Col span={12}><Form.Item name="first_day_target_balance" label="首日目标余额"><InputNumber min={0} precision={2} className="full-width" /></Form.Item></Col>
            <Col span={12}><Form.Item name="first_day_target_tolerance" label="目标容差"><InputNumber min={0} precision={2} className="full-width" /></Form.Item></Col>
            <Col span={12}><Form.Item name="reservation_minutes" label="预占分钟数"><InputNumber min={1} max={240} className="full-width" /></Form.Item></Col>
            <Col span={12}><Form.Item name="default_coupon_amount" label="默认券金额"><InputNumber min={0.01} precision={2} className="full-width" /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>

      <Modal title="添加设备" open={deviceOpen} onCancel={() => setDeviceOpen(false)} onOk={() => deviceForm.submit()} confirmLoading={deviceMutation.isPending}>
        <Form form={deviceForm} layout="vertical" onFinish={(values) => deviceMutation.mutate(values)}>
          <Form.Item name="name" label="设备名称" rules={[{ required: true }]}><Input placeholder="如：手机01" /></Form.Item>
          <Form.Item name="account_category" label="账号类别"><Input /></Form.Item>
          <Form.Item name="note" label="备注"><Input.TextArea /></Form.Item>
        </Form>
      </Modal>

      <Modal title="登记支付宝账号" open={accountOpen} onCancel={() => setAccountOpen(false)} onOk={() => accountForm.submit()} confirmLoading={accountMutation.isPending}>
        <Form<AccountFormValues>
          form={accountForm}
          layout="vertical"
          initialValues={{ phase: 'NOT_STARTED' }}
          onFinish={(values) => accountMutation.mutate(values)}
        >
          <Form.Item name="device_id" label="所属设备" rules={[{ required: true }]}><Select options={devices.data?.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item>
          <Form.Item name="alias" label="账号别名" extra="别名允许重复，系统使用内部ID区分。" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="login_identifier_masked" label="登录标识（脱敏，可选）" extra="不要录入支付宝密码或支付密码。"><Input placeholder="如：138****1234" /></Form.Item>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="initial_recharge_amount" label="实际充值额（可选）"><InputNumber min={0} precision={2} className="full-width" /></Form.Item></Col>
            <Col span={12}><Form.Item name="current_balance" label="当前/期初余额" rules={[{ required: true }]}><InputNumber min={0} precision={2} className="full-width" /></Form.Item></Col>
          </Row>
          <Form.Item name="phase" label="当前阶段"><Select options={Object.entries(phaseText).map(([value, label]) => ({ value, label }))} /></Form.Item>
          <Form.Item name="birthday_set_date" label="设置生日日期"><Input placeholder="YYYY-MM-DD" /></Form.Item>
          <Form.Item name="note" label="备注"><Input.TextArea /></Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={importBatch ? 'Excel 导入预览 · ' + importBatch.filename : 'Excel 导入预览'}
        width={920}
        open={Boolean(importBatch)}
        onClose={() => setImportBatch(null)}
        extra={(
          <Button
            type="primary"
            disabled={!selectedRows.length || importBatch?.status === 'COMMITTED'}
            loading={commitMutation.isPending}
            onClick={() => commitMutation.mutate()}
          >
            导入已选 {selectedRows.length} 行
          </Button>
        )}
      >
        {importBatch && (
          <Space direction="vertical" className="full-width" size="middle">
            <Alert
              type="info"
              showIcon
              message={'共 ' + importBatch.total_rows + ' 行；可直接导入 ' + importBatch.ready_rows + ' 行；需复核 ' + importBatch.review_rows + ' 行'}
              description="A-I列参与导入，J-O列按约定忽略；重复别名允许导入。"
            />
            <Table<AlipayImportRow>
              rowKey="id"
              size="small"
              dataSource={importBatch.rows}
              pagination={{ pageSize: 20, showSizeChanger: false }}
              rowSelection={{
                selectedRowKeys: selectedRows,
                onChange: setSelectedRows,
                getCheckboxProps: (row) => ({ disabled: row.status === 'IMPORTED' || Boolean(row.errors?.length) }),
              }}
              columns={[
                { title: '行', dataIndex: 'row_number', width: 60 },
                { title: '设备', render: (_, row) => row.parsed_data?.device_name || '—' },
                { title: '别名', render: (_, row) => row.parsed_data?.alias || '—' },
                { title: '余额', align: 'right', render: (_, row) => row.parsed_data?.current_balance || '—' },
                { title: '阶段', render: (_, row) => phaseText[String(row.parsed_data?.phase)] ?? String(row.parsed_data?.phase ?? '—') },
                {
                  title: '检查',
                  width: 260,
                  render: (_, row) => (
                    <Space direction="vertical" size={0}>
                      {row.errors?.map((item) => <Tag color="red" key={item}>{item}</Tag>)}
                      {row.warnings?.map((item) => <Tag color="orange" key={item}>{item}</Tag>)}
                      {!row.errors?.length && !row.warnings?.length && <Tag color="green">可导入</Tag>}
                    </Space>
                  ),
                },
                {
                  title: '操作',
                  width: 80,
                  render: (_, row) => importBatch.status !== 'COMMITTED' && row.status !== 'IMPORTED' && (
                    <Button type="link" icon={<EditOutlined />} onClick={() => setEditingImportRow(row)}>修正</Button>
                  ),
                },
              ]}
            />
          </Space>
        )}
      </Drawer>

      <Modal
        title="修正导入行"
        open={Boolean(editingImportRow)}
        onCancel={() => setEditingImportRow(null)}
        onOk={() => importRowForm.submit()}
        confirmLoading={importRowMutation.isPending}
      >
        <Form form={importRowForm} layout="vertical" onFinish={(values) => importRowMutation.mutate(values)}>
          <Form.Item name="device_name" label="设备" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="alias" label="账号别名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="current_balance" label="当前余额" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="phase" label="阶段" rules={[{ required: true }]}><Select options={Object.entries(phaseText).map(([value, label]) => ({ value, label }))} /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
