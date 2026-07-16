from dataclasses import dataclass
from typing import Annotated, Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.modules.iam.models import Member, User

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class TenantContext:
    user_id: int
    tenant_id: int
    role: str
    user_name: str
    email: str


def get_current_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantContext:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
        tenant_id = int(payload["tid"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效") from exc

    row = db.execute(
        select(User, Member).join(Member, Member.user_id == User.id).where(
            User.id == user_id,
            User.is_active.is_(True),
            Member.tenant_id == tenant_id,
            Member.is_active.is_(True),
        )
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用")
    user, member = row
    return TenantContext(user.id, tenant_id, member.role, user.name, user.email)


CurrentContext = Annotated[TenantContext, Depends(get_current_context)]
DbSession = Annotated[Session, Depends(get_db)]


def require_roles(*roles: str) -> Callable:
    def dependency(context: CurrentContext) -> TenantContext:
        if context.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无此操作权限")
        return context

    return dependency