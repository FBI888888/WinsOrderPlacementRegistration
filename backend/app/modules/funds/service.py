from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.funds.models import LedgerAccount, LedgerEntry, LedgerEntryType


@dataclass(frozen=True)
class LedgerBalanceSnapshot:
    advance_balance: Decimal
    commission_payable: Decimal
    net_settlement: Decimal
    source_receivable: Decimal


def order_balance_snapshot(
    db: Session,
    *,
    tenant_id: int,
    contractor_id: int,
    source_id: int,
    actual_paid: Decimal,
    commission: Decimal,
    settlement_income: Decimal,
) -> LedgerBalanceSnapshot:
    db.flush()
    advance_balance = get_balance(
        db,
        tenant_id=tenant_id,
        account=LedgerAccount.ADVANCE,
        contractor_id=contractor_id,
    ) - actual_paid
    commission_payable = get_balance(
        db,
        tenant_id=tenant_id,
        account=LedgerAccount.COMMISSION_PAYABLE,
        contractor_id=contractor_id,
    ) + commission
    source_receivable = get_balance(
        db,
        tenant_id=tenant_id,
        account=LedgerAccount.SOURCE_RECEIVABLE,
        source_id=source_id,
    ) + settlement_income
    return LedgerBalanceSnapshot(
        advance_balance=advance_balance,
        commission_payable=commission_payable,
        net_settlement=advance_balance - commission_payable,
        source_receivable=source_receivable,
    )


def append_entry(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    business_date: date,
    account: LedgerAccount,
    entry_type: LedgerEntryType,
    amount: Decimal,
    contractor_id: int | None = None,
    source_id: int | None = None,
    order_id: int | None = None,
    snapshot: LedgerBalanceSnapshot | None = None,
    settlement_id: int | None = None,
    reversed_entry_id: int | None = None,
    note: str | None = None,
) -> LedgerEntry:
    entry = LedgerEntry(
        tenant_id=tenant_id,
        created_by=user_id,
        business_date=business_date,
        account=account.value,
        entry_type=entry_type.value,
        amount=amount,
        advance_balance_snapshot=(
            snapshot.advance_balance
            if snapshot is not None and account in {
                LedgerAccount.ADVANCE,
                LedgerAccount.COMMISSION_PAYABLE,
            }
            else None
        ),
        commission_payable_snapshot=(
            snapshot.commission_payable
            if snapshot is not None and account in {
                LedgerAccount.ADVANCE,
                LedgerAccount.COMMISSION_PAYABLE,
            }
            else None
        ),
        net_settlement_snapshot=(
            snapshot.net_settlement
            if snapshot is not None and account in {
                LedgerAccount.ADVANCE,
                LedgerAccount.COMMISSION_PAYABLE,
            }
            else None
        ),
        source_receivable_snapshot=(
            snapshot.source_receivable
            if snapshot is not None and account == LedgerAccount.SOURCE_RECEIVABLE
            else None
        ),
        contractor_id=contractor_id,
        source_id=source_id,
        order_id=order_id,
        settlement_id=settlement_id,
        reversed_entry_id=reversed_entry_id,
        note=note,
    )
    db.add(entry)
    return entry


def get_balance(
    db: Session,
    *,
    tenant_id: int,
    account: LedgerAccount,
    contractor_id: int | None = None,
    source_id: int | None = None,
    date_to: date | None = None,
) -> Decimal:
    query = select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
        LedgerEntry.tenant_id == tenant_id,
        LedgerEntry.account == account.value,
    )
    if contractor_id is not None:
        query = query.where(LedgerEntry.contractor_id == contractor_id)
    if source_id is not None:
        query = query.where(LedgerEntry.source_id == source_id)
    if date_to is not None:
        query = query.where(LedgerEntry.business_date <= date_to)
    return Decimal(db.scalar(query) or 0)


def reverse_order_entries(
    db: Session,
    *,
    tenant_id: int,
    order_id: int,
    user_id: int,
    business_date: date,
    note: str,
) -> None:
    entries = list(
        db.scalars(
            select(LedgerEntry).where(
                LedgerEntry.tenant_id == tenant_id,
                LedgerEntry.order_id == order_id,
                LedgerEntry.reversed_entry_id.is_(None),
                LedgerEntry.entry_type != LedgerEntryType.REVERSAL.value,
            )
        )
    )
    already_reversed = set(
        db.scalars(
            select(LedgerEntry.reversed_entry_id).where(
                LedgerEntry.tenant_id == tenant_id,
                LedgerEntry.order_id == order_id,
                LedgerEntry.entry_type == LedgerEntryType.REVERSAL.value,
            )
        )
    )
    for entry in entries:
        if entry.id in already_reversed:
            continue
        append_entry(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            business_date=business_date,
            account=LedgerAccount(entry.account),
            entry_type=LedgerEntryType.REVERSAL,
            amount=-Decimal(entry.amount),
            contractor_id=entry.contractor_id,
            source_id=entry.source_id,
            order_id=order_id,
            reversed_entry_id=entry.id,
            note=note,
        )