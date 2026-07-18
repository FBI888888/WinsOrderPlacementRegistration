from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.funds.models import LedgerAccount, LedgerEntry, LedgerEntryType
from app.modules.funds.service import append_entry, get_balance
from app.modules.iam.audit import record_audit
from app.modules.orders.models import Order, OrderStatus
from app.modules.partners.service import get_contractor, get_source
from app.modules.settlements.models import Settlement, SettlementItem, SettlementStatus, SettlementType
from app.modules.settlements.schemas import SettlementCreate

ZERO = Decimal("0")


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


def _target_info(
    db: Session, *, tenant_id: int, data: SettlementCreate
) -> tuple[str, LedgerAccount, int]:
    if data.settlement_type == SettlementType.SOURCE:
        source = get_source(db, tenant_id, data.source_id or 0)
        return source.name, LedgerAccount.SOURCE_RECEIVABLE, source.id
    contractor = get_contractor(db, tenant_id, data.contractor_id or 0)
    return contractor.name, LedgerAccount.COMMISSION_PAYABLE, contractor.id


def _create_settlement_record(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    data: SettlementCreate,
    clear_current_balance: bool = False,
) -> Settlement:
    counterparty_name, account, target_id = _target_info(db, tenant_id=tenant_id, data=data)
    query = select(Order).where(
        Order.tenant_id == tenant_id,
        Order.status == OrderStatus.SUCCESS.value,
        Order.business_date >= data.date_from,
        Order.business_date <= data.date_to,
    )
    if data.settlement_type == SettlementType.SOURCE:
        query = query.where(Order.source_id == target_id)
    else:
        query = query.where(Order.contractor_id == target_id)

    confirmed_ids = _confirmed_order_ids(db, tenant_id, data.settlement_type)
    orders = [
        order
        for order in db.scalars(query.order_by(Order.business_date, Order.id))
        if order.id not in confirmed_ids
    ]
    account_balance = get_balance(
        db,
        tenant_id=tenant_id,
        account=account,
        source_id=target_id if account == LedgerAccount.SOURCE_RECEIVABLE else None,
        contractor_id=target_id if account == LedgerAccount.COMMISSION_PAYABLE else None,
    )
    if clear_current_balance:
        if account_balance <= ZERO:
            raise HTTPException(status_code=422, detail="当前没有可结清余额")
    elif not orders:
        raise HTTPException(status_code=422, detail="所选范围没有未结算的成功订单")

    order_amount_total = sum((Decimal(order.order_amount) for order in orders), ZERO)
    actual_paid_total = sum((Decimal(order.actual_paid) for order in orders), ZERO)
    commission_total = sum((Decimal(order.commission) for order in orders), ZERO)
    income_total = sum((Decimal(order.settlement_income) for order in orders), ZERO)
    profit_total = sum((Decimal(order.profit) for order in orders), ZERO)
    period_amount = income_total if account == LedgerAccount.SOURCE_RECEIVABLE else commission_total
    settled_amount = (
        account_balance
        if clear_current_balance
        else min(max(account_balance, ZERO), period_amount)
    )
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
        order_amount_total=order_amount_total,
        actual_paid_total=actual_paid_total,
        commission_total=commission_total,
        settlement_income_total=income_total,
        profit_total=profit_total,
        account_balance_snapshot=account_balance,
        account=account.value,
        settled_amount=settled_amount,
        note=data.note,
        created_by=user_id,
    )
    db.add(settlement)
    db.flush()
    for order in orders:
        amount = (
            Decimal(order.settlement_income)
            if data.settlement_type == SettlementType.SOURCE
            else Decimal(order.commission)
        )
        db.add(
            SettlementItem(
                tenant_id=tenant_id,
                settlement_id=settlement.id,
                order_id=order.id,
                amount=amount,
            )
        )
    return settlement


def create_settlement(
    db: Session, *, tenant_id: int, user_id: int, data: SettlementCreate
) -> Settlement:
    settlement = _create_settlement_record(
        db, tenant_id=tenant_id, user_id=user_id, data=data
    )
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="settlement.created",
        resource_type="settlement",
        resource_id=settlement.id,
        payload={"order_count": settlement.order_count, "type": data.settlement_type.value},
    )
    db.commit()
    db.refresh(settlement)
    return settlement


def _confirm_settlement_record(
    db: Session, *, tenant_id: int, user_id: int, settlement: Settlement
) -> Settlement:
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
    if item_order_ids:
        invalid = db.scalar(
            select(Order.id)
            .where(
                Order.tenant_id == tenant_id,
                Order.id.in_(item_order_ids),
                Order.status != OrderStatus.SUCCESS.value,
            )
            .limit(1)
        )
        if invalid:
            raise HTTPException(status_code=409, detail="结算单包含非成功订单，请重新生成")
    settlement.status = SettlementStatus.CONFIRMED.value
    settlement.confirmed_by = user_id
    settlement.confirmed_at = datetime.now(timezone.utc)
    if settlement.settled_amount:
        account = LedgerAccount(settlement.account or "")
        entry_type = (
            LedgerEntryType.SOURCE_RECEIPT
            if account == LedgerAccount.SOURCE_RECEIVABLE
            else LedgerEntryType.COMMISSION_PAYMENT
        )
        append_entry(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            business_date=settlement.date_to,
            account=account,
            entry_type=entry_type,
            amount=-Decimal(settlement.settled_amount),
            contractor_id=settlement.contractor_id,
            source_id=settlement.source_id,
            settlement_id=settlement.id,
            note=f"结算单 {settlement.settlement_no} 清账",
        )
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="settlement.confirmed",
        resource_type="settlement",
        resource_id=settlement.id,
        payload={"settled_amount": str(settlement.settled_amount)},
    )
    return settlement


