from typing import Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    action: str
    resource: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    timestamp: datetime

    model_config = {"from_attributes": True}
