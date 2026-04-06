from uuid import UUID
from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def log_action(
    db: Session,
    user_id: Optional[UUID],
    action: str,
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
