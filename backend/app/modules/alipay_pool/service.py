from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.alipay_pool.importer import coupon_available_at
from app.modules.alipay_pool.models import (
    AccountPhase,
    AccountStatus,
    AlipayAccount,
    AlipayBalanceEntry,
    AlipayCoupon,
    AlipayDevice,
    AlipayImportBatch,
    AlipayImportRow,
    AlipayPoolSettings,
    BalanceEntryType,
    CouponStatus,
    ImportBatchStatus,
    ImportRowStatus,
)
from app.modules.alipay_pool.schemas import (
    AccountCreate,
    AccountUpdate,
    BalanceAdjustmentInput,
    DeviceCreate,
    DeviceUpdate,
    PoolSettingsUpdate,
)
from app.modules.iam.audit import record_audit
from app.modules.iam.models import BusinessMode, Tenant

ZERO = Decimal("0.00")


def ensure_jijihong(db: Session, tenant_id: int) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if not tenant or tenant.business_mode != BusinessMode.JIJIHONG.value:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="当前账套未启用季季红资金池",
        )
    return tenant


def get_pool_settings(db: Session, tenant_id: int) -> AlipayPoolSettings:
    ensure_jijihong(db, tenant_id)
    settings = db.scalar(
        select(AlipayPoolSettings).where(AlipayPoolSettings.tenant_id == tenant_id)
    )
    if not settings:
        settings = AlipayPoolSettings(tenant_id=tenant_id)
        db.add(settings)
        db.flush()
    return settings


def update_pool_settings(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    data: PoolSettingsUpdate,
) -> AlipayPoolSettings:
    settings = get_pool_settings(db, tenant_id)
    changes = data.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(settings, key, value)
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="alipay.settings_updated",
        resource_type="alipay_pool_settings",
        resource_id=settings.id,
        payload=data.model_dump(exclude_none=True, mode="json"),
    )
    db.commit()
    db.refresh(settings)
    return settings


def get_device(db: Session, tenant_id: int, device_id: int) -> AlipayDevice:
    device = db.scalar(
        select(AlipayDevice).where(
            AlipayDevice.id == device_id,
            AlipayDevice.tenant_id == tenant_id,
        )
    )
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    return device


def create_device(
    db: Session, *, tenant_id: int, user_id: int, data: DeviceCreate
) -> AlipayDevice:
    ensure_jijihong(db, tenant_id)
    if db.scalar(
        select(AlipayDevice).where(
            AlipayDevice.tenant_id == tenant_id,
            AlipayDevice.name == data.name.strip(),
        )
    ):
        raise HTTPException(status_code=409, detail="设备名称已存在")
    device = AlipayDevice(
        tenant_id=tenant_id,
        name=data.name.strip(),
        account_category=data.account_category,
        note=data.note,
    )
    db.add(device)
    db.flush()
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="alipay.device_created",
        resource_type="alipay_device",
        resource_id=device.id,
    )
    db.commit()
    db.refresh(device)
    return device


def update_device(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    device_id: int,
    data: DeviceUpdate,
) -> AlipayDevice:
    device = get_device(db, tenant_id, device_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"]:
        duplicate = db.scalar(
            select(AlipayDevice).where(
                AlipayDevice.tenant_id == tenant_id,
                AlipayDevice.name == changes["name"].strip(),
                AlipayDevice.id != device.id,
            )
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="设备名称已存在")
        changes["name"] = changes["name"].strip()
    for key, value in changes.items():
        setattr(device, key, value)
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="alipay.device_updated",
        resource_type="alipay_device",
        resource_id=device.id,
        payload=data.model_dump(exclude_unset=True, mode="json"),
    )
    db.commit()
    db.refresh(device)
    return device


def get_account(
    db: Session,
    tenant_id: int,
    account_id: int,
    *,
    for_update: bool = False,
) -> AlipayAccount:
    query = select(AlipayAccount).where(
        AlipayAccount.id == account_id,
        AlipayAccount.tenant_id == tenant_id,
    )
    if for_update:
        query = query.with_for_update()
    account = db.scalar(query)
    if not account:
        raise HTTPException(status_code=404, detail="支付宝账号不存在")
    return account


