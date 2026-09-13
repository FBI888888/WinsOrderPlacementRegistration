"""add jijihong business mode and alipay pool

Revision ID: f6a1b2c3d4e5
Revises: e54c1d87a9b2
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "e54c1d87a9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "business_mode",
            sa.String(length=20),
            server_default="FEDAICHU",
            nullable=False,
        ),
    )

    op.create_table(
        "alipay_pool_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("external_cash_soft_cap", sa.Numeric(12, 2), nullable=False),
        sa.Column("first_day_target_balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("first_day_target_tolerance", sa.Numeric(12, 2), nullable=False),
        sa.Column("max_split_accounts", sa.Integer(), nullable=False),
        sa.Column("reservation_minutes", sa.Integer(), nullable=False),
        sa.Column("default_coupon_amount", sa.Numeric(12, 2), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", name="uq_alipay_pool_settings_tenant"),
    )
    op.create_index("ix_alipay_pool_settings_tenant_id", "alipay_pool_settings", ["tenant_id"])

    op.create_table(
        "alipay_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("account_category", sa.String(length=100)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(length=500)),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "name", name="uq_alipay_devices_tenant_name"),
    )
    op.create_index("ix_alipay_devices_tenant_id", "alipay_devices", ["tenant_id"])

    op.create_table(
        "alipay_import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("sheet_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("ready_rows", sa.Integer(), nullable=False),
        sa.Column("review_rows", sa.Integer(), nullable=False),
        sa.Column("imported_rows", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "file_hash", name="uq_alipay_import_tenant_hash"),
    )
    op.create_index("ix_alipay_import_batches_tenant_id", "alipay_import_batches", ["tenant_id"])

    op.create_table(
        "alipay_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("alipay_devices.id"), nullable=False),
        sa.Column("alias", sa.String(length=100), nullable=False),
        sa.Column("login_identifier_masked", sa.String(length=255)),
        sa.Column("initial_recharge_amount", sa.Numeric(12, 2)),
        sa.Column("opening_balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("current_balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("reserved_balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("phase", sa.String(length=30), nullable=False),
        sa.Column("birthday_set_date", sa.Date()),
        sa.Column("first_used_at", sa.DateTime(timezone=True)),
        sa.Column("source_batch_id", sa.Integer(), sa.ForeignKey("alipay_import_batches.id")),
        sa.Column("source_row_number", sa.Integer()),
        sa.Column("metadata", sa.JSON()),
        sa.Column("note", sa.String(length=500)),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "tenant_id",
            "source_batch_id",
            "source_row_number",
            name="uq_alipay_accounts_import_source",
        ),
    )
    for name, columns in (
        ("ix_alipay_accounts_tenant_id", ["tenant_id"]),
        ("ix_alipay_accounts_device_id", ["device_id"]),
        ("ix_alipay_accounts_alias", ["alias"]),
        ("ix_alipay_accounts_status", ["status"]),
        ("ix_alipay_accounts_phase", ["phase"]),
        ("ix_alipay_accounts_source_batch_id", ["source_batch_id"]),
    ):
        op.create_index(name, "alipay_accounts", columns)

    op.create_table(
        "alipay_coupons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("alipay_accounts.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True)),
        sa.Column("reserved_plan_id", sa.Integer()),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "account_id", name="uq_alipay_coupon_account"),
    )
    for name, columns in (
        ("ix_alipay_coupons_tenant_id", ["tenant_id"]),
        ("ix_alipay_coupons_account_id", ["account_id"]),
        ("ix_alipay_coupons_status", ["status"]),
        ("ix_alipay_coupons_reserved_plan_id", ["reserved_plan_id"]),
    ):
        op.create_index(name, "alipay_coupons", columns)

    op.create_table(
        "order_payment_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("order_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_coupon", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_external_cash", sa.Numeric(12, 2), nullable=False),
        sa.Column("soft_cap_exceeded", sa.Boolean(), nullable=False),
        sa.Column("warning", sa.String(length=500)),
        sa.Column("algorithm_version", sa.String(length=30), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("reversed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "order_id", "revision", name="uq_payment_plan_revision"),
    )
    for name, columns in (
        ("ix_order_payment_plans_tenant_id", ["tenant_id"]),
        ("ix_order_payment_plans_order_id", ["order_id"]),
        ("ix_order_payment_plans_status", ["status"]),
    ):
        op.create_index(name, "order_payment_plans", columns)

    op.create_table(
        "order_payment_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("order_payment_plans.id"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("alipay_accounts.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("device_name_snapshot", sa.String(length=100), nullable=False),
        sa.Column("account_alias_snapshot", sa.String(length=100), nullable=False),
        sa.Column("coupon_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("external_cash_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_before", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=False),
        *_timestamps(),
    )
    for name, columns in (
        ("ix_order_payment_allocations_tenant_id", ["tenant_id"]),
        ("ix_order_payment_allocations_plan_id", ["plan_id"]),
        ("ix_order_payment_allocations_account_id", ["account_id"]),
    ):
        op.create_index(name, "order_payment_allocations", columns)

    op.create_table(
        "alipay_balance_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("alipay_accounts.id"), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id")),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("order_payment_plans.id")),
        sa.Column("allocation_id", sa.Integer(), sa.ForeignKey("order_payment_allocations.id")),
        sa.Column("entry_type", sa.String(length=30), nullable=False),
        sa.Column("balance_delta", sa.Numeric(12, 2), nullable=False),
        sa.Column("reserved_delta", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=False),
        sa.Column("reserved_after", sa.Numeric(12, 2), nullable=False),
        sa.Column("reversed_entry_id", sa.Integer(), sa.ForeignKey("alipay_balance_entries.id")),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.String(length=500)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("idempotency_key", name="uq_alipay_balance_entry_idempotency"),
    )
    for name, columns in (
        ("ix_alipay_balance_entries_tenant_id", ["tenant_id"]),
        ("ix_alipay_balance_entries_account_id", ["account_id"]),
        ("ix_alipay_balance_entries_order_id", ["order_id"]),
        ("ix_alipay_balance_entries_plan_id", ["plan_id"]),
        ("ix_alipay_balance_entries_allocation_id", ["allocation_id"]),
        ("ix_alipay_balance_entries_entry_type", ["entry_type"]),
        ("ix_alipay_balance_entries_reversed_entry_id", ["reversed_entry_id"]),
    ):
        op.create_index(name, "alipay_balance_entries", columns)

    op.create_table(
        "alipay_import_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("alipay_import_batches.id"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw_data", sa.JSON()),
        sa.Column("parsed_data", sa.JSON()),
        sa.Column("warnings", sa.JSON()),
        sa.Column("errors", sa.JSON()),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("imported_account_id", sa.Integer(), sa.ForeignKey("alipay_accounts.id")),
        *_timestamps(),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_alipay_import_rows_batch_row"),
    )
    for name, columns in (
        ("ix_alipay_import_rows_tenant_id", ["tenant_id"]),
        ("ix_alipay_import_rows_batch_id", ["batch_id"]),
        ("ix_alipay_import_rows_imported_account_id", ["imported_account_id"]),
    ):
        op.create_index(name, "alipay_import_rows", columns)


def downgrade() -> None:
    op.drop_table("alipay_import_rows")
    op.drop_table("alipay_balance_entries")
    op.drop_table("order_payment_allocations")
    op.drop_table("order_payment_plans")
    op.drop_table("alipay_coupons")
    op.drop_table("alipay_accounts")
    op.drop_table("alipay_import_batches")
    op.drop_table("alipay_devices")
    op.drop_table("alipay_pool_settings")
    op.drop_column("tenants", "business_mode")
