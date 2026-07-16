import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons'
import { InputNumber, Tag, Typography } from 'antd'
import type { InputNumberProps } from 'antd'
import type { ReactNode } from 'react'
import { currency, statusText } from './format'

export function PageTitle({
  title,
  description,
  extra,
}: {
  title: string
  description: string
  extra?: ReactNode
}) {
  return (
    <div className="page-title">
      <div>
        <Typography.Title level={2}>{title}</Typography.Title>
        <Typography.Text type="secondary">{description}</Typography.Text>
      </div>
      {extra && <div className="page-actions">{extra}</div>}
    </div>
  )
}

const statusColor: Record<string, string> = {
  DRAFT: 'default',
  DISPATCHED: 'processing',
  SUCCESS: 'success',
  CANCELLED: 'warning',
  REVERSED: 'error',
  CONFIRMED: 'success',
  SOURCE: 'blue',
  CONTRACTOR: 'purple',
  LEADER: 'geekblue',
  RETAIL: 'gold',
}

export function StatusTag({ value }: { value: string }) {
  return <Tag color={statusColor[value]}>{statusText[value] ?? value}</Tag>
}

export function MoneyInput({
  className,
  min = 0,
  precision = 2,
  prefix = '¥',
  onFocus,
  ...props
}: InputNumberProps) {
  return (
    <InputNumber
      {...props}
      min={min}
      precision={precision}
      prefix={prefix}
      className={className ? `full-width ${className}` : 'full-width'}
      onFocus={(event) => {
        event.currentTarget.select()
        onFocus?.(event)
      }}
    />
  )
}

export function Money({ value, signed = false }: { value: string | number; signed?: boolean }) {
  const number = Number(value)
  return (
    <span className={signed ? (number < 0 ? 'money negative' : 'money positive') : 'money'}>
      {signed && number !== 0 && (number > 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />)}
      {currency(number)}
    </span>
  )
}