from decimal import Decimal

import pytest

from app.modules.orders.calculations import calculate_order_amounts
from app.modules.partners.models import SettlementBasis


def test_calculate_order_amounts_from_order_amount():
    result = calculate_order_amounts(
        order_amount=Decimal("100"),
        coupon_amount=Decimal("20"),
        actual_paid=Decimal("70"),
        settlement_basis=SettlementBasis.ORDER_AMOUNT,
        discount=Decimal("0.9"),
        commission=Decimal("5"),
    )

    assert result.settlement_income == Decimal("90.00")
    assert result.cost == Decimal("75.00")
    assert result.profit == Decimal("15.00")


def test_calculate_order_amounts_supports_after_coupon_and_override():
    result = calculate_order_amounts(
        order_amount=Decimal("100"),
        coupon_amount=Decimal("20"),
        actual_paid=Decimal("70"),
        settlement_basis=SettlementBasis.AFTER_COUPON,
        discount=Decimal("0.9"),
        commission=Decimal("5"),
        settlement_income_override=Decimal("76.125"),
    )

    assert result.settlement_income == Decimal("76.13")
    assert result.profit == Decimal("1.13")



def test_calculate_order_amounts_applies_tiered_source_settlement():
    below_threshold = calculate_order_amounts(
        order_amount=Decimal("200"),
        coupon_amount=Decimal("0"),
        actual_paid=Decimal("0"),
        settlement_basis=SettlementBasis.ORDER_AMOUNT,
        discount=Decimal("0.9"),
        commission=Decimal("0"),
    )
    at_threshold = calculate_order_amounts(
        order_amount=Decimal("210"),
        coupon_amount=Decimal("0"),
        actual_paid=Decimal("0"),
        settlement_basis=SettlementBasis.ORDER_AMOUNT,
        discount=Decimal("0.9"),
        commission=Decimal("0"),
    )
    above_threshold = calculate_order_amounts(
        order_amount=Decimal("300"),
        coupon_amount=Decimal("0"),
        actual_paid=Decimal("0"),
        settlement_basis=SettlementBasis.ORDER_AMOUNT,
        discount=Decimal("0.9"),
        commission=Decimal("0"),
    )

    assert below_threshold.settlement_income == Decimal("180.00")
    assert at_threshold.settlement_income == Decimal("189.00")
    assert above_threshold.settlement_income == Decimal("279.00")


def test_tiered_rule_uses_order_amount_for_excess_with_after_coupon_basis():
    result = calculate_order_amounts(
        order_amount=Decimal("300"),
        coupon_amount=Decimal("20"),
        actual_paid=Decimal("0"),
        settlement_basis=SettlementBasis.AFTER_COUPON,
        discount=Decimal("0.9"),
        commission=Decimal("0"),
    )

    assert result.settlement_income == Decimal("261.00")


def test_coupon_cannot_exceed_order_amount():
    with pytest.raises(ValueError, match="优惠券金额"):
        calculate_order_amounts(
            order_amount=Decimal("10"),
            coupon_amount=Decimal("11"),
            actual_paid=Decimal("0"),
            settlement_basis=SettlementBasis.ORDER_AMOUNT,
            discount=Decimal("1"),
            commission=Decimal("0"),
        )