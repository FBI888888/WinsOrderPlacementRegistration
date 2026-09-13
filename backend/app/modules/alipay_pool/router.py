from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select

from app.modules.alipay_pool.importer import create_preview
from app.modules.alipay_pool.models import (
    AccountPhase,
    AccountStatus,
    AlipayAccount,
    AlipayBalanceEntry,
    AlipayCoupon,
    AlipayDevice,
    AlipayImportBatch,
    AlipayImportRow,
    AlipayReconciliation,
    AlipayReconciliationItem,
    FinancialEntryType,
    ImportRowStatus,
    JijihongFinancialEntry,
    OrderPaymentAllocation,
    OrderPaymentPlan,
)
from app.modules.alipay_pool.plan_service import (
    confirm_plan,
    create_jijihong_order_and_reserve,
    expire_plans,
    get_order_plan,
    preview_recommendation,
    recommend_and_reserve,
    replace_jijihong_reservation,
)
from app.modules.alipay_pool.schemas import (
    AccountCreate,
    AccountOutput,
    AccountUpdate,
    AllocationOutput,
    BalanceAdjustmentInput,
    BalanceEntryOutput,
    AccountBalanceEntryListOutput,
    AccountBalanceEntryOutput,
    ConfirmPlanInput,
    DeviceCreate,
    DeviceOutput,
    DeviceUpdate,
    ImportBatchOutput,
    ImportCommitInput,
    ImportRowOutput,
    ImportRowUpdate,
    FinancialEntryListOutput,
    FinancialEntryOutput,
    FundsSummaryOutput,
    JijihongOrderCreateInput,
    JijihongOrderCreateOutput,
    JijihongOrderReservationInput,
    PaymentPlanOutput,
    PoolSettingsOutput,
    PoolSettingsUpdate,
    RecommendationPreviewInput,
    RecommendationPreviewOutput,
    ReconciliationCreateInput,
    ReconciliationItemOutput,
    ReconciliationOutput,
    SuggestedAllocationOutput,
)
from app.modules.alipay_pool.finance_service import (
    confirm_reconciliation,
    create_reconciliation,
    get_reconciliation,
    reverse_reconciliation,
)
from app.modules.alipay_pool.service import (
    active_account_count,
    adjust_balance,
    commit_import,
    create_account,
    create_device,
    ensure_jijihong,
    get_pool_settings,
    promote_available_coupons,
    update_account,
    update_device,
    update_pool_settings,
)
from app.modules.iam.dependencies import CurrentContext, DbSession, require_roles
from app.modules.iam.audit import record_audit
from app.modules.iam.models import MemberRole
from app.modules.orders.router import _one_output

router = APIRouter(prefix="/alipay-pool", tags=["季季红支付宝资金池"])
write_roles = (MemberRole.OWNER.value, MemberRole.BOOKKEEPER.value)


def _device_output(db: DbSession, tenant_id: int, device: AlipayDevice) -> DeviceOutput:
    count = active_account_count(db, tenant_id, device.id)
    return DeviceOutput(
        id=device.id,
        name=device.name,
        account_category=device.account_category,
        is_active=device.is_active,
        note=device.note,
        active_account_count=count,
        capacity_warning=count > 5,
        created_at=device.created_at,
    )


def _account_output(
    account: AlipayAccount,
    device: AlipayDevice,
    coupon: AlipayCoupon | None,
) -> AccountOutput:
    return AccountOutput(
        id=account.id,
        device_id=device.id,
        device_name=device.name,
        alias=account.alias,
        login_identifier_masked=account.login_identifier_masked,
        initial_recharge_amount=account.initial_recharge_amount,
        opening_balance=account.opening_balance,
        current_balance=account.current_balance,
        reserved_balance=account.reserved_balance,
        available_balance=Decimal(account.current_balance)
        - Decimal(account.reserved_balance),
        status=account.status,
        phase=account.phase,
        birthday_set_date=account.birthday_set_date,
        coupon_status=coupon.status if coupon else None,
        coupon_amount=coupon.amount if coupon else None,
        coupon_available_at=coupon.available_at if coupon else None,
        note=account.note,
        created_at=account.created_at,
    )


