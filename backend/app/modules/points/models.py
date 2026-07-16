from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantOwnedMixin, TimestampMixin


class PointEntryType(StrEnum):
    ORDER_EARN = "ORDER_EARN"
    ORDER_REVERSAL = "ORDER_REVERSAL"
    COUPON_REDEMPTION = "COUPON_REDEMPTION"


class PointEntry(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "point_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "event_key", name="uq_point_entries_event_key"),
    )

    business_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    performer_id: Mapped[int] = mapped_column(
        ForeignKey("performers.id"), nullable=False, index=True
    )
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    reversed_entry_id: Mapped[int | None] = mapped_column(ForeignKey("point_entries.id"))
    event_key: Mapped[str] = mapped_column(String(100), nullable=False)
    coupon_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    note: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)