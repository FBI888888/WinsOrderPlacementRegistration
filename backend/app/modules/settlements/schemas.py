from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.settlements.models import SettlementType


class SettlementCreate(BaseModel):
    settlement_type: SettlementType
    date_from: date
    date_to: date
    source_id: int | None = None
    contractor_id: int | None = None
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_target(self):
        if self.date_from > self.date_to:
            raise ValueError("开始日期不能晚于结束日期")
        if self.settlement_type == SettlementType.SOURCE:
            if not self.source_id or self.contractor_id:
                raise ValueError("放单结算必须选择放单人员")
        elif not self.contractor_id or self.source_id:
            raise ValueError("做单结算必须选择学生头子或散户")
        return self


class ClearingRequest(BaseModel):
    settlement_type: SettlementType
    counterparty_id: int
    business_date: date = Field(default_factory=date.today)
    note: str | None = Field(default=None, max_length=500)


class BatchClearingRequest(BaseModel):
    business_date: date = Field(default_factory=date.today)
    note: str | None = Field(default=None, max_length=500)


class ClearingPreviewItem(BaseModel):
    settlement_type: SettlementType
    counterparty_id: int
    counterparty_name: str
    account: str
    balance: Decimal


class SettlementAction(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class SettlementOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    settlement_no: str
    settlement_type: str
    status: str
    date_from: date
    date_to: date
    source_id: int | None
    contractor_id: int | None
    counterparty_name_snapshot: str
    order_count: int
    order_amount_total: Decimal
    actual_paid_total: Decimal
    commission_total: Decimal
    settlement_income_total: Decimal
    profit_total: Decimal
    account_balance_snapshot: Decimal
    account: str | None
    settled_amount: Decimal
    note: str | None
    confirmed_at: datetime | None
    reversed_at: datetime | None
    reversal_reason: str | None
    created_at: datetime