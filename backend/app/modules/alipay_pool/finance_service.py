from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.alipay_pool.calculations import money
from app.modules.alipay_pool.models import (
    AccountPhase,
    AccountStatus,
    AlipayAccount,
    AlipayBalanceEntry,
    AlipayDevice,
    AlipayReconciliation,
    AlipayReconciliationItem,
    BalanceEntryType,
    FinancialEntryType,
    JijihongFinancialEntry,
    OrderPaymentAllocation,
    OrderPaymentPlan,
    ReconciliationStatus,
)
from app.modules.alipay_pool.schemas import ReconciliationCreateInput
from app.modules.alipay_pool.service import _append_balance_entry, ensure_jijihong
from app.modules.iam.audit import record_audit
from app.modules.orders.models import Order, OrderStatus

ZERO = Decimal("0.00")


def _append_financial_entry(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    business_date,
    entry_type: FinancialEntryType,
    amount: Decimal,
    idempotency_key: str,
    order_id: int | None = None,
    plan_id: int | None = None,
    reconciliation_id: int | None = None,
    allocation_id: int | None = None,
    account_id: int | None = None,
    device_id: int | None = None,
    reversed_entry_id: int | None = None,
    note: str | None = None,
) -> JijihongFinancialEntry:
    existing = db.scalar(
        select(JijihongFinancialEntry).where(
            JijihongFinancialEntry.idempotency_key == idempotency_key
        )
    )
    if existing:
        return existing
    entry = JijihongFinancialEntry(
        tenant_id=tenant_id,
        business_date=business_date,
        order_id=order_id,
        plan_id=plan_id,
        reconciliation_id=reconciliation_id,
        allocation_id=allocation_id,
        account_id=account_id,
        device_id=device_id,
        entry_type=entry_type.value,
        amount=money(amount),
        reversed_entry_id=reversed_entry_id,
        idempotency_key=idempotency_key,
        note=note,
        created_by=user_id,
    )
    db.add(entry)
    db.flush()
    return entry


def book_confirmed_order_finance(
    db: Session,
    *,
    order: Order,
    plan: OrderPaymentPlan,
    allocations: list[OrderPaymentAllocation],
    user_id: int,
) -> None:
    customer_received = money(
        order.order_amount
        if order.customer_received_amount is None
        else order.customer_received_amount
    )
    _append_financial_entry(
        db,
        tenant_id=order.tenant_id,
        user_id=user_id,
        business_date=order.business_date,
        entry_type=FinancialEntryType.CUSTOMER_RECEIPT,
        amount=customer_received,
        idempotency_key=f"order:{order.id}:customer-receipt",
        order_id=order.id,
        plan_id=plan.id,
        note=f"订单 {order.order_no} 客户实收",
    )
    for allocation in allocations:
        account = db.get(AlipayAccount, allocation.account_id)
        if not account or account.tenant_id != order.tenant_id:
            raise HTTPException(status_code=409, detail="支付账号已不存在")
        if Decimal(allocation.balance_amount) > 0:
            _append_financial_entry(
                db,
                tenant_id=order.tenant_id,
                user_id=user_id,
                business_date=order.business_date,
                entry_type=FinancialEntryType.BALANCE_COST,
                amount=-Decimal(allocation.balance_amount),
                idempotency_key=f"order:{order.id}:balance-cost:{allocation.id}",
                order_id=order.id,
                plan_id=plan.id,
                allocation_id=allocation.id,
                account_id=account.id,
                device_id=account.device_id,
                note=f"订单 {order.order_no} 支付宝余额成本",
            )
        if Decimal(allocation.external_cash_amount) > 0:
            _append_financial_entry(
                db,
                tenant_id=order.tenant_id,
                user_id=user_id,
                business_date=order.business_date,
                entry_type=FinancialEntryType.EXTERNAL_CASH_COST,
                amount=-Decimal(allocation.external_cash_amount),
                idempotency_key=f"order:{order.id}:external-cash:{allocation.id}",
                order_id=order.id,
                plan_id=plan.id,
                allocation_id=allocation.id,
                account_id=account.id,
                device_id=account.device_id,
                note=f"订单 {order.order_no} 真实付款成本",
            )
    order.customer_received_amount = customer_received
    order.coupon_amount = money(plan.total_coupon)
    order.actual_paid = money(Decimal(plan.total_balance) + Decimal(plan.total_external_cash))
    order.settlement_income = customer_received
    order.commission = ZERO
    order.cost = money(Decimal(plan.total_balance) + Decimal(plan.total_external_cash))
    order.profit = money(customer_received - Decimal(order.cost))
    order.status = OrderStatus.SUCCESS.value
    order.success_at = datetime.now(timezone.utc)


