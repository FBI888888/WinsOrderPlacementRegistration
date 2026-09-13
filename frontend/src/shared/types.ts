export type Role = 'OWNER' | 'BOOKKEEPER' | 'VIEWER'
export type OrderStatus = 'DRAFT' | 'DISPATCHED' | 'SUCCESS' | 'CANCELLED' | 'REVERSED'
export type ContractorType = 'LEADER' | 'RETAIL'
export type PerformerType = 'STUDENT' | 'RETAIL'
export type BusinessMode = 'FEDAICHU' | 'JIJIHONG'
export type SettlementMethod = 'DISCOUNT' | 'FIXED_DEDUCTION'

export interface TenantBrief {
  id: number
  name: string
  role: Role
  business_mode: BusinessMode
}

export interface Me {
  user_id: number
  name: string
  email: string
  tenant_id: number
  tenant_name: string
  business_mode: BusinessMode
  role: Role
  tenants: TenantBrief[]
}

export interface Source {
  id: number
  name: string
  contact?: string
  default_basis: 'ORDER_AMOUNT' | 'AFTER_COUPON'
  default_settlement_method: SettlementMethod
  default_discount: string
  default_fixed_deduction: string
  is_active: boolean
  note?: string
  created_at: string
}

export interface Performer {
  id: number
  name: string
  performer_type: PerformerType
  contractor_id: number
  is_listed: boolean
  is_active: boolean
  note?: string
  created_at: string
}

export interface PerformerOrderStat {
  performer_id: number
  success_count: number
}

export interface PointAccount {
  performer_id: number
  performer_name: string
  performer_type: PerformerType
  contractor_id: number
  contractor_name: string
  is_listed: boolean
  is_active: boolean
  balance: string
  available_coupons: number
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
  source_id?: number
  source_name?: string
  contractor_id?: number
  contractor_type?: ContractorType
  contractor_name?: string
  performer_id?: number
  performer_name?: string
  student_name?: string
  point_balance?: string
  available_coupons: number
  order_amount: string
  customer_received_amount?: string
  coupon_amount: string
  actual_paid: string
  settlement_basis_snapshot: string
  settlement_method_snapshot: SettlementMethod
  discount_snapshot: string
  fixed_deduction_snapshot: string
  settlement_income: string
  income_overridden: boolean
  income_override_reason?: string
  commission: string
  commission_overridden: boolean
  commission_override_reason?: string
  cost: string
  profit: string
  note?: string
  success_at?: string
  created_at: string
}

export interface DashboardSummary {
  business_mode: BusinessMode
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
  customer_received?: string
  coupon_used?: string
  balance_used?: string
  external_cash?: string
  pool_balance?: string
  reconciliation_gain_loss?: string
  period_net_income?: string
}

export interface PerformanceSummary {
  date_from: string
  date_to: string
  order_count: number
  order_amount: string
  coupon_amount: string
  actual_paid: string
  settlement_income: string
  cost: string
  commission: string
  profit: string
  negative_profit_count: number
}

export interface PerformanceDailyRow {
  business_date: string
  order_count: number
  order_amount: string
  coupon_amount: string
  actual_paid: string
  settlement_income: string
  cost: string
  commission: string
  profit: string
  negative_profit_count: number
}

export type PerformanceGroupType = 'source' | 'leader' | 'retail' | 'performer'

export interface PerformanceGroupRow {
  group_type: PerformanceGroupType
  entity_id: number
  entity_name: string
  order_count: number
  order_amount: string
  coupon_amount: string
  actual_paid: string
  settlement_income: string
  cost: string
  commission: string
  profit: string
}

export interface PerformanceReport {
  summary: PerformanceSummary
  sources: PerformanceGroupRow[]
  leaders: PerformanceGroupRow[]
  retails: PerformanceGroupRow[]
  performers: PerformanceGroupRow[]
}

export interface LedgerEntry {
  id: number
  business_date: string
  account: 'ADVANCE' | 'COMMISSION_PAYABLE' | 'SOURCE_RECEIVABLE'
  entry_type: string
  amount: string
  advance_balance_snapshot?: string | null
  commission_payable_snapshot?: string | null
  net_settlement_snapshot?: string | null
  source_receivable_snapshot?: string | null
  contractor_id?: number
  source_id?: number
  order_id?: number
  settlement_id?: number
  note?: string
  created_at: string
}

export interface Balance {
  account: 'ADVANCE' | 'COMMISSION_PAYABLE' | 'SOURCE_RECEIVABLE'
  counterparty_id: number
  counterparty_name: string
  balance: string
}

