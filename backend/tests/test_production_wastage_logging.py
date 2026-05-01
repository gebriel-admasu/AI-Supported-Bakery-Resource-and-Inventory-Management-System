from datetime import date
from decimal import Decimal

from app.core.constants import BatchStatus, RoleEnum, WastageReason, WastageSourceType
from app.core.security import create_access_token
from app.models.product import Product
from app.models.production import ProductionBatch
from app.models.recipe import Recipe
from app.models.user import User
from app.models.wastage import WastageRecord


def _auth_headers(user_id) -> dict:
    token = create_access_token({"sub": str(user_id)})
    return {"Authorization": f"Bearer {token}"}


def test_completed_batch_auto_logs_product_wastage(client, db_session):
    owner = User(
        username="prod_wastage_owner",
        email="prod_wastage_owner@example.com",
        password_hash="hashed",
        full_name="Production Wastage Owner",
        role=RoleEnum.OWNER,
        is_active=True,
    )
    db_session.add(owner)
    db_session.flush()

    recipe = Recipe(
        name="Chapasa Recipe",
        yield_qty=1,
        cost_per_unit="2.50",
        is_active=True,
    )
    db_session.add(recipe)
    db_session.flush()

    product = Product(
        name="Chapasa",
        sku="CHAPASA-01",
        sale_price="8.00",
        recipe_id=recipe.id,
        unit="piece",
        is_active=True,
    )
    db_session.add(product)
    db_session.commit()

    create_response = client.post(
        "/api/v1/production/batches",
        json={
            "recipe_id": str(recipe.id),
            "product_id": str(product.id),
            "batch_size": 10,
            "production_date": date(2026, 5, 1).isoformat(),
        },
        headers=_auth_headers(owner.id),
    )
    assert create_response.status_code == 201
    batch_id = create_response.json()["id"]

    start_response = client.put(
        f"/api/v1/production/batches/{batch_id}",
        json={"status": "in_progress"},
        headers=_auth_headers(owner.id),
    )
    assert start_response.status_code == 200

    complete_response = client.put(
        f"/api/v1/production/batches/{batch_id}",
        json={
            "status": "completed",
            "actual_yield": 8,
        },
        headers=_auth_headers(owner.id),
    )
    assert complete_response.status_code == 200
    completed = complete_response.json()
    assert completed["waste_qty"] == 2

    auto_wastage = (
        db_session.query(WastageRecord)
        .filter(
            WastageRecord.source_type == WastageSourceType.PRODUCTION,
            WastageRecord.product_id == product.id,
            WastageRecord.ingredient_id.is_(None),
            WastageRecord.date == date(2026, 5, 1),
            WastageRecord.reason == WastageReason.PRODUCTION_LOSS,
            WastageRecord.notes == f"Auto-created from production batch {batch_id}",
        )
        .first()
    )
    assert auto_wastage is not None
    assert auto_wastage.quantity == 2
    assert Decimal(str(auto_wastage.unit_price_snapshot)) == Decimal("8.00")
    assert Decimal(str(auto_wastage.total_price_snapshot)) == Decimal("16.00")
    assert Decimal(str(auto_wastage.unit_cost_snapshot)) == Decimal("2.50")
    assert Decimal(str(auto_wastage.total_cost_snapshot)) == Decimal("5.00")


def test_list_batches_backfills_missing_product_wastage_for_completed_batch(client, db_session):
    owner = User(
        username="prod_backfill_owner",
        email="prod_backfill_owner@example.com",
        password_hash="hashed",
        full_name="Production Backfill Owner",
        role=RoleEnum.OWNER,
        is_active=True,
    )
    db_session.add(owner)
    db_session.flush()

    recipe = Recipe(
        name="Backfill Recipe",
        yield_qty=1,
        cost_per_unit="3.00",
        is_active=True,
    )
    db_session.add(recipe)
    db_session.flush()

    product = Product(
        name="Backfill Product",
        sku="BACKFILL-01",
        sale_price="12.00",
        recipe_id=recipe.id,
        unit="piece",
        is_active=True,
    )
    db_session.add(product)
    db_session.flush()

    batch = ProductionBatch(
        recipe_id=recipe.id,
        product_id=product.id,
        batch_size=10,
        actual_yield=8,
        waste_qty=2,
        production_date=date(2026, 5, 1),
        status=BatchStatus.COMPLETED,
        created_by=owner.id,
    )
    db_session.add(batch)
    db_session.commit()

    preexisting = (
        db_session.query(WastageRecord)
        .filter(
            WastageRecord.source_type == WastageSourceType.PRODUCTION,
            WastageRecord.product_id == product.id,
            WastageRecord.ingredient_id.is_(None),
            WastageRecord.notes == f"Auto-created from production batch {batch.id}",
        )
        .first()
    )
    assert preexisting is None

    response = client.get(
        "/api/v1/production/batches",
        headers=_auth_headers(owner.id),
    )
    assert response.status_code == 200

    backfilled = (
        db_session.query(WastageRecord)
        .filter(
            WastageRecord.source_type == WastageSourceType.PRODUCTION,
            WastageRecord.product_id == product.id,
            WastageRecord.ingredient_id.is_(None),
            WastageRecord.date == date(2026, 5, 1),
            WastageRecord.reason == WastageReason.PRODUCTION_LOSS,
            WastageRecord.notes == f"Auto-created from production batch {batch.id}",
        )
        .first()
    )
    assert backfilled is not None
    assert backfilled.quantity == 2
    assert Decimal(str(backfilled.unit_price_snapshot)) == Decimal("12.00")
    assert Decimal(str(backfilled.total_price_snapshot)) == Decimal("24.00")