def reverse_order_finance(
    db: Session, *, tenant_id: int, order: Order, user_id: int, reason: str
) -> None:
    entries = list(
        db.scalars(
            select(JijihongFinancialEntry)
            .where(
                JijihongFinancialEntry.tenant_id == tenant_id,
                JijihongFinancialEntry.order_id == order.id,
                JijihongFinancialEntry.entry_type != FinancialEntryType.REVERSAL.value,
            )
            .order_by(JijihongFinancialEntry.id)
        )
    )
    for entry in entries:
        _append_financial_entry(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            business_date=order.business_date,
            entry_type=FinancialEntryType.REVERSAL,
            amount=-Decimal(entry.amount),
            idempotency_key=f"financial:{entry.id}:reversal",
            order_id=order.id,
            plan_id=entry.plan_id,
            allocation_id=entry.allocation_id,
            account_id=entry.account_id,
            device_id=entry.device_id,
            reversed_entry_id=entry.id,
            note=reason,
        )


def get_reconciliation(
    db: Session, tenant_id: int, reconciliation_id: int, *, for_update: bool = False
) -> AlipayReconciliation:
    query = select(AlipayReconciliation).where(
        AlipayReconciliation.id == reconciliation_id,
        AlipayReconciliation.tenant_id == tenant_id,
    )
    if for_update:
        query = query.with_for_update()
    reconciliation = db.scalar(query)
    if not reconciliation:
        raise HTTPException(status_code=404, detail="账号对账单不存在")
    return reconciliation


def create_reconciliation(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    data: ReconciliationCreateInput,
) -> AlipayReconciliation:
    ensure_jijihong(db, tenant_id)
    account_ids = sorted(item.account_id for item in data.items)
    accounts = list(
        db.scalars(
            select(AlipayAccount)
            .where(
                AlipayAccount.tenant_id == tenant_id,
                AlipayAccount.id.in_(account_ids),
            )
            .order_by(AlipayAccount.id)
        )
    )
    by_id = {account.id: account for account in accounts}
    if set(by_id) != set(account_ids):
        raise HTTPException(status_code=404, detail="对账单包含不存在的支付宝账号")
    reconciliation = AlipayReconciliation(
        tenant_id=tenant_id,
        business_date=data.business_date,
        status=ReconciliationStatus.DRAFT.value,
        note=data.note,
        created_by=user_id,
    )
    db.add(reconciliation)
    db.flush()
    for item in data.items:
        account = by_id[item.account_id]
        actual = money(item.actual_balance)
        snapshot = money(account.current_balance)
        db.add(
            AlipayReconciliationItem(
                tenant_id=tenant_id,
                reconciliation_id=reconciliation.id,
                account_id=account.id,
                device_id=account.device_id,
                system_balance_snapshot=snapshot,
                actual_balance=actual,
                difference=money(actual - snapshot),
                reason=item.reason,
            )
        )
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="alipay.reconciliation_created",
        resource_type="alipay_reconciliation",
        resource_id=reconciliation.id,
        payload={"account_count": len(data.items)},
    )
    db.commit()
    db.refresh(reconciliation)
    return reconciliation


def confirm_reconciliation(
    db: Session, *, tenant_id: int, user_id: int, reconciliation_id: int
) -> AlipayReconciliation:
    ensure_jijihong(db, tenant_id)
    reconciliation = get_reconciliation(db, tenant_id, reconciliation_id, for_update=True)
    if reconciliation.status != ReconciliationStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="只有草稿对账单可以确认")
    items = list(
        db.scalars(
            select(AlipayReconciliationItem)
            .where(AlipayReconciliationItem.reconciliation_id == reconciliation.id)
            .order_by(AlipayReconciliationItem.account_id)
            .with_for_update()
        )
    )
    accounts = {
        account.id: account
        for account in db.scalars(
            select(AlipayAccount)
            .where(
                AlipayAccount.tenant_id == tenant_id,
                AlipayAccount.id.in_([item.account_id for item in items]),
            )
            .order_by(AlipayAccount.id)
            .with_for_update()
        )
    }
    for item in items:
        account = accounts[item.account_id]
        if money(account.current_balance) != money(item.system_balance_snapshot):
            raise HTTPException(status_code=409, detail=f"账号 {account.alias} 余额已变化，请重新创建对账单")
        if Decimal(item.actual_balance) < Decimal(account.reserved_balance):
            raise HTTPException(status_code=409, detail=f"账号 {account.alias} 的实际余额小于已预占余额")
    for item in items:
        account = accounts[item.account_id]
        difference = money(item.difference)
        account.current_balance = money(item.actual_balance)
        account.version += 1
        if account.current_balance == 0 and account.reserved_balance == 0:
            account.status = AccountStatus.EXHAUSTED.value
            account.phase = AccountPhase.EXHAUSTED.value
        elif account.current_balance > 0 and account.status == AccountStatus.EXHAUSTED.value:
            account.status = AccountStatus.ACTIVE.value
            account.phase = AccountPhase.DAY2_ACTIVE.value
        balance_entry = _append_balance_entry(
            db,
            account=account,
            user_id=user_id,
            entry_type=BalanceEntryType.RECONCILIATION_ADJUSTMENT,
            balance_delta=difference,
            idempotency_key=f"reconciliation:{reconciliation.id}:adjust:{account.id}",
            reconciliation_id=reconciliation.id,
            reason=item.reason or "账号盘点差异调整",
        )
        db.flush()
        item.adjustment_entry_id = balance_entry.id
        if difference != 0:
            _append_financial_entry(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                business_date=reconciliation.business_date,
                entry_type=FinancialEntryType.RECONCILIATION_GAIN_LOSS,
                amount=difference,
                idempotency_key=f"reconciliation:{reconciliation.id}:gain-loss:{account.id}",
                reconciliation_id=reconciliation.id,
                account_id=account.id,
                device_id=account.device_id,
                note=item.reason or "账号盘盈盘亏",
            )
    reconciliation.status = ReconciliationStatus.CONFIRMED.value
    reconciliation.confirmed_by = user_id
    reconciliation.confirmed_at = datetime.now(timezone.utc)
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="alipay.reconciliation_confirmed",
        resource_type="alipay_reconciliation",
        resource_id=reconciliation.id,
        payload={"account_count": len(items)},
    )
    db.commit()
    db.refresh(reconciliation)
    return reconciliation


