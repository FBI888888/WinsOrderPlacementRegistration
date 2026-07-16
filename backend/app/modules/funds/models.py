from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantOwnedMixin, TimestampMixin


class LedgerAccount(StrEnum):
    ADVANCE = "ADVANCE"
    COMMISSION_PAYABLE = "COMMISSION_PAYABLE"
    SOURCE_RECEIVABLE = "SOURCE_RECEIVABLE"


class LedgerEntryType(StrEnum):
    ADVANCE_TOPUP = "ADVANCE_TOPUP"
    ORDER_PAYMENT = "ORDER_PAYMENT"
    ADVANCE_RETURN = "ADVANCE_RETURN"
    COMMISSION_ACCRUAL = "COMMISSION_ACCRUAL"
    COMMISSION_PAYMENT = "COMMISSION_PAYMENT"
    SOURCE_ACCRUAL = "SOURCE_ACCRUAL"
    SOURCE_RECEIPT = "SOURCE_RECEIPT"
    REVERSAL = "REVERSAL"


class LedgerEntry(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "ledger_entries"

    business_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    account: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    entry_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    contractor_id: Mapped[int | None] = mapped_column(ForeignKey("contractors.id"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    reversed_entry_id: Mapped[int | None] = mapped_column(ForeignKey("ledger_entries.id"))
    note: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)