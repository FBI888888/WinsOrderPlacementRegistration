from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.modules.iam.dependencies import CurrentContext, DbSession, require_roles
from app.modules.iam.models import MemberRole
from app.modules.settlements.models import Settlement, SettlementStatus, SettlementType
from app.modules.settlements.schemas import (
    BatchClearingRequest,
    ClearingPreviewItem,
    ClearingRequest,
    SettlementAction,
    SettlementCreate,
    SettlementOutput,
)
from app.modules.settlements.service import (
    clear_all_targets,
    clear_target,
    confirm_settlement,
    create_settlement,
    get_settlement,
    list_clearing_preview,
    reverse_settlement,
)

router = APIRouter(prefix="/settlements", tags=["结算"])
write_roles = (MemberRole.OWNER.value, MemberRole.BOOKKEEPER.value)


@router.get("/clearing-preview", response_model=list[ClearingPreviewItem])
def clearing_preview(context: CurrentContext, db: DbSession) -> list[dict]:
    return list_clearing_preview(db, tenant_id=context.tenant_id)


@router.post("/clear", response_model=SettlementOutput)
def clear_one(
    data: ClearingRequest,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> Settlement:
    settlement = clear_target(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        settlement_type=data.settlement_type,
        counterparty_id=data.counterparty_id,
        business_date=data.business_date,
        note=data.note,
    )
    db.commit()
    db.refresh(settlement)
    return settlement


@router.post("/clear-batch", response_model=list[SettlementOutput])
def clear_batch(
    data: BatchClearingRequest,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> list[Settlement]:
    return clear_all_targets(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        business_date=data.business_date,
        note=data.note,
    )


@router.get("", response_model=list[SettlementOutput])
def list_settlements(
    context: CurrentContext,
    db: DbSession,
    settlement_type: SettlementType | None = None,
    settlement_status: SettlementStatus | None = Query(default=None, alias="status"),
) -> list[Settlement]:
    query = select(Settlement).where(Settlement.tenant_id == context.tenant_id)
    if settlement_type:
        query = query.where(Settlement.settlement_type == settlement_type.value)
    if settlement_status:
        query = query.where(Settlement.status == settlement_status.value)
    return list(db.scalars(query.order_by(Settlement.id.desc()).limit(500)))


@router.get("/{settlement_id}", response_model=SettlementOutput)
def retrieve_settlement(
    settlement_id: int, context: CurrentContext, db: DbSession
) -> Settlement:
    return get_settlement(db, context.tenant_id, settlement_id)


@router.post("", response_model=SettlementOutput, status_code=201)
def create_settlement_endpoint(
    data: SettlementCreate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> Settlement:
    return create_settlement(
        db, tenant_id=context.tenant_id, user_id=context.user_id, data=data
    )


@router.post("/{settlement_id}/confirm", response_model=SettlementOutput)
def confirm_settlement_endpoint(
    settlement_id: int,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> Settlement:
    return confirm_settlement(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        settlement_id=settlement_id,
    )


@router.post("/{settlement_id}/reverse", response_model=SettlementOutput)
def reverse_settlement_endpoint(
    settlement_id: int,
    data: SettlementAction,
    db: DbSession,
    context=Depends(require_roles(MemberRole.OWNER.value)),
) -> Settlement:
    return reverse_settlement(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        settlement_id=settlement_id,
        reason=data.reason,
    )