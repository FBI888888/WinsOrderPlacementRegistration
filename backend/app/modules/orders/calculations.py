from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.modules.partners.models import SettlementBasis

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class OrderAmounts:
    settlement_income: Decimal
    commission: Decimal
    cost: Decimal
    profit: Decimal


def calculate_order_amounts(
    *,
    order_amount: Decimal,
    coupon_amount: Decimal,
    actual_paid: Decimal,
    settlement_basis: SettlementBasis,
    discount: Decimal,
    commission: Decimal,
    settlement_income_override: Decimal | None = None,
) -> OrderAmounts:
    if min(order_amount, coupon_amount, actual_paid, commission) < 0:
        raise ValueError("金额不能为负数")
    if coupon_amount > order_amount:
        raise ValueError("优惠券金额不能超过订单标价")
    if discount <= 0 or discount > 1:
        raise ValueError("折扣必须大于0且不超过1")

    after_coupon = money(order_amount - coupon_amount)
    basis_amount = order_amount if settlement_basis == SettlementBasis.ORDER_AMOUNT else after_coupon
    excess_amount = max(order_amount - Decimal("210"), Decimal("0"))
    default_income = basis_amount * discount + excess_amount * (Decimal("1") - discount)
    income = (
        money(settlement_income_override)
        if settlement_income_override is not None
        else money(default_income)
    )
    final_commission = money(commission)
    cost = money(actual_paid + final_commission)
    profit = money(income - cost)
    return OrderAmounts(income, final_commission, cost, profit)