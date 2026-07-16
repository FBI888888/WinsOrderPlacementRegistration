from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.partners.models import ContractorType, PerformerType, SettlementBasis


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    contact: str | None = Field(default=None, max_length=100)
    default_basis: SettlementBasis = SettlementBasis.ORDER_AMOUNT
    default_discount: Decimal = Field(default=Decimal("0.9"), gt=0, le=1)
    note: str | None = Field(default=None, max_length=500)
    effective_date: date = Field(default_factory=date.today)


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    contact: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None
    note: str | None = Field(default=None, max_length=500)


class SourceRateCreate(BaseModel):
    effective_date: date
    settlement_basis: SettlementBasis
    discount: Decimal = Field(gt=0, le=1)


class SourceOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    contact: str | None
    default_basis: str
    default_discount: Decimal
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
    discount: Decimal
    contractor_id: int
    commission: Decimal