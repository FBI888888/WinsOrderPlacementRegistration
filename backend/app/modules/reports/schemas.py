from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DashboardSummary(BaseModel):
    business_mode: str = "FEDAICHU"
    date_from: date
    date_to: date
    order_count: int
    success_count: int
    settlement_income: Decimal
    cost: Decimal
    profit: Decimal
    advance_balance: Decimal
    commission_payable: Decimal
    source_receivable: Decimal
    negative_profit_count: int
    customer_received: Decimal | None = None
    coupon_used: Decimal | None = None
    balance_used: Decimal | None = None
    external_cash: Decimal | None = None
    pool_balance: Decimal | None = None
    reconciliation_gain_loss: Decimal | None = None
    period_net_income: Decimal | None = None


class PerformanceSummary(BaseModel):
    date_from: date
    date_to: date
    order_count: int
    order_amount: Decimal
    coupon_amount: Decimal
    actual_paid: Decimal
    settlement_income: Decimal
    cost: Decimal
    commission: Decimal
    profit: Decimal
    negative_profit_count: int


class PerformanceDailyRow(BaseModel):
    business_date: date
    order_count: int
    order_amount: Decimal
    coupon_amount: Decimal
    actual_paid: Decimal
    settlement_income: Decimal
    cost: Decimal
    commission: Decimal
    profit: Decimal
    negative_profit_count: int


class PerformanceGroupRow(BaseModel):
    group_type: str
    entity_id: int
    entity_name: str
    order_count: int
    order_amount: Decimal
    coupon_amount: Decimal
    actual_paid: Decimal
    settlement_income: Decimal
    cost: Decimal
    commission: Decimal
    profit: Decimal


class PerformanceReport(BaseModel):
    summary: PerformanceSummary
    sources: list[PerformanceGroupRow]
    leaders: list[PerformanceGroupRow]
    retails: list[PerformanceGroupRow]
    performers: list[PerformanceGroupRow]


class ExportTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    fields: list[str] = Field(min_length=1)
    filters: dict | None = None


class ExportTemplateOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    fields: list[str]
    filters: dict | None
    created_at: datetime


class ExportLogOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    export_format: str
    filters: dict | None
    fields: list[str]
    row_count: int
    file_hash: str
    created_at: datetime


class JijihongReportSummary(BaseModel):
    date_from: date
    date_to: date
    order_count: int
    order_amount: Decimal
    customer_received: Decimal
    coupon_used: Decimal
    balance_used: Decimal
    external_cash: Decimal
    cost: Decimal
    profit: Decimal
    reconciliation_gain_loss: Decimal
    period_net_income: Decimal
    soft_cap_exceeded_count: int
    exhausted_account_count: int
    pool_balance: Decimal


class JijihongDailyRow(BaseModel):
    business_date: date
    order_count: int
    order_amount: Decimal
    customer_received: Decimal
    coupon_used: Decimal
    balance_used: Decimal
    external_cash: Decimal
    cost: Decimal
    profit: Decimal


class JijihongBreakdownRow(BaseModel):
    group_type: str
    entity_id: int
    entity_name: str
    order_count: int
    order_amount: Decimal
    customer_received: Decimal
    coupon_used: Decimal
    balance_used: Decimal
    external_cash: Decimal
    cost: Decimal
    profit: Decimal
