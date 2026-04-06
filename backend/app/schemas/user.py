from typing import Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.core.constants import RoleEnum


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: str
    role: RoleEnum = RoleEnum.STORE_MANAGER
    store_id: Optional[UUID] = None


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[RoleEnum] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
    store_id: Optional[UUID] = None


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    full_name: str
    role: RoleEnum
    is_active: bool
    store_id: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    role: str
    username: str
