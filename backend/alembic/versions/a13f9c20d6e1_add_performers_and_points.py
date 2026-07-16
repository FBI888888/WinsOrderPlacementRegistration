"""add performers and point ledger

Revision ID: a13f9c20d6e1
Revises: 4bcb1229f7af
Create Date: 2026-07-16
"""

from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import context, op

revision: str = "a13f9c20d6e1"
down_revision: str | Sequence[str] | None = "4bcb1229f7af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalize_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _backfill() -> None:
    connection = op.get_bind()
    contractors = {
        row.id: row
        for row in connection.execute(
            sa.text(
                "SELECT id, tenant_id, name, normalized_name, contractor_type "
                "FROM contractors ORDER BY id"
            )
        ).mappings()
    }
    performer_ids: dict[tuple[int, str, int, str], int] = {}

    def ensure_performer(
        *, tenant_id: int, performer_type: str, contractor_id: int, name: str
    ) -> int:
        normalized = _normalize_name(name)
        key = (tenant_id, performer_type, contractor_id, normalized)
        if key in performer_ids:
            return performer_ids[key]
        existing = connection.execute(
            sa.text(
                "SELECT id FROM performers WHERE tenant_id = :tenant_id "
                "AND performer_type = :performer_type AND contractor_id = :contractor_id "
                "AND normalized_name = :normalized_name"
            ),
            {
                "tenant_id": tenant_id,
                "performer_type": performer_type,
                "contractor_id": contractor_id,
                "normalized_name": normalized,
            },
        ).scalar_one_or_none()
        if existing is None:
            connection.execute(
                sa.text(
                    "INSERT INTO performers "
                    "(tenant_id, name, normalized_name, performer_type, contractor_id, "
                    "is_listed, is_active) VALUES "
                    "(:tenant_id, :name, :normalized_name, :performer_type, :contractor_id, 1, 1)"
                ),
                {
                    "tenant_id": tenant_id,
                    "name": name.strip(),
                    "normalized_name": normalized,
                    "performer_type": performer_type,
                    "contractor_id": contractor_id,
                },
            )
            existing = connection.execute(
                sa.text(
                    "SELECT id FROM performers WHERE tenant_id = :tenant_id "
                    "AND performer_type = :performer_type AND contractor_id = :contractor_id "
                    "AND normalized_name = :normalized_name"
                ),
                {
                    "tenant_id": tenant_id,
                    "performer_type": performer_type,
                    "contractor_id": contractor_id,
                    "normalized_name": normalized,
                },
            ).scalar_one()
        performer_ids[key] = int(existing)
        return int(existing)

    for contractor in contractors.values():
        if contractor.contractor_type == "RETAIL":
            ensure_performer(
                tenant_id=contractor.tenant_id,
                performer_type="RETAIL",
                contractor_id=contractor.id,
                name=contractor.name,
            )

    orders = connection.execute(
        sa.text(
            "SELECT id, tenant_id, contractor_id, contractor_type, student_name, "
            "order_amount, business_date, status, created_by FROM orders ORDER BY id"
        )
    ).mappings()
    for order in orders:
        contractor = contractors.get(order.contractor_id)
        if contractor is None:
            continue
        performer_id: int | None = None
        performer_name: str | None = None
        if order.contractor_type == "RETAIL":
            performer_name = contractor.name
            performer_id = ensure_performer(
                tenant_id=order.tenant_id,
                performer_type="RETAIL",
                contractor_id=order.contractor_id,
                name=performer_name,
            )
        elif order.student_name and order.student_name.strip():
            performer_name = order.student_name.strip()
            performer_id = ensure_performer(
                tenant_id=order.tenant_id,
                performer_type="STUDENT",
                contractor_id=order.contractor_id,
                name=performer_name,
            )
        if performer_id is None:
            continue
        connection.execute(
            sa.text(
                "UPDATE orders SET performer_id = :performer_id, "
                "performer_name_snapshot = :performer_name WHERE id = :order_id"
            ),
            {
                "performer_id": performer_id,
                "performer_name": performer_name,
                "order_id": order.id,
            },
        )
        if order.status != "SUCCESS":
            continue
        points = (Decimal(order.order_amount) * Decimal("2")).quantize(Decimal("0.01"))
        connection.execute(
            sa.text(
                "UPDATE orders SET point_revision = 1 WHERE id = :order_id"
            ),
            {"order_id": order.id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO point_entries "
                "(tenant_id, business_date, performer_id, entry_type, amount, order_id, "
                "event_key, note, created_by) VALUES "
                "(:tenant_id, :business_date, :performer_id, 'ORDER_EARN', :amount, "
                ":order_id, :event_key, :note, :created_by)"
            ),
            {
                "tenant_id": order.tenant_id,
                "business_date": order.business_date,
                "performer_id": performer_id,
                "amount": points,
                "order_id": order.id,
                "event_key": f"order:{order.id}:1:earn",
                "note": f"历史订单 {order.id} 积分补记",
                "created_by": order.created_by,
            },
        )