def _append_balance_entry(
    db: Session,
    *,
    account: AlipayAccount,
    user_id: int,
    entry_type: BalanceEntryType,
    balance_delta: Decimal = ZERO,
    reserved_delta: Decimal = ZERO,
    idempotency_key: str,
    order_id: int | None = None,
    plan_id: int | None = None,
    reconciliation_id: int | None = None,
    allocation_id: int | None = None,
    reversed_entry_id: int | None = None,
    reason: str | None = None,
) -> AlipayBalanceEntry:
    existing = db.scalar(
        select(AlipayBalanceEntry).where(
            AlipayBalanceEntry.idempotency_key == idempotency_key
        )
    )
    if existing:
        return existing
    entry = AlipayBalanceEntry(
        tenant_id=account.tenant_id,
        account_id=account.id,
        order_id=order_id,
        plan_id=plan_id,
        reconciliation_id=reconciliation_id,
        allocation_id=allocation_id,
        entry_type=entry_type.value,
        balance_delta=balance_delta,
        reserved_delta=reserved_delta,
        balance_after=account.current_balance,
        reserved_after=account.reserved_balance,
        reversed_entry_id=reversed_entry_id,
        idempotency_key=idempotency_key,
        reason=reason,
        created_by=user_id,
    )
    db.add(entry)
    return entry


def _new_coupon(
    *,
    tenant_id: int,
    account_id: int,
    amount: Decimal,
    birthday_set_date,
    available: bool,
) -> AlipayCoupon:
    available_at = coupon_available_at(birthday_set_date)
    if available:
        available_at = datetime.now(timezone.utc)
    elif available_at is None:
        available_at = datetime.combine(
            datetime.now(timezone.utc).date() + timedelta(days=1),
            time.min,
            tzinfo=timezone.utc,
        )
    return AlipayCoupon(
        tenant_id=tenant_id,
        account_id=account_id,
        amount=amount,
        status=CouponStatus.AVAILABLE.value if available else CouponStatus.PENDING.value,
        available_at=available_at,
    )


def create_account(
    db: Session, *, tenant_id: int, user_id: int, data: AccountCreate
) -> AlipayAccount:
    settings = get_pool_settings(db, tenant_id)
    get_device(db, tenant_id, data.device_id)
    if data.status != AccountStatus.EXHAUSTED and active_account_count(db, tenant_id, data.device_id) >= 5:
        raise HTTPException(status_code=409, detail="每台设备最多挂载5个未耗尽支付宝账号")
    balance = Decimal(data.current_balance)
    account = AlipayAccount(
        tenant_id=tenant_id,
        device_id=data.device_id,
        alias=data.alias.strip(),
        login_identifier_masked=data.login_identifier_masked,
        initial_recharge_amount=data.initial_recharge_amount,
        opening_balance=balance,
        current_balance=balance,
        reserved_balance=ZERO,
        status=data.status.value,
        phase=data.phase.value,
        birthday_set_date=data.birthday_set_date,
        note=data.note,
    )
    db.add(account)
    db.flush()
    if data.create_coupon:
        db.add(
            _new_coupon(
                tenant_id=tenant_id,
                account_id=account.id,
                amount=Decimal(settings.default_coupon_amount),
                birthday_set_date=data.birthday_set_date,
                available=data.phase == AccountPhase.DAY2_ACTIVE,
            )
        )
    _append_balance_entry(
        db,
        account=account,
        user_id=user_id,
        entry_type=BalanceEntryType.IMPORT_OPENING,
        balance_delta=balance,
        idempotency_key=f"account:{account.id}:opening",
        reason="手工登记期初余额",
    )
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="alipay.account_created",
        resource_type="alipay_account",
        resource_id=account.id,
        payload={"alias": account.alias, "opening_balance": str(balance)},
    )
    db.commit()
    db.refresh(account)
    return account