export interface ClearingPreviewItem {
  settlement_type: 'SOURCE' | 'CONTRACTOR'
  counterparty_id: number
  counterparty_name: string
  account: 'COMMISSION_PAYABLE' | 'SOURCE_RECEIVABLE'
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
  account?: 'COMMISSION_PAYABLE' | 'SOURCE_RECEIVABLE'
  settled_amount: string
  note?: string
  confirmed_at?: string
  reversed_at?: string
  reversal_reason?: string
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

export interface OrderHistoryItem {
  id: number
  user_id?: number
  user_name?: string
  action: string
  payload?: Record<string, unknown>
  created_at: string
}

export interface AlipayPoolSettings {
  external_cash_soft_cap: string
  first_day_target_balance: string
  first_day_target_tolerance: string
  max_split_accounts: number
  reservation_minutes: number
  default_coupon_amount: string
}

export interface AlipayDevice {
  id: number
  name: string
  account_category?: string
  is_active: boolean
  note?: string
  active_account_count: number
  capacity_warning: boolean
  created_at: string
}

export interface AlipayAccount {
  id: number
  device_id: number
  device_name: string
  alias: string
  login_identifier_masked?: string
  initial_recharge_amount?: string
  opening_balance: string
  current_balance: string
  reserved_balance: string
  available_balance: string
  status: 'ACTIVE' | 'PAUSED' | 'EXHAUSTED'
  phase: 'NOT_STARTED' | 'DAY1_ACTIVE' | 'WAITING_COUPON' | 'DAY2_ACTIVE' | 'EXHAUSTED'
  birthday_set_date?: string
  coupon_status?: 'PENDING' | 'AVAILABLE' | 'RESERVED' | 'USED' | 'EXPIRED'
  coupon_amount?: string
  coupon_available_at?: string
  note?: string
  created_at: string
}

export interface PaymentAllocation {
  id: number
  account_id: number
  sequence: number
  device_name: string
  account_alias: string
  coupon_amount: string
  balance_amount: string
  external_cash_amount: string
  balance_before: string
  balance_after: string
}

export interface PaymentPlan {
  id: number
  order_id: number
  revision: number
  status: 'RESERVED' | 'CONFIRMED' | 'RELEASED' | 'REVERSED' | 'EXPIRED'
  order_amount: string
  total_coupon: string
  total_balance: string
  total_external_cash: string
  soft_cap_exceeded: boolean
  warning?: string
  expires_at: string
  confirmed_at?: string
  allocations: PaymentAllocation[]
}

export interface SuggestedAllocation {
  account_id: number
  device_name: string
  account_alias: string
  coupon_amount: string
  balance_amount: string
  external_cash_amount: string
  balance_before: string
  balance_after: string
}

export interface RecommendationPreview {
  order_amount: string
  total_coupon: string
  total_balance: string
  total_external_cash: string
  soft_cap_exceeded: boolean
  warning?: string
  allocations: SuggestedAllocation[]
}

export interface JijihongOrderCreateResult {
  order: Order
  payment_plan: PaymentPlan
}

export interface JijihongFundsSummary {
  current_balance: string
  reserved_balance: string
  available_balance: string
  customer_receipts: string
  balance_cost: string
  external_cash_cost: string
  reconciliation_gain_loss: string
  order_profit: string
  period_net_income: string
}

export interface AlipayBalanceEntryView {
  id: number
  account_id: number
  account_alias: string
  device_id: number
  device_name: string
  order_id?: number
  plan_id?: number
  entry_type: string
  balance_delta: string
  reserved_delta: string
  balance_after: string
  reserved_after: string
  reason?: string
  created_at: string
}

export interface JijihongFinancialEntry {
  id: number
  business_date: string
  order_id?: number
  plan_id?: number
  account_id?: number
  account_alias?: string
  device_id?: number
  device_name?: string
  entry_type: string
  amount: string
  note?: string
  created_at: string
}

export interface ReconciliationItem {
  id: number
  account_id: number
  account_alias: string
  device_id: number
  device_name: string
  system_balance_snapshot: string
  actual_balance: string
  difference: string
  reason?: string
}

export interface AlipayReconciliation {
  id: number
  business_date: string
  status: 'DRAFT' | 'CONFIRMED' | 'REVERSED'
  note?: string
  created_by: number
  confirmed_by?: number
  confirmed_at?: string
  reversed_by?: number
  reversed_at?: string
  items: ReconciliationItem[]
  created_at: string
}

export interface JijihongReportSummary {
  date_from: string
  date_to: string
  order_count: number
  order_amount: string
  customer_received: string
  coupon_used: string
  balance_used: string
  external_cash: string
  cost: string
  profit: string
  reconciliation_gain_loss: string
  period_net_income: string
  soft_cap_exceeded_count: number
  exhausted_account_count: number
  pool_balance: string
}

export interface JijihongDailyRow {
  business_date: string
  order_count: number
  order_amount: string
  customer_received: string
  coupon_used: string
  balance_used: string
  external_cash: string
  cost: string
  profit: string
}

export interface JijihongBreakdownRow extends Omit<JijihongDailyRow, 'business_date'> {
  group_type: 'device' | 'account' | 'operator'
  entity_id: number
  entity_name: string
}

export interface AlipayImportRow {
  id: number
  row_number: number
  raw_data?: Record<string, string>
  parsed_data?: Record<string, string | boolean | null>
  warnings?: string[]
  errors?: string[]
  status: 'READY' | 'REVIEW' | 'IMPORTED' | 'SKIPPED'
  imported_account_id?: number
}

export interface AlipayImportBatch {
  id: number
  filename: string
  file_hash: string
  sheet_name: string
  status: 'PREVIEW' | 'COMMITTED'
  total_rows: number
  ready_rows: number
  review_rows: number
  imported_rows: number
  rows: AlipayImportRow[]
  created_at: string
}
