from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.orders.models import Order
from app.modules.partners.models import Performer
from app.modules.points.models import PointEntry, PointEntryType

POINTS_PER_CURRENCY = Decimal("2")
COUPON_REDEMPTION_POINTS = Decimal("600")
COUPON_VALUE = Decimal("30")


def points_for_payment(actual_paid: Decimal) -> Decimal:
    return (Decimal(actual_paid) * POINTS_PER_CURRENCY).quantize(Decimal("0.01"))


def get_point_balance(db: Session, *, tenant_id: int, performer_id: int) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(PointEntry.amount), 0)).where(
            PointEntry.tenant_id == tenant_id,
            PointEntry.performer_id == performer_id,
        )
    )
    return Decimal(value or 0).quantize(Decimal("0.01"))


def available_coupons(balance: Decimal) -> int:
    if balance < COUPON_REDEMPTION_POINTS:
        return 0
    return int(balance // COUPON_REDEMPTION_POINTS)


def book_order_points(db: Session, *, order: Order, user_id: int) -> PointEntry | None:
    if order.performer_id is None:
        return None
    order.point_revision += 1
    entry = PointEntry(
        tenant_id=order.tenant_id,
        business_date=order.business_date,
        performer_id=order.performer_id,
        entry_type=PointEntryType.ORDER_EARN.value,
        amount=points_for_payment(Decimal(order.actual_paid)),
        order_id=order.id,
        event_key=f"order:{order.id}:{order.point_revision}:earn",
        note=f"订单 {order.order_no} 积分",
        created_by=user_id,
    )
    db.add(entry)
    return entry


def reverse_order_points(
    db: Session,
    *,
    order: Order,
    user_id: int,
    business_date: date,
    note: str,
) -> list[PointEntry]:
    earned_entries = list(
        db.scalars(
            select(PointEntry).where(
                PointEntry.tenant_id == order.tenant_id,
                PointEntry.order_id == order.id,
                PointEntry.entry_type == PointEntryType.ORDER_EARN.value,
            )
        )
    )
    reversed_ids = set(
        db.scalars(
            select(PointEntry.reversed_entry_id).where(
                PointEntry.tenant_id == order.tenant_id,
                PointEntry.order_id == order.id,
                PointEntry.entry_type == PointEntryType.ORDER_REVERSAL.value,
            )
        )
    )
    reversals: list[PointEntry] = []
    for earned in earned_entries:
        if earned.id in reversed_ids:
            continue
        reversal = PointEntry(
            tenant_id=order.tenant_id,
            business_date=business_date,
            performer_id=earned.performer_id,
            entry_type=PointEntryType.ORDER_REVERSAL.value,
            amount=-Decimal(earned.amount),
            order_id=order.id,
            reversed_entry_id=earned.id,
            event_key=f"order:{order.id}:reverse:{earned.id}",
            note=note,
            created_by=user_id,
        )
        db.add(reversal)
        reversals.append(reversal)
    return reversals


def redeem_coupon(
    db: Session,
    *,
    tenant_id: int,
    performer_id: int,
    user_id: int,
    business_date: date,
    note: str | None,
) -> tuple[PointEntry, Decimal]:
    performer = db.scalar(
        select(Performer)
        .where(Performer.id == performer_id, Performer.tenant_id == tenant_id)
        .with_for_update()
    )
    if not performer:
        raise HTTPException(status_code=404, detail="实际做单人不存在")
    balance = get_point_balance(db, tenant_id=tenant_id, performer_id=performer.id)
    if balance < COUPON_REDEMPTION_POINTS:
        raise HTTPException(status_code=409, detail=f"积分不足，当前剩余 {balance} 积分")
    entry = PointEntry(
        tenant_id=tenant_id,
        business_date=business_date,
        performer_id=performer.id,
        entry_type=PointEntryType.COUPON_REDEMPTION.value,
        amount=-COUPON_REDEMPTION_POINTS,
        event_key=f"redeem:{uuid4().hex}",
        coupon_value=COUPON_VALUE,
        note=note or "手动兑换 30 元优惠券",
        created_by=user_id,
    )
    db.add(entry)
    db.flush()
    return entry, balance - COUPON_REDEMPTION_POINTS