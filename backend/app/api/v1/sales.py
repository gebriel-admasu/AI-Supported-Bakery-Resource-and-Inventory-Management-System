from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.core.constants import RoleEnum, WastageReason, WastageSourceType
from app.database import get_db
from app.models.product import Product
from app.models.sales import SalesRecord
from app.models.store import Store
from app.models.user import User
from app.models.wastage import WastageRecord
from app.models.distribution import Distribution, DistributionItem
from app.core.constants import DistributionStatus
from app.schemas.sales import (
    SalesClosePayload,
    SalesOpenPayload,
    SalesRecordResponse,
    SalesSellPayload,
    SalesUpdatePayload,
)

router = APIRouter()
AUTO_WASTAGE_NOTE_PREFIX = "Auto-created from sales close variance for record "


def _resolve_store_scope(current_user: User, requested_store_id: Optional[UUID]) -> UUID:
    if current_user.role == RoleEnum.STORE_MANAGER:
        if not current_user.store_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Store manager is not assigned to a store",
            )
        if requested_store_id and requested_store_id != current_user.store_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Store manager can only access own store records",
            )
        return current_user.store_id
    if requested_store_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="store_id is required",
        )
    return requested_store_id


def _latest_previous_sales_record(
    db: Session,
    store_id: UUID,
    product_id: UUID,
    target_date: date,
) -> Optional[SalesRecord]:
    return (
        db.query(SalesRecord)
        .filter(
            SalesRecord.store_id == store_id,
            SalesRecord.product_id == product_id,
            SalesRecord.date < target_date,
        )
        .order_by(SalesRecord.date.desc(), SalesRecord.created_at.desc())
        .first()
    )


def _validate_opening_stock_adjustment(
    opening_stock: int,
    previous_record: Optional[SalesRecord],
    notes: Optional[str],
) -> None:
    if not previous_record:
        return
    expected_opening = previous_record.closing_stock
    if opening_stock == expected_opening:
        return
    if not notes or not notes.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Opening stock differs from previous closing stock "
                f"({expected_opening}). Provide adjustment reason in notes."
            ),
        )


def _resolve_opening_stock_for_create(
    current_user: User,
    requested_opening_stock: int,
    previous_record: Optional[SalesRecord],
) -> int:
    if current_user.role != RoleEnum.STORE_MANAGER:
        return requested_opening_stock
    if not previous_record:
        return requested_opening_stock
    expected_opening = previous_record.closing_stock
    if requested_opening_stock != expected_opening:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Opening stock for store manager must equal previous closing stock "
                f"({expected_opening})"
            ),
        )
    return expected_opening


def _enforce_store_manager_today_lock(current_user: User, record_date: date) -> None:
    if current_user.role == RoleEnum.STORE_MANAGER and record_date != date.today():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Store manager can only modify today's sales records",
        )


