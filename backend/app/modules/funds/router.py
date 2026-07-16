from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.modules.funds.models import LedgerAccount, LedgerEntry, LedgerEntryType
from app.modules.funds.schemas import (
    BalanceOutput,
    LedgerOutput,
    ManualTransactionType,
    TransactionCreate,
)
from app.modules.funds.service import append_entry
from app.modules.iam.audit import record_audit
from app.modules.iam.dependencies import CurrentContext, DbSession, require_roles
from app.modules.iam.models import MemberRole
from app.modules.partners.models import Contractor, Source
from app.modules.partners.service import get_contractor, get_source

router = APIRouter(prefix="/funds", tags=["资金流水"])
write_roles = (MemberRole.OWNER.value, MemberRole.BOOKKEEPER.value)


@router.get("/entries", response_model=list[LedgerOutput])
def list_entries(
    context: CurrentContext,
    db: DbSession,
    account: LedgerAccount | None = None,
    contractor_id: int | None = None,
    source_id: int | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[LedgerEntry]:
    query = select(LedgerEntry).where(LedgerEntry.tenant_id == context.tenant_id)
    if account:
        query = query.where(LedgerEntry.account == account.value)
    if contractor_id:
        query = query.where(LedgerEntry.contractor_id == contractor_id)
    if source_id:
        query = query.where(LedgerEntry.source_id == source_id)
    return list(db.scalars(query.order_by(LedgerEntry.business_date.desc(), LedgerEntry.id.desc()).limit(limit)))


@router.post("/transactions", response_model=LedgerOutput, status_code=201)
def create_transaction(
    data: TransactionCreate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> LedgerEntry:
    mapping = {
        ManualTransactionType.ADVANCE_TOPUP: (
            LedgerAccount.ADVANCE,
            LedgerEntryType.ADVANCE_TOPUP,
            Decimal("1"),
        ),
        ManualTransactionType.ADVANCE_RETURN: (
            LedgerAccount.ADVANCE,
            LedgerEntryType.ADVANCE_RETURN,
            Decimal("-1"),
        ),
        ManualTransactionType.COMMISSION_PAYMENT: (
            LedgerAccount.COMMISSION_PAYABLE,
            LedgerEntryType.COMMISSION_PAYMENT,
            Decimal("-1"),
        ),
        ManualTransactionType.SOURCE_RECEIPT: (
            LedgerAccount.SOURCE_RECEIVABLE,
            LedgerEntryType.SOURCE_RECEIPT,
            Decimal("-1"),
        ),
    }
    account, entry_type, sign = mapping[data.transaction_type]
    if data.contractor_id:
        get_contractor(db, context.tenant_id, data.contractor_id)
    if data.source_id:
        get_source(db, context.tenant_id, data.source_id)
    entry = append_entry(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        business_date=data.business_date,
        account=account,
        entry_type=entry_type,
        amount=data.amount * sign,
        contractor_id=data.contractor_id,
        source_id=data.source_id,
        note=data.note,
    )
    db.flush()
    record_audit(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action="fund.transaction_created",
        resource_type="ledger_entry",
        resource_id=entry.id,
        payload=data.model_dump(mode="json"),
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/balances", response_model=list[BalanceOutput])
def list_balances(context: CurrentContext, db: DbSession) -> list[BalanceOutput]:
    contractor_rows = db.execute(
        select(
            LedgerEntry.account,
            Contractor.id,
            Contractor.name,
            func.coalesce(func.sum(LedgerEntry.amount), 0),
        )
        .join(Contractor, Contractor.id == LedgerEntry.contractor_id)
        .where(LedgerEntry.tenant_id == context.tenant_id)
        .group_by(LedgerEntry.account, Contractor.id, Contractor.name)
    ).all()
    source_rows = db.execute(
        select(
            LedgerEntry.account,
            Source.id,
            Source.name,
            func.coalesce(func.sum(LedgerEntry.amount), 0),
        )
        .join(Source, Source.id == LedgerEntry.source_id)
        .where(LedgerEntry.tenant_id == context.tenant_id)
        .group_by(LedgerEntry.account, Source.id, Source.name)
    ).all()
    return [
        BalanceOutput(
            account=LedgerAccount(account),
            counterparty_id=counterparty_id,
            counterparty_name=name,
            balance=Decimal(balance),
        )
        for account, counterparty_id, name, balance in [*contractor_rows, *source_rows]
    ]