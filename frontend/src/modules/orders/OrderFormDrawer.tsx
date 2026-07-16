import { Alert, Col, DatePicker, Divider, Drawer, Form, Input, Radio, Row, Select, Space, Statistic, Typography } from 'antd'
import dayjs from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { MoneyInput } from '../../shared/components'
import { currency } from '../../shared/format'
import type { Contractor, ContractorType, Source } from '../../shared/types'
import { calculateDefaultActualPaid, calculateOrderPreview } from './calculations'

export interface OrderFormValues {
  business_date: ReturnType<typeof dayjs>
  source_id: number
  contractor_type: ContractorType
  contractor_id?: number
  retail_name?: string
  student_name?: string
  order_amount: number
  coupon_amount: number
  actual_paid: number
  settlement_income_override?: number
  income_override_reason?: string
  commission_override?: number
  commission_override_reason?: string
  status: string
  note?: string
}

export function OrderFormDrawer({
  open,
  sources,
  leaders,
  submitting,
  onClose,
  onSubmit,
}: {
  open: boolean
  sources: Source[]
  leaders: Contractor[]
  submitting: boolean
  onClose: () => void
  onSubmit: (values: OrderFormValues) => Promise<void>
}) {
  const [form] = Form.useForm<OrderFormValues>()
  const [actualPaidMode, setActualPaidMode] = useState<'auto' | 'manual'>('auto')
  const [, forceUpdate] = useState(0)
  const values = Form.useWatch([], form)

  useEffect(() => {
    if (open) {
      setActualPaidMode('auto')
      form.resetFields()
      form.setFieldsValue({
        business_date: dayjs(),
        contractor_type: 'LEADER',
        coupon_amount: 0,
        status: 'SUCCESS',
      })
    }
  }, [open, form])

  const preview = useMemo(() => {
    const source = sources.find((item) => item.id === values?.source_id)
    const leader = leaders.find((item) => item.id === values?.contractor_id)
    return calculateOrderPreview({
      settlementBasis: source?.default_basis,
      discount: Number(source?.default_discount ?? 0),
      orderAmount: values?.order_amount,
      couponAmount: values?.coupon_amount,
      actualPaid: values?.actual_paid,
      defaultCommission: Number(leader?.default_commission ?? 0),
      settlementIncomeOverride: values?.settlement_income_override,
      commissionOverride: values?.commission_override,
    })
  }, [values, sources, leaders])

  const contractorType = values?.contractor_type ?? 'LEADER'
  const hasIncomeOverride = values?.settlement_income_override !== undefined && values?.settlement_income_override !== null
  const hasCommissionOverride = values?.commission_override !== undefined && values?.commission_override !== null

  return (
    <Drawer
      title="登记订单"
      width={720}
      open={open}
      onClose={onClose}
      destroyOnHidden
      extra={
        <Space>
          <button className="text-button" type="button" onClick={onClose}>取消</button>
          <button className="primary-html-button" type="button" disabled={submitting} onClick={() => form.submit()}>
            {submitting ? '正在保存…' : '保存订单'}
          </button>
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        message="页面预览使用当前默认费率；保存时后端会按业务日期解析费率并固化快照。"
      />
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        onValuesChange={(changedValues) => {
          if ('actual_paid' in changedValues) {
            setActualPaidMode('manual')
          } else if (
            actualPaidMode === 'auto'
            && ('order_amount' in changedValues || 'coupon_amount' in changedValues)
          ) {
            const currentValues = form.getFieldsValue()
            form.setFieldValue(
              'actual_paid',
              calculateDefaultActualPaid(currentValues.order_amount, currentValues.coupon_amount),
            )
          }
          forceUpdate((value) => value + 1)
        }}
        onFinish={onSubmit}
      >
        <Divider titlePlacement="start">订单归属</Divider>
        <Row gutter={16}>
          <Col xs={24} sm={12}>
            <Form.Item name="business_date" label="业务日期" rules={[{ required: true }]}>
              <DatePicker className="full-width" />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item name="source_id" label="放单人员" rules={[{ required: true, message: '请选择放单人员' }]}>
              <Select
                showSearch
                optionFilterProp="label"
                options={sources.filter((item) => item.is_active).map((item) => ({
                  value: item.id,
                  label: `${item.name} · ${(Number(item.default_discount) * 10).toFixed(2)}折`,
                }))}
              />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="contractor_type" label="做单方式">
          <Radio.Group optionType="button" buttonStyle="solid" options={[{ label: '学生头子', value: 'LEADER' }, { label: '散户', value: 'RETAIL' }]} />
        </Form.Item>
        <Row gutter={16}>
          {contractorType === 'LEADER' ? (
            <>
              <Col xs={24} sm={12}>
                <Form.Item name="contractor_id" label="学生头子" rules={[{ required: true, message: '请选择学生头子' }]}>
                  <Select
                    showSearch
                    optionFilterProp="label"
                    options={leaders.filter((item) => item.is_active).map((item) => ({ value: item.id, label: item.name }))}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12}>
                <Form.Item name="student_name" label="实际学生姓名">
                  <Input placeholder="由头子反馈，可稍后补充" />
                </Form.Item>
              </Col>
            </>
          ) : (
            <Col span={24}>
              <Form.Item name="retail_name" label="散户姓名" rules={[{ required: true, message: '请填写散户姓名' }]}>
                <Input placeholder="同名散户会自动归集资金往来" />
              </Form.Item>
            </Col>
          )}
        </Row>

        <Divider titlePlacement="start">金额与佣金</Divider>
        <Row gutter={16}>
          <Col xs={24} sm={8}>
            <Form.Item name="order_amount" label="订单标价" rules={[{ required: true }]}>
              <MoneyInput min={0.01} />
            </Form.Item>
          </Col>
          <Col xs={24} sm={8}>
            <Form.Item
              name="coupon_amount"
              label="优惠券金额"
              dependencies={['order_amount']}
              rules={[
                { required: true },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    const orderAmount = getFieldValue('order_amount')
                    if (value === undefined || orderAmount === undefined || Number(value) <= Number(orderAmount)) {
                      return Promise.resolve()
                    }
                    return Promise.reject(new Error('优惠券金额不能超过订单标价'))
                  },
                }),
              ]}
            >
              <MoneyInput />
            </Form.Item>
          </Col>
          <Col xs={24} sm={8}>
            <Form.Item
              name="actual_paid"
              label="实付金额"
              extra={actualPaidMode === 'auto' ? '按订单标价减优惠券金额自动计算，可直接修改' : '已切换为手动金额'}
              rules={[{ required: true }]}
            >
              <MoneyInput />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col xs={24} sm={12}>
            <Form.Item
              name="commission_override"
              label={contractorType === 'RETAIL' ? '本单佣金' : '覆盖默认佣金（可选）'}
              rules={contractorType === 'RETAIL' ? [{ required: true, message: '请填写散户佣金' }] : []}
            >
              <MoneyInput />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item
              name="commission_override_reason"
              label="佣金覆盖原因"
              rules={hasCommissionOverride ? [{ required: true, message: '请填写覆盖原因' }] : []}
            >
              <Input disabled={!hasCommissionOverride} placeholder="散户可填写：本单约定" />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col xs={24} sm={12}>
            <Form.Item name="settlement_income_override" label="覆盖结算收入（可选）">
              <MoneyInput />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12}>
            <Form.Item
              name="income_override_reason"
              label="收入覆盖原因"
              rules={hasIncomeOverride ? [{ required: true, message: '请填写覆盖原因' }] : []}
            >
              <Input disabled={!hasIncomeOverride} />
            </Form.Item>
          </Col>
        </Row>

        <div className="calculation-strip">
          <Statistic title="结算收入" value={preview.income} formatter={(value) => currency(Number(value))} />
          <Statistic title="佣金" value={preview.commission} formatter={(value) => currency(Number(value))} />
          <Statistic title="成本" value={preview.cost} formatter={(value) => currency(Number(value))} />
          <Statistic title="预计利润" value={preview.profit} valueStyle={{ color: preview.profit < 0 ? '#b7473a' : '#315c4c' }} formatter={(value) => currency(Number(value))} />
        </div>

        <Divider titlePlacement="start">保存方式</Divider>
        <Row gutter={16}>
          <Col xs={24} sm={10}>
            <Form.Item name="status" label="订单状态">
              <Select options={[{ value: 'DRAFT', label: '草稿' }, { value: 'DISPATCHED', label: '已派单' }, { value: 'SUCCESS', label: '成功并自动入账' }]} />
            </Form.Item>
          </Col>
          <Col xs={24} sm={14}>
            <Form.Item name="note" label="备注">
              <Input.TextArea autoSize={{ minRows: 2, maxRows: 4 }} />
            </Form.Item>
          </Col>
        </Row>
        <Typography.Text type="secondary">成功订单会立即产生实付消耗、佣金应付和放单应收三类流水。</Typography.Text>
      </Form>
    </Drawer>
  )
}