def _sales_response(db: Session, record: SalesRecord) -> dict:
    store = db.query(Store).filter(Store.id == record.store_id).first()
    product = db.query(Product).filter(Product.id == record.product_id).first()
    today_received_qty = _today_received_qty(db, record.store_id, record.product_id, record.date)
    total_product_qty = record.opening_stock + today_received_qty
    effective_wastage_qty = _manual_store_wastage_qty(db, record) + _auto_wastage_qty(db, record)
    expected_closing = total_product_qty - record.quantity_sold - effective_wastage_qty
    variance_qty = expected_closing - record.closing_stock
    return {
        "id": record.id,
        "store_id": record.store_id,
        "store_name": store.name if store else None,
        "product_id": record.product_id,
        "product_name": product.name if product else None,
        "date": record.date,
        "opening_stock": record.opening_stock,
        "today_received_qty": today_received_qty,
        "total_product_qty": total_product_qty,
        "quantity_sold": record.quantity_sold,
        "closing_stock": record.closing_stock,
        "wastage_qty": effective_wastage_qty,
        "expected_closing": expected_closing,
        "variance_qty": variance_qty,
        "total_amount": float(record.total_amount or 0),
        "is_closed": record.is_closed,
        "closed_at": record.closed_at,
        "notes": record.notes,
        "recorded_by": record.recorded_by,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _today_received_qty(db: Session, store_id: UUID, product_id: UUID, sales_date: date) -> int:
    qty = (
        db.query(func.coalesce(func.sum(DistributionItem.quantity_received), 0))
        .join(Distribution, Distribution.id == DistributionItem.distribution_id)
        .filter(
            Distribution.store_id == store_id,
            DistributionItem.product_id == product_id,
            Distribution.status.in_([DistributionStatus.RECEIVED, DistributionStatus.CONFIRMED]),
            func.coalesce(func.date(Distribution.received_at), Distribution.dispatch_date) == sales_date,
        )
        .scalar()
    )
    return int(qty or 0)


def _auto_wastage_note(record_id: UUID) -> str:
    return f"{AUTO_WASTAGE_NOTE_PREFIX}{record_id}"


def _auto_wastage_records(db: Session, record: SalesRecord) -> List[WastageRecord]:
    return (
        db.query(WastageRecord)
        .filter(
            WastageRecord.source_type == WastageSourceType.STORE,
            WastageRecord.store_id == record.store_id,
            WastageRecord.product_id == record.product_id,
            WastageRecord.date == record.date,
            WastageRecord.reason == WastageReason.OTHER,
            WastageRecord.notes == _auto_wastage_note(record.id),
        )
        .order_by(WastageRecord.created_at.asc())
        .all()
    )


def _auto_wastage_qty(db: Session, record: SalesRecord) -> int:
    rows = _auto_wastage_records(db, record)
    return int(sum(r.quantity for r in rows))


def _manual_store_wastage_qty(db: Session, record: SalesRecord) -> int:
    qty = (
        db.query(func.coalesce(func.sum(WastageRecord.quantity), 0))
        .filter(
            WastageRecord.source_type == WastageSourceType.STORE,
            WastageRecord.store_id == record.store_id,
            WastageRecord.product_id == record.product_id,
            WastageRecord.date == record.date,
            or_(
                WastageRecord.notes.is_(None),
                WastageRecord.notes != _auto_wastage_note(record.id),
            ),
        )
        .scalar()
    )
    return int(qty or 0)


def _sync_auto_wastage(
    db: Session,
    record: SalesRecord,
    wastage_qty: int,
    recorded_by: UUID,
    enabled: bool,
) -> None:
    rows = _auto_wastage_records(db, record)

    if (not enabled) or wastage_qty <= 0:
        for row in rows:
            db.delete(row)
        return

    note = _auto_wastage_note(record.id)
    if rows:
        primary = rows[0]
        primary.quantity = wastage_qty
        primary.notes = note
        primary.recorded_by = recorded_by
        for extra in rows[1:]:
            db.delete(extra)
        return

    db.add(
        WastageRecord(
            source_type=WastageSourceType.STORE,
            store_id=record.store_id,
            product_id=record.product_id,
            date=record.date,
            quantity=wastage_qty,
            reason=WastageReason.OTHER,
            notes=note,
            recorded_by=recorded_by,
        )
    )


@router.get("/records", response_model=List[SalesRecordResponse])
async def list_sales_records(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    store_id: Optional[UUID] = None,
    product_id: Optional[UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    is_closed: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.FINANCE_MANAGER, RoleEnum.STORE_MANAGER)
    ),
):
    query = db.query(SalesRecord)
    if current_user.role == RoleEnum.STORE_MANAGER:
        if not current_user.store_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Store manager has no store assignment")
        query = query.filter(SalesRecord.store_id == current_user.store_id)
    elif store_id:
        query = query.filter(SalesRecord.store_id == store_id)
    if product_id:
        query = query.filter(SalesRecord.product_id == product_id)
    if is_closed is not None:
        query = query.filter(SalesRecord.is_closed == is_closed)
    if date_from:
        query = query.filter(SalesRecord.date >= date_from)
    if date_to:
        query = query.filter(SalesRecord.date <= date_to)
    records = (
        query.order_by(SalesRecord.date.desc(), SalesRecord.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_sales_response(db, record) for record in records]


@router.post("/open", response_model=SalesRecordResponse, status_code=status.HTTP_201_CREATED)
async def open_sales_day(
    body: SalesOpenPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(RoleEnum.OWNER, RoleEnum.STORE_MANAGER)
    ),
):
    resolved_store_id = _resolve_store_scope(current_user, body.store_id)
    if body.opening_stock < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Opening stock cannot be negative")
    store = db.query(Store).filter(Store.id == resolved_store_id, Store.is_active == True).first()
    if not store:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active store not found")
    product = db.query(Product).filter(Product.id == body.product_id, Product.is_active == True).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active product not found")
    previous_record = _latest_previous_sales_record(
        db=db,
        store_id=resolved_store_id,
        product_id=body.product_id,
        target_date=body.date,
    )
    opening_stock_to_use = _resolve_opening_stock_for_create(
        current_user=current_user,
        requested_opening_stock=body.opening_stock,
        previous_record=previous_record,
    )
    if current_user.role != RoleEnum.STORE_MANAGER:
        _validate_opening_stock_adjustment(opening_stock_to_use, previous_record, body.notes)
    existing = db.query(SalesRecord).filter(
        SalesRecord.store_id == resolved_store_id,
        SalesRecord.product_id == body.product_id,
        SalesRecord.date == body.date,
    ).first()
    if existing:
        if existing.is_closed:
            existing.is_closed = False
            existing.closed_at = None
            existing.recorded_by = current_user.id
            _sync_auto_wastage(
                db=db,
                record=existing,
                wastage_qty=0,
                recorded_by=current_user.id,
                enabled=False,
            )
            if existing.quantity_sold == 0:
                existing.opening_stock = opening_stock_to_use
                existing.total_amount = Decimal("0")
            manual_wastage = _manual_store_wastage_qty(db, existing)
            existing.wastage_qty = manual_wastage
            existing_today_received = _today_received_qty(
                db, existing.store_id, existing.product_id, existing.date
            )
            existing.closing_stock = max(
                0, existing.opening_stock + existing_today_received - existing.quantity_sold - existing.wastage_qty
            )
            if body.notes is not None:
                existing.notes = body.notes.strip() if body.notes else None
            db.commit()
            db.refresh(existing)
            return _sales_response(db, existing)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sales day already opened for this store/product/date",
        )
    record = SalesRecord(
        store_id=resolved_store_id,
        product_id=body.product_id,
        date=body.date,
        opening_stock=opening_stock_to_use,
        quantity_sold=0,
        closing_stock=opening_stock_to_use,
        wastage_qty=0,
        total_amount=Decimal("0"),
        is_closed=False,
        notes=body.notes.strip() if body.notes else None,
        recorded_by=current_user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _sales_response(db, record)


@router.put("/{record_id}/reopen", response_model=SalesRecordResponse)
async def reopen_sales_day(
    record_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.OWNER, RoleEnum.STORE_MANAGER)),
):
    record = db.query(SalesRecord).filter(SalesRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales record not found")
    _resolve_store_scope(current_user, record.store_id)
    _enforce_store_manager_today_lock(current_user, record.date)
    if not record.is_closed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sales day is already open")
    record.is_closed = False
    record.closed_at = None
    manual_wastage = _manual_store_wastage_qty(db, record)
    record.wastage_qty = manual_wastage
    today_received = _today_received_qty(db, record.store_id, record.product_id, record.date)
    record.closing_stock = max(0, record.opening_stock + today_received - record.quantity_sold - record.wastage_qty)
    record.recorded_by = current_user.id
    _sync_auto_wastage(
        db=db,
        record=record,
        wastage_qty=0,
        recorded_by=current_user.id,
        enabled=False,
    )
    db.commit()
    db.refresh(record)
    return _sales_response(db, record)


@router.put("/{record_id}", response_model=SalesRecordResponse)
async def update_sales_record(
    record_id: UUID,
    body: SalesUpdatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.OWNER, RoleEnum.STORE_MANAGER)),
):
    record = db.query(SalesRecord).filter(SalesRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales record not found")
    _resolve_store_scope(current_user, record.store_id)
    _enforce_store_manager_today_lock(current_user, record.date)

    had_auto_wastage = len(_auto_wastage_records(db, record)) > 0
    opening_stock = record.opening_stock if body.opening_stock is None else body.opening_stock
    quantity_sold = record.quantity_sold if body.quantity_sold is None else body.quantity_sold
    closing_stock = record.closing_stock if body.closing_stock is None else body.closing_stock

    if opening_stock < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Opening stock cannot be negative")
    if quantity_sold < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sold quantity cannot be negative")
    if closing_stock < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Closing stock cannot be negative")
    today_received = _today_received_qty(db, record.store_id, record.product_id, record.date)
    total_product_qty = opening_stock + today_received
    if quantity_sold > total_product_qty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sold quantity cannot be greater than total available product ({total_product_qty})",
        )

    product = db.query(Product).filter(Product.id == record.product_id).first()
    sale_price = Decimal(str(product.sale_price if product else 0))
    expected_closing = total_product_qty - quantity_sold - (record.wastage_qty if record.is_closed else 0)
    if not record.is_closed:
        manual_wastage = _manual_store_wastage_qty(db, record)
        closing_stock = total_product_qty - quantity_sold - manual_wastage

    record.opening_stock = opening_stock
    record.quantity_sold = quantity_sold
    record.closing_stock = closing_stock
    if record.is_closed:
        total_wastage = max(0, total_product_qty - quantity_sold - closing_stock)
        manual_wastage = _manual_store_wastage_qty(db, record)
        residual_wastage = max(0, total_wastage - manual_wastage)
        record.wastage_qty = total_wastage
    else:
        residual_wastage = 0
        record.wastage_qty = _manual_store_wastage_qty(db, record)
    record.total_amount = sale_price * quantity_sold
    if body.notes is not None:
        record.notes = body.notes.strip() if body.notes else None
    record.recorded_by = current_user.id
    _sync_auto_wastage(
        db=db,
        record=record,
        wastage_qty=residual_wastage,
        recorded_by=current_user.id,
        enabled=record.is_closed and had_auto_wastage,
    )
    db.commit()
    db.refresh(record)
    return _sales_response(db, record)


