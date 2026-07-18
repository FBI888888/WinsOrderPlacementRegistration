"""add clearing links and amounts

Revision ID: d91f2a4c8e70
Revises: c7e2a91f4b63
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d91f2a4c8e70"
down_revision: str | Sequence[str] | None = "c7e2a91f4b63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ledger_entries", sa.Column("settlement_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_ledger_entries_settlement_id"),
        "ledger_entries",
        ["settlement_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_ledger_entries_settlement_id_settlements"),
        "ledger_entries",
        "settlements",
        ["settlement_id"],
        ["id"],
    )
    op.add_column("settlements", sa.Column("account", sa.String(length=30), nullable=True))
    op.add_column(
        "settlements",
        sa.Column(
            "settled_amount",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.alter_column("settlements", "settled_amount", server_default=None)


def downgrade() -> None:
    op.drop_column("settlements", "settled_amount")
    op.drop_column("settlements", "account")
    op.drop_constraint(
        op.f("fk_ledger_entries_settlement_id_settlements"), "ledger_entries", type_="foreignkey"
    )
    op.drop_index(op.f("ix_ledger_entries_settlement_id"), table_name="ledger_entries")
    op.drop_column("ledger_entries", "settlement_id")