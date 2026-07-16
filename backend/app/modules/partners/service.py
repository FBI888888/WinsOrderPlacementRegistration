from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.partners.models import (
    Contractor,
    ContractorRate,
    ContractorType,
    Performer,
    PerformerType,
    SettlementBasis,
    Source,
    SourceRate,
)


def normalize_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


def get_source(db: Session, tenant_id: int, source_id: int) -> Source:
    source = db.scalar(select(Source).where(Source.id == source_id, Source.tenant_id == tenant_id))
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="放单人员不存在")
    return source


def get_contractor(db: Session, tenant_id: int, contractor_id: int) -> Contractor:
    contractor = db.scalar(
        select(Contractor).where(Contractor.id == contractor_id, Contractor.tenant_id == tenant_id)
    )
    if not contractor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="做单方不存在")
    return contractor


def resolve_source_rate(
    db: Session, tenant_id: int, source_id: int, business_date: date
) -> tuple[SettlementBasis, Decimal]:
    source = get_source(db, tenant_id, source_id)
    rate = db.scalar(
        select(SourceRate)
        .where(
            SourceRate.tenant_id == tenant_id,
            SourceRate.source_id == source_id,
            SourceRate.effective_date <= business_date,
        )
        .order_by(SourceRate.effective_date.desc(), SourceRate.id.desc())
        .limit(1)
    )
    if rate:
        return SettlementBasis(rate.settlement_basis), Decimal(rate.discount)
    return SettlementBasis(source.default_basis), Decimal(source.default_discount)


def resolve_contractor_rate(
    db: Session, tenant_id: int, contractor_id: int, business_date: date
) -> Decimal:
    contractor = get_contractor(db, tenant_id, contractor_id)
    rate = db.scalar(
        select(ContractorRate)
        .where(
            ContractorRate.tenant_id == tenant_id,
            ContractorRate.contractor_id == contractor_id,
            ContractorRate.effective_date <= business_date,
        )
        .order_by(ContractorRate.effective_date.desc(), ContractorRate.id.desc())
        .limit(1)
    )
    return Decimal(rate.commission_per_order if rate else contractor.default_commission)


def get_performer(db: Session, tenant_id: int, performer_id: int) -> Performer:
    performer = db.scalar(
        select(Performer).where(
            Performer.id == performer_id,
            Performer.tenant_id == tenant_id,
        )
    )
    if not performer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="实际做单人不存在")
    return performer


def get_or_create_performer(
    db: Session,
    *,
    tenant_id: int,
    contractor_id: int,
    performer_type: PerformerType,
    name: str,
    is_listed: bool,
) -> Performer:
    normalized = normalize_name(name)
    if not normalized:
        raise HTTPException(status_code=422, detail="实际做单人姓名不能为空")
    performer = db.scalar(
        select(Performer).where(
            Performer.tenant_id == tenant_id,
            Performer.performer_type == performer_type.value,
            Performer.contractor_id == contractor_id,
            Performer.normalized_name == normalized,
        )
    )
    if performer:
        if is_listed and not performer.is_listed:
            performer.is_listed = True
        return performer
    performer = Performer(
        tenant_id=tenant_id,
        name=name.strip(),
        normalized_name=normalized,
        performer_type=performer_type.value,
        contractor_id=contractor_id,
        is_listed=is_listed,
    )
    db.add(performer)
    db.flush()
    return performer


def get_or_create_retail(db: Session, tenant_id: int, name: str) -> Contractor:
    normalized = normalize_name(name)
    contractor = db.scalar(
        select(Contractor).where(
            Contractor.tenant_id == tenant_id,
            Contractor.contractor_type == ContractorType.RETAIL.value,
            Contractor.normalized_name == normalized,
        )
    )
    if contractor:
        return contractor
    contractor = Contractor(
        tenant_id=tenant_id,
        name=name.strip(),
        normalized_name=normalized,
        contractor_type=ContractorType.RETAIL.value,
        default_commission=Decimal("0"),
    )
    db.add(contractor)
    db.flush()
    return contractor


def resolve_performer_assignment(
    db: Session,
    *,
    tenant_id: int,
    contractor_type: ContractorType,
    contractor_id: int | None,
    performer_id: int | None,
    performer_name: str | None,
    save_performer: bool,
    allow_inactive_contractor_id: int | None = None,
    allow_inactive_performer_id: int | None = None,
) -> tuple[Contractor, Performer]:
    if performer_id is not None:
        performer = get_performer(db, tenant_id, performer_id)
        expected_type = (
            PerformerType.STUDENT
            if contractor_type == ContractorType.LEADER
            else PerformerType.RETAIL
        )
        if performer.performer_type != expected_type.value:
            raise HTTPException(status_code=422, detail="实际做单人类型与做单方式不匹配")
        if contractor_type == ContractorType.LEADER and performer.contractor_id != contractor_id:
            raise HTTPException(status_code=422, detail="该学生不属于所选学生头子")
        contractor = get_contractor(db, tenant_id, performer.contractor_id)
    elif contractor_type == ContractorType.LEADER:
        if contractor_id is None:
            raise HTTPException(status_code=422, detail="请选择学生头子")
        if not performer_name:
            raise HTTPException(status_code=422, detail="请选择或填写实际做单学生")
        contractor = get_contractor(db, tenant_id, contractor_id)
        performer = get_or_create_performer(
            db,
            tenant_id=tenant_id,
            contractor_id=contractor.id,
            performer_type=PerformerType.STUDENT,
            name=performer_name,
            is_listed=save_performer,
        )
    else:
        if not performer_name:
            raise HTTPException(status_code=422, detail="请选择或填写散户姓名")
        contractor = get_or_create_retail(db, tenant_id, performer_name)
        performer = get_or_create_performer(
            db,
            tenant_id=tenant_id,
            contractor_id=contractor.id,
            performer_type=PerformerType.RETAIL,
            name=contractor.name,
            is_listed=save_performer,
        )

    expected_contractor_type = contractor_type.value
    if contractor.contractor_type != expected_contractor_type:
        raise HTTPException(status_code=422, detail="合作方类型与做单方式不匹配")
    if not contractor.is_active and contractor.id != allow_inactive_contractor_id:
        raise HTTPException(status_code=422, detail="所选合作方已停用")
    if not performer.is_active and performer.id != allow_inactive_performer_id:
        raise HTTPException(status_code=422, detail="实际做单人已停用")
    if save_performer and not performer.is_listed:
        performer.is_listed = True
    return contractor, performer