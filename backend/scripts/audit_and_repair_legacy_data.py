import argparse
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.funds.models import LedgerAccount, LedgerEntryType
from app.modules.funds.service import append_entry
from app.modules.iam.audit import record_audit
from app.modules.iam.models import Member, MemberRole, User
from app.modules.orders.calculations import calculate_order_amounts
from app.modules.orders.models import Order, OrderStatus
from app.modules.partners.models import SettlementBasis
from app.modules.settlements.models import Settlement, SettlementItem, SettlementStatus

ZERO = Decimal("0")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class OrderRepair:
    order_id: int
    order_no: str
    tenant_id: int
    business_date: date
    old_income: Decimal
    new_income: Decimal
    old_cost: Decimal
    new_cost: Decimal
    old_profit: Decimal
    new_profit: Decimal

    @property
    def income_delta(self) -> Decimal:
        return self.new_income - self.old_income


@dataclass(frozen=True)
class RepairSummary:
    tenant_id: int
    repaired_orders: int
    income_delta: Decimal
    confirmed_settlement_delta: Decimal
    draft_account_repairs: int


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审计并修复旧订单金额及结算链路")
    parser.add_argument("--tenant-id", type=int, help="只处理指定账套；不填写则处理全部账套")
    parser.add_argument("--user-id", type=int, help="写入流水和审计日志时使用的操作人")
    parser.add_argument("--apply", action="store_true", help="正式执行；默认只读预览")
    return parser.parse_args()


def resolve_user_id(db: Session, tenant_id: int, requested: int | None) -> int:
    if requested is not None:
        valid = db.scalar(
            select(Member.id)
            .join(User, User.id == Member.user_id)
            .where(
                Member.tenant_id == tenant_id,
                Member.user_id == requested,
                Member.role.in_((MemberRole.OWNER.value, MemberRole.BOOKKEEPER.value)),
                Member.is_active.is_(True),
                User.is_active.is_(True),
            )
        )
        if valid is None:
            raise RuntimeError(f"用户 {requested} 不是当前账套的有效 OWNER 或 BOOKKEEPER")
        return requested

    user_id = db.scalar(
        select(Member.user_id)
        .join(User, User.id == Member.user_id)
        .where(
            Member.tenant_id == tenant_id,
            Member.role.in_((MemberRole.OWNER.value, MemberRole.BOOKKEEPER.value)),
            Member.is_active.is_(True),
            User.is_active.is_(True),
        )
        .order_by(Member.user_id)
        .limit(1)
    )
    if user_id is None:
        raise RuntimeError(f"账套 {tenant_id} 没有可记录修复审计的有效操作人")
    return user_id


def calculate_repair(order: Order) -> OrderRepair | None:
    amounts = calculate_order_amounts(
        order_amount=Decimal(order.order_amount),
        coupon_amount=Decimal(order.coupon_amount),
        actual_paid=Decimal(order.actual_paid),
        settlement_basis=SettlementBasis(order.settlement_basis_snapshot),
        discount=Decimal(order.discount_snapshot),
        commission=Decimal(order.commission),
        settlement_income_override=(
            Decimal(order.settlement_income) if order.income_overridden else None
        ),
    )
    old_income = Decimal(order.settlement_income)
    old_cost = Decimal(order.cost)
    old_profit = Decimal(order.profit)
    if (
        old_income == amounts.settlement_income
        and old_cost == amounts.cost
        and old_profit == amounts.profit
    ):
        return None
    return OrderRepair(
        order_id=order.id,
        order_no=order.order_no,
        tenant_id=order.tenant_id,
        business_date=order.business_date,
        old_income=old_income,
        new_income=amounts.settlement_income,
        old_cost=old_cost,
        new_cost=amounts.cost,
        old_profit=old_profit,
        new_profit=amounts.profit,
    )


