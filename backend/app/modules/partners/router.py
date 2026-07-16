from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.iam.audit import record_audit
from app.modules.iam.dependencies import CurrentContext, DbSession, require_roles
from app.modules.iam.models import MemberRole
from app.modules.partners.models import (
    Contractor,
    ContractorRate,
    ContractorType,
    Performer,
    PerformerType,
    Source,
    SourceRate,
)
from app.modules.partners.schemas import (
    ContractorCreate,
    ContractorOutput,
    ContractorRateCreate,
    ContractorUpdate,
    PerformerCreate,
    PerformerOutput,
    PerformerUpdate,
    SourceCreate,
    SourceOutput,
    SourceRateCreate,
    SourceUpdate,
)
from app.modules.partners.service import (
    get_contractor,
    get_or_create_performer,
    get_performer,
    get_source,
    normalize_name,
)

router = APIRouter(prefix="/partners", tags=["合作方与费率"])
write_roles = (MemberRole.OWNER.value, MemberRole.BOOKKEEPER.value)


@router.get("/sources", response_model=list[SourceOutput])
def list_sources(context: CurrentContext, db: DbSession, active_only: bool = False) -> list[Source]:
    query = select(Source).where(Source.tenant_id == context.tenant_id)
    if active_only:
        query = query.where(Source.is_active.is_(True))
    return list(db.scalars(query.order_by(Source.name)))


