from datetime import date
from decimal import Decimal
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
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

ENTRY_TYPE_TEXT = {
    LedgerEntryType.ADVANCE_TOPUP.value: "垫资/补款",
    LedgerEntryType.ORDER_PAYMENT.value: "订单实付",
    LedgerEntryType.ADVANCE_RETURN.value: "退回垫资",
    LedgerEntryType.COMMISSION_ACCRUAL.value: "佣金计提",
    LedgerEntryType.COMMISSION_PAYMENT.value: "支付佣金",
    LedgerEntryType.SOURCE_ACCRUAL.value: "放单应收",
    LedgerEntryType.SOURCE_RECEIPT.value: "放单收款",
    LedgerEntryType.REVERSAL.value: "冲正流水",
}
ACCOUNT_TEXT = {
    LedgerAccount.ADVANCE.value: "垫资余额",
    LedgerAccount.COMMISSION_PAYABLE.value: "佣金应付",
    LedgerAccount.SOURCE_RECEIVABLE.value: "放单应收",
}
MAX_EXPORT_ROWS = 100_000


def _entry_filters(
    *,
    tenant_id: int,
    account: LedgerAccount | None = None,
    contractor_id: int | None = None,
    source_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
    filters = [LedgerEntry.tenant_id == tenant_id]
    if account is not None:
        filters.append(LedgerEntry.account == account.value)
    if contractor_id is not None:
        filters.append(LedgerEntry.contractor_id == contractor_id)
    if source_id is not None:
        filters.append(LedgerEntry.source_id == source_id)
    if date_from is not None:
        filters.append(LedgerEntry.business_date >= date_from)
    if date_to is not None:
        filters.append(LedgerEntry.business_date <= date_to)
    return filters


def _optional_amount(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


@router.get("/entries", response_model=list[LedgerOutput])
def list_entries(
    context: CurrentContext,
    db: DbSession,
    account: LedgerAccount | None = None,
    contractor_id: int | None = None,
    source_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[LedgerEntry]:
    filters = _entry_filters(
        tenant_id=context.tenant_id,
        account=account,
        contractor_id=contractor_id,
        source_id=source_id,
        date_from=date_from,
        date_to=date_to,
    )
    query = (
        select(LedgerEntry)
        .where(*filters)
        .order_by(LedgerEntry.business_date.desc(), LedgerEntry.id.desc())
        .limit(limit)
    )
    return list(db.scalars(query))


@router.get("/entries/export")
def export_entries(
    context: CurrentContext,
    db: DbSession,
    date_from: date,
    date_to: date,
    contractor_id: int | None = None,
    source_id: int | None = None,
):
    if (contractor_id is None) == (source_id is None):
        raise HTTPException(status_code=422, detail="必须且只能选择一个往来对象")

    if contractor_id is not None:
        counterparty = get_contractor(db, context.tenant_id, contractor_id)
        counterparty_kind = "contractor"
        counterparty_id = contractor_id
    else:
        assert source_id is not None
        counterparty = get_source(db, context.tenant_id, source_id)
        counterparty_kind = "source"
        counterparty_id = source_id

    filters = _entry_filters(
        tenant_id=context.tenant_id,
        contractor_id=contractor_id,
        source_id=source_id,
        date_from=date_from,
        date_to=date_to,
    )
    records = list(
        db.scalars(
            select(LedgerEntry)
            .where(*filters)
            .order_by(LedgerEntry.business_date.desc(), LedgerEntry.id.desc())
            .limit(MAX_EXPORT_ROWS + 1)
        )
    )
    if len(records) > MAX_EXPORT_ROWS:
        raise HTTPException(status_code=413, detail="导出数据超过 100000 条，请缩小日期范围")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "资金流水"
    sheet.append(
        [
            "流水ID",
            "业务日期",
            "记录时间",
            "流水类型",
            "账户",
            "往来对象",
            "关联订单",
            "关联结算单",
            "变动金额",
            "垫资可用余额",
            "待付佣金",
            "扣佣待结算",
            "放单应收",
            "备注",
        ]
    )
    for entry in records:
        sheet.append(
            [
                entry.id,
                entry.business_date.isoformat(),
                entry.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                ENTRY_TYPE_TEXT.get(entry.entry_type, entry.entry_type),
                ACCOUNT_TEXT.get(entry.account, entry.account),
                counterparty.name,
                entry.order_id,
                entry.settlement_id,
                float(entry.amount),
                _optional_amount(entry.advance_balance_snapshot),
                _optional_amount(entry.commission_payable_snapshot),
                _optional_amount(entry.net_settlement_snapshot),
                _optional_amount(entry.source_receivable_snapshot),
                entry.note or "",
            ]
        )

    sheet.freeze_panes = "A2"
    for row in sheet.iter_rows(min_row=2, min_col=9, max_col=13):
        for cell in row:
            cell.number_format = "0.00;[Red]-0.00"
    for column in sheet.columns:
        letter = column[0].column_letter
        sheet.column_dimensions[letter].width = min(
            max(len(str(cell.value or "")) for cell in column) + 2,
            28,
        )

    buffer = BytesIO()
    workbook.save(buffer)
    content = buffer.getvalue()
    record_audit(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action="fund.ledger_exported",
        resource_type=counterparty_kind,
        resource_id=counterparty_id,
        payload={
            "counterparty_name": counterparty.name,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "row_count": len(records),
        },
    )
    db.commit()

    filename = (
        f"ledger-{counterparty_kind}-{counterparty_id}-"
        f"{date_from:%Y%m%d}-{date_to:%Y%m%d}.xlsx"
    )
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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