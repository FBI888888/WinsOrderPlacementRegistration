from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.funds.models import LedgerAccount, LedgerEntryType
from app.modules.funds.service import append_entry, reverse_order_entries
from app.modules.iam.audit import record_audit
from app.modules.orders.calculations import calculate_order_amounts
from app.modules.orders.models import Order, OrderStatus
from app.modules.orders.schemas import OrderCreate, OrderUpdate
from app.modules.partners.models import ContractorType
from app.modules.partners.service import (
    get_contractor,
    get_or_create_retail,
    get_source,
    resolve_contractor_rate,
    resolve_source_rate,
)


def get_order(db: Session, tenant_id: int, order_id: int) -> Order:
    order = db.scalar(select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id))
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")
    return order


def _assignment(
    db: Session,
    *,
    tenant_id: int,
    contractor_type: ContractorType,
    contractor_id: int | None,
    retail_name: str | None,
    business_date,
    commission_override: Decimal | None,
) -> tuple[int, str, Decimal, bool]:
    if contractor_type == ContractorType.LEADER:
        if not contractor_id:
            raise HTTPException(status_code=422, detail="请选择学生头子")
        contractor = get_contractor(db, tenant_id, contractor_id)
        if contractor.contractor_type != ContractorType.LEADER.value or not contractor.is_active:
            raise HTTPException(status_code=422, detail="学生头子不可用")
        configured = resolve_contractor_rate(db, tenant_id, contractor.id, business_date)
        return (
            contractor.id,
            contractor.name,
            commission_override if commission_override is not None else configured,
            commission_override is not None,
        )

    if not retail_name:
        raise HTTPException(status_code=422, detail="请填写散户姓名")
    if commission_override is None:
        raise HTTPException(status_code=422, detail="请填写散户佣金")
    contractor = get_or_create_retail(db, tenant_id, retail_name)
    return contractor.id, contractor.name, commission_override, True


def _financial_values(
    db: Session,
    *,
    tenant_id: int,
    business_date,
    source_id: int,
    contractor_type: ContractorType,
    contractor_id: int | None,
    retail_name: str | None,
    order_amount: Decimal,
    coupon_amount: Decimal,
    actual_paid: Decimal,
    settlement_income_override: Decimal | None,
    commission_override: Decimal | None,
) -> dict:
    source = get_source(db, tenant_id, source_id)
    if not source.is_active:
        raise HTTPException(status_code=422, detail="放单人员已停用")
    basis, discount = resolve_source_rate(db, tenant_id, source_id, business_date)
    final_contractor_id, contractor_name, commission, commission_overridden = _assignment(
        db,
        tenant_id=tenant_id,
        contractor_type=contractor_type,
        contractor_id=contractor_id,
        retail_name=retail_name,
        business_date=business_date,
        commission_override=commission_override,
    )
    try:
        amounts = calculate_order_amounts(
            order_amount=order_amount,
            coupon_amount=coupon_amount,
            actual_paid=actual_paid,
            settlement_basis=basis,
            discount=discount,
            commission=commission,
            settlement_income_override=settlement_income_override,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "contractor_id": final_contractor_id,
        "contractor_name_snapshot": contractor_name,
        "settlement_basis_snapshot": basis.value,
        "discount_snapshot": discount,
        "settlement_income": amounts.settlement_income,
        "income_overridden": settlement_income_override is not None,
        "commission": amounts.commission,
        "commission_overridden": commission_overridden,
        "cost": amounts.cost,
        "profit": amounts.profit,
    }


def _book_success(db: Session, order: Order, user_id: int) -> None:
    if Decimal(order.actual_paid) != 0:
        append_entry(
            db,
            tenant_id=order.tenant_id,
            user_id=user_id,
            business_date=order.business_date,
            account=LedgerAccount.ADVANCE,
            entry_type=LedgerEntryType.ORDER_PAYMENT,
            amount=-Decimal(order.actual_paid),
            contractor_id=order.contractor_id,
            order_id=order.id,
            note=f"订单 {order.order_no} 实付",
        )
    if Decimal(order.commission) != 0:
        append_entry(
            db,
            tenant_id=order.tenant_id,
            user_id=user_id,
            business_date=order.business_date,
            account=LedgerAccount.COMMISSION_PAYABLE,
            entry_type=LedgerEntryType.COMMISSION_ACCRUAL,
            amount=Decimal(order.commission),
            contractor_id=order.contractor_id,
            order_id=order.id,
            note=f"订单 {order.order_no} 佣金",
        )
    append_entry(
        db,
        tenant_id=order.tenant_id,
        user_id=user_id,
        business_date=order.business_date,
        account=LedgerAccount.SOURCE_RECEIVABLE,
        entry_type=LedgerEntryType.SOURCE_ACCRUAL,
        amount=Decimal(order.settlement_income),
        source_id=order.source_id,
        order_id=order.id,
        note=f"订单 {order.order_no} 放单收入",
    )
    order.status = OrderStatus.SUCCESS.value
    order.success_at = datetime.now(timezone.utc)


