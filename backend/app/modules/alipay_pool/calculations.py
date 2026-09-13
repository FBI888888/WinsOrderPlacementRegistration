from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from itertools import combinations

from app.modules.alipay_pool.models import AccountPhase

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Candidate:
    account_id: int
    device_name: str
    alias: str
    phase: str
    balance: Decimal
    coupon: Decimal


@dataclass(frozen=True)
class SuggestedAllocation:
    account_id: int
    device_name: str
    alias: str
    coupon_amount: Decimal
    balance_amount: Decimal
    external_cash_amount: Decimal
    balance_before: Decimal
    balance_after: Decimal


@dataclass(frozen=True)
class Suggestion:
    allocations: list[SuggestedAllocation]
    total_coupon: Decimal
    total_balance: Decimal
    total_external_cash: Decimal
    soft_cap_exceeded: bool


def _evaluate_combo(
    combo: tuple[Candidate, ...],
    *,
    order_amount: Decimal,
    soft_cap: Decimal,
    first_day_target: Decimal,
    first_day_tolerance: Decimal,
) -> tuple[tuple, Suggestion] | None:
    best: tuple[tuple, Suggestion] | None = None
    count = len(combo)
    for coupon_mask in range(1 << count):
        coupon_amounts = [
            item.coupon if coupon_mask & (1 << index) else Decimal("0")
            for index, item in enumerate(combo)
        ]
        total_coupon = sum(coupon_amounts, Decimal("0"))
        if total_coupon > order_amount:
            continue
        for clear_mask in range(1 << count):
            balances = [Decimal("0") for _ in combo]
            for index, item in enumerate(combo):
                if clear_mask & (1 << index):
                    balances[index] = item.balance
            if total_coupon + sum(balances, Decimal("0")) > order_amount:
                continue

            remaining = order_amount - total_coupon - sum(balances, Decimal("0"))
            non_clear = [index for index in range(count) if not clear_mask & (1 << index)]

            # 第二天账号先消耗；第一天账号先只消耗目标余额以上的部分。
            passes = [
                [
                    index
                    for index in non_clear
                    if combo[index].phase == AccountPhase.DAY2_ACTIVE.value
                ],
                [
                    index
                    for index in non_clear
                    if combo[index].phase != AccountPhase.DAY2_ACTIVE.value
                ],
                non_clear,
            ]
            for pass_no, indexes in enumerate(passes):
                for index in sorted(indexes, key=lambda i: (combo[i].balance, combo[i].account_id)):
                    if remaining <= 0:
                        break
                    capacity = combo[index].balance - balances[index]
                    if pass_no == 1:
                        capacity = min(
                            capacity,
                            max(
                                combo[index].balance
                                - max(first_day_target - first_day_tolerance, Decimal("0")),
                                Decimal("0"),
                            ),
                        )
                    take = min(capacity, remaining)
                    if take > 0:
                        balances[index] += take
                        remaining -= take

            cash = money(max(remaining, Decimal("0")))
            used_indexes = [
                index
                for index in range(count)
                if balances[index] > 0 or coupon_amounts[index] > 0
            ]
            if not used_indexes:
                used_indexes = [0]
            cash_index = used_indexes[-1]
            allocations: list[SuggestedAllocation] = []
            cleared = 0
            target_penalty = Decimal("0")
            for index in used_indexes:
                item = combo[index]
                after = money(item.balance - balances[index])
                if after == 0 and balances[index] > 0:
                    cleared += 1
                elif item.phase != AccountPhase.DAY2_ACTIVE.value:
                    target_penalty += max(
                        abs(after - first_day_target) - first_day_tolerance,
                        Decimal("0"),
                    )
                allocations.append(
                    SuggestedAllocation(
                        account_id=item.account_id,
                        device_name=item.device_name,
                        alias=item.alias,
                        coupon_amount=money(coupon_amounts[index]),
                        balance_amount=money(balances[index]),
                        external_cash_amount=cash if index == cash_index else Decimal("0"),
                        balance_before=money(item.balance),
                        balance_after=after,
                    )
                )
            over_cap = cash > soft_cap
            score = (
                1 if over_cap else 0,
                cash if over_cap else Decimal("0"),
                -cleared,
                -sum(1 for value in coupon_amounts if value > 0),
                cash,
                len(allocations),
                target_penalty,
                tuple(item.account_id for item in combo),
            )
            suggestion = Suggestion(
                allocations=allocations,
                total_coupon=money(total_coupon),
                total_balance=money(sum(balances, Decimal("0"))),
                total_external_cash=cash,
                soft_cap_exceeded=over_cap,
            )
            if best is None or score < best[0]:
                best = (score, suggestion)
    return best


def recommend(
    candidates: list[Candidate],
    *,
    order_amount: Decimal,
    soft_cap: Decimal,
    first_day_target: Decimal,
    first_day_tolerance: Decimal,
    max_split_accounts: int,
) -> Suggestion:
    if not candidates:
        raise ValueError("没有可用的支付宝账号")

    # 保留小余额/第二天账号、接近订单额账号和大余额账号，兼顾清空与覆盖能力。
    ranked = sorted(
        candidates,
        key=lambda item: (
            0 if item.phase == AccountPhase.DAY2_ACTIVE.value else 1,
            0 if item.coupon > 0 else 1,
            item.balance,
            item.account_id,
        ),
    )
    diversified = [
        *ranked[:24],
        *sorted(candidates, key=lambda item: (abs(item.balance - order_amount), item.account_id))[:16],
        *sorted(candidates, key=lambda item: (-item.balance, item.account_id))[:12],
    ]
    pool = list({item.account_id: item for item in diversified}.values())
    best: tuple[tuple, Suggestion] | None = None
    for split_count in range(1, min(max_split_accounts, len(pool)) + 1):
        for combo in combinations(pool, split_count):
            evaluated = _evaluate_combo(
                combo,
                order_amount=money(order_amount),
                soft_cap=money(soft_cap),
                first_day_target=money(first_day_target),
                first_day_tolerance=money(first_day_tolerance),
            )
            if evaluated and (best is None or evaluated[0] < best[0]):
                best = evaluated
    if best is None:
        raise ValueError("无法生成支付方案")
    return best[1]
