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