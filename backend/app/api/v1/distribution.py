from typing import Dict, List, Optional
from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import require_role
from app.core.constants import BatchStatus, DistributionStatus, DiscrepancyStatus, RoleEnum, WastageReason, WastageSourceType
from app.models.distribution import Distribution, DistributionItem
from app.models.production import ProductionBatch
from app.models.product import Product
from app.models.store import Store
from app.models.user import User
from app.models.wastage import WastageRecord
from app.services.recipe_costing import resolve_recipe_unit_cost
from app.schemas.distribution import (
    DistributionCreate,
    DistributionDiscrepancyDecision,
    DistributionItemReceive,
    DistributionItemResponse,
    DistributionResponse,
)

router = APIRouter()


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _resolve_product_unit_cost(db: Session, product_id: UUID) -> tuple[Decimal, str, bool]:
    recipe_id_row = db.query(Product.recipe_id).filter(Product.id == product_id).first()
    if not recipe_id_row:
        return Decimal("0"), "fallback_zero", True
    unit_cost = resolve_recipe_unit_cost(db, recipe_id_row[0])
    if unit_cost <= 0:
        return Decimal("0"), "fallback_zero", True
    return unit_cost, "product_recipe_cost", False


def _resolve_product_unit_price(db: Session, product_id: UUID) -> Decimal:
    row = (
        db.query(Product.sale_price)
        .filter(Product.id == product_id)
        .first()
    )
    if not row or row[0] is None:
        return Decimal("0")
    return _to_decimal(row[0])


def _dist_response(db: Session, dist: Distribution) -> dict:
    store = db.query(Store).filter(Store.id == dist.store_id).first()
    delivery_person = (
        db.query(User).filter(User.id == dist.delivery_person_id).first()
        if dist.delivery_person_id
        else None
    )
    reviewer = db.query(User).filter(User.id == dist.reviewed_by).first() if dist.reviewed_by else None
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
            discrepancy_qty=item.discrepancy_qty,
            discrepancy_reason=item.discrepancy_reason,
            discrepancy_note=item.discrepancy_note,
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
        "delivery_person_id": dist.delivery_person_id,
        "delivery_person_name": delivery_person.full_name if delivery_person else None,
        "driver_count_confirmed": dist.driver_count_confirmed,
        "driver_count_confirmed_by": dist.driver_count_confirmed_by,
        "driver_count_confirmed_at": dist.driver_count_confirmed_at,
        "received_by": dist.received_by,
        "received_at": dist.received_at,
        "has_discrepancy": dist.has_discrepancy,
        "discrepancy_status": dist.discrepancy_status.value if dist.discrepancy_status else "none",
        "reviewed_by": dist.reviewed_by,
        "reviewed_by_name": reviewer.full_name if reviewer else None,
        "reviewed_at": dist.reviewed_at,
        "review_note": dist.review_note,
        "is_locked": dist.is_locked,
        "items": items,
        "created_at": dist.created_at,
        "updated_at": dist.updated_at,
    }


