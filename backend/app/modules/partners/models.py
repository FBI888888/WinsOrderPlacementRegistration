from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantOwnedMixin, TimestampMixin


class SettlementBasis(StrEnum):
    ORDER_AMOUNT = "ORDER_AMOUNT"
    AFTER_COUPON = "AFTER_COUPON"


class ContractorType(StrEnum):
    LEADER = "LEADER"
    RETAIL = "RETAIL"


class Source(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_sources_tenant_name"),)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    contact: Mapped[str | None] = mapped_column(String(100))
    default_basis: Mapped[str] = mapped_column(String(30), nullable=False)
    default_discount: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))


class SourceRate(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "source_rates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_id", "effective_date", name="uq_source_rates_effective"),
    )

    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    settlement_basis: Mapped[str] = mapped_column(String(30), nullable=False)
    discount: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)


class Contractor(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "contractors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "contractor_type", "normalized_name", name="uq_contractors_identity"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(100), nullable=False)
    contractor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    contact: Mapped[str | None] = mapped_column(String(100))
    default_commission: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))


class ContractorRate(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "contractor_rates"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "contractor_id", "effective_date", name="uq_contractor_rates_effective"
        ),
    )

    contractor_id: Mapped[int] = mapped_column(ForeignKey("contractors.id"), nullable=False, index=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    commission_per_order: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)