def upgrade() -> None:
    op.create_table(
        "performers",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("normalized_name", sa.String(length=100), nullable=False),
        sa.Column("performer_type", sa.String(length=20), nullable=False),
        sa.Column("contractor_id", sa.Integer(), nullable=False),
        sa.Column("is_listed", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["contractor_id"], ["contractors.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "performer_type",
            "contractor_id",
            "normalized_name",
            name="uq_performers_identity",
        ),
    )
    op.create_index(op.f("ix_performers_tenant_id"), "performers", ["tenant_id"])
    op.create_index(op.f("ix_performers_contractor_id"), "performers", ["contractor_id"])
    op.create_index(op.f("ix_performers_performer_type"), "performers", ["performer_type"])

    op.add_column("orders", sa.Column("performer_id", sa.Integer(), nullable=True))
    op.add_column(
        "orders", sa.Column("performer_name_snapshot", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "orders",
        sa.Column("point_revision", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_index(op.f("ix_orders_performer_id"), "orders", ["performer_id"])
    op.create_foreign_key(
        op.f("fk_orders_performer_id_performers"),
        "orders",
        "performers",
        ["performer_id"],
        ["id"],
    )

    op.create_table(
        "point_entries",
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("performer_id", sa.Integer(), nullable=False),
        sa.Column("entry_type", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Numeric(precision=16, scale=2), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("reversed_entry_id", sa.Integer(), nullable=True),
        sa.Column("event_key", sa.String(length=100), nullable=False),
        sa.Column("coupon_value", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["performer_id"], ["performers.id"]),
        sa.ForeignKeyConstraint(["reversed_entry_id"], ["point_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "event_key", name="uq_point_entries_event_key"),
    )
    op.create_index(op.f("ix_point_entries_tenant_id"), "point_entries", ["tenant_id"])
    op.create_index(
        op.f("ix_point_entries_business_date"), "point_entries", ["business_date"]
    )
    op.create_index(op.f("ix_point_entries_performer_id"), "point_entries", ["performer_id"])
    op.create_index(op.f("ix_point_entries_entry_type"), "point_entries", ["entry_type"])
    op.create_index(op.f("ix_point_entries_order_id"), "point_entries", ["order_id"])

    if not context.is_offline_mode():
        _backfill()


def downgrade() -> None:
    op.drop_index(op.f("ix_point_entries_order_id"), table_name="point_entries")
    op.drop_index(op.f("ix_point_entries_entry_type"), table_name="point_entries")
    op.drop_index(op.f("ix_point_entries_performer_id"), table_name="point_entries")
    op.drop_index(op.f("ix_point_entries_business_date"), table_name="point_entries")
    op.drop_index(op.f("ix_point_entries_tenant_id"), table_name="point_entries")
    op.drop_table("point_entries")
    op.drop_constraint(op.f("fk_orders_performer_id_performers"), "orders", type_="foreignkey")
    op.drop_index(op.f("ix_orders_performer_id"), table_name="orders")
    op.drop_column("orders", "point_revision")
    op.drop_column("orders", "performer_name_snapshot")
    op.drop_column("orders", "performer_id")
    op.drop_index(op.f("ix_performers_performer_type"), table_name="performers")
    op.drop_index(op.f("ix_performers_contractor_id"), table_name="performers")
    op.drop_index(op.f("ix_performers_tenant_id"), table_name="performers")
    op.drop_table("performers")