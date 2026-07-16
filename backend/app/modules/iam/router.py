from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.modules.iam.audit import record_audit
from app.modules.iam.dependencies import CurrentContext, DbSession, require_roles
from app.modules.iam.models import AuditLog, Member, MemberRole, Tenant, User
from app.modules.iam.schemas import (
    AuditOutput,
    AuthOutput,
    LoginInput,
    MeOutput,
    MemberCreate,
    MemberOutput,
    MemberUpdate,
    RegisterInput,
    TenantBrief,
)
from app.modules.iam.service import login, register, revoke_refresh_token, rotate_refresh_token

router = APIRouter(prefix="/auth", tags=["认证与成员"])
settings = get_settings()


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "refresh_token",
        token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        max_age=settings.refresh_token_days * 86400,
        path=f"{settings.api_prefix}/auth",
    )


@router.post("/register", response_model=AuthOutput, status_code=status.HTTP_201_CREATED)
def register_endpoint(data: RegisterInput, response: Response, db: DbSession) -> AuthOutput:
    auth, refresh = register(db, data)
    _set_refresh_cookie(response, refresh)
    return auth


@router.post("/login", response_model=AuthOutput)
def login_endpoint(data: LoginInput, response: Response, db: DbSession) -> AuthOutput:
    auth, refresh = login(db, data)
    _set_refresh_cookie(response, refresh)
    return auth


@router.post("/refresh", response_model=AuthOutput)
def refresh_endpoint(
    response: Response,
    db: DbSession,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> AuthOutput:
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少刷新凭证")
    auth, refresh = rotate_refresh_token(db, refresh_token)
    _set_refresh_cookie(response, refresh)
    return auth


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_endpoint(
    response: Response,
    db: DbSession,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> None:
    revoke_refresh_token(db, refresh_token)
    response.delete_cookie("refresh_token", path=f"{settings.api_prefix}/auth")


@router.get("/me", response_model=MeOutput)
def me(context: CurrentContext, db: DbSession) -> MeOutput:
    tenant = db.get(Tenant, context.tenant_id)
    memberships = db.execute(
        select(Member, Tenant)
        .join(Tenant, Tenant.id == Member.tenant_id)
        .where(Member.user_id == context.user_id, Member.is_active.is_(True))
    ).all()
    return MeOutput(
        user_id=context.user_id,
        name=context.user_name,
        email=context.email,
        tenant_id=context.tenant_id,
        tenant_name=tenant.name if tenant else "",
        role=context.role,
        tenants=[TenantBrief(id=t.id, name=t.name, role=m.role) for m, t in memberships],
    )


@router.get("/members", response_model=list[MemberOutput])
def list_members(context: CurrentContext, db: DbSession) -> list[MemberOutput]:
    rows = db.execute(
        select(Member, User)
        .join(User, User.id == Member.user_id)
        .where(Member.tenant_id == context.tenant_id)
        .order_by(Member.id)
    ).all()
    return [
        MemberOutput(
            id=member.id,
            user_id=user.id,
            name=user.name,
            email=user.email,
            role=member.role,
            is_active=member.is_active,
            created_at=member.created_at,
        )
        for member, user in rows
    ]


@router.post("/members", response_model=MemberOutput, status_code=status.HTTP_201_CREATED)
def create_member(
    data: MemberCreate,
    db: DbSession,
    context=Depends(require_roles(MemberRole.OWNER.value)),
) -> MemberOutput:
    email = data.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(email=email, name=data.name, password_hash=hash_password(data.password))
        db.add(user)
        db.flush()
    if db.scalar(
        select(Member).where(Member.tenant_id == context.tenant_id, Member.user_id == user.id)
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该用户已在当前账套")
    member = Member(
        tenant_id=context.tenant_id,
        user_id=user.id,
        role=data.role.value,
    )
    db.add(member)
    db.flush()
    record_audit(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action="member.created",
        resource_type="member",
        resource_id=member.id,
        payload={"email": email, "role": data.role.value},
    )
    db.commit()
    db.refresh(member)
    return MemberOutput(
        id=member.id,
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=member.role,
        is_active=member.is_active,
        created_at=member.created_at,
    )


@router.patch("/members/{member_id}", response_model=MemberOutput)
def update_member(
    member_id: int,
    data: MemberUpdate,
    db: DbSession,
    context=Depends(require_roles(MemberRole.OWNER.value)),
) -> MemberOutput:
    row = db.execute(
        select(Member, User)
        .join(User, User.id == Member.user_id)
        .where(Member.id == member_id, Member.tenant_id == context.tenant_id)
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成员不存在")
    member, user = row
    if member.user_id == context.user_id and data.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能停用自己")
    if data.role is not None:
        member.role = data.role.value
    if data.is_active is not None:
        member.is_active = data.is_active
    record_audit(
        db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action="member.updated",
        resource_type="member",
        resource_id=member.id,
        payload=data.model_dump(exclude_none=True, mode="json"),
    )
    db.commit()
    db.refresh(member)
    return MemberOutput(
        id=member.id,
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=member.role,
        is_active=member.is_active,
        created_at=member.created_at,
    )


@router.get("/audit-logs", response_model=list[AuditOutput])
def list_audit_logs(
    db: DbSession,
    limit: int = 100,
    context=Depends(require_roles(MemberRole.OWNER.value)),
) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.tenant_id == context.tenant_id)
            .order_by(AuditLog.id.desc())
            .limit(min(limit, 500))
        )
    )