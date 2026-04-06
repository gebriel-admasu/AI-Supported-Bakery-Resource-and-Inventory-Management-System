from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_user, require_role
from app.core.constants import RoleEnum
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services.audit_service import log_action

router = APIRouter()


@router.get("/", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    role: Optional[RoleEnum] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.ADMIN, RoleEnum.OWNER)),
):
    query = db.query(User)
    if role is not None:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    return query.order_by(User.created_at.desc()).offset(skip).limit(limit).all()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.ADMIN)),
):
    existing = db.query(User).filter(
        (User.username == user_in.username) | (User.email == user_in.email)
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already exists",
        )
    user = User(
        username=user_in.username,
        email=user_in.email,
        password_hash=hash_password(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role,
        store_id=user_in.store_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_action(
        db,
        user_id=current_user.id,
        action="user_created",
        resource="users",
        resource_id=str(user.id),
        details=f"Created user {user.username} with role {user.role.value}",
        ip_address=request.client.host if request.client else None,
    )
    return user


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.ADMIN, RoleEnum.OWNER)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_in: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.ADMIN)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user_in.model_dump(exclude_unset=True)
    changed_fields = []

    if "password" in update_data:
        update_data["password_hash"] = hash_password(update_data.pop("password"))
        changed_fields.append("password")

    for field, value in update_data.items():
        old_value = getattr(user, field, None)
        if old_value != value:
            changed_fields.append(field)
        setattr(user, field, value)

    db.commit()
    db.refresh(user)

    if changed_fields:
        log_action(
            db,
            user_id=current_user.id,
            action="user_updated",
            resource="users",
            resource_id=str(user.id),
            details=f"Updated fields: {', '.join(changed_fields)}",
            ip_address=request.client.host if request.client else None,
        )
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.ADMIN)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account",
        )
    user.is_active = False
    db.commit()

    log_action(
        db,
        user_id=current_user.id,
        action="user_deactivated",
        resource="users",
        resource_id=str(user.id),
        details=f"Deactivated user {user.username}",
        ip_address=request.client.host if request.client else None,
    )


@router.post("/{user_id}/reactivate", response_model=UserResponse)
async def reactivate_user(
    user_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.ADMIN)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    db.commit()
    db.refresh(user)

    log_action(
        db,
        user_id=current_user.id,
        action="user_reactivated",
        resource="users",
        resource_id=str(user.id),
        details=f"Reactivated user {user.username}",
        ip_address=request.client.host if request.client else None,
    )
    return user
