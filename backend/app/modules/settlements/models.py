from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantOwnedMixin, TimestampMixin


class SettlementType(StrEnum):
    SOURCE = "SOURCE"
    CONTRACTOR = "CONTRACTOR"


class SettlementStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    REVERSED = "REVERSED"


class Settlement(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "settlements"
    __table_args__ = (UniqueConstraint("tenant_id", "settlement_no", name="uq_settlements_tenant_no"),)

    settlement_no: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    settlement_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), index=True)
    contractor_id: Mapped[int | None] = mapped_column(ForeignKey("contractors.id"), index=True)
    counterparty_name_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    order_count: Mapped[int] = mapped_column(default=0, nullable=False)
    order_amount_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    actual_paid_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    commission_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    settlement_income_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    profit_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    account_balance_snapshot: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str | None] = mapped_column(String(300))


class SettlementItem(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "settlement_items"
    __table_args__ = (
        UniqueConstraint("settlement_id", "order_id", name="uq_settlement_items_order"),
    )

    settlement_id: Mapped[int] = mapped_column(ForeignKey("settlements.id"), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)