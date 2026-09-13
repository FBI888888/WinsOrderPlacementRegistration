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
from app.modules.alipay_pool.models import (
    AccountStatus,
    AlipayAccount,
    AlipayDevice,
    FinancialEntryType,
    JijihongFinancialEntry,
    OrderPaymentAllocation,
    OrderPaymentPlan,
    PaymentPlanStatus,
)
from app.modules.iam.audit import record_audit
from app.modules.iam.dependencies import CurrentContext, DbSession, require_roles
from app.modules.iam.models import BusinessMode, MemberRole, Tenant, User
from app.modules.orders.models import Order, OrderStatus
from app.modules.orders.query import build_order_filters
from app.modules.partners.models import ContractorType, Source
from app.modules.reports.models import ExportLog, ExportTemplate
from app.modules.reports.schemas import (
    DashboardSummary,
    ExportLogOutput,
    ExportTemplateCreate,
    ExportTemplateOutput,
    PerformanceDailyRow,
    PerformanceGroupRow,
    PerformanceReport,
    PerformanceSummary,
    JijihongBreakdownRow,
    JijihongDailyRow,
    JijihongReportSummary,
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
JIJIHONG_EXPORT_FIELDS = [
    "business_date",
    "order_no",
    "status",
    "order_amount",
    "customer_received",
    "coupon_used",
    "balance_used",
    "external_cash",
    "cost",
    "profit",
    "soft_cap_exceeded",
    "note",
]


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
    tenant = db.get(Tenant, context.tenant_id)
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
    if tenant and tenant.business_mode == BusinessMode.JIJIHONG.value:
        coupon_used, balance_used, external_cash = db.execute(
            select(
                func.coalesce(func.sum(OrderPaymentPlan.total_coupon), 0),
                func.coalesce(func.sum(OrderPaymentPlan.total_balance), 0),
                func.coalesce(func.sum(OrderPaymentPlan.total_external_cash), 0),
            )
            .join(Order, Order.id == OrderPaymentPlan.order_id)
            .where(
                OrderPaymentPlan.tenant_id == context.tenant_id,
                OrderPaymentPlan.status == PaymentPlanStatus.CONFIRMED.value,
                Order.business_date >= date_from,
                Order.business_date <= date_to,
            )
        ).one()
        pool_balance = db.scalar(
            select(func.coalesce(func.sum(AlipayAccount.current_balance), 0)).where(
                AlipayAccount.tenant_id == context.tenant_id
            )
        ) or 0
        gain_loss = db.scalar(
            select(func.coalesce(func.sum(JijihongFinancialEntry.amount), 0)).where(
                JijihongFinancialEntry.tenant_id == context.tenant_id,
                JijihongFinancialEntry.business_date >= date_from,
                JijihongFinancialEntry.business_date <= date_to,
                JijihongFinancialEntry.reconciliation_id.is_not(None),
                JijihongFinancialEntry.entry_type.in_([
                    FinancialEntryType.RECONCILIATION_GAIN_LOSS.value,
                    FinancialEntryType.REVERSAL.value,
                ]),
            )
        ) or 0
        return DashboardSummary(
            business_mode=BusinessMode.JIJIHONG.value,
            date_from=date_from,
            date_to=date_to,
            order_count=order_count,
            success_count=success_count,
            settlement_income=income,
            cost=cost,
            profit=profit,
            advance_balance=pool_balance,
            commission_payable=0,
            source_receivable=0,
            negative_profit_count=negative_count,
            customer_received=income,
            coupon_used=coupon_used,
            balance_used=balance_used,
            external_cash=external_cash,
            pool_balance=pool_balance,
            reconciliation_gain_loss=gain_loss,
            period_net_income=Decimal(profit) + Decimal(gain_loss),
        )
    return DashboardSummary(
        business_mode=BusinessMode.FEDAICHU.value,
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


def _decimal(value) -> Decimal:
    return Decimal(value or 0)


def _ensure_jijihong_report(db: DbSession, tenant_id: int) -> None:
    tenant = db.get(Tenant, tenant_id)
    if not tenant or tenant.business_mode != BusinessMode.JIJIHONG.value:
        raise HTTPException(status_code=404, detail="当前业务模式不提供季季红报表")


def _jijihong_success_filters(tenant_id: int, date_from: date, date_to: date) -> list:
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
    return [
        Order.tenant_id == tenant_id,
        Order.business_date >= date_from,
        Order.business_date <= date_to,
        Order.status == OrderStatus.SUCCESS.value,
        OrderPaymentPlan.status == PaymentPlanStatus.CONFIRMED.value,
    ]


def _jijihong_metrics():
    return (
        func.count(Order.id),
        func.coalesce(func.sum(Order.order_amount), 0),
        func.coalesce(func.sum(Order.customer_received_amount), 0),
        func.coalesce(func.sum(OrderPaymentPlan.total_coupon), 0),
        func.coalesce(func.sum(OrderPaymentPlan.total_balance), 0),
        func.coalesce(func.sum(OrderPaymentPlan.total_external_cash), 0),
        func.coalesce(func.sum(Order.cost), 0),
        func.coalesce(func.sum(Order.profit), 0),
        func.coalesce(
            func.sum(case((OrderPaymentPlan.soft_cap_exceeded.is_(True), 1), else_=0)),
            0,
        ),
    )


@router.get("/jijihong/summary", response_model=JijihongReportSummary)
def jijihong_summary(
    context: CurrentContext,
    db: DbSession,
    date_from: date = Query(default_factory=date.today),
    date_to: date = Query(default_factory=date.today),
) -> JijihongReportSummary:
    _ensure_jijihong_report(db, context.tenant_id)
    filters = _jijihong_success_filters(context.tenant_id, date_from, date_to)
    values = db.execute(
        select(*_jijihong_metrics())
        .join(OrderPaymentPlan, OrderPaymentPlan.order_id == Order.id)
        .where(*filters)
    ).one()
    gain_loss = db.scalar(
        select(func.coalesce(func.sum(JijihongFinancialEntry.amount), 0)).where(
            JijihongFinancialEntry.tenant_id == context.tenant_id,
            JijihongFinancialEntry.business_date >= date_from,
            JijihongFinancialEntry.business_date <= date_to,
            JijihongFinancialEntry.reconciliation_id.is_not(None),
            JijihongFinancialEntry.entry_type.in_(
                [
                    FinancialEntryType.RECONCILIATION_GAIN_LOSS.value,
                    FinancialEntryType.REVERSAL.value,
                ]
            ),
        )
    ) or 0
    exhausted_count = db.scalar(
        select(func.count(AlipayAccount.id)).where(
            AlipayAccount.tenant_id == context.tenant_id,
            AlipayAccount.status == AccountStatus.EXHAUSTED.value,
        )
    ) or 0
    pool_balance = db.scalar(
        select(func.coalesce(func.sum(AlipayAccount.current_balance), 0)).where(
            AlipayAccount.tenant_id == context.tenant_id
        )
    ) or 0
    (
        order_count,
        order_amount,
        customer_received,
        coupon_used,
        balance_used,
        external_cash,
        cost,
        profit,
        soft_cap_count,
    ) = values
    return JijihongReportSummary(
        date_from=date_from,
        date_to=date_to,
        order_count=int(order_count),
        order_amount=_decimal(order_amount),
        customer_received=_decimal(customer_received),
        coupon_used=_decimal(coupon_used),
        balance_used=_decimal(balance_used),
        external_cash=_decimal(external_cash),
        cost=_decimal(cost),
        profit=_decimal(profit),
        reconciliation_gain_loss=_decimal(gain_loss),
        period_net_income=_decimal(profit) + _decimal(gain_loss),
        soft_cap_exceeded_count=int(soft_cap_count),
        exhausted_account_count=int(exhausted_count),
        pool_balance=_decimal(pool_balance),
    )


@router.get("/jijihong/daily", response_model=list[JijihongDailyRow])
def jijihong_daily(
    context: CurrentContext,
    db: DbSession,
    date_from: date = Query(default_factory=date.today),
    date_to: date = Query(default_factory=date.today),
) -> list[JijihongDailyRow]:
    _ensure_jijihong_report(db, context.tenant_id)
    filters = _jijihong_success_filters(context.tenant_id, date_from, date_to)
    rows = db.execute(
        select(Order.business_date, *_jijihong_metrics())
        .join(OrderPaymentPlan, OrderPaymentPlan.order_id == Order.id)
        .where(*filters)
        .group_by(Order.business_date)
        .order_by(Order.business_date)
    ).all()
    return [
        JijihongDailyRow(
            business_date=row[0],
            order_count=int(row[1]),
            order_amount=_decimal(row[2]),
            customer_received=_decimal(row[3]),
            coupon_used=_decimal(row[4]),
            balance_used=_decimal(row[5]),
            external_cash=_decimal(row[6]),
            cost=_decimal(row[7]),
            profit=_decimal(row[8]),
        )
        for row in rows
    ]


@router.get("/jijihong/breakdown", response_model=list[JijihongBreakdownRow])
def jijihong_breakdown(
    context: CurrentContext,
    db: DbSession,
    group_by: str = Query(pattern="^(device|account|operator)$"),
    date_from: date = Query(default_factory=date.today),
    date_to: date = Query(default_factory=date.today),
) -> list[JijihongBreakdownRow]:
    _ensure_jijihong_report(db, context.tenant_id)
    filters = _jijihong_success_filters(context.tenant_id, date_from, date_to)
    buckets: dict[int, dict] = {}
    if group_by == "operator":
        rows = db.execute(
            select(Order, OrderPaymentPlan, User)
            .join(OrderPaymentPlan, OrderPaymentPlan.order_id == Order.id)
            .join(User, User.id == Order.created_by)
            .where(*filters)
        ).all()
        for order, plan, user in rows:
            bucket = buckets.setdefault(
                user.id,
                {"name": user.name, "orders": set(), "order": Decimal(0), "received": Decimal(0),
                 "coupon": Decimal(0), "balance": Decimal(0), "cash": Decimal(0), "cost": Decimal(0),
                 "profit": Decimal(0)},
            )
            bucket["orders"].add(order.id)
            bucket["order"] += _decimal(order.order_amount)
            bucket["received"] += _decimal(order.customer_received_amount)
            bucket["coupon"] += _decimal(plan.total_coupon)
            bucket["balance"] += _decimal(plan.total_balance)
            bucket["cash"] += _decimal(plan.total_external_cash)
            bucket["cost"] += _decimal(order.cost)
            bucket["profit"] += _decimal(order.profit)
    else:
        rows = db.execute(
            select(Order, OrderPaymentAllocation, AlipayAccount, AlipayDevice)
            .join(OrderPaymentPlan, OrderPaymentPlan.order_id == Order.id)
            .join(OrderPaymentAllocation, OrderPaymentAllocation.plan_id == OrderPaymentPlan.id)
            .join(AlipayAccount, AlipayAccount.id == OrderPaymentAllocation.account_id)
            .join(AlipayDevice, AlipayDevice.id == AlipayAccount.device_id)
            .where(*filters)
        ).all()
        for order, allocation, account, device in rows:
            entity_id = device.id if group_by == "device" else account.id
            entity_name = device.name if group_by == "device" else account.alias
            bucket = buckets.setdefault(
                entity_id,
                {"name": entity_name, "orders": set(), "order": Decimal(0), "received": Decimal(0),
                 "coupon": Decimal(0), "balance": Decimal(0), "cash": Decimal(0), "cost": Decimal(0),
                 "profit": Decimal(0)},
            )
            gross = _decimal(allocation.coupon_amount) + _decimal(allocation.balance_amount) + _decimal(allocation.external_cash_amount)
            ratio = gross / _decimal(order.order_amount) if _decimal(order.order_amount) else Decimal(0)
            bucket["orders"].add(order.id)
            bucket["order"] += gross
            bucket["received"] += _decimal(order.customer_received_amount) * ratio
            bucket["coupon"] += _decimal(allocation.coupon_amount)
            bucket["balance"] += _decimal(allocation.balance_amount)
            bucket["cash"] += _decimal(allocation.external_cash_amount)
            bucket["cost"] += (_decimal(allocation.balance_amount) + _decimal(allocation.external_cash_amount))
            bucket["profit"] += _decimal(order.profit) * ratio
    return [
        JijihongBreakdownRow(
            group_type=group_by,
            entity_id=entity_id,
            entity_name=bucket["name"],
            order_count=len(bucket["orders"]),
            order_amount=bucket["order"],
            customer_received=bucket["received"],
            coupon_used=bucket["coupon"],
            balance_used=bucket["balance"],
            external_cash=bucket["cash"],
            cost=bucket["cost"],
            profit=bucket["profit"],
        )
        for entity_id, bucket in sorted(buckets.items(), key=lambda item: item[1]["profit"], reverse=True)
    ]


def _performance_metrics():
    return (
        func.count(Order.id),
        func.coalesce(func.sum(Order.order_amount), 0),
        func.coalesce(func.sum(Order.coupon_amount), 0),
        func.coalesce(func.sum(Order.actual_paid), 0),
        func.coalesce(func.sum(Order.settlement_income), 0),
        func.coalesce(func.sum(Order.cost), 0),
        func.coalesce(func.sum(Order.commission), 0),
        func.coalesce(func.sum(Order.profit), 0),
        func.coalesce(func.sum(case((Order.profit < 0, 1), else_=0)), 0),
    )


def _performance_group(
    db,
    *,
    base_filters: list,
    group_type: str,
    entity_id_column,
    entity_name_column,
    extra_filters: list | None = None,
    join_source: bool = False,
) -> list[PerformanceGroupRow]:
    filters = [*base_filters, *(extra_filters or [])]
    query = select(
        entity_id_column,
        entity_name_column,
        func.count(Order.id),
        func.coalesce(func.sum(Order.order_amount), 0),
        func.coalesce(func.sum(Order.coupon_amount), 0),
        func.coalesce(func.sum(Order.actual_paid), 0),
        func.coalesce(func.sum(Order.settlement_income), 0),
        func.coalesce(func.sum(Order.cost), 0),
        func.coalesce(func.sum(Order.commission), 0),
        func.coalesce(func.sum(Order.profit), 0),
    )
    if join_source:
        query = query.join(Source, Source.id == Order.source_id)
    rows = db.execute(
        query.where(*filters)
        .group_by(entity_id_column, entity_name_column)
        .order_by(func.sum(Order.profit).desc(), entity_name_column)
    ).all()
    return [
        PerformanceGroupRow(
            group_type=group_type,
            entity_id=entity_id,
            entity_name=entity_name or "未命名",
            order_count=order_count,
            order_amount=_decimal(order_amount),
            coupon_amount=_decimal(coupon_amount),
            actual_paid=_decimal(actual_paid),
            settlement_income=_decimal(settlement_income),
            cost=_decimal(cost),
            commission=_decimal(commission),
            profit=_decimal(profit),
        )
        for (
            entity_id,
            entity_name,
            order_count,
            order_amount,
            coupon_amount,
            actual_paid,
            settlement_income,
            cost,
            commission,
            profit,
        ) in rows
    ]


@router.get("/performance", response_model=PerformanceReport)
def performance_report(
    context: CurrentContext,
    db: DbSession,
    date_from: date = Query(default_factory=date.today),
    date_to: date = Query(default_factory=date.today),
) -> PerformanceReport:
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
    base_filters = [
        Order.tenant_id == context.tenant_id,
        Order.business_date >= date_from,
        Order.business_date <= date_to,
        Order.status == OrderStatus.SUCCESS.value,
    ]
    (
        order_count,
        order_amount,
        coupon_amount,
        actual_paid,
        settlement_income,
        cost,
        commission,
        profit,
        negative_count,
    ) = db.execute(select(*_performance_metrics()).where(*base_filters)).one()
    return PerformanceReport(
        summary=PerformanceSummary(
            date_from=date_from,
            date_to=date_to,
            order_count=order_count,
            order_amount=_decimal(order_amount),
            coupon_amount=_decimal(coupon_amount),
            actual_paid=_decimal(actual_paid),
            settlement_income=_decimal(settlement_income),
            cost=_decimal(cost),
            commission=_decimal(commission),
            profit=_decimal(profit),
            negative_profit_count=int(negative_count),
        ),
        sources=_performance_group(
            db,
            base_filters=base_filters,
            group_type="source",
            entity_id_column=Order.source_id,
            entity_name_column=Source.name,
            join_source=True,
        ),
        leaders=_performance_group(
            db,
            base_filters=base_filters,
            group_type="leader",
            entity_id_column=Order.contractor_id,
            entity_name_column=Order.contractor_name_snapshot,
            extra_filters=[Order.contractor_type == ContractorType.LEADER.value],
        ),
        retails=_performance_group(
            db,
            base_filters=base_filters,
            group_type="retail",
            entity_id_column=Order.contractor_id,
            entity_name_column=Order.contractor_name_snapshot,
            extra_filters=[Order.contractor_type == ContractorType.RETAIL.value],
        ),
        performers=_performance_group(
            db,
            base_filters=base_filters,
            group_type="performer",
            entity_id_column=Order.performer_id,
            entity_name_column=Order.performer_name_snapshot,
            extra_filters=[Order.performer_id.is_not(None)],
        ),
    )


@router.get("/performance/daily", response_model=list[PerformanceDailyRow])
def daily_performance_report(
    context: CurrentContext,
    db: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[PerformanceDailyRow]:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
    filters = [
        Order.tenant_id == context.tenant_id,
        Order.status == OrderStatus.SUCCESS.value,
    ]
    if date_from:
        filters.append(Order.business_date >= date_from)
    if date_to:
        filters.append(Order.business_date <= date_to)
    rows = db.execute(
        select(Order.business_date, *_performance_metrics())
        .where(*filters)
        .group_by(Order.business_date)
        .order_by(Order.business_date.desc())
    ).all()
    return [
        PerformanceDailyRow(
            business_date=business_date,
            order_count=order_count,
            order_amount=_decimal(order_amount),
            coupon_amount=_decimal(coupon_amount),
            actual_paid=_decimal(actual_paid),
            settlement_income=_decimal(settlement_income),
            cost=_decimal(cost),
            commission=_decimal(commission),
            profit=_decimal(profit),
            negative_profit_count=int(negative_count),
        )
        for (
            business_date,
            order_count,
            order_amount,
            coupon_amount,
            actual_paid,
            settlement_income,
            cost,
            commission,
            profit,
            negative_count,
        ) in rows
    ]


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
    performer_id: int | None = None,
    contractor_type: ContractorType | None = None,
    keyword: str | None = Query(default=None, max_length=100),
):
    invalid_fields = set(fields) - set(FIELD_DEFINITIONS)
    if invalid_fields or not fields:
        raise HTTPException(status_code=422, detail="导出字段无效")
    filters = build_order_filters(
        tenant_id=context.tenant_id,
        date_from=date_from,
        date_to=date_to,
        order_status=order_status,
        source_id=source_id,
        contractor_id=contractor_id,
        performer_id=performer_id,
        contractor_type=contractor_type,
        keyword=keyword,
    )
    if order_ids:
        filters.append(Order.id.in_(order_ids))

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
        "performer_id": performer_id,
        "contractor_type": contractor_type.value if contractor_type else None,
        "keyword": keyword,
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


@router.get("/jijihong/orders/export")
def export_jijihong_orders(
    context: CurrentContext,
    db: DbSession,
    export_format: str = Query(default="xlsx", pattern="^(xlsx|csv)$"),
    date_from: date | None = None,
    date_to: date | None = None,
):
    _ensure_jijihong_report(db, context.tenant_id)
    filters = [Order.tenant_id == context.tenant_id]
    if date_from:
        filters.append(Order.business_date >= date_from)
    if date_to:
        filters.append(Order.business_date <= date_to)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
    records = db.execute(
        select(Order, OrderPaymentPlan)
        .outerjoin(
            OrderPaymentPlan,
            (OrderPaymentPlan.order_id == Order.id)
            & (OrderPaymentPlan.status == PaymentPlanStatus.CONFIRMED.value),
        )
        .where(*filters)
        .order_by(Order.business_date, Order.id)
        .limit(100_000)
    ).all()
    headers = [
        "业务日期", "订单号", "状态", "订单金额", "客户实收", "优惠券",
        "支付宝余额消耗", "真实付款", "订单成本", "订单利润", "真实付款超限", "备注",
    ]
    rows = [
        [
            order.business_date.isoformat(),
            order.order_no,
            order.status,
            float(order.order_amount),
            float(order.customer_received_amount or 0),
            float(plan.total_coupon if plan else order.coupon_amount),
            float(plan.total_balance if plan else 0),
            float(plan.total_external_cash if plan else 0),
            float(order.cost),
            float(order.profit),
            "是" if plan and plan.soft_cap_exceeded else "否",
            order.note or "",
        ]
        for order, plan in records
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
        sheet.title = "季季红订单"
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        sheet.freeze_panes = "A2"
        for column in sheet.columns:
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = min(
                max(len(str(cell.value or "")) for cell in column) + 2, 24
            )
        buffer = BytesIO()
        workbook.save(buffer)
        content = buffer.getvalue()
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    db.add(
        ExportLog(
            tenant_id=context.tenant_id,
            export_format=export_format,
            filters={
                "business_mode": BusinessMode.JIJIHONG.value,
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
            },
            fields=JIJIHONG_EXPORT_FIELDS,
            row_count=len(rows),
            file_hash=sha256(content).hexdigest(),
            created_by=context.user_id,
        )
    )
    record_audit(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action="report.jijihong_exported",
        resource_type="export_log",
        payload={"format": export_format, "row_count": len(rows)},
    )
    db.commit()
    filename = f"jijihong-orders-{date.today():%Y%m%d}.{export_format}"
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