def update_account(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    account_id: int,
    data: AccountUpdate,
) -> AlipayAccount:
    account = get_account(db, tenant_id, account_id, for_update=True)
    changes = data.model_dump(exclude_unset=True)
    if "device_id" in changes and changes["device_id"] is not None:
        get_device(db, tenant_id, changes["device_id"])
    target_device_id = changes.get("device_id", account.device_id)
    target_status = changes.get("status", account.status)
    target_status_value = target_status.value if hasattr(target_status, "value") else target_status
    if target_status_value != AccountStatus.EXHAUSTED.value and (
        target_device_id != account.device_id or account.status == AccountStatus.EXHAUSTED.value
    ):
        occupied = int(
            db.scalar(
                select(func.count(AlipayAccount.id)).where(
                    AlipayAccount.tenant_id == tenant_id,
                    AlipayAccount.device_id == target_device_id,
                    AlipayAccount.status != AccountStatus.EXHAUSTED.value,
                    AlipayAccount.id != account.id,
                )
            )
            or 0
        )
        if occupied >= 5:
            raise HTTPException(status_code=409, detail="每台设备最多挂载5个未耗尽支付宝账号")
    if "alias" in changes and changes["alias"]:
        changes["alias"] = changes["alias"].strip()
    for key, value in changes.items():
        setattr(account, key, value.value if hasattr(value, "value") else value)
    account.version += 1
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="alipay.account_updated",
        resource_type="alipay_account",
        resource_id=account.id,
        payload=data.model_dump(exclude_unset=True, mode="json"),
    )
    db.commit()
    db.refresh(account)
    return account


def adjust_balance(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    account_id: int,
    data: BalanceAdjustmentInput,
) -> AlipayAccount:
    account = get_account(db, tenant_id, account_id, for_update=True)
    new_balance = Decimal(account.current_balance) + Decimal(data.amount)
    if new_balance < Decimal(account.reserved_balance) or new_balance < 0:
        raise HTTPException(status_code=409, detail="调整后余额不能小于已预占金额")
    account.current_balance = new_balance
    account.version += 1
    if new_balance == 0:
        account.status = AccountStatus.EXHAUSTED.value
        account.phase = AccountPhase.EXHAUSTED.value
    _append_balance_entry(
        db,
        account=account,
        user_id=user_id,
        entry_type=BalanceEntryType.MANUAL_ADJUSTMENT,
        balance_delta=Decimal(data.amount),
        idempotency_key=f"account:{account.id}:adjust:{account.version}",
        reason=data.reason,
    )
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="alipay.balance_adjusted",
        resource_type="alipay_account",
        resource_id=account.id,
        payload={"amount": str(data.amount), "reason": data.reason},
    )
    db.commit()
    db.refresh(account)
    return account


def promote_available_coupons(db: Session, tenant_id: int) -> None:
    now = datetime.now(timezone.utc)
    coupons = list(
        db.scalars(
            select(AlipayCoupon).where(
                AlipayCoupon.tenant_id == tenant_id,
                AlipayCoupon.status == CouponStatus.PENDING.value,
                AlipayCoupon.available_at.is_not(None),
                AlipayCoupon.available_at <= now,
            )
        )
    )
    for coupon in coupons:
        coupon.status = CouponStatus.AVAILABLE.value
        account = db.scalar(
            select(AlipayAccount).where(
                AlipayAccount.id == coupon.account_id,
                AlipayAccount.tenant_id == tenant_id,
            )
        )
        if account and account.phase == AccountPhase.WAITING_COUPON.value:
            account.phase = AccountPhase.DAY2_ACTIVE.value


