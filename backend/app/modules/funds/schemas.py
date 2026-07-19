from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.funds.models import LedgerAccount, LedgerEntryType


class ManualTransactionType(StrEnum):
    ADVANCE_TOPUP = "ADVANCE_TOPUP"
    ADVANCE_RETURN = "ADVANCE_RETURN"
    COMMISSION_PAYMENT = "COMMISSION_PAYMENT"
    SOURCE_RECEIPT = "SOURCE_RECEIPT"


class TransactionCreate(BaseModel):
    business_date: date = Field(default_factory=date.today)
    transaction_type: ManualTransactionType
    amount: Decimal = Field(gt=0)
    contractor_id: int | None = None
    source_id: int | None = None
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_counterparty(self):
        if self.transaction_type == ManualTransactionType.SOURCE_RECEIPT:
            if not self.source_id or self.contractor_id:
                raise ValueError("放单收款必须选择放单人员")
        elif not self.contractor_id or self.source_id:
            raise ValueError("做单资金流水必须选择做单方")
        return self


class LedgerOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_date: date
    account: str
    entry_type: str
    amount: Decimal
    advance_balance_snapshot: Decimal | None
    commission_payable_snapshot: Decimal | None
    net_settlement_snapshot: Decimal | None
    source_receivable_snapshot: Decimal | None
    contractor_id: int | None
    source_id: int | None
    order_id: int | None
    settlement_id: int | None
    reversed_entry_id: int | None
    note: str | None
    created_by: int
    created_at: datetime


class BalanceOutput(BaseModel):
    account: LedgerAccount
    counterparty_id: int
    counterparty_name: str
    balance: Decimal