from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.alipay_pool.calculations import Candidate, money, recommend
from app.modules.alipay_pool.models import (
    AccountPhase,
    AccountStatus,
    AlipayAccount,
    AlipayBalanceEntry,
    AlipayCoupon,
    AlipayDevice,
    BalanceEntryType,
    CouponStatus,
    OrderPaymentAllocation,
    OrderPaymentPlan,
    PaymentPlanStatus,
)
from app.modules.alipay_pool.schemas import (
    ConfirmPlanInput,
    JijihongOrderCreateInput,
    JijihongOrderReservationInput,
    SelectedAllocationInput,
)
from app.modules.alipay_pool.service import (
    _append_balance_entry,
    ensure_jijihong,
    get_account,
    get_pool_settings,
    promote_available_coupons,
)
from app.modules.iam.audit import record_audit
from app.modules.orders.models import Order, OrderStatus

ZERO = Decimal("0.00")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _get_order(db: Session, tenant_id: int, order_id: int, *, for_update=False) -> Order:
    query = select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id)
    if for_update:
        query = query.with_for_update()
    order = db.scalar(query)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order


def get_plan(db: Session, tenant_id: int, plan_id: int) -> OrderPaymentPlan:
    plan = db.scalar(
        select(OrderPaymentPlan).where(
            OrderPaymentPlan.id == plan_id,
            OrderPaymentPlan.tenant_id == tenant_id,
        )
    )
    if not plan:
        raise HTTPException(status_code=404, detail="支付方案不存在")
    return plan


def get_order_plan(
    db: Session, tenant_id: int, order_id: int
) -> OrderPaymentPlan | None:
    return db.scalar(
        select(OrderPaymentPlan)
        .where(
            OrderPaymentPlan.tenant_id == tenant_id,
            OrderPaymentPlan.order_id == order_id,
        )
        .order_by(OrderPaymentPlan.revision.desc())
    )


def _release_plan(
    db: Session,
    *,
    plan: OrderPaymentPlan,
    user_id: int,
    target_status: PaymentPlanStatus,
    reason: str,
) -> None:
    if plan.status != PaymentPlanStatus.RESERVED.value:
        return
    allocations = list(
        db.scalars(
            select(OrderPaymentAllocation)
            .where(OrderPaymentAllocation.plan_id == plan.id)
            .order_by(OrderPaymentAllocation.sequence)
        )
    )
    for allocation in allocations:
        account = get_account(
            db, plan.tenant_id, allocation.account_id, for_update=True
        )
        release_amount = min(
            Decimal(account.reserved_balance), Decimal(allocation.balance_amount)
        )
        account.reserved_balance = Decimal(account.reserved_balance) - release_amount
        account.version += 1
        _append_balance_entry(
            db,
            account=account,
            user_id=user_id,
            entry_type=BalanceEntryType.RELEASE,
            reserved_delta=-release_amount,
            idempotency_key=f"plan:{plan.id}:release:{account.id}",
            order_id=plan.order_id,
            plan_id=plan.id,
            allocation_id=allocation.id,
            reason=reason,
        )
        coupon = db.scalar(
            select(AlipayCoupon).where(
                AlipayCoupon.account_id == account.id,
                AlipayCoupon.reserved_plan_id == plan.id,
            )
        )
        if coupon:
            coupon.status = (
                CouponStatus.AVAILABLE.value
                if coupon.available_at is None
                or _aware(coupon.available_at) <= datetime.now(timezone.utc)
                else CouponStatus.PENDING.value
            )
            coupon.reserved_plan_id = None
    plan.status = target_status.value
    plan.released_at = datetime.now(timezone.utc)


def release_reserved_plan_for_order(
    db: Session,
    *,
    tenant_id: int,
    order_id: int,
    user_id: int,
    reason: str,
) -> None:
    plan = db.scalar(
        select(OrderPaymentPlan)
        .where(
            OrderPaymentPlan.tenant_id == tenant_id,
            OrderPaymentPlan.order_id == order_id,
            OrderPaymentPlan.status == PaymentPlanStatus.RESERVED.value,
        )
        .with_for_update()
    )
    if plan:
        _release_plan(
            db,
            plan=plan,
            user_id=user_id,
            target_status=PaymentPlanStatus.RELEASED,
            reason=reason,
        )