def confirm_settlement(
    db: Session, *, tenant_id: int, user_id: int, settlement_id: int
) -> Settlement:
    settlement = get_settlement(db, tenant_id, settlement_id)
    _confirm_settlement_record(
        db, tenant_id=tenant_id, user_id=user_id, settlement=settlement
    )
    db.commit()
    db.refresh(settlement)
    return settlement


def _reverse_settlement_entries(
    db: Session, *, tenant_id: int, user_id: int, settlement: Settlement, reason: str
) -> None:
    entries = list(
        db.scalars(
            select(LedgerEntry).where(
                LedgerEntry.tenant_id == tenant_id,
                LedgerEntry.settlement_id == settlement.id,
                LedgerEntry.entry_type != LedgerEntryType.REVERSAL.value,
            )
        )
    )
    reversed_ids = set(
        db.scalars(
            select(LedgerEntry.reversed_entry_id).where(
                LedgerEntry.tenant_id == tenant_id,
                LedgerEntry.settlement_id == settlement.id,
                LedgerEntry.entry_type == LedgerEntryType.REVERSAL.value,
            )
        )
    )
    for entry in entries:
        if entry.id in reversed_ids:
            continue
        append_entry(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            business_date=date.today(),
            account=LedgerAccount(entry.account),
            entry_type=LedgerEntryType.REVERSAL,
            amount=-Decimal(entry.amount),
            contractor_id=entry.contractor_id,
            source_id=entry.source_id,
            settlement_id=settlement.id,
            reversed_entry_id=entry.id,
            note=reason,
        )


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
    _reverse_settlement_entries(
        db, tenant_id=tenant_id, user_id=user_id, settlement=settlement, reason=reason
    )
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


def list_clearing_preview(db: Session, *, tenant_id: int) -> list[dict]:
    rows = db.execute(
        select(
            LedgerEntry.account,
            LedgerEntry.contractor_id,
            LedgerEntry.source_id,
        )
        .where(LedgerEntry.tenant_id == tenant_id)
        .group_by(LedgerEntry.account, LedgerEntry.contractor_id, LedgerEntry.source_id)
    ).all()
    result: list[dict] = []
    for account_value, contractor_id, source_id in rows:
        account = LedgerAccount(account_value)
        if account == LedgerAccount.COMMISSION_PAYABLE and contractor_id:
            balance = get_balance(
                db, tenant_id=tenant_id, account=account, contractor_id=contractor_id
            )
            name = get_contractor(db, tenant_id, contractor_id).name
            target_type = SettlementType.CONTRACTOR
            target_id = contractor_id
        elif account == LedgerAccount.SOURCE_RECEIVABLE and source_id:
            balance = get_balance(db, tenant_id=tenant_id, account=account, source_id=source_id)
            name = get_source(db, tenant_id, source_id).name
            target_type = SettlementType.SOURCE
            target_id = source_id
        else:
            continue
        if balance > ZERO:
            result.append(
                {
                    "settlement_type": target_type.value,
                    "counterparty_id": target_id,
                    "counterparty_name": name,
                    "account": account.value,
                    "balance": balance,
                }
            )
    return result


def clear_target(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    settlement_type: SettlementType,
    counterparty_id: int,
    business_date: date,
    note: str | None,
) -> Settlement:
    data = SettlementCreate(
        settlement_type=settlement_type,
        date_from=date(1970, 1, 1),
        date_to=business_date,
        source_id=counterparty_id if settlement_type == SettlementType.SOURCE else None,
        contractor_id=counterparty_id if settlement_type == SettlementType.CONTRACTOR else None,
        note=note,
    )
    settlement = _create_settlement_record(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        data=data,
        clear_current_balance=True,
    )
    _confirm_settlement_record(
        db, tenant_id=tenant_id, user_id=user_id, settlement=settlement
    )
    return settlement


def clear_all_targets(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    business_date: date,
    note: str | None,
) -> list[Settlement]:
    targets = list_clearing_preview(db, tenant_id=tenant_id)
    settlements = [
        clear_target(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            settlement_type=SettlementType(target["settlement_type"]),
            counterparty_id=target["counterparty_id"],
            business_date=business_date,
            note=note,
        )
        for target in targets
    ]
    db.commit()
    for settlement in settlements:
        db.refresh(settlement)
    return settlements