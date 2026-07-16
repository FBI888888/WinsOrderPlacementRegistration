export type Role = 'OWNER' | 'BOOKKEEPER' | 'VIEWER'
export type OrderStatus = 'DRAFT' | 'DISPATCHED' | 'SUCCESS' | 'CANCELLED' | 'REVERSED'
export type ContractorType = 'LEADER' | 'RETAIL'

export interface Me {
  user_id: number
  name: string
  email: string
  tenant_id: number
  tenant_name: string
  role: Role
}

export interface Source {
  id: number
  name: string
  contact?: string
  default_basis: 'ORDER_AMOUNT' | 'AFTER_COUPON'
  default_discount: string
  is_active: boolean
  note?: string
  created_at: string
}

export interface Contractor {
  id: number
  name: string
  contractor_type: ContractorType
  contact?: string
  default_commission: string
  is_active: boolean
  note?: string
  created_at: string
}

export interface Order {
  id: number
  order_no: string
  business_date: string
  status: OrderStatus
  source_id: number
  source_name: string
  contractor_id: number
  contractor_type: ContractorType
  contractor_name: string
  student_name?: string
  order_amount: string
  coupon_amount: string
  actual_paid: string
  settlement_basis_snapshot: string
  discount_snapshot: string
  settlement_income: string
  income_overridden: boolean
  commission: string
  commission_overridden: boolean
  cost: string
  profit: string
  note?: string
  success_at?: string
  created_at: string
}

export interface DashboardSummary {
  date_from: string
  date_to: string
  order_count: number
  success_count: number
  settlement_income: string
  cost: string
  profit: string
  advance_balance: string
  commission_payable: string
  source_receivable: string
  negative_profit_count: number
}

export interface LedgerEntry {
  id: number
  business_date: string
  account: 'ADVANCE' | 'COMMISSION_PAYABLE' | 'SOURCE_RECEIVABLE'
  entry_type: string
  amount: string
  contractor_id?: number
  source_id?: number
  order_id?: number
  note?: string
  created_at: string
}

export interface Balance {
  account: 'ADVANCE' | 'COMMISSION_PAYABLE' | 'SOURCE_RECEIVABLE'
  counterparty_id: number
  counterparty_name: string
  balance: string
}

export interface Settlement {
  id: number
  settlement_no: string
  settlement_type: 'SOURCE' | 'CONTRACTOR'
  status: 'DRAFT' | 'CONFIRMED' | 'REVERSED'
  date_from: string
  date_to: string
  source_id?: number
  contractor_id?: number
  counterparty_name_snapshot: string
  order_count: number
  order_amount_total: string
  actual_paid_total: string
  commission_total: string
  settlement_income_total: string
  profit_total: string
  account_balance_snapshot: string
  note?: string
  created_at: string
}

export interface Member {
  id: number
  user_id: number
  name: string
  email: string
  role: Role
  is_active: boolean
  created_at: string
}

export interface AuditLog {
  id: number
  user_id?: number
  action: string
  resource_type: string
  resource_id?: string
  payload?: Record<string, unknown>
  created_at: string
}