def expire_plans(db: Session, tenant_id: int, user_id: int) -> None:
    now = datetime.now(timezone.utc)
    plans = list(
        db.scalars(
            select(OrderPaymentPlan).where(
                OrderPaymentPlan.tenant_id == tenant_id,
                OrderPaymentPlan.status == PaymentPlanStatus.RESERVED.value,
                OrderPaymentPlan.expires_at <= now,
            )
        )
    )
    for plan in plans:
        _release_plan(
            db,
            plan=plan,
            user_id=user_id,
            target_status=PaymentPlanStatus.EXPIRED,
            reason="预占超时自动释放",
        )


def _recommendation_candidates(db: Session, tenant_id: int) -> list[Candidate]:
    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(AlipayAccount, AlipayDevice, AlipayCoupon)
        .join(AlipayDevice, AlipayDevice.id == AlipayAccount.device_id)
        .outerjoin(
            AlipayCoupon,
            (AlipayCoupon.account_id == AlipayAccount.id)
            & (AlipayCoupon.tenant_id == tenant_id),
        )
        .where(
            AlipayAccount.tenant_id == tenant_id,
            AlipayAccount.status == AccountStatus.ACTIVE.value,
            AlipayAccount.phase.in_([
                AccountPhase.NOT_STARTED.value,
                AccountPhase.DAY1_ACTIVE.value,
                AccountPhase.DAY2_ACTIVE.value,
            ]),
            AlipayDevice.is_active.is_(True),
        )
    ).all()
    candidates: list[Candidate] = []
    for account, device, coupon in rows:
        available = money(Decimal(account.current_balance) - Decimal(account.reserved_balance))
        coupon_available = bool(
            coupon
            and (
                coupon.status == CouponStatus.AVAILABLE.value
                or (
                    coupon.status == CouponStatus.PENDING.value
                    and coupon.available_at is not None
                    and _aware(coupon.available_at) <= now
                )
            )
        )
        coupon_amount = Decimal(coupon.amount) if coupon_available else ZERO
        if available > 0 or coupon_amount > 0:
            candidates.append(
                Candidate(
                    account_id=account.id,
                    device_name=device.name,
                    alias=account.alias,
                    phase=account.phase,
                    balance=available,
                    coupon=coupon_amount,
                )
            )
    return candidates


