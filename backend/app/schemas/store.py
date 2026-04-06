from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


class StoreCreate(BaseModel):
    name: str
    location: Optional[str] = None


class StoreUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    is_active: Optional[bool] = None


class StoreResponse(BaseModel):
    id: UUID
    name: str
    location: Optional[str] = None
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}