@router.put("/{record_id}/sell", response_model=SalesRecordResponse)
async def record_sale(
    record_id: UUID,
    body: SalesSellPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.OWNER, RoleEnum.STORE_MANAGER)),
):
    record = db.query(SalesRecord).filter(SalesRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales record not found")
    _resolve_store_scope(current_user, record.store_id)
    _enforce_store_manager_today_lock(current_user, record.date)
    if record.is_closed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sales day already closed")
    if body.quantity_sold <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sold quantity must be positive")
    today_received = _today_received_qty(db, record.store_id, record.product_id, record.date)
    total_product_qty = record.opening_stock + today_received
    manual_wastage = _manual_store_wastage_qty(db, record)
    record.wastage_qty = manual_wastage
    available_before_sale = max(0, total_product_qty - record.quantity_sold - manual_wastage)
    if body.quantity_sold > available_before_sale:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock to sell. Available {available_before_sale}",
        )
    product = db.query(Product).filter(Product.id == record.product_id).first()
    sale_price = Decimal(str(product.sale_price if product else 0))
    record.quantity_sold += body.quantity_sold
    record.closing_stock = max(0, total_product_qty - record.quantity_sold - manual_wastage)
    record.total_amount = Decimal(str(record.total_amount or 0)) + (sale_price * body.quantity_sold)
    if body.notes:
        record.notes = body.notes.strip()
    record.recorded_by = current_user.id
    db.commit()
    db.refresh(record)
    return _sales_response(db, record)