def preview_recommendation(
    db: Session, *, tenant_id: int, user_id: int, order_amount: Decimal
):
    ensure_jijihong(db, tenant_id)
    expire_plans(db, tenant_id, user_id)
    promote_available_coupons(db, tenant_id)
    settings = get_pool_settings(db, tenant_id)
    try:
        return recommend(
            _recommendation_candidates(db, tenant_id),
            order_amount=money(order_amount),
            soft_cap=Decimal(settings.external_cash_soft_cap),
            first_day_target=Decimal(settings.first_day_target_balance),
            first_day_tolerance=Decimal(settings.first_day_target_tolerance),
            max_split_accounts=settings.max_split_accounts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def reserve_selected_plan(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    order: Order,
    selected: list[SelectedAllocationInput],
    override_reason: str | None,
) -> OrderPaymentPlan:
    ensure_jijihong(db, tenant_id)
    settings = get_pool_settings(db, tenant_id)
    if len(selected) > settings.max_split_accounts:
        raise HTTPException(status_code=422, detail="拆单账号数量超过资金池设置")
    if len({item.account_id for item in selected}) != len(selected):
        raise HTTPException(status_code=422, detail="支付方案中的支付宝账号不能重复")
    total_coupon = money(sum((Decimal(item.coupon_amount) for item in selected), ZERO))
    total_balance = money(sum((Decimal(item.balance_amount) for item in selected), ZERO))
    total_cash = money(sum((Decimal(item.external_cash_amount) for item in selected), ZERO))
    if money(total_coupon + total_balance + total_cash) != money(order.order_amount):
        raise HTTPException(status_code=422, detail="优惠券、余额和真实付款合计必须等于订单金额")
    if total_cash > Decimal(settings.external_cash_soft_cap) and not (override_reason or "").strip():
        raise HTTPException(status_code=422, detail="真实付款超过软上限时必须填写原因")

    account_ids = sorted(item.account_id for item in selected)
    rows = db.execute(
        select(AlipayAccount, AlipayDevice, AlipayCoupon)
        .join(AlipayDevice, AlipayDevice.id == AlipayAccount.device_id)
        .outerjoin(AlipayCoupon, AlipayCoupon.account_id == AlipayAccount.id)
        .where(
            AlipayAccount.tenant_id == tenant_id,
            AlipayAccount.id.in_(account_ids),
        )
        .order_by(AlipayAccount.id)
        .with_for_update()
    ).all()
    by_id = {account.id: (account, device, coupon) for account, device, coupon in rows}
    if set(by_id) != set(account_ids):
        raise HTTPException(status_code=404, detail="支付方案包含不存在的支付宝账号")

    now = datetime.now(timezone.utc)
    for item in selected:
        account, device, coupon = by_id[item.account_id]
        if account.status != AccountStatus.ACTIVE.value or not device.is_active:
            raise HTTPException(status_code=409, detail=f"账号 {account.alias} 当前不可用")
        if account.phase not in {
            AccountPhase.NOT_STARTED.value,
            AccountPhase.DAY1_ACTIVE.value,
            AccountPhase.DAY2_ACTIVE.value,
        }:
            raise HTTPException(status_code=409, detail=f"账号 {account.alias} 当前阶段不可支付")
        available = Decimal(account.current_balance) - Decimal(account.reserved_balance)
        if Decimal(item.balance_amount) > available:
            raise HTTPException(status_code=409, detail=f"账号 {account.alias} 可用余额不足")
        if Decimal(item.coupon_amount) > 0:
            coupon_available = bool(
                coupon
                and (
                    coupon.status == CouponStatus.AVAILABLE.value
                    or (
                        coupon.status == CouponStatus.PENDING.value
                        and coupon.available_at is not None
                        and _aware(coupon.available_at) <= now
                    )
                )
            )
            if not coupon_available or Decimal(item.coupon_amount) != Decimal(coupon.amount):
                raise HTTPException(status_code=409, detail=f"账号 {account.alias} 优惠券不可用或未整张使用")

    revision = int(
        db.scalar(
            select(func.max(OrderPaymentPlan.revision)).where(
                OrderPaymentPlan.tenant_id == tenant_id,
                OrderPaymentPlan.order_id == order.id,
            )
        )
        or 0
    ) + 1
    warning = (
        f"真实付款 {total_cash} 元超过软上限 {settings.external_cash_soft_cap} 元；{override_reason}"
        if total_cash > Decimal(settings.external_cash_soft_cap)
        else None
    )
    plan = OrderPaymentPlan(
        tenant_id=tenant_id,
        order_id=order.id,
        revision=revision,
        status=PaymentPlanStatus.RESERVED.value,
        order_amount=money(order.order_amount),
        total_coupon=total_coupon,
        total_balance=total_balance,
        total_external_cash=total_cash,
        soft_cap_exceeded=total_cash > Decimal(settings.external_cash_soft_cap),
        warning=warning,
        algorithm_version="v2-live-preview",
        expires_at=now + timedelta(minutes=settings.reservation_minutes),
        created_by=user_id,
    )
    db.add(plan)
    db.flush()
    for sequence, item in enumerate(selected, start=1):
        account, device, coupon = by_id[item.account_id]
        allocation = OrderPaymentAllocation(
            tenant_id=tenant_id,
            plan_id=plan.id,
            account_id=account.id,
            sequence=sequence,
            device_name_snapshot=device.name,
            account_alias_snapshot=account.alias,
            coupon_amount=money(item.coupon_amount),
            balance_amount=money(item.balance_amount),
            external_cash_amount=money(item.external_cash_amount),
            balance_before=money(account.current_balance),
            balance_after=money(Decimal(account.current_balance) - Decimal(item.balance_amount)),
        )
        db.add(allocation)
        db.flush()
        account.reserved_balance = Decimal(account.reserved_balance) + Decimal(item.balance_amount)
        account.version += 1
        _append_balance_entry(
            db,
            account=account,
            user_id=user_id,
            entry_type=BalanceEntryType.RESERVE,
            reserved_delta=Decimal(item.balance_amount),
            idempotency_key=f"plan:{plan.id}:reserve:{account.id}",
            order_id=order.id,
            plan_id=plan.id,
            allocation_id=allocation.id,
            reason="录单保存并预占支付方案",
        )
        if Decimal(item.coupon_amount) > 0 and coupon:
            coupon.status = CouponStatus.RESERVED.value
            coupon.reserved_plan_id = plan.id
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="alipay.plan_reserved",
        resource_type="order_payment_plan",
        resource_id=plan.id,
        payload={"order_id": order.id, "revision": revision},
    )
    return plan


