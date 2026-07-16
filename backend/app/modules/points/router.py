from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.modules.iam.audit import record_audit
from app.modules.iam.dependencies import CurrentContext, DbSession, require_roles
from app.modules.iam.models import MemberRole
from app.modules.orders.models import Order, OrderStatus
from app.modules.partners.models import Contractor, Performer
from app.modules.points.models import PointEntry
from app.modules.points.schemas import (
    PendingPointOrderOutput,
    PointAccountOutput,
    PointEntryOutput,
    RedeemCouponInput,
    RedeemCouponOutput,
)
from app.modules.points.service import available_coupons, redeem_coupon

router = APIRouter(prefix="/points", tags=["做单人积分"])
write_roles = (MemberRole.OWNER.value, MemberRole.BOOKKEEPER.value)


@router.get("/accounts", response_model=list[PointAccountOutput])
def list_point_accounts(
    context: CurrentContext,
    db: DbSession,
    contractor_id: int | None = None,
    active_only: bool = False,
) -> list[PointAccountOutput]:
    balance_subquery = (
        select(
            PointEntry.performer_id,
            func.coalesce(func.sum(PointEntry.amount), 0).label("balance"),
        )
        .where(PointEntry.tenant_id == context.tenant_id)
        .group_by(PointEntry.performer_id)
        .subquery()
    )
    query = (
        select(
            Performer,
            Contractor.name,
            func.coalesce(balance_subquery.c.balance, 0),
        )
        .join(Contractor, Contractor.id == Performer.contractor_id)
        .outerjoin(balance_subquery, balance_subquery.c.performer_id == Performer.id)
        .where(Performer.tenant_id == context.tenant_id)
    )
    if contractor_id is not None:
        query = query.where(Performer.contractor_id == contractor_id)
    if active_only:
        query = query.where(Performer.is_active.is_(True))
    rows = db.execute(query.order_by(Contractor.name, Performer.name)).all()
    result: list[PointAccountOutput] = []
    for performer, contractor_name, raw_balance in rows:
        balance = Decimal(raw_balance or 0).quantize(Decimal("0.01"))
        result.append(
            PointAccountOutput(
                performer_id=performer.id,
                performer_name=performer.name,
                performer_type=performer.performer_type,
                contractor_id=performer.contractor_id,
                contractor_name=contractor_name,
                is_listed=performer.is_listed,
                is_active=performer.is_active,
                balance=balance,
                available_coupons=available_coupons(balance),
            )
        )
    return result


@router.get("/entries", response_model=list[PointEntryOutput])
def list_point_entries(
    context: CurrentContext,
    db: DbSession,
    performer_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[PointEntry]:
    query = select(PointEntry).where(PointEntry.tenant_id == context.tenant_id)
    if performer_id is not None:
        query = query.where(PointEntry.performer_id == performer_id)
    return list(db.scalars(query.order_by(PointEntry.id.desc()).limit(limit)))


@router.get("/pending-orders", response_model=list[PendingPointOrderOutput])
def list_pending_point_orders(
    context: CurrentContext,
    db: DbSession,
) -> list[PendingPointOrderOutput]:
    rows = db.execute(
        select(Order, Contractor.name)
        .join(Contractor, Contractor.id == Order.contractor_id)
        .where(
            Order.tenant_id == context.tenant_id,
            Order.status == OrderStatus.SUCCESS.value,
            Order.performer_id.is_(None),
        )
        .order_by(Order.business_date, Order.id)
    ).all()
    return [
        PendingPointOrderOutput(
            id=order.id,
            order_no=order.order_no,
            business_date=order.business_date,
            contractor_id=order.contractor_id,
            contractor_name=contractor_name,
            order_amount=order.order_amount,
        )
        for order, contractor_name in rows
    ]


@router.post("/performers/{performer_id}/redeem", response_model=RedeemCouponOutput)
def redeem_performer_coupon(
    performer_id: int,
    data: RedeemCouponInput,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> RedeemCouponOutput:
    entry, balance = redeem_coupon(
        db,
        tenant_id=context.tenant_id,
        performer_id=performer_id,
        user_id=context.user_id,
        business_date=date.today(),
        note=data.note,
    )
    record_audit(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action="points.coupon_redeemed",
        resource_type="performer",
        resource_id=performer_id,
        payload={"points": "600", "coupon_value": "30", "balance": str(balance)},
    )
    db.commit()
    db.refresh(entry)
    return RedeemCouponOutput(
        entry=entry,
        balance=balance,
        available_coupons=available_coupons(balance),
    )