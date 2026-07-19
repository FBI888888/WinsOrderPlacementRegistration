"""add ledger balance snapshots

Revision ID: e54c1d87a9b2
Revises: d91f2a4c8e70
Create Date: 2026-07-19
"""

from collections.abc import Mapping, Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "e54c1d87a9b2"
down_revision: str | Sequence[str] | None = "d91f2a4c8e70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORDER_ENTRY_TYPES = {"ORDER_PAYMENT", "COMMISSION_ACCRUAL", "SOURCE_ACCRUAL"}
ZERO = Decimal("0")


def _balance_key(row: Mapping) -> tuple[int, str, int] | None:
    account = row["account"]
    counterparty_id = (
        row["source_id"] if account == "SOURCE_RECEIVABLE" else row["contractor_id"]
    )
    if counterparty_id is None:
        return None
    return row["tenant_id"], account, counterparty_id


def build_snapshot_updates(rows: Sequence[Mapping]) -> list[dict]:
    balances: dict[tuple[int, str, int], Decimal] = {}
    updates: list[dict] = []
    pending_key: tuple[int, int] | None = None
    pending_rows: list[Mapping] = []

    def balance(tenant_id: int, account: str, counterparty_id: int) -> Decimal:
        return balances.get((tenant_id, account, counterparty_id), ZERO)

    def flush_pending() -> None:
        nonlocal pending_rows
        for row in pending_rows:
            update = {
                "id": row["id"],
                "advance_balance_snapshot": None,
                "commission_payable_snapshot": None,
                "net_settlement_snapshot": None,
                "source_receivable_snapshot": None,
            }
            if row["account"] in {"ADVANCE", "COMMISSION_PAYABLE"}:
                contractor_id = row["contractor_id"]
                advance = balance(row["tenant_id"], "ADVANCE", contractor_id)
                commission = balance(
                    row["tenant_id"], "COMMISSION_PAYABLE", contractor_id
                )
                update.update(
                    advance_balance_snapshot=advance,
                    commission_payable_snapshot=commission,
                    net_settlement_snapshot=advance - commission,
                )
            elif row["account"] == "SOURCE_RECEIVABLE":
                update["source_receivable_snapshot"] = balance(
                    row["tenant_id"], "SOURCE_RECEIVABLE", row["source_id"]
                )
            updates.append(update)
        pending_rows = []

    for row in rows:
        is_order_entry = (
            row["order_id"] is not None and row["entry_type"] in ORDER_ENTRY_TYPES
        )
        group_key = (row["tenant_id"], row["order_id"]) if is_order_entry else None
        if pending_rows and group_key != pending_key:
            flush_pending()
        if not is_order_entry:
            pending_key = None

        key = _balance_key(row)
        if key is not None:
            balances[key] = balances.get(key, ZERO) + Decimal(row["amount"])

        if is_order_entry:
            pending_key = group_key
            pending_rows.append(row)

    flush_pending()
    return updates


def upgrade() -> None:
    snapshot_columns = (
        "advance_balance_snapshot",
        "commission_payable_snapshot",
        "net_settlement_snapshot",
        "source_receivable_snapshot",
    )
    for column_name in snapshot_columns:
        op.add_column(
            "ledger_entries",
            sa.Column(column_name, sa.Numeric(precision=14, scale=2), nullable=True),
        )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, tenant_id, account, entry_type, amount,
                   contractor_id, source_id, order_id
            FROM ledger_entries
            ORDER BY tenant_id, id
            """
        )
    ).mappings().all()
    updates = build_snapshot_updates(rows)
    if updates:
        connection.execute(
            sa.text(
                """
                UPDATE ledger_entries
                SET advance_balance_snapshot = :advance_balance_snapshot,
                    commission_payable_snapshot = :commission_payable_snapshot,
                    net_settlement_snapshot = :net_settlement_snapshot,
                    source_receivable_snapshot = :source_receivable_snapshot
                WHERE id = :id
                """
            ),
            updates,
        )


def downgrade() -> None:
    op.drop_column("ledger_entries", "source_receivable_snapshot")
    op.drop_column("ledger_entries", "net_settlement_snapshot")
    op.drop_column("ledger_entries", "commission_payable_snapshot")
    op.drop_column("ledger_entries", "advance_balance_snapshot")