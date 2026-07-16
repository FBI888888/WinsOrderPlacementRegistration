from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.modules.funds.models import LedgerAccount, LedgerEntryType
from app.modules.funds.service import append_entry
from app.modules.iam.models import Member, MemberRole, Tenant, User
from app.modules.orders.models import OrderStatus
from app.modules.orders.schemas import OrderCreate
from app.modules.orders.service import create_order
from app.modules.partners.models import (
    Contractor,
    ContractorRate,
    ContractorType,
    SettlementBasis,
    Source,
    SourceRate,
)

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo12345"


def main() -> None:
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == DEMO_EMAIL)):
            print("Demo data already exists")
            return
        tenant = Tenant(name="演示做单工作室")
        user = User(name="演示负责人", email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD))
        db.add_all([tenant, user])
        db.flush()
        db.add(Member(tenant_id=tenant.id, user_id=user.id, role=MemberRole.OWNER.value))

        source = Source(
            tenant_id=tenant.id,
            name="演示渠道",
            default_basis=SettlementBasis.ORDER_AMOUNT.value,
            default_discount=Decimal("0.9000"),
        )
        leader = Contractor(
            tenant_id=tenant.id,
            name="演示学生组长",
            normalized_name="演示学生组长",
            contractor_type=ContractorType.LEADER.value,
            default_commission=Decimal("5.00"),
        )
        db.add_all([source, leader])
        db.flush()
        db.add_all([
            SourceRate(
                tenant_id=tenant.id,
                source_id=source.id,
                effective_date=date.today(),
                settlement_basis=SettlementBasis.ORDER_AMOUNT.value,
                discount=Decimal("0.9000"),
            ),
            ContractorRate(
                tenant_id=tenant.id,
                contractor_id=leader.id,
                effective_date=date.today(),
                commission_per_order=Decimal("5.00"),
            ),
        ])
        append_entry(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            business_date=date.today(),
            account=LedgerAccount.ADVANCE,
            entry_type=LedgerEntryType.ADVANCE_TOPUP,
            amount=Decimal("2000.00"),
            contractor_id=leader.id,
            note="演示初始垫资",
        )
        db.commit()

        create_order(
            db,
            tenant_id=tenant.id,
            user_id=user.id,
            data=OrderCreate(
                business_date=date.today(),
                source_id=source.id,
                contractor_type=ContractorType.LEADER,
                contractor_id=leader.id,
                performer_name="演示学生",
                order_amount=Decimal("100.00"),
                coupon_amount=Decimal("20.00"),
                actual_paid=Decimal("70.00"),
                status=OrderStatus.SUCCESS,
            ),
        )
        print(f"Demo login: {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()