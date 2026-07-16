from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.modules.iam.audit import record_audit
from app.modules.iam.models import Member, MemberRole, RefreshSession, Tenant, User
from app.modules.iam.schemas import AuthOutput, LoginInput, RegisterInput


def _issue_tokens(db: Session, *, user_id: int, tenant_id: int, role: str) -> tuple[AuthOutput, str]:
    access = create_access_token(user_id=user_id, tenant_id=tenant_id, role=role)
    raw_refresh, refresh_hash, expires_at = create_refresh_token()
    db.add(
        RefreshSession(
            tenant_id=tenant_id,
            user_id=user_id,
            token_hash=refresh_hash,
            expires_at=expires_at,
        )
    )
    return AuthOutput(access_token=access, expires_in=30 * 60), raw_refresh


def register(db: Session, data: RegisterInput) -> tuple[AuthOutput, str]:
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已注册")

    tenant = Tenant(name=data.tenant_name)
    user = User(email=email, name=data.name, password_hash=hash_password(data.password))
    db.add_all([tenant, user])
    db.flush()
    member = Member(tenant_id=tenant.id, user_id=user.id, role=MemberRole.OWNER.value)
    db.add(member)
    auth, refresh = _issue_tokens(
        db, user_id=user.id, tenant_id=tenant.id, role=MemberRole.OWNER.value
    )
    record_audit(
        db,
        tenant_id=tenant.id,
        user_id=user.id,
        action="tenant.created",
        resource_type="tenant",
        resource_id=tenant.id,
    )
    db.commit()
    return auth, refresh


def login(db: Session, data: LoginInput) -> tuple[AuthOutput, str]:
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not user.is_active or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")

    query = select(Member).where(Member.user_id == user.id, Member.is_active.is_(True))
    if data.tenant_id is not None:
        query = query.where(Member.tenant_id == data.tenant_id)
    member = db.scalars(query.order_by(Member.id)).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有可用账套")

    auth, refresh = _issue_tokens(
        db, user_id=user.id, tenant_id=member.tenant_id, role=member.role
    )
    record_audit(
        db,
        tenant_id=member.tenant_id,
        user_id=user.id,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
    )
    db.commit()
    return auth, refresh


def rotate_refresh_token(db: Session, raw_token: str) -> tuple[AuthOutput, str]:
    session = db.scalar(
        select(RefreshSession).where(
            RefreshSession.token_hash == hash_token(raw_token),
            RefreshSession.revoked_at.is_(None),
        )
    )
    now = datetime.now(timezone.utc)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新凭证无效")
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新凭证已过期")

    member = db.scalar(
        select(Member).where(
            Member.user_id == session.user_id,
            Member.tenant_id == session.tenant_id,
            Member.is_active.is_(True),
        )
    )
    if not member:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="成员身份已停用")

    session.revoked_at = now
    auth, refresh = _issue_tokens(
        db, user_id=session.user_id, tenant_id=session.tenant_id, role=member.role
    )
    db.commit()
    return auth, refresh


def revoke_refresh_token(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    session = db.scalar(select(RefreshSession).where(RefreshSession.token_hash == hash_token(raw_token)))
    if session and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()