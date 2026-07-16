"""calculate active order points from actual paid amount

Revision ID: c7e2a91f4b63
Revises: a13f9c20d6e1
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7e2a91f4b63"
down_revision: str | Sequence[str] | None = "a13f9c20d6e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _recalculate_active_earnings(amount_column: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE point_entries AS earned
            INNER JOIN orders AS related_order ON related_order.id = earned.order_id
            LEFT JOIN point_entries AS reversal
                ON reversal.reversed_entry_id = earned.id
                AND reversal.entry_type = 'ORDER_REVERSAL'
            SET earned.amount = ROUND(related_order.{amount_column} * 2, 2)
            WHERE earned.entry_type = 'ORDER_EARN'
                AND reversal.id IS NULL
            """
        )
    )


def upgrade() -> None:
    _recalculate_active_earnings("actual_paid")


def downgrade() -> None:
    _recalculate_active_earnings("order_amount")