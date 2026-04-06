from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import require_role
from app.core.constants import RoleEnum, WastageReason
from app.models.wastage import WastageRecord
from app.models.product import Product
from app.models.store import Store
from app.models.user import User
from app.schemas.wastage import WastageCreate, WastageResponse

router = APIRouter()


def _wastage_response(db: Session, record: WastageRecord) -> dict:
    store = db.query(Store).filter(Store.id == record.store_id).first()
    product = db.query(Product).filter(Product.id == record.product_id).first()
    return {
        "id": record.id,
        "store_id": record.store_id,
        "store_name": store.name if store else None,
        "product_id": record.product_id,
        "product_name": product.name if product else None,
        "date": record.date,
        "quantity": record.quantity,
        "reason": record.reason.value if record.reason else record.reason,
        "notes": record.notes,
        "recorded_by": record.recorded_by,
        "created_at": record.created_at,
    }


@router.get("/", response_model=List[WastageResponse])
async def list_wastage(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    store_id: Optional[UUID] = None,
    product_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER, RoleEnum.STORE_MANAGER)
    ),
):
    query = db.query(WastageRecord)
    if store_id:
        query = query.filter(WastageRecord.store_id == store_id)
    if product_id:
        query = query.filter(WastageRecord.product_id == product_id)
    records = (
        query.order_by(WastageRecord.date.desc(), WastageRecord.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_wastage_response(db, r) for r in records]


@router.post("/", response_model=WastageResponse, status_code=status.HTTP_201_CREATED)
async def create_wastage(
    body: WastageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER, RoleEnum.STORE_MANAGER)
    ),
):
    store = db.query(Store).filter(Store.id == body.store_id, Store.is_active == True).first()
    if not store:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active store not found")

    product = db.query(Product).filter(Product.id == body.product_id, Product.is_active == True).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active product not found")

    try:
        WastageReason(body.reason)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid reason: {body.reason}. Must be one of: {[r.value for r in WastageReason]}",
        )

    record = WastageRecord(
        store_id=body.store_id,
        product_id=body.product_id,
        date=body.date,
        quantity=body.quantity,
        reason=WastageReason(body.reason),
        notes=body.notes,
        recorded_by=current_user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _wastage_response(db, record)
