from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.alipay_pool.models import AccountPhase, AccountStatus


class PoolSettingsUpdate(BaseModel):
    external_cash_soft_cap: Decimal | None = Field(default=None, ge=0)
    first_day_target_balance: Decimal | None = Field(default=None, ge=0)
    first_day_target_tolerance: Decimal | None = Field(default=None, ge=0)
    max_split_accounts: int | None = Field(default=None, ge=1, le=5)
    reservation_minutes: int | None = Field(default=None, ge=1, le=240)
    default_coupon_amount: Decimal | None = Field(default=None, gt=0)


class PoolSettingsOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    external_cash_soft_cap: Decimal
    first_day_target_balance: Decimal
    first_day_target_tolerance: Decimal
    max_split_accounts: int
    reservation_minutes: int
    default_coupon_amount: Decimal


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    account_category: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    account_category: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None
    note: str | None = Field(default=None, max_length=500)


class DeviceOutput(BaseModel):
    id: int
    name: str
    account_category: str | None
    is_active: bool
    note: str | None
    active_account_count: int
    capacity_warning: bool
    created_at: datetime


class AccountCreate(BaseModel):
    device_id: int
    alias: str = Field(min_length=1, max_length=100)
    login_identifier_masked: str | None = Field(default=None, max_length=255)
    initial_recharge_amount: Decimal | None = Field(default=None, ge=0)
    current_balance: Decimal = Field(ge=0)
    status: AccountStatus = AccountStatus.ACTIVE
    phase: AccountPhase = AccountPhase.NOT_STARTED
    birthday_set_date: date | None = None
    create_coupon: bool = True
    note: str | None = Field(default=None, max_length=500)


class AccountUpdate(BaseModel):
    device_id: int | None = None
    alias: str | None = Field(default=None, min_length=1, max_length=100)
    login_identifier_masked: str | None = Field(default=None, max_length=255)
    status: AccountStatus | None = None
    phase: AccountPhase | None = None
    birthday_set_date: date | None = None
    note: str | None = Field(default=None, max_length=500)


class BalanceAdjustmentInput(BaseModel):
    amount: Decimal
    reason: str = Field(min_length=2, max_length=500)

    @model_validator(mode="after")
    def non_zero(self):
        if self.amount == 0:
            raise ValueError("调整金额不能为0")
        return self


class AccountOutput(BaseModel):
    id: int
    device_id: int
    device_name: str
    alias: str
    login_identifier_masked: str | None
    initial_recharge_amount: Decimal | None
    opening_balance: Decimal
    current_balance: Decimal
    reserved_balance: Decimal
    available_balance: Decimal
    status: str
    phase: str
    birthday_set_date: date | None
    coupon_status: str | None
    coupon_amount: Decimal | None
    coupon_available_at: datetime | None
    note: str | None
    created_at: datetime


class AllocationOutput(BaseModel):
    id: int
    account_id: int
    sequence: int
    device_name: str
    account_alias: str
    coupon_amount: Decimal
    balance_amount: Decimal
    external_cash_amount: Decimal
    balance_before: Decimal
    balance_after: Decimal


class PaymentPlanOutput(BaseModel):
    id: int
    order_id: int
    revision: int
    status: str
    order_amount: Decimal
    total_coupon: Decimal
    total_balance: Decimal
    total_external_cash: Decimal
    soft_cap_exceeded: bool
    warning: str | None
    expires_at: datetime
    confirmed_at: datetime | None
    allocations: list[AllocationOutput]


class ConfirmAllocationInput(BaseModel):
    account_id: int
    coupon_amount: Decimal = Field(default=Decimal("0"), ge=0)
    balance_amount: Decimal = Field(default=Decimal("0"), ge=0)
    external_cash_amount: Decimal = Field(default=Decimal("0"), ge=0)


class ConfirmPlanInput(BaseModel):
    allocations: list[ConfirmAllocationInput] | None = None


class ImportRowOutput(BaseModel):
    id: int
    row_number: int
    raw_data: dict | None
    parsed_data: dict | None
    warnings: list | None
    errors: list | None
    status: str
    imported_account_id: int | None


class ImportBatchOutput(BaseModel):
    id: int
    filename: str
    file_hash: str
    sheet_name: str
    status: str
    total_rows: int
    ready_rows: int
    review_rows: int
    imported_rows: int
    rows: list[ImportRowOutput]
    created_at: datetime


class ImportCommitInput(BaseModel):
    row_ids: list[int] | None = None


