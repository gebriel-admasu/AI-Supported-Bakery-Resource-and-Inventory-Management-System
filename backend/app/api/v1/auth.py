from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.schemas.user import TokenResponse
from app.services.audit_service import log_action

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == form_data.username).first()
    client_ip = request.client.host if request.client else None

    if not user or not verify_password(form_data.password, user.password_hash):
        log_action(
            db,
            user_id=user.id if user else None,
            action="login_failed",
            resource="auth",
            details=f"Failed login attempt for username: {form_data.username}",
            ip_address=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        log_action(
            db,
            user_id=user.id,
            action="login_blocked",
            resource="auth",
            details="Login blocked: account deactivated",
            ip_address=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role.value}
    )
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    log_action(
        db,
        user_id=user.id,
        action="login_success",
        resource="auth",
        details=f"User {user.username} logged in",
        ip_address=client_ip,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        role=user.role.value,
        username=user.username,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    payload = decode_token(refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role.value}
    )
    new_refresh = create_refresh_token(data={"sub": str(user.id)})
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        token_type="bearer",
        role=user.role.value,
        username=user.username,
    )
