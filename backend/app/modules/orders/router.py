from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.modules.iam.dependencies import CurrentContext, DbSession, require_roles
from app.modules.iam.models import AuditLog, MemberRole, User
from app.modules.orders.models import Order, OrderStatus
from app.modules.orders.query import build_order_filters
from app.modules.orders.schemas import (
    OrderCreate,
    OrderHistoryItem,
    OrderListOutput,
    OrderOutput,
    PerformerOrderStat,
    OrderStatusUpdate,
    OrderUpdate,
)
from app.modules.orders.service import create_order, get_order, transition_order, update_order
from app.modules.partners.models import ContractorType, Source
from app.modules.points.service import available_coupons, get_point_balance

router = APIRouter(prefix="/orders", tags=["订单"])
write_roles = (MemberRole.OWNER.value, MemberRole.BOOKKEEPER.value)


def _output(
    order: Order,
    source_name: str,
    *,
    point_balance=None,
) -> OrderOutput:
    return OrderOutput(
        id=order.id,
        order_no=order.order_no,
        business_date=order.business_date,
        status=order.status,
        source_id=order.source_id,
        source_name=source_name,
        contractor_id=order.contractor_id,
        contractor_type=order.contractor_type,
        contractor_name=order.contractor_name_snapshot,
        performer_id=order.performer_id,
        performer_name=order.performer_name_snapshot,
        student_name=order.student_name,
        point_balance=point_balance,
        available_coupons=available_coupons(point_balance) if point_balance is not None else 0,
        order_amount=order.order_amount,
        coupon_amount=order.coupon_amount,
        actual_paid=order.actual_paid,
        settlement_basis_snapshot=order.settlement_basis_snapshot,
        discount_snapshot=order.discount_snapshot,
        settlement_income=order.settlement_income,
        income_overridden=order.income_overridden,
        income_override_reason=order.income_override_reason,
        commission=order.commission,
        commission_overridden=order.commission_overridden,
        commission_override_reason=order.commission_override_reason,
        cost=order.cost,
        profit=order.profit,
        note=order.note,
        success_at=order.success_at,
        created_at=order.created_at,
    )


def _one_output(db: DbSession, tenant_id: int, order: Order) -> OrderOutput:
    source_name = db.scalar(
        select(Source.name).where(Source.id == order.source_id, Source.tenant_id == tenant_id)
    ) or "已删除放单人"
    balance = (
        get_point_balance(
            db,
            tenant_id=tenant_id,
            performer_id=order.performer_id,
        )
        if order.performer_id is not None
        else None
    )
    return _output(order, source_name, point_balance=balance)


@router.get("", response_model=OrderListOutput)
def list_orders(
    context: CurrentContext,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    date_from: date | None = None,
    date_to: date | None = None,
    order_status: OrderStatus | None = Query(default=None, alias="status"),
    source_id: int | None = None,
    contractor_id: int | None = None,
    performer_id: int | None = None,
    contractor_type: ContractorType | None = None,
    profit_sign: str | None = Query(default=None, pattern="^(positive|negative|zero)$"),
    keyword: str | None = Query(default=None, max_length=100),
) -> OrderListOutput:
    filters = build_order_filters(
        tenant_id=context.tenant_id,
        date_from=date_from,
        date_to=date_to,
        order_status=order_status,
        source_id=source_id,
        contractor_id=contractor_id,
        performer_id=performer_id,
        contractor_type=contractor_type,
        profit_sign=profit_sign,
        keyword=keyword,
    )

    total = db.scalar(
        select(func.count(Order.id)).join(Source, Source.id == Order.source_id).where(*filters)
    ) or 0
    rows = db.execute(
        select(Order, Source.name)
        .join(Source, Source.id == Order.source_id)
        .where(*filters)
        .order_by(Order.business_date.desc(), Order.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return OrderListOutput(
        items=[_output(order, source_name) for order, source_name in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/performer-stats", response_model=list[PerformerOrderStat])
def list_performer_stats(
    context: CurrentContext,
    db: DbSession,
) -> list[PerformerOrderStat]:
    rows = db.execute(
        select(Order.performer_id, func.count(Order.id))
        .where(
            Order.tenant_id == context.tenant_id,
            Order.status == OrderStatus.SUCCESS.value,
            Order.performer_id.is_not(None),
        )
        .group_by(Order.performer_id)
    ).all()
    return [
        PerformerOrderStat(performer_id=performer_id, success_count=success_count)
        for performer_id, success_count in rows
    ]


@router.get("/{order_id}", response_model=OrderOutput)
def retrieve_order(order_id: int, context: CurrentContext, db: DbSession) -> OrderOutput:
    return _one_output(db, context.tenant_id, get_order(db, context.tenant_id, order_id))


@router.get("/{order_id}/history", response_model=list[OrderHistoryItem])
def list_order_history(order_id: int, context: CurrentContext, db: DbSession) -> list[OrderHistoryItem]:
    get_order(db, context.tenant_id, order_id)
    rows = db.execute(
        select(AuditLog, User.name)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(
            AuditLog.tenant_id == context.tenant_id,
            AuditLog.resource_type == "order",
            AuditLog.resource_id == str(order_id),
        )
        .order_by(AuditLog.id.desc())
    ).all()
    return [
        OrderHistoryItem(
            id=log.id,
            user_id=log.user_id,
            user_name=user_name,
            action=log.action,
            payload=log.payload,
            created_at=log.created_at,
        )
        for log, user_name in rows
    ]


@router.post("", response_model=OrderOutput, status_code=201)
def create_order_endpoint(
    data: OrderCreate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> OrderOutput:
    order = create_order(db, tenant_id=context.tenant_id, user_id=context.user_id, data=data)
    return _one_output(db, context.tenant_id, order)


@router.patch("/{order_id}", response_model=OrderOutput)
def update_order_endpoint(
    order_id: int,
    data: OrderUpdate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> OrderOutput:
    order = update_order(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        order_id=order_id,
        data=data,
    )
    return _one_output(db, context.tenant_id, order)


@router.post("/{order_id}/status", response_model=OrderOutput)
def transition_order_endpoint(
    order_id: int,
    data: OrderStatusUpdate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> OrderOutput:
    order = transition_order(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        order_id=order_id,
        target=data.status,
        reason=data.reason,
    )
    return _one_output(db, context.tenant_id, order)