def commit_import(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    batch_id: int,
    row_ids: list[int] | None,
) -> AlipayImportBatch:
    settings = get_pool_settings(db, tenant_id)
    batch = db.scalar(
        select(AlipayImportBatch)
        .where(
            AlipayImportBatch.id == batch_id,
            AlipayImportBatch.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if not batch:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    if batch.status == ImportBatchStatus.COMMITTED.value:
        raise HTTPException(status_code=409, detail="该导入批次已提交，不能重复导入")
    query = select(AlipayImportRow).where(
        AlipayImportRow.batch_id == batch.id,
        AlipayImportRow.tenant_id == tenant_id,
        AlipayImportRow.status.in_(
            [ImportRowStatus.READY.value, ImportRowStatus.REVIEW.value]
        ),
    )
    if row_ids is None:
        query = query.where(AlipayImportRow.status == ImportRowStatus.READY.value)
    else:
        query = query.where(AlipayImportRow.id.in_(row_ids))
    rows = list(
        db.scalars(query.order_by(AlipayImportRow.row_number).with_for_update())
    )
    imported = 0
    for row in rows:
        if row.errors:
            continue
        parsed = row.parsed_data or {}
        device_name = parsed.get("device_name")
        alias = parsed.get("alias")
        if not device_name or not alias or parsed.get("current_balance") is None:
            continue
        device = db.scalar(
            select(AlipayDevice).where(
                AlipayDevice.tenant_id == tenant_id,
                AlipayDevice.name == device_name,
            )
        )
        if not device:
            device = AlipayDevice(
                tenant_id=tenant_id,
                name=device_name,
                account_category=parsed.get("account_category"),
            )
            db.add(device)
            db.flush()
        if active_account_count(db, tenant_id, device.id) >= 5:
            raise HTTPException(
                status_code=409,
                detail=f"设备 {device.name} 已挂载5个未耗尽账号，请先更换耗尽账号",
            )
        try:
            balance = Decimal(str(parsed["current_balance"]))
            if not balance.is_finite() or balance < 0:
                raise ValueError
            AccountPhase(parsed["phase"])
            AccountStatus(parsed["status"])
            birthday = (
                date.fromisoformat(parsed["birthday_set_date"])
                if parsed.get("birthday_set_date")
                else None
            )
        except (ArithmeticError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"第{row.row_number}行修正数据无效，请重新检查",
            ) from exc
        account = AlipayAccount(
            tenant_id=tenant_id,
            device_id=device.id,
            alias=alias,
            opening_balance=balance,
            current_balance=balance,
            reserved_balance=ZERO,
            status=parsed["status"],
            phase=parsed["phase"],
            birthday_set_date=birthday,
            source_batch_id=batch.id,
            source_row_number=row.row_number,
            extra_data={
                "company": parsed.get("company"),
                "enterprise_id": parsed.get("enterprise_id"),
                "step": parsed.get("step"),
                "created_date": parsed.get("created_date"),
            },
        )
        db.add(account)
        db.flush()
        should_create_coupon = bool(
            parsed.get("coupon_available")
            or birthday
            or parsed["phase"] == AccountPhase.WAITING_COUPON.value
        )
        if should_create_coupon:
            db.add(
                _new_coupon(
                    tenant_id=tenant_id,
                    account_id=account.id,
                    amount=Decimal(settings.default_coupon_amount),
                    birthday_set_date=birthday,
                    available=bool(parsed.get("coupon_available")),
                )
            )
        _append_balance_entry(
            db,
            account=account,
            user_id=user_id,
            entry_type=BalanceEntryType.IMPORT_OPENING,
            balance_delta=balance,
            idempotency_key=f"import:{batch.id}:{row.row_number}",
            reason=f"Excel导入第{row.row_number}行",
        )
        row.status = ImportRowStatus.IMPORTED.value
        row.imported_account_id = account.id
        imported += 1
    batch.imported_rows += imported
    batch.status = ImportBatchStatus.COMMITTED.value
    batch.committed_at = datetime.now(timezone.utc)
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="alipay.import_committed",
        resource_type="alipay_import_batch",
        resource_id=batch.id,
        payload={"imported_rows": imported},
    )
    db.commit()
    db.refresh(batch)
    return batch


def active_account_count(db: Session, tenant_id: int, device_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(AlipayAccount.id)).where(
                AlipayAccount.tenant_id == tenant_id,
                AlipayAccount.device_id == device_id,
                AlipayAccount.status != AccountStatus.EXHAUSTED.value,
            )
        )
        or 0
    )
