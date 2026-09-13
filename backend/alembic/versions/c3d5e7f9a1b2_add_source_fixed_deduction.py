"""add source fixed deduction settlement

Revision ID: c3d5e7f9a1b2
Revises: b8c2d4e6f8a0
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d5e7f9a1b2"
down_revision: str | Sequence[str] | None = "b8c2d4e6f8a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column(
            "default_settlement_method",
            sa.String(length=30),
            server_default="DISCOUNT",
            nullable=False,
        ),
    )
    op.add_column(
        "sources",
        sa.Column(
            "default_fixed_deduction",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "source_rates",
        sa.Column(
            "settlement_method",
            sa.String(length=30),
            server_default="DISCOUNT",
            nullable=False,
        ),
    )
    op.add_column(
        "source_rates",
        sa.Column(
            "fixed_deduction",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "settlement_method_snapshot",
            sa.String(length=30),
            server_default="DISCOUNT",
            nullable=False,
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "fixed_deduction_snapshot",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("orders", "fixed_deduction_snapshot")
    op.drop_column("orders", "settlement_method_snapshot")
    op.drop_column("source_rates", "fixed_deduction")
    op.drop_column("source_rates", "settlement_method")
    op.drop_column("sources", "default_fixed_deduction")
    op.drop_column("sources", "default_settlement_method")