@router.post("/sources", response_model=SourceOutput, status_code=status.HTTP_201_CREATED)
def create_source(
    data: SourceCreate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> Source:
    source = Source(
        tenant_id=context.tenant_id,
        name=data.name.strip(),
        contact=data.contact,
        default_basis=data.default_basis.value,
        default_discount=data.default_discount,
        note=data.note,
    )
    db.add(source)
    try:
        db.flush()
        db.add(
            SourceRate(
                tenant_id=context.tenant_id,
                source_id=source.id,
                effective_date=data.effective_date,
                settlement_basis=data.default_basis.value,
                discount=data.default_discount,
            )
        )
        record_audit(
            db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            action="source.created",
            resource_type="source",
            resource_id=source.id,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="放单人员名称重复") from exc
    db.refresh(source)
    return source


@router.patch("/sources/{source_id}", response_model=SourceOutput)
def update_source(
    source_id: int,
    data: SourceUpdate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> Source:
    source = get_source(db, context.tenant_id, source_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        if key == "name" and value:
            value = value.strip()
        setattr(source, key, value)
    record_audit(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action="source.updated",
        resource_type="source",
        resource_id=source.id,
        payload=data.model_dump(exclude_unset=True, mode="json"),
    )
    db.commit()
    db.refresh(source)
    return source


@router.post("/sources/{source_id}/rates", status_code=status.HTTP_201_CREATED)
def create_source_rate(
    source_id: int,
    data: SourceRateCreate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> dict:
    source = get_source(db, context.tenant_id, source_id)
    rate = SourceRate(
        tenant_id=context.tenant_id,
        source_id=source.id,
        effective_date=data.effective_date,
        settlement_basis=data.settlement_basis.value,
        discount=data.discount,
    )
    if data.effective_date <= date.today():
        source.default_basis = data.settlement_basis.value
        source.default_discount = data.discount
    db.add(rate)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该日期已配置费率") from exc
    return {"id": rate.id, "message": "费率已生效"}


@router.get("/contractors", response_model=list[ContractorOutput])
def list_contractors(
    context: CurrentContext,
    db: DbSession,
    contractor_type: ContractorType | None = Query(default=None),
    active_only: bool = False,
) -> list[Contractor]:
    query = select(Contractor).where(Contractor.tenant_id == context.tenant_id)
    if contractor_type:
        query = query.where(Contractor.contractor_type == contractor_type.value)
    if active_only:
        query = query.where(Contractor.is_active.is_(True))
    return list(db.scalars(query.order_by(Contractor.contractor_type, Contractor.name)))


@router.get("/performers", response_model=list[PerformerOutput])
def list_performers(
    context: CurrentContext,
    db: DbSession,
    contractor_id: int | None = None,
    performer_type: PerformerType | None = Query(default=None),
    active_only: bool = False,
    listed_only: bool = False,
) -> list[Performer]:
    query = select(Performer).where(Performer.tenant_id == context.tenant_id)
    if contractor_id is not None:
        query = query.where(Performer.contractor_id == contractor_id)
    if performer_type is not None:
        query = query.where(Performer.performer_type == performer_type.value)
    if active_only:
        query = query.where(Performer.is_active.is_(True))
    if listed_only:
        query = query.where(Performer.is_listed.is_(True))
    return list(db.scalars(query.order_by(Performer.name, Performer.id)))


@router.post("/performers", response_model=PerformerOutput, status_code=status.HTTP_201_CREATED)
def create_performer(
    data: PerformerCreate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> Performer:
    contractor = get_contractor(db, context.tenant_id, data.contractor_id)
    expected_contractor_type = (
        ContractorType.LEADER.value
        if data.performer_type == PerformerType.STUDENT
        else ContractorType.RETAIL.value
    )
    if contractor.contractor_type != expected_contractor_type:
        raise HTTPException(status_code=422, detail="实际做单人类型与合作方类型不匹配")
    if not contractor.is_active:
        raise HTTPException(status_code=422, detail="合作方已停用，不能新增实际做单人")
    normalized_name = normalize_name(data.name)
    existing = db.scalar(
        select(Performer).where(
            Performer.tenant_id == context.tenant_id,
            Performer.performer_type == data.performer_type.value,
            Performer.contractor_id == contractor.id,
            Performer.normalized_name == normalized_name,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="该合作方名下已存在同名做单人")
    performer = get_or_create_performer(
        db,
        tenant_id=context.tenant_id,
        contractor_id=contractor.id,
        performer_type=data.performer_type,
        name=data.name,
        is_listed=data.is_listed,
    )
    if performer.note is None:
        performer.note = data.note
    record_audit(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action="performer.created",
        resource_type="performer",
        resource_id=performer.id,
        payload={"contractor_id": contractor.id, "performer_type": data.performer_type.value},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="该合作方名下已存在同名做单人") from exc
    db.refresh(performer)
    return performer


@router.patch("/performers/{performer_id}", response_model=PerformerOutput)
def update_performer(
    performer_id: int,
    data: PerformerUpdate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> Performer:
    performer = get_performer(db, context.tenant_id, performer_id)
    if performer.performer_type == PerformerType.RETAIL.value and data.name is not None:
        raise HTTPException(status_code=422, detail="散户姓名请在散户合作方中修改")
    for key, value in data.model_dump(exclude_unset=True).items():
        if key == "name" and value:
            performer.normalized_name = normalize_name(value)
            value = value.strip()
        setattr(performer, key, value)
    record_audit(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action="performer.updated",
        resource_type="performer",
        resource_id=performer.id,
        payload=data.model_dump(exclude_unset=True, mode="json"),
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="该学生头子名下已存在同名学生") from exc
    db.refresh(performer)
    return performer


@router.post("/contractors", response_model=ContractorOutput, status_code=status.HTTP_201_CREATED)
def create_contractor(
    data: ContractorCreate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> Contractor:
    contractor = Contractor(
        tenant_id=context.tenant_id,
        name=data.name.strip(),
        normalized_name=normalize_name(data.name),
        contractor_type=data.contractor_type.value,
        contact=data.contact,
        default_commission=(
            data.default_commission if data.contractor_type == ContractorType.LEADER else 0
        ),
        note=data.note,
    )
    db.add(contractor)
    try:
        db.flush()
        if data.contractor_type == ContractorType.LEADER:
            db.add(
                ContractorRate(
                    tenant_id=context.tenant_id,
                    contractor_id=contractor.id,
                    effective_date=data.effective_date,
                    commission_per_order=data.default_commission,
                )
            )
        else:
            get_or_create_performer(
                db,
                tenant_id=context.tenant_id,
                contractor_id=contractor.id,
                performer_type=PerformerType.RETAIL,
                name=contractor.name,
                is_listed=True,
            )
        record_audit(
            db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            action="contractor.created",
            resource_type="contractor",
            resource_id=contractor.id,
            payload={"contractor_type": data.contractor_type.value},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        label = "学生头子" if data.contractor_type == ContractorType.LEADER else "散户"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{label}名称重复") from exc
    db.refresh(contractor)
    return contractor


@router.patch("/contractors/{contractor_id}", response_model=ContractorOutput)
def update_contractor(
    contractor_id: int,
    data: ContractorUpdate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> Contractor:
    contractor = get_contractor(db, context.tenant_id, contractor_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        if key == "name" and value:
            contractor.normalized_name = normalize_name(value)
            value = value.strip()
        setattr(contractor, key, value)
    if contractor.contractor_type == ContractorType.RETAIL.value:
        performer = db.scalar(
            select(Performer).where(
                Performer.tenant_id == context.tenant_id,
                Performer.contractor_id == contractor.id,
                Performer.performer_type == PerformerType.RETAIL.value,
            )
        )
        if performer:
            performer.name = contractor.name
            performer.normalized_name = contractor.normalized_name
            performer.is_active = contractor.is_active
        else:
            get_or_create_performer(
                db,
                tenant_id=context.tenant_id,
                contractor_id=contractor.id,
                performer_type=PerformerType.RETAIL,
                name=contractor.name,
                is_listed=True,
            )
    record_audit(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action="contractor.updated",
        resource_type="contractor",
        resource_id=contractor.id,
        payload=data.model_dump(exclude_unset=True, mode="json"),
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        label = (
            "学生头子"
            if contractor.contractor_type == ContractorType.LEADER.value
            else "散户"
        )
        raise HTTPException(status_code=409, detail=f"{label}名称重复") from exc
    db.refresh(contractor)
    return contractor


@router.post("/contractors/{contractor_id}/rates", status_code=status.HTTP_201_CREATED)
def create_contractor_rate(
    contractor_id: int,
    data: ContractorRateCreate,
    db: DbSession,
    context=Depends(require_roles(*write_roles)),
) -> dict:
    contractor = get_contractor(db, context.tenant_id, contractor_id)
    if contractor.contractor_type != ContractorType.LEADER.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="散户佣金按订单填写")
    rate = ContractorRate(
        tenant_id=context.tenant_id,
        contractor_id=contractor.id,
        effective_date=data.effective_date,
        commission_per_order=data.commission_per_order,
    )
    if data.effective_date <= date.today():
        contractor.default_commission = data.commission_per_order
    db.add(rate)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该日期已配置佣金") from exc
    return {"id": rate.id, "message": "佣金规则已生效"}