from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from scripts.audit_and_repair_legacy_data import calculate_repair


def make_order(**overrides):
    values = {
        "id": 1,
        "order_no": "20260717-TEST",
        "tenant_id": 1,
        "business_date": date(2026, 7, 17),
        "order_amount": Decimal("224"),
        "coupon_amount": Decimal("50"),
        "actual_paid": Decimal("200"),
        "settlement_basis_snapshot": "ORDER_AMOUNT",
        "discount_snapshot": Decimal("0.9"),
        "settlement_income": Decimal("201.60"),
        "income_overridden": False,
        "commission": Decimal("5"),
        "cost": Decimal("205"),
        "profit": Decimal("-3.40"),
        "status": "SUCCESS",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_calculate_repair_uses_current_210_segment_rule():
    repair = calculate_repair(make_order())

    assert repair is not None
    assert repair.old_income == Decimal("201.60")
    assert repair.new_income == Decimal("203.00")
    assert repair.old_cost == Decimal("205.00")
    assert repair.new_cost == Decimal("205.00")
    assert repair.old_profit == Decimal("-3.40")
    assert repair.new_profit == Decimal("-2.00")
    assert repair.income_delta == Decimal("1.40")


def test_calculate_repair_is_idempotent_after_snapshot_update():
    order = make_order(
        settlement_income=Decimal("203.00"),
        profit=Decimal("-2.00"),
    )

    assert calculate_repair(order) is None


def test_overridden_income_is_not_replaced_by_default_formula():
    order = make_order(
        settlement_income=Decimal("180.00"),
        profit=Decimal("-25.00"),
        income_overridden=True,
    )

    assert calculate_repair(order) is None