class ImportRowUpdate(BaseModel):
    parsed_data: dict


class BalanceEntryOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    order_id: int | None
    plan_id: int | None
    entry_type: str
    balance_delta: Decimal
    reserved_delta: Decimal
    balance_after: Decimal
    reserved_after: Decimal
    reason: str | None
    created_at: datetime


class SuggestedAllocationOutput(BaseModel):
    account_id: int
    device_name: str
    account_alias: str
    coupon_amount: Decimal
    balance_amount: Decimal
    external_cash_amount: Decimal
    balance_before: Decimal
    balance_after: Decimal


class RecommendationPreviewInput(BaseModel):
    order_amount: Decimal = Field(gt=0)


class RecommendationPreviewOutput(BaseModel):
    order_amount: Decimal
    total_coupon: Decimal
    total_balance: Decimal
    total_external_cash: Decimal
    soft_cap_exceeded: bool
    warning: str | None
    allocations: list[SuggestedAllocationOutput]


class SelectedAllocationInput(BaseModel):
    account_id: int
    coupon_amount: Decimal = Field(default=Decimal("0"), ge=0)
    balance_amount: Decimal = Field(default=Decimal("0"), ge=0)
    external_cash_amount: Decimal = Field(default=Decimal("0"), ge=0)


class JijihongOrderCreateInput(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=64)
    business_date: date = Field(default_factory=date.today)
    order_amount: Decimal = Field(gt=0)
    customer_received_amount: Decimal | None = Field(default=None, ge=0)
    allocations: list[SelectedAllocationInput] = Field(min_length=1, max_length=5)
    external_cash_override_reason: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_allocations(self):
        account_ids = [item.account_id for item in self.allocations]
        if len(account_ids) != len(set(account_ids)):
            raise ValueError("支付方案中的支付宝账号不能重复")
        return self


class JijihongOrderReservationInput(BaseModel):
    order_amount: Decimal = Field(gt=0)
    customer_received_amount: Decimal = Field(ge=0)
    allocations: list[SelectedAllocationInput] = Field(min_length=1, max_length=5)
    external_cash_override_reason: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_allocations(self):
        account_ids = [item.account_id for item in self.allocations]
        if len(account_ids) != len(set(account_ids)):
            raise ValueError("支付方案中的支付宝账号不能重复")
        return self


class JijihongOrderCreateOutput(BaseModel):
    order: dict
    payment_plan: PaymentPlanOutput


class FinancialEntryOutput(BaseModel):
    id: int
    business_date: date
    order_id: int | None
    plan_id: int | None
    account_id: int | None
    account_alias: str | None
    device_id: int | None
    device_name: str | None
    entry_type: str
    amount: Decimal
    note: str | None
    created_at: datetime


class FinancialEntryListOutput(BaseModel):
    items: list[FinancialEntryOutput]
    total: int
    page: int
    page_size: int


class AccountBalanceEntryOutput(BalanceEntryOutput):
    account_alias: str
    device_id: int
    device_name: str


class AccountBalanceEntryListOutput(BaseModel):
    items: list[AccountBalanceEntryOutput]
    total: int
    page: int
    page_size: int


class FundsSummaryOutput(BaseModel):
    current_balance: Decimal
    reserved_balance: Decimal
    available_balance: Decimal
    customer_receipts: Decimal
    balance_cost: Decimal
    external_cash_cost: Decimal
    reconciliation_gain_loss: Decimal
    order_profit: Decimal
    period_net_income: Decimal


class ReconciliationItemInput(BaseModel):
    account_id: int
    actual_balance: Decimal = Field(ge=0)
    reason: str | None = Field(default=None, max_length=500)


class ReconciliationCreateInput(BaseModel):
    business_date: date = Field(default_factory=date.today)
    note: str | None = Field(default=None, max_length=500)
    items: list[ReconciliationItemInput] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_accounts(self):
        ids = [item.account_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("同一盘点单不能重复选择账号")
        return self


class ReconciliationItemOutput(BaseModel):
    id: int
    account_id: int
    account_alias: str
    device_id: int
    device_name: str
    system_balance_snapshot: Decimal
    actual_balance: Decimal
    difference: Decimal
    reason: str | None


class ReconciliationOutput(BaseModel):
    id: int
    business_date: date
    status: str
    note: str | None
    created_by: int
    confirmed_by: int | None
    confirmed_at: datetime | None
    reversed_by: int | None
    reversed_at: datetime | None
    items: list[ReconciliationItemOutput]
    created_at: datetime
