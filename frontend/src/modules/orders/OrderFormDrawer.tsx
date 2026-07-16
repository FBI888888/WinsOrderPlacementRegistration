import { Alert, AutoComplete, Checkbox, Col, DatePicker, Divider, Drawer, Dropdown, Form, Input, Radio, Row, Select, Space, Statistic, Typography } from 'antd'
import type { InputNumberProps } from 'antd'
import dayjs from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { MoneyInput } from '../../shared/components'
import { currency } from '../../shared/format'
import type { Contractor, ContractorType, Order, Performer, Source } from '../../shared/types'
import { calculateDefaultActualPaid, calculateOrderPreview } from './calculations'

const normalizeName = (value?: string) => value?.trim().toLocaleLowerCase().replace(/\s+/g, ' ') ?? ''

const couponPresets = [10, 30, 50]

function CouponAmountInput(props: InputNumberProps) {
  return (
    <Dropdown
      trigger={['click']}
      menu={{
        items: couponPresets.map((amount) => ({ key: String(amount), label: `${amount}元` })),
        onClick: ({ key }) => props.onChange?.(Number(key)),
      }}
    >
      <div className="full-width">
        <MoneyInput {...props} />
      </div>
    </Dropdown>
  )
}

export interface OrderFormValues {
  business_date: ReturnType<typeof dayjs>
  source_id: number
  contractor_type: ContractorType
  contractor_id?: number
  performer_id?: number
  performer_name?: string
  save_performer: boolean
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
  mode = 'create',
  initialOrder,
  sources,
  leaders,
  performers,
  submitting,
  onClose,
  onSubmit,
}: {
  open: boolean
  mode?: 'create' | 'edit'
  initialOrder?: Order | null
  sources: Source[]
  leaders: Contractor[]
  performers: Performer[]
  submitting: boolean
  onClose: () => void
  onSubmit: (values: OrderFormValues) => Promise<void>
}) {
  const [form] = Form.useForm<OrderFormValues>()
  const [actualPaidMode, setActualPaidMode] = useState<'auto' | 'manual'>('auto')
  const [, forceUpdate] = useState(0)
  const values = Form.useWatch([], form)
  const isEdit = mode === 'edit'

  useEffect(() => {
    if (!open) return
    if (isEdit && initialOrder) {
      setActualPaidMode('manual')
      form.resetFields()
      const useCommissionOverride = initialOrder.commission_overridden || initialOrder.contractor_type === 'RETAIL'
      form.setFieldsValue({
        business_date: dayjs(initialOrder.business_date),
        source_id: initialOrder.source_id,
        contractor_type: initialOrder.contractor_type,
        contractor_id: initialOrder.contractor_type === 'LEADER' ? initialOrder.contractor_id : undefined,
        performer_id: initialOrder.performer_id,
        performer_name: initialOrder.performer_name,
        save_performer: true,
        order_amount: Number(initialOrder.order_amount),
        coupon_amount: Number(initialOrder.coupon_amount),
        actual_paid: Number(initialOrder.actual_paid),
        settlement_income_override: initialOrder.income_overridden ? Number(initialOrder.settlement_income) : undefined,
        income_override_reason: initialOrder.income_overridden ? initialOrder.income_override_reason : undefined,
        commission_override: useCommissionOverride ? Number(initialOrder.commission) : undefined,
        commission_override_reason: useCommissionOverride ? initialOrder.commission_override_reason : undefined,
        status: initialOrder.status,
        note: initialOrder.note,
      })
      return
    }
    setActualPaidMode('auto')
    form.resetFields()
    form.setFieldsValue({
      business_date: dayjs(),
      contractor_type: 'LEADER',
      coupon_amount: 0,
      save_performer: true,
      status: 'SUCCESS',
    })
  }, [open, form, isEdit, initialOrder])

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
  const performerOptions = useMemo(() => {
    const expectedType = contractorType === 'LEADER' ? 'STUDENT' : 'RETAIL'
    return performers.filter((item) => {
      if (item.performer_type !== expectedType) return false
      if (contractorType === 'LEADER' && item.contractor_id !== values?.contractor_id) return false
      if (isEdit && item.id === initialOrder?.performer_id) return true
      return item.is_listed && item.is_active
    })
  }, [contractorType, performers, values?.contractor_id, isEdit, initialOrder])
  const matchedPerformer = performerOptions.find(
    (item) => normalizeName(item.name) === normalizeName(values?.performer_name),
  )
  const hasIncomeOverride = values?.settlement_income_override !== undefined && values?.settlement_income_override !== null
  const hasCommissionOverride = values?.commission_override !== undefined && values?.commission_override !== null

  const sourceOptions = useMemo(() => {
    const active = sources.filter((item) => item.is_active)
    if (isEdit && initialOrder) {
      const current = sources.find((item) => item.id === initialOrder.source_id)
      if (current && !current.is_active) return [...active, current]
    }
    return active
  }, [sources, isEdit, initialOrder])

  const leaderOptions = useMemo(() => {
    const active = leaders.filter((item) => item.is_active)
    if (isEdit && initialOrder?.contractor_type === 'LEADER') {
      const current = leaders.find((item) => item.id === initialOrder.contractor_id)
      if (current && !current.is_active) return [...active, current]
    }
    return active
  }, [leaders, isEdit, initialOrder])

  return (
    <Drawer
      title={isEdit ? '编辑订单' : '登记订单'}
      width={720}
      open={open}
      onClose={onClose}
      destroyOnHidden
      extra={
        <Space>
          <button className="text-button" type="button" onClick={onClose}>取消</button>
          <button className="primary-html-button" type="button" disabled={submitting} onClick={() => form.submit()}>
            {submitting ? '正在保存…' : isEdit ? '保存修改' : '保存订单'}
          </button>
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        message={isEdit
          ? '保存后会按业务日期重新计算订单；成功订单会自动冲销旧流水并按修改后的数据重新入账。'
          : '页面预览使用当前默认费率；保存时后端会按业务日期解析费率并固化快照。'}
      />
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        onValuesChange={(changedValues) => {
          if ('contractor_type' in changedValues) {
            form.setFieldsValue({
              contractor_id: undefined,
              performer_id: undefined,
              performer_name: undefined,
              save_performer: true,
              commission_override: undefined,
              commission_override_reason: undefined,
            })
          } else if ('contractor_id' in changedValues) {
            form.setFieldsValue({ performer_id: undefined, performer_name: undefined, save_performer: true })
          }
          if ('commission_override' in changedValues && changedValues.commission_override == null) {
            form.setFieldValue('commission_override_reason', undefined)
          }
          if ('settlement_income_override' in changedValues && changedValues.settlement_income_override == null) {
            form.setFieldValue('income_override_reason', undefined)
          }
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
        onFinish={async (formValues) => {
          const matched = performerOptions.find(
            (item) => normalizeName(item.name) === normalizeName(formValues.performer_name),
          )
          await onSubmit({
            ...formValues,
            performer_id: matched?.id,
            performer_name: matched ? undefined : formValues.performer_name?.trim(),
            save_performer: matched ? true : formValues.save_performer,
          })
        }}
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
                options={sourceOptions.map((item) => ({
                  value: item.id,
                  label: `${item.name} · ${(Number(item.default_discount) * 10).toFixed(2)}折${!item.is_active ? '（停用）' : ''}`,
                }))}
              />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="contractor_type" label="做单方式">
          <Radio.Group optionType="button" buttonStyle="solid" options={[{ label: '学生头子', value: 'LEADER' }, { label: '散户', value: 'RETAIL' }]} />
        </Form.Item>
        <Row gutter={16}>
          {contractorType === 'LEADER' && (
            <Col xs={24} sm={12}>
              <Form.Item name="contractor_id" label="学生头子" rules={[{ required: true, message: '请选择学生头子' }]}>
                <Select
                  showSearch
                  optionFilterProp="label"
                  options={leaderOptions.map((item) => ({
                    value: item.id,
                    label: `${item.name}${!item.is_active ? '（停用）' : ''}`,
                  }))}
                />
              </Form.Item>
            </Col>
          )}
          <Col xs={24} sm={contractorType === 'LEADER' ? 12 : 24}>
            <Form.Item
              name="performer_name"
              label={contractorType === 'LEADER' ? '实际做单学生' : '散户姓名'}
              rules={[{ required: true, whitespace: true, message: contractorType === 'LEADER' ? '请选择或填写实际做单学生' : '请选择或填写散户姓名' }]}
            >
              <AutoComplete
                disabled={contractorType === 'LEADER' && !values?.contractor_id}
                options={performerOptions.map((item) => ({
                  value: item.name,
                  label: `${item.name}${!item.is_active ? '（停用）' : ''}`,
                }))}
                filterOption={(inputValue, option) =>
                  String(option?.value ?? '').toLocaleLowerCase().includes(inputValue.toLocaleLowerCase())
                }
                placeholder={contractorType === 'LEADER' ? '选择已保存学生，或直接输入新姓名' : '选择已保存散户，或直接输入新姓名'}
              />
            </Form.Item>
          </Col>
        </Row>
        {values?.performer_name && !matchedPerformer && (
          <Form.Item name="save_performer" valuePropName="checked">
            <Checkbox>
              {contractorType === 'LEADER' ? '添加到该学生头子名下（默认添加）' : '添加到散户名单（默认添加）'}
            </Checkbox>
          </Form.Item>
        )}

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
              <CouponAmountInput />
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
          {!isEdit && (
            <Col xs={24} sm={10}>
              <Form.Item name="status" label="订单状态">
                <Select options={[{ value: 'DRAFT', label: '草稿' }, { value: 'DISPATCHED', label: '已派单' }, { value: 'SUCCESS', label: '成功并自动入账' }]} />
              </Form.Item>
            </Col>
          )}
          <Col xs={24} sm={isEdit ? 24 : 14}>
            <Form.Item name="note" label="备注">
              <Input.TextArea autoSize={{ minRows: 2, maxRows: 4 }} />
            </Form.Item>
          </Col>
        </Row>
        <Typography.Text type="secondary">
          {isEdit ? '编辑订单不会改变当前状态；如订单已被确认结算，需先冲正对应结算单。' : '成功订单会立即产生实付消耗、佣金应付和放单应收三类流水。'}
        </Typography.Text>
      </Form>
    </Drawer>
  )
}
