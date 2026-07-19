import importlib.util
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.modules.funds.models import LedgerEntry
from tests.conftest import TestingSession
from tests.test_workflow import create_business_data, create_order


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "e54c1d87a9b2_add_ledger_balance_snapshots.py"
)


def load_snapshot_migration():
    spec = importlib.util.spec_from_file_location("ledger_snapshot_migration", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_historical_snapshot_backfill_groups_order_entries():
    migration = load_snapshot_migration()
    rows = [
        {
            "id": 1,
            "tenant_id": 1,
            "account": "ADVANCE",
            "entry_type": "ADVANCE_TOPUP",
            "amount": Decimal("1000.00"),
            "contractor_id": 7,
            "source_id": None,
            "order_id": None,
        },
        {
            "id": 2,
            "tenant_id": 1,
            "account": "ADVANCE",
            "entry_type": "ORDER_PAYMENT",
            "amount": Decimal("-70.00"),
            "contractor_id": 7,
            "source_id": None,
            "order_id": 101,
        },
        {
            "id": 3,
            "tenant_id": 1,
            "account": "COMMISSION_PAYABLE",
            "entry_type": "COMMISSION_ACCRUAL",
            "amount": Decimal("5.00"),
            "contractor_id": 7,
            "source_id": None,
            "order_id": 101,
        },
        {
            "id": 4,
            "tenant_id": 1,
            "account": "SOURCE_RECEIVABLE",
            "entry_type": "SOURCE_ACCRUAL",
            "amount": Decimal("90.00"),
            "contractor_id": None,
            "source_id": 9,
            "order_id": 101,
        },
        {
            "id": 5,
            "tenant_id": 1,
            "account": "COMMISSION_PAYABLE",
            "entry_type": "COMMISSION_PAYMENT",
            "amount": Decimal("-2.00"),
            "contractor_id": 7,
            "source_id": None,
            "order_id": None,
        },
        {
            "id": 6,
            "tenant_id": 1,
            "account": "ADVANCE",
            "entry_type": "ORDER_PAYMENT",
            "amount": Decimal("-50.00"),
            "contractor_id": 7,
            "source_id": None,
            "order_id": 102,
        },
        {
            "id": 7,
            "tenant_id": 1,
            "account": "COMMISSION_PAYABLE",
            "entry_type": "COMMISSION_ACCRUAL",
            "amount": Decimal("5.00"),
            "contractor_id": 7,
            "source_id": None,
            "order_id": 102,
        },
        {
            "id": 8,
            "tenant_id": 1,
            "account": "SOURCE_RECEIVABLE",
            "entry_type": "SOURCE_ACCRUAL",
            "amount": Decimal("100.00"),
            "contractor_id": None,
            "source_id": 9,
            "order_id": 102,
        },
    ]

    updates = migration.build_snapshot_updates(rows)
    by_id = {item["id"]: item for item in updates}

    assert by_id[2]["advance_balance_snapshot"] == Decimal("930.00")
    assert by_id[2]["commission_payable_snapshot"] == Decimal("5.00")
    assert by_id[2]["net_settlement_snapshot"] == Decimal("925.00")
    assert by_id[3]["net_settlement_snapshot"] == Decimal("925.00")
    assert by_id[4]["source_receivable_snapshot"] == Decimal("90.00")
    assert by_id[6]["advance_balance_snapshot"] == Decimal("880.00")
    assert by_id[6]["commission_payable_snapshot"] == Decimal("8.00")
    assert by_id[6]["net_settlement_snapshot"] == Decimal("872.00")
    assert by_id[8]["source_receivable_snapshot"] == Decimal("190.00")
    assert len(by_id) == 6


def test_success_order_writes_post_booking_snapshots(client, auth_headers):
    source_id, leader_id, _ = create_business_data(client, auth_headers)
    order = create_order(
        client,
        auth_headers,
        source_id=source_id,
        leader_id=leader_id,
        status="SUCCESS",
        order_amount="120",
        coupon_amount="20",
        actual_paid="60",
    )

    with TestingSession() as db:
        entries = list(
            db.scalars(
                select(LedgerEntry)
                .where(LedgerEntry.order_id == order["id"])
                .order_by(LedgerEntry.id)
            )
        )

    assert len(entries) == 3
    contractor_entries = [entry for entry in entries if entry.contractor_id == leader_id]
    source_entries = [entry for entry in entries if entry.source_id == source_id]
    assert {entry.advance_balance_snapshot for entry in contractor_entries} == {Decimal("870.00")}
    assert {entry.commission_payable_snapshot for entry in contractor_entries} == {Decimal("10.00")}
    assert {entry.net_settlement_snapshot for entry in contractor_entries} == {Decimal("860.00")}
    assert {entry.source_receivable_snapshot for entry in source_entries} == {Decimal("198.00")}


def test_editing_success_order_rebuilds_snapshots(client, auth_headers):
    source_id, leader_id, _ = create_business_data(client, auth_headers)
    order = create_order(
        client,
        auth_headers,
        source_id=source_id,
        leader_id=leader_id,
        status="SUCCESS",
    )

    updated = client.patch(
        f"/api/v1/orders/{order['id']}",
        headers=auth_headers,
        json={"actual_paid": "60", "commission_override": "8", "commission_override_reason": "修正佣金"},
    )
    assert updated.status_code == 200, updated.text

    with TestingSession() as db:
        entries = list(
            db.scalars(
                select(LedgerEntry)
                .where(LedgerEntry.order_id == order["id"])
                .order_by(LedgerEntry.id)
            )
        )

    reversed_entry_ids = {
        entry.reversed_entry_id for entry in entries if entry.reversed_entry_id is not None
    }
    active_entries = [
        entry
        for entry in entries
        if entry.entry_type != "REVERSAL" and entry.id not in reversed_entry_ids
    ]
    contractor_entries = [entry for entry in active_entries if entry.contractor_id == leader_id]
    source_entries = [entry for entry in active_entries if entry.source_id == source_id]
    assert {entry.advance_balance_snapshot for entry in contractor_entries} == {Decimal("870.00")}
    assert {entry.commission_payable_snapshot for entry in contractor_entries} == {Decimal("13.00")}
    assert {entry.net_settlement_snapshot for entry in contractor_entries} == {Decimal("857.00")}
    assert {entry.source_receivable_snapshot for entry in source_entries} == {Decimal("180.00")}