def find_repairs(db: Session, tenant_id: int) -> list[OrderRepair]:
    orders = db.scalars(
        select(Order)
        .where(Order.tenant_id == tenant_id)
        .order_by(Order.business_date, Order.id)
    )
    return [repair for order in orders if (repair := calculate_repair(order)) is not None]


def settlement_totals(db: Session, settlement: Settlement) -> dict[str, Decimal | int]:
    items = list(
        db.scalars(
            select(SettlementItem)
            .where(SettlementItem.settlement_id == settlement.id)
            .order_by(SettlementItem.id)
        )
    )
    orders = {
        order.id: order
        for order in db.scalars(
            select(Order).where(Order.id.in_([item.order_id for item in items]))
        )
    }
    return {
        "order_count": len(items),
        "order_amount_total": sum(
            (Decimal(orders[item.order_id].order_amount) for item in items), ZERO
        ),
        "actual_paid_total": sum(
            (Decimal(orders[item.order_id].actual_paid) for item in items), ZERO
        ),
        "commission_total": sum(
            (Decimal(orders[item.order_id].commission) for item in items), ZERO
        ),
        "settlement_income_total": sum(
            (Decimal(orders[item.order_id].settlement_income) for item in items), ZERO
        ),
        "profit_total": sum(
            (Decimal(orders[item.order_id].profit) for item in items), ZERO
        ),
    }


def print_repairs(tenant_id: int, repairs: list[OrderRepair]) -> None:
    print(f"账套 {tenant_id}：发现 {len(repairs)} 条金额异常")
    for repair in repairs:
        print(
            f"  {repair.order_no} {repair.business_date}: "
            f"结算收入 {repair.old_income:.2f} -> {repair.new_income:.2f}, "
            f"成本 {repair.old_cost:.2f} -> {repair.new_cost:.2f}, "
            f"利润 {repair.old_profit:.2f} -> {repair.new_profit:.2f}"
        )


def repair_orders(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    repairs: list[OrderRepair],
) -> Decimal:
    income_delta = ZERO
    for repair in repairs:
        order = db.scalar(
            select(Order)
            .where(Order.id == repair.order_id, Order.tenant_id == tenant_id)
            .with_for_update()
        )
        if order is None:
            raise RuntimeError(f"订单 {repair.order_id} 在修复过程中不存在")
        latest = calculate_repair(order)
        if latest is None:
            continue
        order.settlement_income = latest.new_income
        order.cost = latest.new_cost
        order.profit = latest.new_profit
        if order.status == OrderStatus.SUCCESS.value and latest.income_delta:
            append_entry(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                business_date=order.business_date,
                account=LedgerAccount.SOURCE_RECEIVABLE,
                entry_type=LedgerEntryType.SOURCE_ACCRUAL,
                amount=latest.income_delta,
                source_id=order.source_id,
                order_id=order.id,
                note=f"旧订单金额修复：订单 {order.order_no} 放单收入差额",
            )
            income_delta += latest.income_delta
    return income_delta


