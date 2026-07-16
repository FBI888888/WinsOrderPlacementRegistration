from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantOwnedMixin, TimestampMixin


class OrderStatus(StrEnum):
    DRAFT = "DRAFT"
    DISPATCHED = "DISPATCHED"
    SUCCESS = "SUCCESS"
    CANCELLED = "CANCELLED"
    REVERSED = "REVERSED"


class Order(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("tenant_id", "order_no", name="uq_orders_tenant_no"),)

    order_no: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    business_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    contractor_id: Mapped[int] = mapped_column(ForeignKey("contractors.id"), nullable=False, index=True)
    contractor_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    contractor_name_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    student_name: Mapped[str | None] = mapped_column(String(100))

    order_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    coupon_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    actual_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    settlement_basis_snapshot: Mapped[str] = mapped_column(String(30), nullable=False)
    discount_snapshot: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    settlement_income: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    income_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    income_override_reason: Mapped[str | None] = mapped_column(String(300))
    commission: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    commission_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    commission_override_reason: Mapped[str | None] = mapped_column(String(300))
    cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    profit: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    note: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))