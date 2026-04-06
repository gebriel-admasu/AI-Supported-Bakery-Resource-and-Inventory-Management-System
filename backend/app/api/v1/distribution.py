from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import require_role
from app.core.constants import DistributionStatus, RoleEnum
from app.models.distribution import Distribution, DistributionItem
from app.models.product import Product
from app.models.store import Store
from app.models.user import User
from app.schemas.distribution import (
    DistributionCreate,
    DistributionItemReceive,
    DistributionItemResponse,
    DistributionResponse,
)

router = APIRouter()


def _dist_response(db: Session, dist: Distribution) -> dict:
    store = db.query(Store).filter(Store.id == dist.store_id).first()
    items_rows = (
        db.query(DistributionItem, Product.name)
        .outerjoin(Product, DistributionItem.product_id == Product.id)
        .filter(DistributionItem.distribution_id == dist.id)
        .all()
    )
    items = [
        DistributionItemResponse(
            id=item.id,
            product_id=item.product_id,
            product_name=prod_name,
            quantity_sent=item.quantity_sent,
            quantity_received=item.quantity_received,
        )
        for item, prod_name in items_rows
    ]
    return {
        "id": dist.id,
        "store_id": dist.store_id,
        "store_name": store.name if store else None,
        "dispatch_date": dist.dispatch_date,
        "status": dist.status.value if dist.status else "dispatched",
        "dispatched_by": dist.dispatched_by,
        "received_by": dist.received_by,
        "is_locked": dist.is_locked,
        "items": items,
        "created_at": dist.created_at,
        "updated_at": dist.updated_at,
    }


@router.get("/", response_model=List[DistributionResponse])
async def list_distributions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    store_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER, RoleEnum.STORE_MANAGER)
    ),
):
    query = db.query(Distribution)
    if store_id:
        query = query.filter(Distribution.store_id == store_id)
    if status_filter:
        try:
            ds = DistributionStatus(status_filter)
            query = query.filter(Distribution.status == ds)
        except ValueError:
            pass
    rows = (
        query.order_by(Distribution.dispatch_date.desc(), Distribution.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_dist_response(db, d) for d in rows]


@router.get("/{dist_id}", response_model=DistributionResponse)
async def get_distribution(
    dist_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER, RoleEnum.STORE_MANAGER)
    ),
):
    dist = db.query(Distribution).filter(Distribution.id == dist_id).first()
    if not dist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Distribution not found")
    return _dist_response(db, dist)


@router.post("/", response_model=DistributionResponse, status_code=status.HTTP_201_CREATED)
async def create_distribution(
    body: DistributionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    store = db.query(Store).filter(Store.id == body.store_id, Store.is_active == True).first()
    if not store:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active store not found")

    if not body.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one item is required")

    for item in body.items:
        prod = db.query(Product).filter(Product.id == item.product_id, Product.is_active == True).first()
        if not prod:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Active product {item.product_id} not found",
            )

    dist = Distribution(
        store_id=body.store_id,
        dispatch_date=body.dispatch_date,
        status=DistributionStatus.DISPATCHED,
        dispatched_by=current_user.id,
    )
    db.add(dist)
    db.flush()

    for item in body.items:
        di = DistributionItem(
            distribution_id=dist.id,
            product_id=item.product_id,
            quantity_sent=item.quantity_sent,
        )
        db.add(di)

    db.commit()
    db.refresh(dist)
    return _dist_response(db, dist)


@router.put("/{dist_id}/status", response_model=DistributionResponse)
async def update_distribution_status(
    dist_id: UUID,
    new_status: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER, RoleEnum.STORE_MANAGER)
    ),
):
    dist = db.query(Distribution).filter(Distribution.id == dist_id).first()
    if not dist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Distribution not found")

    if dist.is_locked:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Distribution is locked")

    try:
        target = DistributionStatus(new_status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {new_status}",
        )

    old = dist.status
    valid_transitions = {
        DistributionStatus.DISPATCHED: [DistributionStatus.IN_TRANSIT],
        DistributionStatus.IN_TRANSIT: [DistributionStatus.RECEIVED],
        DistributionStatus.RECEIVED: [DistributionStatus.CONFIRMED],
    }

    if target not in valid_transitions.get(old, []):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from {old.value} to {target.value}",
        )

    dist.status = target

    if target == DistributionStatus.RECEIVED:
        dist.received_by = current_user.id
    elif target == DistributionStatus.CONFIRMED:
        dist.is_locked = True

    db.commit()
    db.refresh(dist)
    return _dist_response(db, dist)


@router.put("/{dist_id}/receive", response_model=DistributionResponse)
async def receive_items(
    dist_id: UUID,
    items: List[DistributionItemReceive],
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.STORE_MANAGER)
    ),
):
    dist = db.query(Distribution).filter(Distribution.id == dist_id).first()
    if not dist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Distribution not found")

    if dist.status not in (DistributionStatus.RECEIVED, DistributionStatus.IN_TRANSIT):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only record received quantities when status is in_transit or received",
        )

    for payload in items:
        di = db.query(DistributionItem).filter(
            DistributionItem.id == payload.item_id,
            DistributionItem.distribution_id == dist.id,
        ).first()
        if not di:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Distribution item {payload.item_id} not found",
            )
        di.quantity_received = payload.quantity_received

    if dist.status == DistributionStatus.IN_TRANSIT:
        dist.status = DistributionStatus.RECEIVED
        dist.received_by = current_user.id

    db.commit()
    db.refresh(dist)
    return _dist_response(db, dist)