def _one_account(db: DbSession, tenant_id: int, account_id: int) -> AccountOutput:
    row = db.execute(
        select(AlipayAccount, AlipayDevice, AlipayCoupon)
        .join(AlipayDevice, AlipayDevice.id == AlipayAccount.device_id)
        .outerjoin(AlipayCoupon, AlipayCoupon.account_id == AlipayAccount.id)
        .where(
            AlipayAccount.id == account_id,
            AlipayAccount.tenant_id == tenant_id,
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="支付宝账号不存在")
    return _account_output(*row)


def _plan_output(db: DbSession, plan: OrderPaymentPlan) -> PaymentPlanOutput:
    allocations = list(
        db.scalars(
            select(OrderPaymentAllocation)
            .where(OrderPaymentAllocation.plan_id == plan.id)
            .order_by(OrderPaymentAllocation.sequence)
        )
    )
    return PaymentPlanOutput(
        id=plan.id,
        order_id=plan.order_id,
        revision=plan.revision,
        status=plan.status,
        order_amount=plan.order_amount,
        total_coupon=plan.total_coupon,
        total_balance=plan.total_balance,
        total_external_cash=plan.total_external_cash,
        soft_cap_exceeded=plan.soft_cap_exceeded,
        warning=plan.warning,
        expires_at=plan.expires_at,
        confirmed_at=plan.confirmed_at,
        allocations=[
            AllocationOutput(
                id=item.id,
                account_id=item.account_id,
                sequence=item.sequence,
                device_name=item.device_name_snapshot,
                account_alias=item.account_alias_snapshot,
                coupon_amount=item.coupon_amount,
                balance_amount=item.balance_amount,
                external_cash_amount=item.external_cash_amount,
                balance_before=item.balance_before,
                balance_after=item.balance_after,
            )
            for item in allocations
        ],
    )


def _batch_output(db: DbSession, batch: AlipayImportBatch) -> ImportBatchOutput:
    rows = list(
        db.scalars(
            select(AlipayImportRow)
            .where(AlipayImportRow.batch_id == batch.id)
            .order_by(AlipayImportRow.row_number)
        )
    )
    return ImportBatchOutput(
        id=batch.id,
        filename=batch.filename,
        file_hash=batch.file_hash,
        sheet_name=batch.sheet_name,
        status=batch.status,
        total_rows=batch.total_rows,
        ready_rows=batch.ready_rows,
        review_rows=batch.review_rows,
        imported_rows=batch.imported_rows,
        rows=[
            ImportRowOutput(
                id=row.id,
                row_number=row.row_number,
                raw_data=row.raw_data,
                parsed_data=row.parsed_data,
                warnings=row.warnings,
                errors=row.errors,
                status=row.status,
                imported_account_id=row.imported_account_id,
            )
            for row in rows
        ],
        created_at=batch.created_at,
    )


def _reconciliation_output(
    db: DbSession, reconciliation: AlipayReconciliation
) -> ReconciliationOutput:
    rows = db.execute(
        select(AlipayReconciliationItem, AlipayAccount, AlipayDevice)
        .join(AlipayAccount, AlipayAccount.id == AlipayReconciliationItem.account_id)
        .join(AlipayDevice, AlipayDevice.id == AlipayReconciliationItem.device_id)
        .where(AlipayReconciliationItem.reconciliation_id == reconciliation.id)
        .order_by(AlipayDevice.name, AlipayAccount.alias)
    ).all()
    return ReconciliationOutput(
        id=reconciliation.id,
        business_date=reconciliation.business_date,
        status=reconciliation.status,
        note=reconciliation.note,
        created_by=reconciliation.created_by,
        confirmed_by=reconciliation.confirmed_by,
        confirmed_at=reconciliation.confirmed_at,
        reversed_by=reconciliation.reversed_by,
        reversed_at=reconciliation.reversed_at,
        items=[
            ReconciliationItemOutput(
                id=item.id,
                account_id=account.id,
                account_alias=account.alias,
                device_id=device.id,
                device_name=device.name,
                system_balance_snapshot=item.system_balance_snapshot,
                actual_balance=item.actual_balance,
                difference=item.difference,
                reason=item.reason,
            )
            for item, account, device in rows
        ],
        created_at=reconciliation.created_at,
    )


@router.get("/settings", response_model=PoolSettingsOutput)
def retrieve_settings(context: CurrentContext, db: DbSession):
    return get_pool_settings(db, context.tenant_id)


@router.patch("/settings", response_model=PoolSettingsOutput)
def patch_settings(
    data: PoolSettingsUpdate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    return update_pool_settings(
        db, tenant_id=context.tenant_id, user_id=context.user_id, data=data
    )


@router.get("/devices", response_model=list[DeviceOutput])
def list_devices(context: CurrentContext, db: DbSession):
    ensure_jijihong(db, context.tenant_id)
    devices = list(
        db.scalars(
            select(AlipayDevice)
            .where(AlipayDevice.tenant_id == context.tenant_id)
            .order_by(AlipayDevice.name)
        )
    )
    return [_device_output(db, context.tenant_id, device) for device in devices]


@router.post("/devices", response_model=DeviceOutput, status_code=201)
def post_device(
    data: DeviceCreate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    device = create_device(
        db, tenant_id=context.tenant_id, user_id=context.user_id, data=data
    )
    return _device_output(db, context.tenant_id, device)


@router.patch("/devices/{device_id}", response_model=DeviceOutput)
def patch_device(
    device_id: int,
    data: DeviceUpdate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    device = update_device(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        device_id=device_id,
        data=data,
    )
    return _device_output(db, context.tenant_id, device)


@router.get("/accounts", response_model=list[AccountOutput])
def list_accounts(
    context: CurrentContext,
    db: DbSession,
    device_id: int | None = None,
    account_status: str | None = Query(default=None, alias="status"),
    phase: str | None = None,
    keyword: str | None = Query(default=None, max_length=100),
):
    ensure_jijihong(db, context.tenant_id)
    expire_plans(db, context.tenant_id, context.user_id)
    promote_available_coupons(db, context.tenant_id)
    query = (
        select(AlipayAccount, AlipayDevice, AlipayCoupon)
        .join(AlipayDevice, AlipayDevice.id == AlipayAccount.device_id)
        .outerjoin(AlipayCoupon, AlipayCoupon.account_id == AlipayAccount.id)
        .where(AlipayAccount.tenant_id == context.tenant_id)
    )
    if device_id is not None:
        query = query.where(AlipayAccount.device_id == device_id)
    if account_status:
        query = query.where(AlipayAccount.status == account_status)
    if phase:
        query = query.where(AlipayAccount.phase == phase)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        query = query.where(
            or_(
                AlipayAccount.alias.like(pattern),
                AlipayDevice.name.like(pattern),
            )
        )
    rows = db.execute(query.order_by(AlipayDevice.name, AlipayAccount.id)).all()
    db.commit()
    return [_account_output(*row) for row in rows]


@router.post("/accounts", response_model=AccountOutput, status_code=201)
def post_account(
    data: AccountCreate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    account = create_account(
        db, tenant_id=context.tenant_id, user_id=context.user_id, data=data
    )
    return _one_account(db, context.tenant_id, account.id)


@router.patch("/accounts/{account_id}", response_model=AccountOutput)
def patch_account(
    account_id: int,
    data: AccountUpdate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    account = update_account(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        account_id=account_id,
        data=data,
    )
    return _one_account(db, context.tenant_id, account.id)


@router.post("/accounts/{account_id}/adjust", response_model=AccountOutput)
def post_adjustment(
    account_id: int,
    data: BalanceAdjustmentInput,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    account = adjust_balance(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        account_id=account_id,
        data=data,
    )
    return _one_account(db, context.tenant_id, account.id)


@router.get("/balance-entries", response_model=list[BalanceEntryOutput])
def list_balance_entries(
    context: CurrentContext,
    db: DbSession,
    account_id: int | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
):
    ensure_jijihong(db, context.tenant_id)
    query = select(AlipayBalanceEntry).where(
        AlipayBalanceEntry.tenant_id == context.tenant_id
    )
    if account_id is not None:
        query = query.where(AlipayBalanceEntry.account_id == account_id)
    return list(
        db.scalars(query.order_by(AlipayBalanceEntry.id.desc()).limit(limit))
    )


@router.post("/imports/preview", response_model=ImportBatchOutput)
async def preview_import(
    db: DbSession,
    file: UploadFile = File(...),
    context=Depends(require_roles(*write_roles)),
):
    ensure_jijihong(db, context.tenant_id)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="文件为空")
    batch = create_preview(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        filename=file.filename or "支付宝账号.xlsx",
        content=content,
    )
    return _batch_output(db, batch)


@router.get("/imports/{batch_id}", response_model=ImportBatchOutput)
def retrieve_import(batch_id: int, context: CurrentContext, db: DbSession):
    ensure_jijihong(db, context.tenant_id)
    batch = db.scalar(
        select(AlipayImportBatch).where(
            AlipayImportBatch.id == batch_id,
            AlipayImportBatch.tenant_id == context.tenant_id,
        )
    )
    if not batch:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    return _batch_output(db, batch)


@router.patch("/imports/{batch_id}/rows/{row_id}", response_model=ImportRowOutput)
def patch_import_row(
    batch_id: int,
    row_id: int,
    data: ImportRowUpdate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    ensure_jijihong(db, context.tenant_id)
    batch = db.scalar(
        select(AlipayImportBatch).where(
            AlipayImportBatch.id == batch_id,
            AlipayImportBatch.tenant_id == context.tenant_id,
        )
    )
    if not batch:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    if batch.status == "COMMITTED":
        raise HTTPException(status_code=409, detail="已提交的导入批次不能再修改")
    row = db.scalar(
        select(AlipayImportRow).where(
            AlipayImportRow.id == row_id,
            AlipayImportRow.batch_id == batch_id,
            AlipayImportRow.tenant_id == context.tenant_id,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="导入行不存在")
    if row.status == ImportRowStatus.IMPORTED.value:
        raise HTTPException(status_code=409, detail="已导入的行不能再修改")
    row.parsed_data = data.parsed_data
    required = ("device_name", "alias", "current_balance", "phase", "status")
    row.errors = [f"缺少字段 {key}" for key in required if not data.parsed_data.get(key)]
    try:
        balance = Decimal(str(data.parsed_data.get("current_balance")))
        if not balance.is_finite() or balance < 0:
            raise ValueError
    except (ArithmeticError, TypeError, ValueError):
        row.errors.append("当前余额必须是非负金额")
    if data.parsed_data.get("phase") not in {item.value for item in AccountPhase}:
        row.errors.append("账号阶段无效")
    if data.parsed_data.get("status") not in {item.value for item in AccountStatus}:
        row.errors.append("账号状态无效")
    row.status = (
        ImportRowStatus.REVIEW.value if row.errors else ImportRowStatus.READY.value
    )
    record_audit(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action="alipay.import_row_updated",
        resource_type="alipay_import_row",
        resource_id=row.id,
        payload={"batch_id": batch_id, "row_number": row.row_number},
    )
    db.commit()
    db.refresh(row)
    return ImportRowOutput(
        id=row.id,
        row_number=row.row_number,
        raw_data=row.raw_data,
        parsed_data=row.parsed_data,
        warnings=row.warnings,
        errors=row.errors,
        status=row.status,
        imported_account_id=row.imported_account_id,
    )


@router.post("/imports/{batch_id}/commit", response_model=ImportBatchOutput)
def post_import_commit(
    batch_id: int,
    data: ImportCommitInput,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    batch = commit_import(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        batch_id=batch_id,
        row_ids=data.row_ids,
    )
    return _batch_output(db, batch)


@router.post("/orders/{order_id}/recommend", response_model=PaymentPlanOutput)
def recommend_order_payment(
    order_id: int,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    plan = recommend_and_reserve(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        order_id=order_id,
    )
    return _plan_output(db, plan)


@router.post("/recommendations/preview", response_model=RecommendationPreviewOutput)
def preview_order_payment(
    data: RecommendationPreviewInput,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    suggestion = preview_recommendation(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        order_amount=data.order_amount,
    )
    settings = get_pool_settings(db, context.tenant_id)
    db.commit()
    warning = (
        f"最优方案仍需真实付款 {suggestion.total_external_cash} 元，超过软上限 "
        f"{settings.external_cash_soft_cap} 元"
        if suggestion.soft_cap_exceeded
        else None
    )
    return RecommendationPreviewOutput(
        order_amount=data.order_amount,
        total_coupon=suggestion.total_coupon,
        total_balance=suggestion.total_balance,
        total_external_cash=suggestion.total_external_cash,
        soft_cap_exceeded=suggestion.soft_cap_exceeded,
        warning=warning,
        allocations=[
            SuggestedAllocationOutput(
                account_id=item.account_id,
                device_name=item.device_name,
                account_alias=item.alias,
                coupon_amount=item.coupon_amount,
                balance_amount=item.balance_amount,
                external_cash_amount=item.external_cash_amount,
                balance_before=item.balance_before,
                balance_after=item.balance_after,
            )
            for item in suggestion.allocations
        ],
    )


@router.post("/orders", response_model=JijihongOrderCreateOutput, status_code=201)
def create_order_with_reservation(
    data: JijihongOrderCreateInput,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    order, plan = create_jijihong_order_and_reserve(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        data=data,
    )
    return JijihongOrderCreateOutput(
        order=_one_output(db, context.tenant_id, order).model_dump(),
        payment_plan=_plan_output(db, plan),
    )


@router.put("/orders/{order_id}/reservation", response_model=JijihongOrderCreateOutput)
def replace_order_reservation(
    order_id: int,
    data: JijihongOrderReservationInput,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    order, plan = replace_jijihong_reservation(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        order_id=order_id,
        data=data,
    )
    return JijihongOrderCreateOutput(
        order=_one_output(db, context.tenant_id, order).model_dump(),
        payment_plan=_plan_output(db, plan),
    )


@router.get("/orders/{order_id}/plan", response_model=PaymentPlanOutput | None)
def retrieve_order_plan(order_id: int, context: CurrentContext, db: DbSession):
    ensure_jijihong(db, context.tenant_id)
    expire_plans(db, context.tenant_id, context.user_id)
    db.commit()
    plan = get_order_plan(db, context.tenant_id, order_id)
    return _plan_output(db, plan) if plan else None


@router.post("/payment-plans/{plan_id}/confirm", response_model=PaymentPlanOutput)
def confirm_order_payment(
    plan_id: int,
    data: ConfirmPlanInput,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    plan = confirm_plan(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        plan_id=plan_id,
        data=data,
    )
    return _plan_output(db, plan)


@router.get("/funds/summary", response_model=FundsSummaryOutput)
def funds_summary(
    context: CurrentContext,
    db: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
):
    ensure_jijihong(db, context.tenant_id)
    balances = db.execute(
        select(
            func.coalesce(func.sum(AlipayAccount.current_balance), 0),
            func.coalesce(func.sum(AlipayAccount.reserved_balance), 0),
        ).where(AlipayAccount.tenant_id == context.tenant_id)
    ).one()
    filters = [JijihongFinancialEntry.tenant_id == context.tenant_id]
    if date_from:
        filters.append(JijihongFinancialEntry.business_date >= date_from)
    if date_to:
        filters.append(JijihongFinancialEntry.business_date <= date_to)
    entries = list(db.scalars(select(JijihongFinancialEntry).where(*filters)))
    reversed_ids = [entry.reversed_entry_id for entry in entries if entry.reversed_entry_id]
    originals = {
        entry.id: entry
        for entry in db.scalars(
            select(JijihongFinancialEntry).where(JijihongFinancialEntry.id.in_(reversed_ids))
        )
    } if reversed_ids else {}
    receipts = Decimal(0)
    balance_cost = Decimal(0)
    cash_cost = Decimal(0)
    gain_loss = Decimal(0)
    for entry in entries:
        amount = Decimal(entry.amount)
        entry_type = entry.entry_type
        if entry_type == FinancialEntryType.REVERSAL.value:
            original = originals.get(entry.reversed_entry_id)
            entry_type = original.entry_type if original else entry_type
        if entry_type == FinancialEntryType.CUSTOMER_RECEIPT.value:
            receipts += amount
        elif entry_type == FinancialEntryType.BALANCE_COST.value:
            balance_cost -= amount
        elif entry_type == FinancialEntryType.EXTERNAL_CASH_COST.value:
            cash_cost -= amount
        elif entry_type == FinancialEntryType.RECONCILIATION_GAIN_LOSS.value:
            gain_loss += amount
    order_profit = receipts - balance_cost - cash_cost
    return FundsSummaryOutput(
        current_balance=balances[0],
        reserved_balance=balances[1],
        available_balance=Decimal(balances[0]) - Decimal(balances[1]),
        customer_receipts=receipts,
        balance_cost=balance_cost,
        external_cash_cost=cash_cost,
        reconciliation_gain_loss=gain_loss,
        order_profit=order_profit,
        period_net_income=order_profit + gain_loss,
    )


@router.get("/funds/account-entries", response_model=AccountBalanceEntryListOutput)
def account_entries(
    context: CurrentContext,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    device_id: int | None = None,
    account_id: int | None = None,
    entry_type: str | None = None,
    order_id: int | None = None,
):
    ensure_jijihong(db, context.tenant_id)
    filters = [AlipayBalanceEntry.tenant_id == context.tenant_id]
    if device_id is not None:
        filters.append(AlipayAccount.device_id == device_id)
    if account_id is not None:
        filters.append(AlipayBalanceEntry.account_id == account_id)
    if entry_type:
        filters.append(AlipayBalanceEntry.entry_type == entry_type)
    if order_id is not None:
        filters.append(AlipayBalanceEntry.order_id == order_id)
    base = (
        select(AlipayBalanceEntry, AlipayAccount, AlipayDevice)
        .join(AlipayAccount, AlipayAccount.id == AlipayBalanceEntry.account_id)
        .join(AlipayDevice, AlipayDevice.id == AlipayAccount.device_id)
        .where(*filters)
    )
    total = db.scalar(
        select(func.count(AlipayBalanceEntry.id))
        .join(AlipayAccount, AlipayAccount.id == AlipayBalanceEntry.account_id)
        .where(*filters)
    ) or 0
    rows = db.execute(
        base.order_by(AlipayBalanceEntry.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return AccountBalanceEntryListOutput(
        items=[
            AccountBalanceEntryOutput(
                id=entry.id,
                account_id=entry.account_id,
                order_id=entry.order_id,
                plan_id=entry.plan_id,
                entry_type=entry.entry_type,
                balance_delta=entry.balance_delta,
                reserved_delta=entry.reserved_delta,
                balance_after=entry.balance_after,
                reserved_after=entry.reserved_after,
                reason=entry.reason,
                created_at=entry.created_at,
                account_alias=account.alias,
                device_id=device.id,
                device_name=device.name,
            )
            for entry, account, device in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/funds/financial-entries", response_model=FinancialEntryListOutput)
def financial_entries(
    context: CurrentContext,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    date_from: date | None = None,
    date_to: date | None = None,
    device_id: int | None = None,
    account_id: int | None = None,
    entry_type: str | None = None,
):
    ensure_jijihong(db, context.tenant_id)
    filters = [JijihongFinancialEntry.tenant_id == context.tenant_id]
    if date_from:
        filters.append(JijihongFinancialEntry.business_date >= date_from)
    if date_to:
        filters.append(JijihongFinancialEntry.business_date <= date_to)
    if device_id is not None:
        filters.append(JijihongFinancialEntry.device_id == device_id)
    if account_id is not None:
        filters.append(JijihongFinancialEntry.account_id == account_id)
    if entry_type:
        filters.append(JijihongFinancialEntry.entry_type == entry_type)
    total = db.scalar(select(func.count(JijihongFinancialEntry.id)).where(*filters)) or 0
    rows = db.execute(
        select(JijihongFinancialEntry, AlipayAccount.alias, AlipayDevice.name)
        .outerjoin(AlipayAccount, AlipayAccount.id == JijihongFinancialEntry.account_id)
        .outerjoin(AlipayDevice, AlipayDevice.id == JijihongFinancialEntry.device_id)
        .where(*filters)
        .order_by(JijihongFinancialEntry.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return FinancialEntryListOutput(
        items=[
            FinancialEntryOutput(
                id=entry.id,
                business_date=entry.business_date,
                order_id=entry.order_id,
                plan_id=entry.plan_id,
                account_id=entry.account_id,
                account_alias=account_alias,
                device_id=entry.device_id,
                device_name=device_name,
                entry_type=entry.entry_type,
                amount=entry.amount,
                note=entry.note,
                created_at=entry.created_at,
            )
            for entry, account_alias, device_name in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/reconciliations", response_model=list[ReconciliationOutput])
def list_reconciliations(context: CurrentContext, db: DbSession):
    ensure_jijihong(db, context.tenant_id)
    rows = list(
        db.scalars(
            select(AlipayReconciliation)
            .where(AlipayReconciliation.tenant_id == context.tenant_id)
            .order_by(AlipayReconciliation.business_date.desc(), AlipayReconciliation.id.desc())
        )
    )
    return [_reconciliation_output(db, row) for row in rows]


@router.get("/reconciliations/{reconciliation_id}", response_model=ReconciliationOutput)
def retrieve_reconciliation(reconciliation_id: int, context: CurrentContext, db: DbSession):
    ensure_jijihong(db, context.tenant_id)
    return _reconciliation_output(db, get_reconciliation(db, context.tenant_id, reconciliation_id))


@router.post("/reconciliations", response_model=ReconciliationOutput, status_code=201)
def post_reconciliation(
    data: ReconciliationCreateInput,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    row = create_reconciliation(
        db, tenant_id=context.tenant_id, user_id=context.user_id, data=data
    )
    return _reconciliation_output(db, row)


@router.post("/reconciliations/{reconciliation_id}/confirm", response_model=ReconciliationOutput)
def post_confirm_reconciliation(
    reconciliation_id: int,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    row = confirm_reconciliation(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        reconciliation_id=reconciliation_id,
    )
    return _reconciliation_output(db, row)


@router.post("/reconciliations/{reconciliation_id}/reverse", response_model=ReconciliationOutput)
def post_reverse_reconciliation(
    reconciliation_id: int,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
):
    row = reverse_reconciliation(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        reconciliation_id=reconciliation_id,
    )
    return _reconciliation_output(db, row)
