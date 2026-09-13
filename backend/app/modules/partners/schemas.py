from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.partners.models import ContractorType, PerformerType, SettlementBasis, SettlementMethod


def _normalize_settlement(
    *,
    method: SettlementMethod,
    discount: Decimal | None,
    fixed_deduction: Decimal | None,
    require_discount: bool,
) -> tuple[Decimal, Decimal]:
    if method == SettlementMethod.FIXED_DEDUCTION:
        deduction = Decimal("10") if fixed_deduction is None else Decimal(fixed_deduction)
        if deduction < 0:
            raise ValueError("固定减额不能为负数")
        return Decimal("1"), deduction
    if discount is None:
        if require_discount:
            raise ValueError("折扣方式必须填写折扣")
        discount = Decimal("0.9")
    if discount <= 0 or discount > 1:
        raise ValueError("折扣必须大于0且不超过1")
    return Decimal(discount), Decimal("0")


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    contact: str | None = Field(default=None, max_length=100)
    default_basis: SettlementBasis = SettlementBasis.ORDER_AMOUNT
    default_settlement_method: SettlementMethod = SettlementMethod.DISCOUNT
    default_discount: Decimal | None = None
    default_fixed_deduction: Decimal | None = None
    note: str | None = Field(default=None, max_length=500)
    effective_date: date = Field(default_factory=date.today)

    @model_validator(mode="after")
    def normalize_settlement(self):
        discount, deduction = _normalize_settlement(
            method=self.default_settlement_method,
            discount=self.default_discount,
            fixed_deduction=self.default_fixed_deduction,
            require_discount=False,
        )
        self.default_discount = discount
        self.default_fixed_deduction = deduction
        return self


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    contact: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None
    note: str | None = Field(default=None, max_length=500)


class SourceRateCreate(BaseModel):
    effective_date: date
    settlement_basis: SettlementBasis
    settlement_method: SettlementMethod = SettlementMethod.DISCOUNT
    discount: Decimal | None = None
    fixed_deduction: Decimal | None = None

    @model_validator(mode="after")
    def normalize_settlement(self):
        discount, deduction = _normalize_settlement(
            method=self.settlement_method,
            discount=self.discount,
            fixed_deduction=self.fixed_deduction,
            require_discount=True,
        )
        self.discount = discount
        self.fixed_deduction = deduction
        return self


class SourceOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    contact: str | None
    default_basis: str
    default_settlement_method: str
    default_discount: Decimal
    default_fixed_deduction: Decimal
    is_active: bool
    note: str | None
    created_at: datetime


class ContractorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    contractor_type: ContractorType = ContractorType.LEADER
    contact: str | None = Field(default=None, max_length=100)
    default_commission: Decimal = Field(default=Decimal("0"), ge=0)
    note: str | None = Field(default=None, max_length=500)
    effective_date: date = Field(default_factory=date.today)


class ContractorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    contact: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None
    note: str | None = Field(default=None, max_length=500)


class ContractorRateCreate(BaseModel):
    effective_date: date
    commission_per_order: Decimal = Field(ge=0)


class ContractorOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    contractor_type: str
    contact: str | None
    default_commission: Decimal
    is_active: bool
    note: str | None
    created_at: datetime


class PerformerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    performer_type: PerformerType
    contractor_id: int
    is_listed: bool = True
    note: str | None = Field(default=None, max_length=500)


class PerformerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_listed: bool | None = None
    is_active: bool | None = None
    note: str | None = Field(default=None, max_length=500)


class PerformerOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    performer_type: str
    contractor_id: int
    is_listed: bool
    is_active: bool
    note: str | None
    created_at: datetime


class RateSnapshot(BaseModel):
    source_id: int
    settlement_basis: SettlementBasis
    settlement_method: SettlementMethod = SettlementMethod.DISCOUNT
    discount: Decimal
    fixed_deduction: Decimal = Decimal("0")
    contractor_id: int
    commission: Decimal