def _check_distribution_access(current_user: User, dist: Distribution) -> None:
    if current_user.role == RoleEnum.DELIVERY_STAFF and dist.delivery_person_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    if (
        current_user.role == RoleEnum.STORE_MANAGER
        and current_user.store_id is not None
        and dist.store_id != current_user.store_id
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")


def _map_discrepancy_reason(reason: Optional[str]) -> WastageReason:
    if not reason:
        return WastageReason.OTHER
    reason_text = reason.strip().lower()
    if "damage" in reason_text:
        return WastageReason.DAMAGE
    if "spoil" in reason_text:
        return WastageReason.SPOILAGE
    if "expir" in reason_text:
        return WastageReason.EXPIRY
    return WastageReason.OTHER


def _is_count_error_reason(reason: Optional[str]) -> bool:
    if not reason:
        return False
    reason_text = reason.strip().lower()
    return (
        "count error" in reason_text
        or "counting error" in reason_text
        or "miscount" in reason_text
        or "count mismatch" in reason_text
    )


@router.get("/", response_model=List[DistributionResponse])
async def list_distributions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    store_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            RoleEnum.OWNER,
            RoleEnum.PRODUCTION_MANAGER,
            RoleEnum.STORE_MANAGER,
            RoleEnum.DELIVERY_STAFF,
        )
    ),
):
    query = db.query(Distribution)
    if current_user.role == RoleEnum.DELIVERY_STAFF:
        query = query.filter(Distribution.delivery_person_id == current_user.id)
    elif current_user.role == RoleEnum.STORE_MANAGER and current_user.store_id is not None:
        query = query.filter(Distribution.store_id == current_user.store_id)
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
        require_role(
            RoleEnum.OWNER,
            RoleEnum.PRODUCTION_MANAGER,
            RoleEnum.STORE_MANAGER,
            RoleEnum.DELIVERY_STAFF,
        )
    ),
):
    dist = db.query(Distribution).filter(Distribution.id == dist_id).first()
    if not dist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Distribution not found")
    _check_distribution_access(current_user, dist)
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

    delivery_person = None
    if body.delivery_person_id:
        delivery_person = (
            db.query(User)
            .filter(
                User.id == body.delivery_person_id,
                User.role == RoleEnum.DELIVERY_STAFF,
                User.is_active == True,
            )
            .first()
        )
        if not delivery_person:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assigned delivery person not found or inactive",
            )

    requested_by_product: Dict[UUID, int] = {}
    for item in body.items:
        if item.quantity_sent <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dispatch quantity must be greater than zero",
            )

        prod = db.query(Product).filter(Product.id == item.product_id, Product.is_active == True).first()
        if not prod:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Active product {item.product_id} not found",
            )
        requested_by_product[item.product_id] = requested_by_product.get(item.product_id, 0) + item.quantity_sent

    for product_id, requested_qty in requested_by_product.items():
        produced_qty = (
            db.query(func.coalesce(func.sum(ProductionBatch.actual_yield), 0))
            .filter(
                ProductionBatch.product_id == product_id,
                ProductionBatch.status == BatchStatus.COMPLETED,
            )
            .scalar()
        )
        dispatched_qty = (
            db.query(func.coalesce(func.sum(DistributionItem.quantity_sent), 0))
            .filter(DistributionItem.product_id == product_id)
            .scalar()
        )
        available_qty = int(produced_qty or 0) - int(dispatched_qty or 0)
        if available_qty <= 0:
            product_name = (
                db.query(Product.name).filter(Product.id == product_id).scalar()
                or str(product_id)
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Dispatch not allowed: no available produced stock for '{product_name}'",
            )
        if requested_qty > available_qty:
            product_name = (
                db.query(Product.name).filter(Product.id == product_id).scalar()
                or str(product_id)
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Dispatch not allowed: requested {requested_qty} of '{product_name}' "
                    f"but only {available_qty} available from produced stock"
                ),
            )

    dist = Distribution(
        store_id=body.store_id,
        dispatch_date=body.dispatch_date,
        status=DistributionStatus.DISPATCHED,
        dispatched_by=current_user.id,
        delivery_person_id=delivery_person.id if delivery_person else None,
        driver_count_confirmed=False,
        has_discrepancy=False,
        discrepancy_status=DiscrepancyStatus.NONE,
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
        require_role(
            RoleEnum.OWNER,
            RoleEnum.PRODUCTION_MANAGER,
            RoleEnum.STORE_MANAGER,
            RoleEnum.DELIVERY_STAFF,
        )
    ),
):
    dist = db.query(Distribution).filter(Distribution.id == dist_id).first()
    if not dist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Distribution not found")
    _check_distribution_access(current_user, dist)

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
    if old == DistributionStatus.IN_TRANSIT and target == DistributionStatus.RECEIVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use receive endpoint to record quantities before marking as received",
        )

    valid_transitions = {
        DistributionStatus.DISPATCHED: [DistributionStatus.IN_TRANSIT],
        DistributionStatus.RECEIVED: [DistributionStatus.CONFIRMED],
    }

    if target not in valid_transitions.get(old, []):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from {old.value} to {target.value}",
        )

    if target == DistributionStatus.IN_TRANSIT:
        if current_user.role not in (RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    elif target == DistributionStatus.CONFIRMED:
        if current_user.role not in (RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        if dist.has_discrepancy and dist.discrepancy_status != DiscrepancyStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot confirm distribution until discrepancy is approved",
            )

    dist.status = target

    if target == DistributionStatus.IN_TRANSIT:
        dist.driver_count_confirmed = False
        dist.driver_count_confirmed_by = None
        dist.driver_count_confirmed_at = None
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
    _check_distribution_access(current_user, dist)

    if dist.status not in (DistributionStatus.RECEIVED, DistributionStatus.IN_TRANSIT):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only record received quantities when status is in_transit or received",
        )
    if dist.status == DistributionStatus.IN_TRANSIT and not dist.driver_count_confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Delivery staff must confirm loaded counts before store receipt",
        )

    has_discrepancy = False
    for payload in items:
        if payload.quantity_received < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Received quantities cannot be negative",
            )
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
        discrepancy_qty = di.quantity_sent - payload.quantity_received
        di.discrepancy_qty = discrepancy_qty
        if discrepancy_qty != 0:
            if not payload.discrepancy_reason or not payload.discrepancy_reason.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Discrepancy reason is required when sent and received differ",
                )
            if dist.driver_count_confirmed and _is_count_error_reason(payload.discrepancy_reason):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Count error is not allowed after driver count confirmation",
                )
            di.discrepancy_reason = payload.discrepancy_reason.strip()
            di.discrepancy_note = payload.discrepancy_note.strip() if payload.discrepancy_note else None
            has_discrepancy = True
        else:
            di.discrepancy_reason = None
            di.discrepancy_note = None

    dist.status = DistributionStatus.RECEIVED
    dist.received_by = current_user.id
    dist.received_at = datetime.now(timezone.utc)
    dist.has_discrepancy = has_discrepancy
    dist.discrepancy_status = (
        DiscrepancyStatus.PENDING_APPROVAL if has_discrepancy else DiscrepancyStatus.NONE
    )
    if not has_discrepancy:
        dist.reviewed_by = None
        dist.reviewed_at = None
        dist.review_note = None

    db.commit()
    db.refresh(dist)
    return _dist_response(db, dist)