def create_jijihong_order_and_reserve(
    db: Session, *, tenant_id: int, user_id: int, data: JijihongOrderCreateInput
) -> tuple[Order, OrderPaymentPlan]:
    ensure_jijihong(db, tenant_id)
    customer_received = money(
        data.order_amount
        if data.customer_received_amount is None
        else data.customer_received_amount
    )
    if data.idempotency_key:
        existing = db.scalar(
            select(Order).where(
                Order.tenant_id == tenant_id,
                Order.client_request_id == data.idempotency_key,
            )
        )
        if existing:
            if (
                existing.business_date != data.business_date
                or money(existing.order_amount) != money(data.order_amount)
                or money(existing.customer_received_amount) != customer_received
            ):
                raise HTTPException(status_code=409, detail="幂等键已用于不同的订单内容")
            existing_plan = db.scalar(
                select(OrderPaymentPlan)
                .where(
                    OrderPaymentPlan.tenant_id == tenant_id,
                    OrderPaymentPlan.order_id == existing.id,
                )
                .order_by(OrderPaymentPlan.revision.desc())
            )
            if not existing_plan:
                raise HTTPException(status_code=409, detail="重复订单缺少支付方案，请联系管理员")
            return existing, existing_plan
    expire_plans(db, tenant_id, user_id)
    order = Order(
        tenant_id=tenant_id,
        order_no=f"{data.business_date:%Y%m%d}-{uuid4().hex[:8].upper()}",
        client_request_id=data.idempotency_key,
        business_date=data.business_date,
        status=OrderStatus.DRAFT.value,
        source_id=None,
        contractor_id=None,
        contractor_type=None,
        contractor_name_snapshot=None,
        performer_id=None,
        performer_name_snapshot=None,
        student_name=None,
        order_amount=money(data.order_amount),
        customer_received_amount=customer_received,
        coupon_amount=ZERO,
        actual_paid=ZERO,
        settlement_basis_snapshot="JIJIHONG",
        settlement_method_snapshot="DISCOUNT",
        discount_snapshot=Decimal("1"),
        fixed_deduction_snapshot=Decimal("0"),
        settlement_income=customer_received,
        income_overridden=False,
        commission=ZERO,
        commission_overridden=False,
        cost=ZERO,
        profit=ZERO,
        note=data.note,
        created_by=user_id,
    )
    db.add(order)
    db.flush()
    plan = reserve_selected_plan(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        order=order,
        selected=data.allocations,
        override_reason=data.external_cash_override_reason,
    )
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="order.created",
        resource_type="order",
        resource_id=order.id,
        payload={"status": order.status, "order_no": order.order_no, "business_mode": "JIJIHONG"},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if data.idempotency_key:
            existing = db.scalar(
                select(Order).where(
                    Order.tenant_id == tenant_id,
                    Order.client_request_id == data.idempotency_key,
                )
            )
            if existing:
                existing_plan = db.scalar(
                    select(OrderPaymentPlan)
                    .where(
                        OrderPaymentPlan.tenant_id == tenant_id,
                        OrderPaymentPlan.order_id == existing.id,
                    )
                    .order_by(OrderPaymentPlan.revision.desc())
                )
                if existing_plan:
                    return existing, existing_plan
        raise
    db.refresh(order)
    db.refresh(plan)
    return order, plan


def replace_jijihong_reservation(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    order_id: int,
    data: JijihongOrderReservationInput,
) -> tuple[Order, OrderPaymentPlan]:
    ensure_jijihong(db, tenant_id)
    expire_plans(db, tenant_id, user_id)
    order = _get_order(db, tenant_id, order_id, for_update=True)
    if order.status not in (OrderStatus.DRAFT.value, OrderStatus.DISPATCHED.value):
        raise HTTPException(status_code=409, detail="只有待付款订单可以修改预占方案")
    release_reserved_plan_for_order(
        db,
        tenant_id=tenant_id,
        order_id=order.id,
        user_id=user_id,
        reason="录单修改并替换预占方案",
    )
    order.order_amount = money(data.order_amount)
    order.customer_received_amount = money(data.customer_received_amount)
    order.settlement_income = order.customer_received_amount
    order.note = data.note
    plan = reserve_selected_plan(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        order=order,
        selected=data.allocations,
        override_reason=data.external_cash_override_reason,
    )
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="order.payment_reservation_replaced",
        resource_type="order",
        resource_id=order.id,
        payload={"plan_id": plan.id, "revision": plan.revision},
    )
    db.commit()
    db.refresh(order)
    db.refresh(plan)
    return order, plan