def create_order(db: Session, *, tenant_id: int, user_id: int, data: OrderCreate) -> Order:
    financial = _financial_values(
        db,
        tenant_id=tenant_id,
        business_date=data.business_date,
        source_id=data.source_id,
        contractor_type=data.contractor_type,
        contractor_id=data.contractor_id,
        retail_name=data.retail_name,
        order_amount=data.order_amount,
        coupon_amount=data.coupon_amount,
        actual_paid=data.actual_paid,
        settlement_income_override=data.settlement_income_override,
        commission_override=data.commission_override,
    )
    order = Order(
        tenant_id=tenant_id,
        order_no=f"{data.business_date:%Y%m%d}-{uuid4().hex[:8].upper()}",
        business_date=data.business_date,
        status=OrderStatus.DRAFT.value,
        source_id=data.source_id,
        contractor_type=data.contractor_type.value,
        student_name=data.student_name,
        order_amount=data.order_amount,
        coupon_amount=data.coupon_amount,
        actual_paid=data.actual_paid,
        income_override_reason=data.income_override_reason,
        commission_override_reason=data.commission_override_reason,
        note=data.note,
        created_by=user_id,
        **financial,
    )
    db.add(order)
    db.flush()
    if data.status == OrderStatus.SUCCESS:
        _book_success(db, order, user_id)
    elif data.status == OrderStatus.DISPATCHED:
        order.status = OrderStatus.DISPATCHED.value
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="order.created",
        resource_type="order",
        resource_id=order.id,
        payload={"status": order.status, "order_no": order.order_no},
    )
    db.commit()
    db.refresh(order)
    return order


def update_order(
    db: Session, *, tenant_id: int, user_id: int, order_id: int, data: OrderUpdate
) -> Order:
    order = get_order(db, tenant_id, order_id)
    if order.status not in (OrderStatus.DRAFT.value, OrderStatus.DISPATCHED.value):
        raise HTTPException(status_code=409, detail="已成功、取消或冲正的订单不能直接修改")

    changes = data.model_dump(exclude_unset=True)
    business_date = changes.get("business_date", order.business_date)
    source_id = changes.get("source_id", order.source_id)
    contractor_type = ContractorType(changes.get("contractor_type", order.contractor_type))
    contractor_id = changes.get("contractor_id", order.contractor_id)
    retail_name = changes.get(
        "retail_name",
        order.contractor_name_snapshot if contractor_type == ContractorType.RETAIL else None,
    )
    order_amount = changes.get("order_amount", Decimal(order.order_amount))
    coupon_amount = changes.get("coupon_amount", Decimal(order.coupon_amount))
    actual_paid = changes.get("actual_paid", Decimal(order.actual_paid))
    income_override = (
        changes.get("settlement_income_override")
        if "settlement_income_override" in changes
        else (Decimal(order.settlement_income) if order.income_overridden else None)
    )
    commission_override = (
        changes.get("commission_override")
        if "commission_override" in changes
        else (Decimal(order.commission) if order.commission_overridden else None)
    )
    financial = _financial_values(
        db,
        tenant_id=tenant_id,
        business_date=business_date,
        source_id=source_id,
        contractor_type=contractor_type,
        contractor_id=contractor_id,
        retail_name=retail_name,
        order_amount=order_amount,
        coupon_amount=coupon_amount,
        actual_paid=actual_paid,
        settlement_income_override=income_override,
        commission_override=commission_override,
    )
    order.business_date = business_date
    order.source_id = source_id
    order.contractor_type = contractor_type.value
    order.student_name = changes.get("student_name", order.student_name)
    order.order_amount = order_amount
    order.coupon_amount = coupon_amount
    order.actual_paid = actual_paid
    order.income_override_reason = changes.get("income_override_reason", order.income_override_reason)
    order.commission_override_reason = changes.get(
        "commission_override_reason", order.commission_override_reason
    )
    order.note = changes.get("note", order.note)
    for key, value in financial.items():
        setattr(order, key, value)
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="order.updated",
        resource_type="order",
        resource_id=order.id,
        payload=data.model_dump(exclude_unset=True, mode="json"),
    )
    db.commit()
    db.refresh(order)
    return order


def transition_order(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    order_id: int,
    target: OrderStatus,
    reason: str | None,
) -> Order:
    order = get_order(db, tenant_id, order_id)
    current = OrderStatus(order.status)
    allowed = {
        OrderStatus.DRAFT: {OrderStatus.DISPATCHED, OrderStatus.SUCCESS, OrderStatus.CANCELLED},
        OrderStatus.DISPATCHED: {OrderStatus.DRAFT, OrderStatus.SUCCESS, OrderStatus.CANCELLED},
        OrderStatus.SUCCESS: {OrderStatus.REVERSED},
    }
    if target not in allowed.get(current, set()):
        raise HTTPException(status_code=409, detail=f"不能从 {current.value} 变更为 {target.value}")
    if target in (OrderStatus.CANCELLED, OrderStatus.REVERSED) and not reason:
        raise HTTPException(status_code=422, detail="取消或冲正必须填写原因")
    if target == OrderStatus.SUCCESS:
        _book_success(db, order, user_id)
    elif target == OrderStatus.REVERSED:
        from app.modules.settlements.service import ensure_order_not_locked

        ensure_order_not_locked(db, tenant_id=tenant_id, order_id=order.id)
        reverse_order_entries(
            db,
            tenant_id=tenant_id,
            order_id=order.id,
            user_id=user_id,
            business_date=order.business_date,
            note=reason or "订单冲正",
        )
        order.status = target.value
    else:
        order.status = target.value
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="order.status_changed",
        resource_type="order",
        resource_id=order.id,
        payload={"from": current.value, "to": target.value, "reason": reason},
    )
    db.commit()
    db.refresh(order)
    return order