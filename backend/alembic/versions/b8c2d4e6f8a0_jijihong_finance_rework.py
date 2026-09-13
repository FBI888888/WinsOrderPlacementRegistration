"""jijihong finance rework

Revision ID: b8c2d4e6f8a0
Revises: f6a1b2c3d4e5
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8c2d4e6f8a0"
down_revision: str | Sequence[str] | None = "f6a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def _backfill_confirmed_order_finance() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    orders = sa.Table("orders", metadata, autoload_with=bind)
    tenants = sa.Table("tenants", metadata, autoload_with=bind)
    plans = sa.Table("order_payment_plans", metadata, autoload_with=bind)
    allocations = sa.Table("order_payment_allocations", metadata, autoload_with=bind)
    accounts = sa.Table("alipay_accounts", metadata, autoload_with=bind)
    financial = sa.Table("jijihong_financial_entries", metadata, autoload_with=bind)
    rows = bind.execute(
        sa.select(
            orders.c.id.label("order_id"),
            orders.c.tenant_id,
            orders.c.business_date,
            orders.c.order_no,
            orders.c.order_amount,
            orders.c.customer_received_amount,
            orders.c.created_by,
            plans.c.id.label("plan_id"),
            allocations.c.id.label("allocation_id"),
            allocations.c.account_id,
            allocations.c.balance_amount,
            allocations.c.external_cash_amount,
            accounts.c.device_id,
        )
        .select_from(
            orders.join(tenants, tenants.c.id == orders.c.tenant_id)
            .join(
                plans,
                (plans.c.order_id == orders.c.id) & (plans.c.status == "CONFIRMED"),
            )
            .join(allocations, allocations.c.plan_id == plans.c.id)
            .join(accounts, accounts.c.id == allocations.c.account_id)
        )
        .where(
            tenants.c.business_mode == "JIJIHONG",
            orders.c.status == "SUCCESS",
        )
        .order_by(orders.c.id, allocations.c.id)
    ).mappings()
    seen_orders: set[int] = set()
    for row in rows:
        common = {
            "tenant_id": row["tenant_id"],
            "business_date": row["business_date"],
            "order_id": row["order_id"],
            "plan_id": row["plan_id"],
            "created_by": row["created_by"],
        }
        if row["order_id"] not in seen_orders:
            bind.execute(
                financial.insert().values(
                    **common,
                    entry_type="CUSTOMER_RECEIPT",
                    amount=row["customer_received_amount"] or row["order_amount"],
                    idempotency_key=f"order:{row['order_id']}:customer-receipt",
                    note=f"订单 {row['order_no']} 客户实收（历史回填）",
                )
            )
            seen_orders.add(row["order_id"])
        allocation_common = {
            **common,
            "allocation_id": row["allocation_id"],
            "account_id": row["account_id"],
            "device_id": row["device_id"],
        }
        if row["balance_amount"]:
            bind.execute(
                financial.insert().values(
                    **allocation_common,
                    entry_type="BALANCE_COST",
                    amount=-row["balance_amount"],
                    idempotency_key=f"order:{row['order_id']}:balance-cost:{row['allocation_id']}",
                    note=f"订单 {row['order_no']} 支付宝余额成本（历史回填）",
                )
            )
        if row["external_cash_amount"]:
            bind.execute(
                financial.insert().values(
                    **allocation_common,
                    entry_type="EXTERNAL_CASH_COST",
                    amount=-row["external_cash_amount"],
                    idempotency_key=f"order:{row['order_id']}:external-cash:{row['allocation_id']}",
                    note=f"订单 {row['order_no']} 真实付款成本（历史回填）",
                )
            )


def upgrade() -> None:
    op.alter_column("orders", "source_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("orders", "contractor_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("orders", "contractor_type", existing_type=sa.String(length=20), nullable=True)
    op.alter_column("orders", "contractor_name_snapshot", existing_type=sa.String(length=100), nullable=True)
    op.add_column("orders", sa.Column("customer_received_amount", sa.Numeric(14, 2)))
    op.add_column("orders", sa.Column("client_request_id", sa.String(64)))
    op.create_unique_constraint(
        "uq_orders_tenant_client_request", "orders", ["tenant_id", "client_request_id"]
    )
    op.execute(
        "UPDATE orders SET customer_received_amount = order_amount "
        "WHERE customer_received_amount IS NULL AND tenant_id IN "
        "(SELECT id FROM tenants WHERE business_mode = 'JIJIHONG')"
    )
    op.add_column(
        "alipay_balance_entries",
        sa.Column("reconciliation_id", sa.Integer()),
    )

    op.create_table(
        "jijihong_financial_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id")),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("order_payment_plans.id")),
        sa.Column("reconciliation_id", sa.Integer()),
        sa.Column("allocation_id", sa.Integer(), sa.ForeignKey("order_payment_allocations.id")),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("alipay_accounts.id")),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("alipay_devices.id")),
        sa.Column("entry_type", sa.String(40), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reversed_entry_id", sa.Integer(), sa.ForeignKey("jijihong_financial_entries.id")),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("note", sa.String(500)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("idempotency_key", name="uq_jijihong_financial_entry_idempotency"),
    )
    for name, cols in (
        ("ix_jijihong_financial_entries_tenant_id", ["tenant_id"]),
        ("ix_jijihong_financial_entries_business_date", ["business_date"]),
        ("ix_jijihong_financial_entries_order_id", ["order_id"]),
        ("ix_jijihong_financial_entries_plan_id", ["plan_id"]),
        ("ix_jijihong_financial_entries_reconciliation_id", ["reconciliation_id"]),
        ("ix_jijihong_financial_entries_allocation_id", ["allocation_id"]),
        ("ix_jijihong_financial_entries_account_id", ["account_id"]),
        ("ix_jijihong_financial_entries_device_id", ["device_id"]),
        ("ix_jijihong_financial_entries_entry_type", ["entry_type"]),
        ("ix_jijihong_financial_entries_reversed_entry_id", ["reversed_entry_id"]),
    ):
        op.create_index(name, "jijihong_financial_entries", cols)

    op.create_table(
        "alipay_reconciliations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("note", sa.String(500)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("confirmed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("reversed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("reversed_at", sa.DateTime(timezone=True)),
        *_timestamps(),
    )
    for name, cols in (
        ("ix_alipay_reconciliations_tenant_id", ["tenant_id"]),
        ("ix_alipay_reconciliations_business_date", ["business_date"]),
        ("ix_alipay_reconciliations_status", ["status"]),
    ):
        op.create_index(name, "alipay_reconciliations", cols)

    op.create_table(
        "alipay_reconciliation_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("reconciliation_id", sa.Integer(), sa.ForeignKey("alipay_reconciliations.id"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("alipay_accounts.id"), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("alipay_devices.id"), nullable=False),
        sa.Column("system_balance_snapshot", sa.Numeric(14, 2), nullable=False),
        sa.Column("actual_balance", sa.Numeric(14, 2), nullable=False),
        sa.Column("difference", sa.Numeric(14, 2), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("adjustment_entry_id", sa.Integer(), sa.ForeignKey("alipay_balance_entries.id")),
        *_timestamps(),
        sa.UniqueConstraint("reconciliation_id", "account_id", name="uq_alipay_reconciliation_account"),
    )
    for name, cols in (
        ("ix_alipay_reconciliation_items_tenant_id", ["tenant_id"]),
        ("ix_alipay_reconciliation_items_reconciliation_id", ["reconciliation_id"]),
        ("ix_alipay_reconciliation_items_account_id", ["account_id"]),
        ("ix_alipay_reconciliation_items_device_id", ["device_id"]),
    ):
        op.create_index(name, "alipay_reconciliation_items", cols)
    op.create_foreign_key(
        "fk_jijihong_financial_entries_reconciliation_id",
        "jijihong_financial_entries",
        "alipay_reconciliations",
        ["reconciliation_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_alipay_balance_entries_reconciliation_id",
        "alipay_balance_entries",
        "alipay_reconciliations",
        ["reconciliation_id"],
        ["id"],
    )
    op.create_index(
        "ix_alipay_balance_entries_reconciliation_id",
        "alipay_balance_entries",
        ["reconciliation_id"],
    )
    _backfill_confirmed_order_finance()


def downgrade() -> None:
    op.drop_constraint(
        "fk_alipay_balance_entries_reconciliation_id",
        "alipay_balance_entries",
        type_="foreignkey",
    )
    op.drop_index("ix_alipay_balance_entries_reconciliation_id", table_name="alipay_balance_entries")
    op.drop_table("alipay_reconciliation_items")
    op.drop_table("jijihong_financial_entries")
    op.drop_table("alipay_reconciliations")
    op.drop_column("alipay_balance_entries", "reconciliation_id")
    op.drop_column("orders", "customer_received_amount")
    op.drop_constraint("uq_orders_tenant_client_request", "orders", type_="unique")
    op.drop_column("orders", "client_request_id")
    op.alter_column("orders", "contractor_name_snapshot", existing_type=sa.String(length=100), nullable=False)
    op.alter_column("orders", "contractor_type", existing_type=sa.String(length=20), nullable=False)
    op.alter_column("orders", "contractor_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("orders", "source_id", existing_type=sa.Integer(), nullable=False)