def repair_settlements(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    order_ids: set[int],
) -> tuple[Decimal, int]:
    settlements = list(
        db.scalars(
            select(Settlement)
            .where(Settlement.tenant_id == tenant_id)
            .order_by(Settlement.id)
        )
    )
    confirmed_delta = ZERO
    draft_account_repairs = 0
    for settlement in settlements:
        if settlement.account is None:
            settlement.account = (
                "SOURCE_RECEIVABLE"
                if settlement.settlement_type == "SOURCE"
                else "COMMISSION_PAYABLE"
            )
            draft_account_repairs += 1

        items = list(
            db.scalars(
                select(SettlementItem)
                .where(SettlementItem.settlement_id == settlement.id)
                .order_by(SettlementItem.id)
            )
        )
        touched_delta = ZERO
        for item in items:
            order = db.get(Order, item.order_id)
            if order is None or order.tenant_id != tenant_id:
                raise RuntimeError(f"结算单 {settlement.id} 存在无效订单明细")
            if order.id not in order_ids:
                continue
            new_item_amount = (
                Decimal(order.settlement_income)
                if settlement.settlement_type == "SOURCE"
                else Decimal(order.commission)
            )
            if Decimal(item.amount) != new_item_amount:
                old_item_amount = Decimal(item.amount)
                item.amount = new_item_amount
                if settlement.settlement_type == "SOURCE":
                    touched_delta += new_item_amount - old_item_amount

        if not items:
            continue
        totals = settlement_totals(db, settlement)
        for field in (
            "order_count",
            "order_amount_total",
            "actual_paid_total",
            "commission_total",
            "settlement_income_total",
            "profit_total",
        ):
            setattr(settlement, field, totals[field])

        if (
            settlement.settlement_type == "SOURCE"
            and settlement.status == SettlementStatus.CONFIRMED.value
            and touched_delta
        ):
            settlement.settled_amount = money(
                Decimal(settlement.settled_amount) + touched_delta
            )
            append_entry(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                business_date=settlement.date_to,
                account=LedgerAccount.SOURCE_RECEIVABLE,
                entry_type=LedgerEntryType.SOURCE_RECEIPT,
                amount=-touched_delta,
                source_id=settlement.source_id,
                settlement_id=settlement.id,
                note=f"旧订单金额修复：结算单 {settlement.settlement_no} 清账差额",
            )
            confirmed_delta += touched_delta
    return confirmed_delta, draft_account_repairs


def tenant_ids(db: Session, requested: int | None) -> list[int]:
    if requested is not None:
        return [requested]
    return list(db.scalars(select(Member.tenant_id).distinct().order_by(Member.tenant_id)))


def run_preview(db: Session, requested_tenant_id: int | None) -> None:
    for tenant_id in tenant_ids(db, requested_tenant_id):
        repairs = find_repairs(db, tenant_id)
        print_repairs(tenant_id, repairs)
    print("当前为只读预览，未修改任何数据。")


def run_apply(
    db: Session,
    *,
    requested_tenant_id: int | None,
    requested_user_id: int | None,
) -> list[RepairSummary]:
    summaries: list[RepairSummary] = []
    for tenant_id in tenant_ids(db, requested_tenant_id):
        user_id = resolve_user_id(db, tenant_id, requested_user_id)
        repairs = find_repairs(db, tenant_id)
        order_ids = {repair.order_id for repair in repairs}
        income_delta = repair_orders(
            db, tenant_id=tenant_id, user_id=user_id, repairs=repairs
        )
        settlement_delta, draft_repairs = repair_settlements(
            db, tenant_id=tenant_id, user_id=user_id, order_ids=order_ids
        )
        if not (repairs or draft_repairs):
            summaries.append(RepairSummary(tenant_id, 0, ZERO, ZERO, 0))
            continue
        record_audit(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            action="legacy_data.repaired",
            resource_type="legacy_repair",
            payload={
                "order_count": len(order_ids),
                "income_delta": str(income_delta),
                "confirmed_settlement_delta": str(settlement_delta),
                "draft_account_repairs": draft_repairs,
            },
        )
        summaries.append(
            RepairSummary(
                tenant_id,
                len(order_ids),
                income_delta,
                settlement_delta,
                draft_repairs,
            )
        )
    return summaries


def main() -> None:
    args = parse_args()
    with SessionLocal() as db:
        if not args.apply:
            run_preview(db, args.tenant_id)
            return
        with db.begin():
            summaries = run_apply(
                db,
                requested_tenant_id=args.tenant_id,
                requested_user_id=args.user_id,
            )
    for summary in summaries:
        print(
            f"账套 {summary.tenant_id} 已修复订单 {summary.repaired_orders} 条，"
            f"收入差额 {summary.income_delta:.2f}，"
            f"已确认结算调整 {summary.confirmed_settlement_delta:.2f}，"
            f"草稿账户补齐 {summary.draft_account_repairs} 条。"
        )


if __name__ == "__main__":
    main()