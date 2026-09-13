from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantOwnedMixin, TimestampMixin


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    EXHAUSTED = "EXHAUSTED"


class AccountPhase(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    DAY1_ACTIVE = "DAY1_ACTIVE"
    WAITING_COUPON = "WAITING_COUPON"
    DAY2_ACTIVE = "DAY2_ACTIVE"
    EXHAUSTED = "EXHAUSTED"


class CouponStatus(StrEnum):
    PENDING = "PENDING"
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    USED = "USED"
    EXPIRED = "EXPIRED"


class PaymentPlanStatus(StrEnum):
    RESERVED = "RESERVED"
    CONFIRMED = "CONFIRMED"
    RELEASED = "RELEASED"
    REVERSED = "REVERSED"
    EXPIRED = "EXPIRED"


class BalanceEntryType(StrEnum):
    IMPORT_OPENING = "IMPORT_OPENING"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"
    RESERVE = "RESERVE"
    RELEASE = "RELEASE"
    CONFIRM = "CONFIRM"
    REVERSAL = "REVERSAL"
    RECONCILIATION_ADJUSTMENT = "RECONCILIATION_ADJUSTMENT"


class FinancialEntryType(StrEnum):
    CUSTOMER_RECEIPT = "CUSTOMER_RECEIPT"
    BALANCE_COST = "BALANCE_COST"
    EXTERNAL_CASH_COST = "EXTERNAL_CASH_COST"
    RECONCILIATION_GAIN_LOSS = "RECONCILIATION_GAIN_LOSS"
    REVERSAL = "REVERSAL"


class ReconciliationStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    REVERSED = "REVERSED"


class ImportBatchStatus(StrEnum):
    PREVIEW = "PREVIEW"
    COMMITTED = "COMMITTED"


class ImportRowStatus(StrEnum):
    READY = "READY"
    REVIEW = "REVIEW"
    IMPORTED = "IMPORTED"
    SKIPPED = "SKIPPED"


class AlipayPoolSettings(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "alipay_pool_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_alipay_pool_settings_tenant"),
    )

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    external_cash_soft_cap: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("8"), nullable=False
    )
    first_day_target_balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("100"), nullable=False
    )
    first_day_target_tolerance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("8"), nullable=False
    )
    max_split_accounts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    reservation_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    default_coupon_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("20"), nullable=False
    )


class AlipayDevice(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "alipay_devices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_alipay_devices_tenant_name"),
    )

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_category: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))


class AlipayImportBatch(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "alipay_import_batches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "file_hash", name="uq_alipay_import_tenant_hash"),
    )

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ready_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    review_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AlipayImportRow(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "alipay_import_rows"
    __table_args__ = (
        UniqueConstraint("batch_id", "row_number", name="uq_alipay_import_rows_batch_row"),
    )

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("alipay_import_batches.id"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict | None] = mapped_column(JSON)
    parsed_data: Mapped[dict | None] = mapped_column(JSON)
    warnings: Mapped[list | None] = mapped_column(JSON)
    errors: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    imported_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("alipay_accounts.id"), index=True
    )


class AlipayAccount(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "alipay_accounts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_batch_id", "source_row_number",
            name="uq_alipay_accounts_import_source",
        ),
    )

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("alipay_devices.id"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    login_identifier_masked: Mapped[str | None] = mapped_column(String(255))
    initial_recharge_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reserved_balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    phase: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    birthday_set_date: Mapped[date | None] = mapped_column(Date)
    first_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("alipay_import_batches.id"), index=True
    )
    source_row_number: Mapped[int | None] = mapped_column(Integer)
    extra_data: Mapped[dict | None] = mapped_column("metadata", JSON)
    note: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AlipayCoupon(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "alipay_coupons"
    __table_args__ = (
        UniqueConstraint("tenant_id", "account_id", name="uq_alipay_coupon_account"),
    )

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("alipay_accounts.id"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reserved_plan_id: Mapped[int | None] = mapped_column(Integer, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrderPaymentPlan(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "order_payment_plans"
    __table_args__ = (
        UniqueConstraint("tenant_id", "order_id", "revision", name="uq_payment_plan_revision"),
    )

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    order_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_coupon: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_external_cash: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    soft_cap_exceeded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    warning: Mapped[str | None] = mapped_column(String(500))
    algorithm_version: Mapped[str] = mapped_column(String(30), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)


class OrderPaymentAllocation(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "order_payment_allocations"

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("order_payment_plans.id"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("alipay_accounts.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    device_name_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    account_alias_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    coupon_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    external_cash_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)


class AlipayBalanceEntry(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "alipay_balance_entries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_alipay_balance_entry_idempotency"),
    )

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("alipay_accounts.id"), nullable=False, index=True
    )
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("order_payment_plans.id"), index=True)
    reconciliation_id: Mapped[int | None] = mapped_column(ForeignKey("alipay_reconciliations.id"), index=True)
    allocation_id: Mapped[int | None] = mapped_column(
        ForeignKey("order_payment_allocations.id"), index=True
    )
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    balance_delta: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reserved_delta: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reserved_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reversed_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("alipay_balance_entries.id"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)


class JijihongFinancialEntry(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "jijihong_financial_entries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_jijihong_financial_entry_idempotency"),
    )

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    business_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("order_payment_plans.id"), index=True)
    reconciliation_id: Mapped[int | None] = mapped_column(
        ForeignKey("alipay_reconciliations.id"), index=True
    )
    allocation_id: Mapped[int | None] = mapped_column(ForeignKey("order_payment_allocations.id"), index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("alipay_accounts.id"), index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("alipay_devices.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reversed_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("jijihong_financial_entries.id"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)


class AlipayReconciliation(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "alipay_reconciliations"

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    business_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AlipayReconciliationItem(Base, IdMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "alipay_reconciliation_items"
    __table_args__ = (
        UniqueConstraint("reconciliation_id", "account_id", name="uq_alipay_reconciliation_account"),
    )

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    reconciliation_id: Mapped[int] = mapped_column(
        ForeignKey("alipay_reconciliations.id"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(ForeignKey("alipay_accounts.id"), nullable=False, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("alipay_devices.id"), nullable=False, index=True)
    system_balance_snapshot: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    actual_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    difference: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    adjustment_entry_id: Mapped[int | None] = mapped_column(ForeignKey("alipay_balance_entries.id"))
