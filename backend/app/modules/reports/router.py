import csv
from datetime import date
from decimal import Decimal
from hashlib import sha256
from io import BytesIO, StringIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import case, func, select

from app.modules.funds.models import LedgerAccount, LedgerEntry
from app.modules.iam.audit import record_audit
from app.modules.iam.dependencies import CurrentContext, DbSession, require_roles
from app.modules.iam.models import MemberRole
from app.modules.orders.models import Order, OrderStatus
from app.modules.partners.models import ContractorType, Source
from app.modules.reports.models import ExportLog, ExportTemplate
from app.modules.reports.schemas import (
    DashboardSummary,
    ExportLogOutput,
    ExportTemplateCreate,
    ExportTemplateOutput,
)

router = APIRouter(prefix="/reports", tags=["报表与导出"])

FIELD_DEFINITIONS = {
    "business_date": ("业务日期", lambda order, source: order.business_date.isoformat()),
    "order_no": ("订单号", lambda order, source: order.order_no),
    "status": ("状态", lambda order, source: order.status),
    "source_name": ("放单人员", lambda order, source: source),
    "contractor_type": ("做单类型", lambda order, source: order.contractor_type),
    "contractor_name": ("结算合作方/学生头子", lambda order, source: order.contractor_name_snapshot),
    "student_name": ("实际做单人", lambda order, source: order.performer_name_snapshot or ""),
    "order_amount": ("订单标价", lambda order, source: float(order.order_amount)),
    "coupon_amount": ("优惠券金额", lambda order, source: float(order.coupon_amount)),
    "actual_paid": ("实付金额", lambda order, source: float(order.actual_paid)),
    "settlement_income": ("结算收入", lambda order, source: float(order.settlement_income)),
    "commission": ("佣金", lambda order, source: float(order.commission)),
    "cost": ("成本", lambda order, source: float(order.cost)),
    "profit": ("利润", lambda order, source: float(order.profit)),
    "note": ("备注", lambda order, source: order.note or ""),
}
DEFAULT_FIELDS = list(FIELD_DEFINITIONS)


def _ledger_total(db, tenant_id: int, account: LedgerAccount) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.tenant_id == tenant_id,
            LedgerEntry.account == account.value,
        )
    )
    return Decimal(value or 0)


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(
    context: CurrentContext,
    db: DbSession,
    date_from: date = Query(default_factory=date.today),
    date_to: date = Query(default_factory=date.today),
) -> DashboardSummary:
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
    base = [
        Order.tenant_id == context.tenant_id,
        Order.business_date >= date_from,
        Order.business_date <= date_to,
    ]
    order_count = db.scalar(select(func.count(Order.id)).where(*base)) or 0
    success_filters = [*base, Order.status == OrderStatus.SUCCESS.value]
    success_count, income, cost, profit, negative_count = db.execute(
        select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.settlement_income), 0),
            func.coalesce(func.sum(Order.cost), 0),
            func.coalesce(func.sum(Order.profit), 0),
            func.coalesce(func.sum(case((Order.profit < 0, 1), else_=0)), 0),
        ).where(*success_filters)
    ).one()
    return DashboardSummary(
        date_from=date_from,
        date_to=date_to,
        order_count=order_count,
        success_count=success_count,
        settlement_income=Decimal(income),
        cost=Decimal(cost),
        profit=Decimal(profit),
        advance_balance=_ledger_total(db, context.tenant_id, LedgerAccount.ADVANCE),
        commission_payable=_ledger_total(
            db, context.tenant_id, LedgerAccount.COMMISSION_PAYABLE
        ),
        source_receivable=_ledger_total(
            db, context.tenant_id, LedgerAccount.SOURCE_RECEIVABLE
        ),
        negative_profit_count=int(negative_count),
    )


@router.get("/export-fields")
def export_fields(context: CurrentContext) -> list[dict]:
    return [{"value": key, "label": label} for key, (label, _) in FIELD_DEFINITIONS.items()]


