from sqlalchemy.orm import Session

from app.modules.iam.models import AuditLog


def record_audit(
    db: Session,
    *,
    tenant_id: int,
    user_id: int | None,
    action: str,
    resource_type: str,
    resource_id: int | str | None = None,
    payload: dict | None = None,
) -> AuditLog:
    log = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        payload=payload,
    )
    db.add(log)
    return log