def reverse_reconciliation(
    db: Session, *, tenant_id: int, user_id: int, reconciliation_id: int
) -> AlipayReconciliation:
    ensure_jijihong(db, tenant_id)
    reconciliation = get_reconciliation(db, tenant_id, reconciliation_id, for_update=True)
    if reconciliation.status != ReconciliationStatus.CONFIRMED.value:
        raise HTTPException(status_code=409, detail="只有已确认对账单可以冲正")
    items = list(
        db.scalars(
            select(AlipayReconciliationItem)
            .where(AlipayReconciliationItem.reconciliation_id == reconciliation.id)
            .order_by(AlipayReconciliationItem.account_id)
            .with_for_update()
        )
    )
    accounts = {
        account.id: account
        for account in db.scalars(
            select(AlipayAccount)
            .where(
                AlipayAccount.tenant_id == tenant_id,
                AlipayAccount.id.in_([item.account_id for item in items]),
            )
            .order_by(AlipayAccount.id)
            .with_for_update()
        )
    }
    for item in items:
        account = accounts[item.account_id]
        new_balance = money(Decimal(account.current_balance) - Decimal(item.difference))
        if new_balance < Decimal(account.reserved_balance) or new_balance < 0:
            raise HTTPException(status_code=409, detail=f"账号 {account.alias} 当前余额不足以冲正盘点")
    for item in items:
        account = accounts[item.account_id]
        account.current_balance = money(Decimal(account.current_balance) - Decimal(item.difference))
        account.version += 1
        original = db.get(AlipayBalanceEntry, item.adjustment_entry_id) if item.adjustment_entry_id else None
        _append_balance_entry(
            db,
            account=account,
            user_id=user_id,
            entry_type=BalanceEntryType.REVERSAL,
            balance_delta=-Decimal(item.difference),
            idempotency_key=f"reconciliation:{reconciliation.id}:reverse:{account.id}",
            reconciliation_id=reconciliation.id,
            reversed_entry_id=original.id if original else None,
            reason="账号对账冲正",
        )
        financial = db.scalar(
            select(JijihongFinancialEntry).where(
                JijihongFinancialEntry.reconciliation_id == reconciliation.id,
                JijihongFinancialEntry.account_id == account.id,
                JijihongFinancialEntry.entry_type == FinancialEntryType.RECONCILIATION_GAIN_LOSS.value,
            )
        )
        if financial:
            _append_financial_entry(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                business_date=reconciliation.business_date,
                entry_type=FinancialEntryType.REVERSAL,
                amount=-Decimal(financial.amount),
                idempotency_key=f"financial:{financial.id}:reversal",
                reconciliation_id=reconciliation.id,
                account_id=account.id,
                device_id=account.device_id,
                reversed_entry_id=financial.id,
                note="账号对账冲正",
            )
    reconciliation.status = ReconciliationStatus.REVERSED.value
    reconciliation.reversed_by = user_id
    reconciliation.reversed_at = datetime.now(timezone.utc)
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="alipay.reconciliation_reversed",
        resource_type="alipay_reconciliation",
        resource_id=reconciliation.id,
        payload={"account_count": len(items)},
    )
    db.commit()
    db.refresh(reconciliation)
    return reconciliation