def recommend_and_reserve(
    db: Session, *, tenant_id: int, user_id: int, order_id: int
) -> OrderPaymentPlan:
    ensure_jijihong(db, tenant_id)
    order = _get_order(db, tenant_id, order_id, for_update=True)
    if order.status not in (OrderStatus.DRAFT.value, OrderStatus.DISPATCHED.value):
        raise HTTPException(status_code=409, detail="只有草稿或已派单订单可以推荐支付方案")
    expire_plans(db, tenant_id, user_id)
    release_reserved_plan_for_order(
        db,
        tenant_id=tenant_id,
        order_id=order.id,
        user_id=user_id,
        reason="重新推荐支付方案",
    )
    promote_available_coupons(db, tenant_id)
    settings = get_pool_settings(db, tenant_id)
    rows = db.execute(
        select(AlipayAccount, AlipayDevice, AlipayCoupon)
        .join(AlipayDevice, AlipayDevice.id == AlipayAccount.device_id)
        .outerjoin(
            AlipayCoupon,
            (AlipayCoupon.account_id == AlipayAccount.id)
            & (AlipayCoupon.tenant_id == tenant_id),
        )
        .where(
            AlipayAccount.tenant_id == tenant_id,
            AlipayAccount.status == AccountStatus.ACTIVE.value,
            AlipayAccount.phase.in_(
                [
                    AccountPhase.NOT_STARTED.value,
                    AccountPhase.DAY1_ACTIVE.value,
                    AccountPhase.DAY2_ACTIVE.value,
                ]
            ),
            AlipayDevice.is_active.is_(True),
        )
    ).all()
    candidates: list[Candidate] = []
    for account, device, coupon in rows:
        available = money(
            Decimal(account.current_balance) - Decimal(account.reserved_balance)
        )
        coupon_amount = (
            Decimal(coupon.amount)
            if coupon and coupon.status == CouponStatus.AVAILABLE.value
            else ZERO
        )
        if available > 0 or coupon_amount > 0:
            candidates.append(
                Candidate(
                    account_id=account.id,
                    device_name=device.name,
                    alias=account.alias,
                    phase=account.phase,
                    balance=available,
                    coupon=coupon_amount,
                )
            )
    try:
        suggestion = recommend(
            candidates,
            order_amount=Decimal(order.order_amount),
            soft_cap=Decimal(settings.external_cash_soft_cap),
            first_day_target=Decimal(settings.first_day_target_balance),
            first_day_tolerance=Decimal(settings.first_day_target_tolerance),
            max_split_accounts=settings.max_split_accounts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    revision = int(
        db.scalar(
            select(func.max(OrderPaymentPlan.revision)).where(
                OrderPaymentPlan.tenant_id == tenant_id,
                OrderPaymentPlan.order_id == order.id,
            )
        )
        or 0
    ) + 1
    warning = (
        f"最优方案仍需真实付款 {suggestion.total_external_cash} 元，"
        f"超过软上限 {settings.external_cash_soft_cap} 元"
        if suggestion.soft_cap_exceeded
        else None
    )
    plan = OrderPaymentPlan(
        tenant_id=tenant_id,
        order_id=order.id,
        revision=revision,
        status=PaymentPlanStatus.RESERVED.value,
        order_amount=order.order_amount,
        total_coupon=suggestion.total_coupon,
        total_balance=suggestion.total_balance,
        total_external_cash=suggestion.total_external_cash,
        soft_cap_exceeded=suggestion.soft_cap_exceeded,
        warning=warning,
        algorithm_version="v1-clearing-first",
        expires_at=datetime.now(timezone.utc)
        + timedelta(minutes=settings.reservation_minutes),
        created_by=user_id,
    )
    db.add(plan)
    db.flush()
    for sequence, suggested in enumerate(suggestion.allocations, start=1):
        account = get_account(
            db, tenant_id, suggested.account_id, for_update=True
        )
        available = Decimal(account.current_balance) - Decimal(account.reserved_balance)
        if available < suggested.balance_amount:
            raise HTTPException(status_code=409, detail="账号余额已变化，请重新推荐")
        allocation = OrderPaymentAllocation(
            tenant_id=tenant_id,
            plan_id=plan.id,
            account_id=account.id,
            sequence=sequence,
            device_name_snapshot=suggested.device_name,
            account_alias_snapshot=suggested.alias,
            coupon_amount=suggested.coupon_amount,
            balance_amount=suggested.balance_amount,
            external_cash_amount=suggested.external_cash_amount,
            balance_before=suggested.balance_before,
            balance_after=suggested.balance_after,
        )
        db.add(allocation)
        db.flush()
        account.reserved_balance = (
            Decimal(account.reserved_balance) + suggested.balance_amount
        )
        account.version += 1
        _append_balance_entry(
            db,
            account=account,
            user_id=user_id,
            entry_type=BalanceEntryType.RESERVE,
            reserved_delta=suggested.balance_amount,
            idempotency_key=f"plan:{plan.id}:reserve:{account.id}",
            order_id=order.id,
            plan_id=plan.id,
            allocation_id=allocation.id,
            reason="订单支付方案预占",
        )
        if suggested.coupon_amount > 0:
            coupon = db.scalar(
                select(AlipayCoupon)
                .where(
                    AlipayCoupon.account_id == account.id,
                    AlipayCoupon.status == CouponStatus.AVAILABLE.value,
                )
                .with_for_update()
            )
            if not coupon or Decimal(coupon.amount) < suggested.coupon_amount:
                raise HTTPException(status_code=409, detail="优惠券状态已变化，请重新推荐")
            coupon.status = CouponStatus.RESERVED.value
            coupon.reserved_plan_id = plan.id
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="alipay.plan_reserved",
        resource_type="order_payment_plan",
        resource_id=plan.id,
        payload={
            "order_id": order.id,
            "balance": str(plan.total_balance),
            "coupon": str(plan.total_coupon),
            "external_cash": str(plan.total_external_cash),
        },
    )
    db.commit()
    db.refresh(plan)
    return plan


