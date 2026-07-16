from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.funds.models import LedgerAccount, LedgerEntry, LedgerEntryType


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
        contractor_id=contractor_id,
        source_id=source_id,
        order_id=order_id,
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
) -> Decimal:
    query = select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
        LedgerEntry.tenant_id == tenant_id,
        LedgerEntry.account == account.value,
    )
    if contractor_id is not None:
        query = query.where(LedgerEntry.contractor_id == contractor_id)
    if source_id is not None:
        query = query.where(LedgerEntry.source_id == source_id)
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