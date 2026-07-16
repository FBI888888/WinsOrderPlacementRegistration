from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.modules.orders.models import OrderStatus
from app.modules.partners.models import ContractorType


class OrderCreate(BaseModel):
    business_date: date = Field(default_factory=date.today)
    source_id: int
    contractor_type: ContractorType
    contractor_id: int | None = None
    retail_name: str | None = Field(default=None, max_length=100)
    student_name: str | None = Field(default=None, max_length=100)
    order_amount: Decimal = Field(gt=0)
    coupon_amount: Decimal = Field(default=Decimal("0"), ge=0)
    actual_paid: Decimal = Field(ge=0)
    settlement_income_override: Decimal | None = Field(default=None, ge=0)
    income_override_reason: str | None = Field(default=None, max_length=300)
    commission_override: Decimal | None = Field(default=None, ge=0)
    commission_override_reason: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=500)
    status: OrderStatus = OrderStatus.DRAFT

    @model_validator(mode="after")
    def validate_assignment(self):
        if self.contractor_type == ContractorType.LEADER:
            if not self.contractor_id or self.retail_name:
                raise ValueError("学生头子订单必须选择学生头子")
        elif not self.retail_name or self.contractor_id:
            raise ValueError("散户订单必须填写散户姓名")
        if self.settlement_income_override is not None and not self.income_override_reason:
            raise ValueError("覆盖结算收入时必须填写原因")
        if self.commission_override is not None and not self.commission_override_reason:
            raise ValueError("覆盖佣金时必须填写原因")
        if self.contractor_type == ContractorType.RETAIL and self.commission_override is None:
            raise ValueError("散户订单必须填写佣金")
        if self.status in (OrderStatus.CANCELLED, OrderStatus.REVERSED):
            raise ValueError("新订单不能直接设为取消或冲正")
        return self


class OrderUpdate(BaseModel):
    business_date: date | None = None
    source_id: int | None = None
    contractor_type: ContractorType | None = None
    contractor_id: int | None = None
    retail_name: str | None = Field(default=None, max_length=100)
    student_name: str | None = Field(default=None, max_length=100)
    order_amount: Decimal | None = Field(default=None, gt=0)
    coupon_amount: Decimal | None = Field(default=None, ge=0)
    actual_paid: Decimal | None = Field(default=None, ge=0)
    settlement_income_override: Decimal | None = Field(default=None, ge=0)
    income_override_reason: str | None = Field(default=None, max_length=300)
    commission_override: Decimal | None = Field(default=None, ge=0)
    commission_override_reason: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=500)


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    reason: str | None = Field(default=None, max_length=300)


class OrderOutput(BaseModel):
    id: int
    order_no: str
    business_date: date
    status: str
    source_id: int
    source_name: str
    contractor_id: int
    contractor_type: str
    contractor_name: str
    student_name: str | None
    order_amount: Decimal
    coupon_amount: Decimal
    actual_paid: Decimal
    settlement_basis_snapshot: str
    discount_snapshot: Decimal
    settlement_income: Decimal
    income_overridden: bool
    commission: Decimal
    commission_overridden: bool
    cost: Decimal
    profit: Decimal
    note: str | None
    success_at: datetime | None
    created_at: datetime


class OrderListOutput(BaseModel):
    items: list[OrderOutput]
    total: int
    page: int
    page_size: int