def confirm_plan(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    plan_id: int,
    data: ConfirmPlanInput,
) -> OrderPaymentPlan:
    ensure_jijihong(db, tenant_id)
    plan = db.scalar(
        select(OrderPaymentPlan)
        .where(
            OrderPaymentPlan.id == plan_id,
            OrderPaymentPlan.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if not plan:
        raise HTTPException(status_code=404, detail="支付方案不存在")
    if plan.status != PaymentPlanStatus.RESERVED.value:
        raise HTTPException(status_code=409, detail="支付方案不是待确认状态")
    if _aware(plan.expires_at) <= datetime.now(timezone.utc):
        _release_plan(
            db,
            plan=plan,
            user_id=user_id,
            target_status=PaymentPlanStatus.EXPIRED,
            reason="确认时方案已过期",
        )
        db.commit()
        raise HTTPException(status_code=409, detail="支付方案已过期，请重新推荐")
    order = _get_order(db, tenant_id, plan.order_id, for_update=True)
    if order.status not in (OrderStatus.DRAFT.value, OrderStatus.DISPATCHED.value):
        raise HTTPException(status_code=409, detail="订单状态已变化，无法确认")
    allocations = list(
        db.scalars(
            select(OrderPaymentAllocation)
            .where(OrderPaymentAllocation.plan_id == plan.id)
            .order_by(OrderPaymentAllocation.sequence)
        )
    )
    account_ids = sorted(allocation.account_id for allocation in allocations)
    accounts = {
        account.id: account
        for account in db.scalars(
            select(AlipayAccount)
            .where(
                AlipayAccount.tenant_id == tenant_id,
                AlipayAccount.id.in_(account_ids),
            )
            .order_by(AlipayAccount.id)
            .with_for_update()
        )
    }
    coupons = {
        coupon.account_id: coupon
        for coupon in db.scalars(
            select(AlipayCoupon)
            .where(
                AlipayCoupon.tenant_id == tenant_id,
                AlipayCoupon.account_id.in_(account_ids),
            )
            .order_by(AlipayCoupon.account_id)
            .with_for_update()
        )
    }
    if set(accounts) != set(account_ids):
        raise HTTPException(status_code=409, detail="支付账号已不存在")
    provided = (
        {item.account_id: item for item in data.allocations}
        if data.allocations is not None
        else None
    )
    if provided is not None and set(provided) != {item.account_id for item in allocations}:
        raise HTTPException(status_code=422, detail="确认账号必须与推荐方案一致")
    if provided is not None and plan.algorithm_version == "v2-live-preview":
        changed = any(
            money(provided[item.account_id].coupon_amount) != money(item.coupon_amount)
            or money(provided[item.account_id].balance_amount) != money(item.balance_amount)
            or money(provided[item.account_id].external_cash_amount)
            != money(item.external_cash_amount)
            for item in allocations
        )
        if changed:
            raise HTTPException(status_code=409, detail="新录单流程必须先替换预占方案，再确认付款")

    settings = get_pool_settings(db, tenant_id)
    total_coupon = ZERO
    total_balance = ZERO
    total_cash = ZERO
    for allocation in allocations:
        actual = provided.get(allocation.account_id) if provided is not None else None
        coupon_amount = (
            money(actual.coupon_amount) if actual else Decimal(allocation.coupon_amount)
        )
        balance_amount = (
            money(actual.balance_amount) if actual else Decimal(allocation.balance_amount)
        )
        cash_amount = (
            money(actual.external_cash_amount)
            if actual
            else Decimal(allocation.external_cash_amount)
        )
        account = accounts[allocation.account_id]
        old_reserved = Decimal(allocation.balance_amount)
        available_for_plan = (
            Decimal(account.current_balance)
            - Decimal(account.reserved_balance)
            + old_reserved
        )
        if balance_amount > available_for_plan:
            raise HTTPException(status_code=409, detail=f"账号 {account.alias} 可用余额不足")
        coupon = coupons.get(account.id)
        if coupon_amount > 0 and (
            not coupon
            or coupon.status != CouponStatus.RESERVED.value
            or coupon.reserved_plan_id != plan.id
            or coupon_amount > Decimal(coupon.amount)
        ):
            raise HTTPException(status_code=409, detail=f"账号 {account.alias} 优惠券不可用")
        if coupon_amount > 0 and coupon and coupon_amount != Decimal(coupon.amount):
            raise HTTPException(status_code=422, detail="优惠券必须整张使用")
        total_coupon += coupon_amount
        total_balance += balance_amount
        total_cash += cash_amount

    if money(total_coupon + total_balance + total_cash) != money(plan.order_amount):
        raise HTTPException(status_code=422, detail="优惠券、余额和真实付款合计必须等于订单金额")

    for allocation in allocations:
        actual = provided.get(allocation.account_id) if provided is not None else None
        coupon_amount = (
            money(actual.coupon_amount) if actual else Decimal(allocation.coupon_amount)
        )
        balance_amount = (
            money(actual.balance_amount) if actual else Decimal(allocation.balance_amount)
        )
        cash_amount = (
            money(actual.external_cash_amount)
            if actual
            else Decimal(allocation.external_cash_amount)
        )
        account = accounts[allocation.account_id]
        old_reserved = Decimal(allocation.balance_amount)
        account.reserved_balance = Decimal(account.reserved_balance) - old_reserved
        account.current_balance = Decimal(account.current_balance) - balance_amount
        account.version += 1
        if account.current_balance == 0:
            account.status = AccountStatus.EXHAUSTED.value
            account.phase = AccountPhase.EXHAUSTED.value
        allocation.coupon_amount = coupon_amount
        allocation.balance_amount = balance_amount
        allocation.external_cash_amount = cash_amount
        allocation.balance_before = Decimal(account.current_balance) + balance_amount
        allocation.balance_after = account.current_balance
        _append_balance_entry(
            db,
            account=account,
            user_id=user_id,
            entry_type=BalanceEntryType.CONFIRM,
            balance_delta=-balance_amount,
            reserved_delta=-old_reserved,
            idempotency_key=f"plan:{plan.id}:confirm:{account.id}",
            order_id=order.id,
            plan_id=plan.id,
            allocation_id=allocation.id,
            reason="人工确认订单支付成功",
        )
        coupon = coupons.get(account.id)
        if account.first_used_at is None and balance_amount > 0:
            account.first_used_at = datetime.now(timezone.utc)
        if (
            account.phase in (
                AccountPhase.NOT_STARTED.value,
                AccountPhase.DAY1_ACTIVE.value,
            )
            and account.status == AccountStatus.ACTIVE.value
        ):
            account.phase = AccountPhase.DAY1_ACTIVE.value
            if (
                coupon
                and coupon.status == CouponStatus.PENDING.value
                and Decimal(account.current_balance)
                <= Decimal(settings.first_day_target_balance)
                + Decimal(settings.first_day_target_tolerance)
            ):
                account.phase = AccountPhase.WAITING_COUPON.value
        if coupon and coupon.reserved_plan_id == plan.id:
            coupon.reserved_plan_id = None
            if coupon_amount > 0:
                coupon.status = CouponStatus.USED.value
                coupon.used_at = datetime.now(timezone.utc)
            else:
                coupon.status = CouponStatus.AVAILABLE.value

    plan.total_coupon = money(total_coupon)
    plan.total_balance = money(total_balance)
    plan.total_external_cash = money(total_cash)
    plan.soft_cap_exceeded = plan.total_external_cash > settings.external_cash_soft_cap
    plan.warning = (
        f"实际真实付款 {plan.total_external_cash} 元超过软上限 "
        f"{settings.external_cash_soft_cap} 元"
        if plan.soft_cap_exceeded
        else None
    )
    plan.status = PaymentPlanStatus.CONFIRMED.value
    plan.confirmed_at = datetime.now(timezone.utc)

    from app.modules.alipay_pool.finance_service import book_confirmed_order_finance

    book_confirmed_order_finance(
        db,
        order=order,
        plan=plan,
        allocations=allocations,
        user_id=user_id,
    )
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="alipay.plan_confirmed",
        resource_type="order_payment_plan",
        resource_id=plan.id,
        payload={
            "order_id": order.id,
            "balance": str(plan.total_balance),
            "coupon": str(plan.total_coupon),
            "external_cash": str(plan.total_external_cash),
            "allocations": [
                {
                    "account_id": item.account_id,
                    "coupon": str(item.coupon_amount),
                    "balance": str(item.balance_amount),
                    "external_cash": str(item.external_cash_amount),
                }
                for item in allocations
            ],
        },
    )
    db.commit()
    db.refresh(plan)
    return plan


def reverse_confirmed_plan_for_order(
    db: Session,
    *,
    tenant_id: int,
    order_id: int,
    user_id: int,
    reason: str,
) -> None:
    plan = db.scalar(
        select(OrderPaymentPlan)
        .where(
            OrderPaymentPlan.tenant_id == tenant_id,
            OrderPaymentPlan.order_id == order_id,
            OrderPaymentPlan.status == PaymentPlanStatus.CONFIRMED.value,
        )
        .with_for_update()
    )
    if not plan:
        return
    allocations = list(
        db.scalars(
            select(OrderPaymentAllocation).where(
                OrderPaymentAllocation.plan_id == plan.id
            )
        )
    )
    for allocation in allocations:
        account = get_account(db, tenant_id, allocation.account_id, for_update=True)
        account.current_balance = (
            Decimal(account.current_balance) + Decimal(allocation.balance_amount)
        )
        account.version += 1
        if account.current_balance > 0 and account.status == AccountStatus.EXHAUSTED.value:
            account.status = AccountStatus.ACTIVE.value
            account.phase = AccountPhase.DAY2_ACTIVE.value
        confirmed_entry = db.scalar(
            select(AlipayBalanceEntry).where(
                AlipayBalanceEntry.plan_id == plan.id,
                AlipayBalanceEntry.account_id == account.id,
                AlipayBalanceEntry.entry_type == BalanceEntryType.CONFIRM.value,
            )
        )
        _append_balance_entry(
            db,
            account=account,
            user_id=user_id,
            entry_type=BalanceEntryType.REVERSAL,
            balance_delta=Decimal(allocation.balance_amount),
            idempotency_key=f"plan:{plan.id}:reversal:{account.id}",
            order_id=order_id,
            plan_id=plan.id,
            allocation_id=allocation.id,
            reversed_entry_id=confirmed_entry.id if confirmed_entry else None,
            reason=reason,
        )
        if allocation.coupon_amount > 0:
            coupon = db.scalar(
                select(AlipayCoupon).where(AlipayCoupon.account_id == account.id)
            )
            if coupon and coupon.status == CouponStatus.USED.value:
                coupon.status = CouponStatus.AVAILABLE.value
                coupon.used_at = None
    plan.status = PaymentPlanStatus.REVERSED.value
    plan.reversed_at = datetime.now(timezone.utc)
    order = _get_order(db, tenant_id, order_id)
    from app.modules.alipay_pool.finance_service import reverse_order_finance

    reverse_order_finance(
        db,
        tenant_id=tenant_id,
        order=order,
        user_id=user_id,
        reason=reason,
    )
    record_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action="alipay.plan_reversed",
        resource_type="order_payment_plan",
        resource_id=plan.id,
        payload={"order_id": order_id, "reason": reason},
    )


def has_confirmed_plan(db: Session, tenant_id: int, order_id: int) -> bool:
    return bool(
        db.scalar(
            select(OrderPaymentPlan.id).where(
                OrderPaymentPlan.tenant_id == tenant_id,
                OrderPaymentPlan.order_id == order_id,
                OrderPaymentPlan.status == PaymentPlanStatus.CONFIRMED.value,
            )
        )
    )
