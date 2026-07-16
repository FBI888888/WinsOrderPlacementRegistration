from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DashboardSummary(BaseModel):
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