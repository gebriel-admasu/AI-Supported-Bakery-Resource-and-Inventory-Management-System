from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_user, require_role
from app.core.constants import RoleEnum
from app.models.store import Store
from app.models.user import User
from app.schemas.store import StoreCreate, StoreResponse, StoreUpdate

router = APIRouter()


@router.get("/", response_model=List[StoreResponse])
async def list_stores(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Store).order_by(Store.created_at.desc()).all()


@router.post("/", response_model=StoreResponse, status_code=status.HTTP_201_CREATED)
async def create_store(
    body: StoreCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.ADMIN, RoleEnum.OWNER)),
):
    existing = db.query(Store).filter(Store.name == body.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A store with this name already exists",
        )
    store = Store(name=body.name, location=body.location)
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


@router.put("/{store_id}", response_model=StoreResponse)
async def update_store(
    store_id: UUID,
    body: StoreUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.ADMIN, RoleEnum.OWNER)),
):
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")

    update_data = body.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != store.name:
        other = (
            db.query(Store)
            .filter(Store.name == update_data["name"], Store.id != store_id)
            .first()
        )
        if other:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A store with this name already exists",
            )
    for field, value in update_data.items():
        setattr(store, field, value)
    db.commit()
    db.refresh(store)
    return store