@router.get("/orders/export")
def export_orders(
    context: CurrentContext,
    db: DbSession,
    export_format: str = Query(default="xlsx", pattern="^(xlsx|csv)$"),
    fields: list[str] = Query(default=DEFAULT_FIELDS),
    order_ids: list[int] | None = Query(default=None),
    date_from: date | None = None,
    date_to: date | None = None,
    order_status: OrderStatus | None = Query(default=None, alias="status"),
    source_id: int | None = None,
    contractor_id: int | None = None,
    contractor_type: ContractorType | None = None,
):
    invalid_fields = set(fields) - set(FIELD_DEFINITIONS)
    if invalid_fields or not fields:
        raise HTTPException(status_code=422, detail="导出字段无效")
    filters = [Order.tenant_id == context.tenant_id]
    if order_ids:
        filters.append(Order.id.in_(order_ids))
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

    records = db.execute(
        select(Order, Source.name)
        .join(Source, Source.id == Order.source_id)
        .where(*filters)
        .order_by(Order.business_date, Order.id)
        .limit(100_000)
    ).all()
    headers = [FIELD_DEFINITIONS[field][0] for field in fields]
    rows = [
        [FIELD_DEFINITIONS[field][1](order, source_name) for field in fields]
        for order, source_name in records
    ]
    if export_format == "csv":
        text = StringIO(newline="")
        writer = csv.writer(text)
        writer.writerow(headers)
        writer.writerows(rows)
        content = text.getvalue().encode("utf-8-sig")
        media_type = "text/csv; charset=utf-8"
    else:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "订单明细"
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        sheet.freeze_panes = "A2"
        for column in sheet.columns:
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = min(
                max(len(str(cell.value or "")) for cell in column) + 2, 28
            )
        buffer = BytesIO()
        workbook.save(buffer)
        content = buffer.getvalue()
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    filter_snapshot = {
        "order_ids": order_ids,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "status": order_status.value if order_status else None,
        "source_id": source_id,
        "contractor_id": contractor_id,
        "contractor_type": contractor_type.value if contractor_type else None,
    }
    digest = sha256(content).hexdigest()
    log = ExportLog(
        tenant_id=context.tenant_id,
        export_format=export_format,
        filters=filter_snapshot,
        fields=fields,
        row_count=len(rows),
        file_hash=digest,
        created_by=context.user_id,
    )
    db.add(log)
    record_audit(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action="report.exported",
        resource_type="export_log",
        payload={"format": export_format, "row_count": len(rows)},
    )
    db.commit()
    filename = f"orders-{date.today():%Y%m%d}.{export_format}"
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/templates", response_model=list[ExportTemplateOutput])
def list_templates(context: CurrentContext, db: DbSession) -> list[ExportTemplate]:
    return list(
        db.scalars(
            select(ExportTemplate)
            .where(ExportTemplate.tenant_id == context.tenant_id)
            .order_by(ExportTemplate.id.desc())
        )
    )


@router.post("/templates", response_model=ExportTemplateOutput, status_code=201)
def create_template(
    data: ExportTemplateCreate,
    db: DbSession,
    context=Depends(require_roles(MemberRole.OWNER.value, MemberRole.BOOKKEEPER.value)),
) -> ExportTemplate:
    if set(data.fields) - set(FIELD_DEFINITIONS):
        raise HTTPException(status_code=422, detail="模板包含无效字段")
    template = ExportTemplate(
        tenant_id=context.tenant_id,
        name=data.name,
        fields=data.fields,
        filters=data.filters,
        created_by=context.user_id,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.get("/export-logs", response_model=list[ExportLogOutput])
def list_export_logs(context: CurrentContext, db: DbSession) -> list[ExportLog]:
    return list(
        db.scalars(
            select(ExportLog)
            .where(ExportLog.tenant_id == context.tenant_id)
            .order_by(ExportLog.id.desc())
            .limit(100)
        )
    )