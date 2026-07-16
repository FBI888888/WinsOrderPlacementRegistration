from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.partners.models import (
    Contractor,
    ContractorRate,
    ContractorType,
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