from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.modules.iam.dependencies import CurrentContext, DbSession, require_roles
from app.modules.iam.models import MemberRole
from app.modules.orders.models import Order, OrderStatus
from app.modules.orders.schemas import (
    OrderCreate,
    OrderListOutput,
    OrderOutput,
    OrderStatusUpdate,
    OrderUpdate,
)
from app.modules.orders.service import create_order, get_order, transition_order, update_order
from app.modules.partners.models import Contractor, ContractorType, Source

router = APIRouter(prefix="/orders", tags=["订单"])
write_roles = (MemberRole.OWNER.value, MemberRole.BOOKKEEPER.value)


def _output(order: Order, source_name: str) -> OrderOutput:
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
        student_name=order.student_name,
        order_amount=order.order_amount,
        coupon_amount=order.coupon_amount,
        actual_paid=order.actual_paid,
        settlement_basis_snapshot=order.settlement_basis_snapshot,
        discount_snapshot=order.discount_snapshot,
        settlement_income=order.settlement_income,
        income_overridden=order.income_overridden,
        commission=order.commission,
        commission_overridden=order.commission_overridden,
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
    return _output(order, source_name)


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
    contractor_type: ContractorType | None = None,
    profit_sign: str | None = Query(default=None, pattern="^(positive|negative|zero)$"),
) -> OrderListOutput:
    filters = [Order.tenant_id == context.tenant_id]
    if date_from:
        filters.append(Order.business_date >= date_from)
    if date_to:
        filters.append(Order.business_date <= date_to)
    if order_status:
        filters.append(Order.status == order_status.value)
    if source_id:
        filters.append(Order.source_id == source_id)
    if contractor_id:
        filters.append(Order.contractor_id == contractor_id)
    if contractor_type:
        filters.append(Order.contractor_type == contractor_type.value)
    if profit_sign == "positive":
        filters.append(Order.profit > 0)
    elif profit_sign == "negative":
        filters.append(Order.profit < 0)
    elif profit_sign == "zero":
        filters.append(Order.profit == 0)

    total = db.scalar(select(func.count(Order.id)).where(*filters)) or 0
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


@router.get("/{order_id}", response_model=OrderOutput)
def retrieve_order(order_id: int, context: CurrentContext, db: DbSession) -> OrderOutput:
    return _one_output(db, context.tenant_id, get_order(db, context.tenant_id, order_id))


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