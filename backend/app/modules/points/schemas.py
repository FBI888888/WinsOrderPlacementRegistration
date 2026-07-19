from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PointAccountOutput(BaseModel):
    performer_id: int
    performer_name: str
    performer_type: str
    contractor_id: int
    contractor_name: str
    is_listed: bool
    is_active: bool
    balance: Decimal
    available_coupons: int


class PointEntryOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_date: date
    performer_id: int
    entry_type: str
    amount: Decimal
    order_id: int | None
    coupon_value: Decimal | None
    note: str | None
    created_by: int
    created_at: datetime


class RedeemCouponInput(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class RedeemCouponOutput(BaseModel):
    entry: PointEntryOutput
    balance: Decimal
    available_coupons: int


class PendingPointOrderOutput(BaseModel):
    id: int
    order_no: str
    business_date: date
    contractor_id: int
    contractor_name: str
    order_amount: Decimal
    created_at: datetime