@router.put("/{record_id}/close", response_model=SalesRecordResponse)
async def close_sales_day(
    record_id: UUID,
    body: SalesClosePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(RoleEnum.OWNER, RoleEnum.STORE_MANAGER)),
):
    record = db.query(SalesRecord).filter(SalesRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales record not found")
    _resolve_store_scope(current_user, record.store_id)
    _enforce_store_manager_today_lock(current_user, record.date)
    if record.is_closed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sales day already closed")
    if body.closing_stock < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Closing stock cannot be negative")
    today_received = _today_received_qty(db, record.store_id, record.product_id, record.date)
    expected_without_wastage = record.opening_stock + today_received - record.quantity_sold
    variance_qty = expected_without_wastage - body.closing_stock
    total_wastage_qty = max(0, variance_qty)
    manual_wastage_qty = _manual_store_wastage_qty(db, record)
    residual_wastage_qty = max(0, total_wastage_qty - manual_wastage_qty)
    record.closing_stock = body.closing_stock
    record.wastage_qty = total_wastage_qty
    record.is_closed = True
    record.closed_at = datetime.now(timezone.utc)
    if body.notes:
        record.notes = body.notes.strip()
    record.recorded_by = current_user.id
    _sync_auto_wastage(
        db=db,
        record=record,
        wastage_qty=residual_wastage_qty,
        recorded_by=current_user.id,
        enabled=body.auto_record_wastage,
    )
    db.commit()
    db.refresh(record)
    return _sales_response(db, record)