@router.put("/{dist_id}/discrepancy/approve", response_model=DistributionResponse)
async def approve_discrepancy(
    dist_id: UUID,
    body: DistributionDiscrepancyDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    dist = db.query(Distribution).filter(Distribution.id == dist_id).first()
    if not dist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Distribution not found")
    if not dist.has_discrepancy:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No discrepancy to approve",
        )
    if dist.discrepancy_status != DiscrepancyStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Discrepancy is not pending approval",
        )

    dist.discrepancy_status = DiscrepancyStatus.APPROVED
    dist.reviewed_by = current_user.id
    dist.reviewed_at = datetime.now(timezone.utc)
    dist.review_note = body.review_note.strip() if body.review_note else None

    items = db.query(DistributionItem).filter(DistributionItem.distribution_id == dist.id).all()
    for item in items:
        if item.discrepancy_qty <= 0:
            continue
        if _is_count_error_reason(item.discrepancy_reason):
            continue
        unit_price_snapshot = _resolve_product_unit_price(db, item.product_id)
        unit_cost_snapshot, cost_source, is_estimated_cost = _resolve_product_unit_cost(db, item.product_id)
        db.add(
            WastageRecord(
                source_type=WastageSourceType.STORE,
                store_id=dist.store_id,
                product_id=item.product_id,
                date=dist.dispatch_date,
                quantity=item.discrepancy_qty,
                unit_price_snapshot=unit_price_snapshot,
                total_price_snapshot=unit_price_snapshot * Decimal(item.discrepancy_qty),
                unit_cost_snapshot=unit_cost_snapshot,
                total_cost_snapshot=unit_cost_snapshot * Decimal(item.discrepancy_qty),
                cost_source=cost_source,
                is_estimated_cost=is_estimated_cost,
                reason=_map_discrepancy_reason(item.discrepancy_reason),
                notes=item.discrepancy_note or f"Auto-created from distribution discrepancy {dist.id}",
                recorded_by=current_user.id,
            )
        )

    db.commit()
    db.refresh(dist)
    return _dist_response(db, dist)


@router.put("/{dist_id}/driver-confirm-count", response_model=DistributionResponse)
async def confirm_driver_count(
    dist_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.DELIVERY_STAFF)
    ),
):
    dist = db.query(Distribution).filter(Distribution.id == dist_id).first()
    if not dist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Distribution not found")
    _check_distribution_access(current_user, dist)
    if dist.status != DistributionStatus.IN_TRANSIT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Count confirmation is only allowed when status is in_transit",
        )
    dist.driver_count_confirmed = True
    dist.driver_count_confirmed_by = current_user.id
    dist.driver_count_confirmed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(dist)
    return _dist_response(db, dist)


@router.put("/{dist_id}/discrepancy/reject", response_model=DistributionResponse)
async def reject_discrepancy(
    dist_id: UUID,
    body: DistributionDiscrepancyDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.PRODUCTION_MANAGER)
    ),
):
    dist = db.query(Distribution).filter(Distribution.id == dist_id).first()
    if not dist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Distribution not found")
    if not dist.has_discrepancy:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No discrepancy to reject",
        )
    if dist.discrepancy_status != DiscrepancyStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Discrepancy is not pending approval",
        )

    dist.discrepancy_status = DiscrepancyStatus.REJECTED
    dist.reviewed_by = current_user.id
    dist.reviewed_at = datetime.now(timezone.utc)
    dist.review_note = body.review_note.strip() if body.review_note else None
    db.commit()
    db.refresh(dist)
    return _dist_response(db, dist)
