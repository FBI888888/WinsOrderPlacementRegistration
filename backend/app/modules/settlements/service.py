from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.funds.models import LedgerAccount
from app.modules.funds.service import get_balance
from app.modules.iam.audit import record_audit
from app.modules.orders.models import Order, OrderStatus
from app.modules.partners.service import get_contractor, get_source
from app.modules.settlements.models import Settlement, SettlementItem, SettlementStatus, SettlementType
from app.modules.settlements.schemas import SettlementCreate


def get_settlement(db: Session, tenant_id: int, settlement_id: int) -> Settlement:
    settlement = db.scalar(
        select(Settlement).where(
            Settlement.id == settlement_id, Settlement.tenant_id == tenant_id
        )
    )
    if not settlement:
        raise HTTPException(status_code=404, detail="结算单不存在")
    return settlement


def ensure_order_not_locked(db: Session, *, tenant_id: int, order_id: int) -> None:
    locked = db.scalar(
        select(SettlementItem.id)
        .join(Settlement, Settlement.id == SettlementItem.settlement_id)
        .where(
            SettlementItem.tenant_id == tenant_id,
            SettlementItem.order_id == order_id,
            Settlement.status == SettlementStatus.CONFIRMED.value,
        )
        .limit(1)
    )
    if locked:
        raise HTTPException(status_code=409, detail="订单已结算锁定，请先冲正对应结算单")


def _confirmed_order_ids(
    db: Session, tenant_id: int, settlement_type: SettlementType
) -> set[int]:
    return set(
        db.scalars(
            select(SettlementItem.order_id)
            .join(Settlement, Settlement.id == SettlementItem.settlement_id)
            .where(
                SettlementItem.tenant_id == tenant_id,
                Settlement.settlement_type == settlement_type.value,
                Settlement.status == SettlementStatus.CONFIRMED.value,
            )
        )
    )


def create_settlement(
    db: Session, *, tenant_id: int, user_id: int, data: SettlementCreate
) -> Settlement:
    query = select(Order).where(
        Order.tenant_id == tenant_id,
        Order.status == OrderStatus.SUCCESS.value,
        Order.business_date >= data.date_from,
        Order.business_date <= data.date_to,
    )
    if data.settlement_type == SettlementType.SOURCE:
        source = get_source(db, tenant_id, data.source_id or 0)
        query = query.where(Order.source_id == source.id)
        counterparty_name = source.name
        account_balance = get_balance(
            db,
            tenant_id=tenant_id,
            account=LedgerAccount.SOURCE_RECEIVABLE,
            source_id=source.id,
        )
    else:
        contractor = get_contractor(db, tenant_id, data.contractor_id or 0)
        query = query.where(Order.contractor_id == contractor.id)
        counterparty_name = contractor.name
        account_balance = get_balance(
            db,
            tenant_id=tenant_id,
            account=LedgerAccount.ADVANCE,
            contractor_id=contractor.id,
        )

    confirmed_ids = _confirmed_order_ids(db, tenant_id, data.settlement_type)
    orders = [order for order in db.scalars(query.order_by(Order.business_date, Order.id)) if order.id not in confirmed_ids]
    if not orders:
        raise HTTPException(status_code=422, detail="所选范围没有未结算的成功订单")

    settlement = Settlement(
        tenant_id=tenant_id,
        settlement_no=f"JS-{data.date_to:%Y%m%d}-{uuid4().hex[:8].upper()}",
        settlement_type=data.settlement_type.value,
        status=SettlementStatus.DRAFT.value,
        date_from=data.date_from,
        date_to=data.date_to,
        source_id=data.source_id,
        contractor_id=data.contractor_id,
        counterparty_name_snapshot=counterparty_name,
        order_count=len(orders),
        order_amount_total=sum((Decimal(o.order_amount) for o in orders), Decimal("0")),
        actual_paid_total=sum((Decimal(o.actual_paid) for o in orders), Decimal("0")),
        commission_total=sum((Decimal(o.commission) for o in orders), Decimal("0")),
        settlement_income_total=sum((Decimal(o.settlement_income) for o in orders), Decimal("0")),
        profit_total=sum((Decimal(o.profit) for o in orders), Decimal("0")),
        account_balance_snapshot=account_balance,
        note=data.note,
        created_by=user_id,
    )
    db.add(settlement)
    db.flush()
    for order in orders:
        amount = (
            Decimal(order.settlement_income)
            if data.settlement_type == SettlementType.SOURCE
            else Decimal(order.actual_paid) + Decimal(order.commission)
        )
        db.add(
            SettlementItem(
                tenant_id=tenant_id,
                settlement_id=settlement.id,
                order_id=order.id,
                amount=amount,
            )
        )
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="settlement.created",
        resource_type="settlement",
        resource_id=settlement.id,
        payload={"order_count": len(orders), "type": data.settlement_type.value},
    )
    db.commit()
    db.refresh(settlement)
    return settlement


def confirm_settlement(
    db: Session, *, tenant_id: int, user_id: int, settlement_id: int
) -> Settlement:
    settlement = get_settlement(db, tenant_id, settlement_id)
    if settlement.status != SettlementStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="只有草稿结算单可以确认")
    item_order_ids = set(
        db.scalars(
            select(SettlementItem.order_id).where(
                SettlementItem.tenant_id == tenant_id,
                SettlementItem.settlement_id == settlement.id,
            )
        )
    )
    conflicts = _confirmed_order_ids(db, tenant_id, SettlementType(settlement.settlement_type))
    if item_order_ids & conflicts:
        raise HTTPException(status_code=409, detail="部分订单已被其他结算单确认，请重新生成")
    invalid = db.scalar(
        select(Order.id).where(
            Order.tenant_id == tenant_id,
            Order.id.in_(item_order_ids),
            Order.status != OrderStatus.SUCCESS.value,
        ).limit(1)
    )
    if invalid:
        raise HTTPException(status_code=409, detail="结算单包含非成功订单，请重新生成")
    settlement.status = SettlementStatus.CONFIRMED.value
    settlement.confirmed_by = user_id
    settlement.confirmed_at = datetime.now(timezone.utc)
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="settlement.confirmed",
        resource_type="settlement",
        resource_id=settlement.id,
    )
    db.commit()
    db.refresh(settlement)
    return settlement


def reverse_settlement(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    settlement_id: int,
    reason: str | None,
) -> Settlement:
    settlement = get_settlement(db, tenant_id, settlement_id)
    if settlement.status != SettlementStatus.CONFIRMED.value:
        raise HTTPException(status_code=409, detail="只有已确认结算单可以冲正")
    if not reason:
        raise HTTPException(status_code=422, detail="冲正必须填写原因")
    settlement.status = SettlementStatus.REVERSED.value
    settlement.reversed_by = user_id
    settlement.reversed_at = datetime.now(timezone.utc)
    settlement.reversal_reason = reason
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="settlement.reversed",
        resource_type="settlement",
        resource_id=settlement.id,
        payload={"reason": reason},
    )
    db.commit()
    db.refresh(settlement)
    return settlement