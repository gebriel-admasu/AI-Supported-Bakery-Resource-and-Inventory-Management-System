from datetime import date

from app.core.constants import BatchStatus, RoleEnum
from app.core.security import create_access_token
from app.models.distribution import Distribution, DistributionItem
from app.models.product import Product
from app.models.production import ProductionBatch
from app.models.recipe import Recipe
from app.models.store import Store
from app.models.user import User


def _auth_headers(user_id) -> dict:
    token = create_access_token({"sub": str(user_id)})
    return {"Authorization": f"Bearer {token}"}


def test_production_stock_summary_returns_remaining_qty(client, db_session):
    owner = User(
        username="stock_owner",
        email="stock_owner@example.com",
        password_hash="hashed",
        full_name="Stock Owner",
        role=RoleEnum.OWNER,
        is_active=True,
    )
    db_session.add(owner)

    store = Store(name="Stock Store", location="HQ", is_active=True)
    db_session.add(store)

    recipe = Recipe(name="Stock Recipe", yield_qty=10, cost_per_unit="2.00", is_active=True)
    db_session.add(recipe)
    db_session.flush()

    product = Product(
        name="Stock Product",
        sku="STK-001",
        sale_price="7.50",
        recipe_id=recipe.id,
        is_active=True,
    )
    db_session.add(product)
    db_session.flush()

    completed_batch = ProductionBatch(
        recipe_id=recipe.id,
        product_id=product.id,
        batch_size=1,
        actual_yield=100,
        waste_qty=0,
        production_date=date(2026, 5, 1),
        status=BatchStatus.COMPLETED,
        created_by=owner.id,
    )
    db_session.add(completed_batch)
    db_session.flush()

    dist = Distribution(
        store_id=store.id,
        dispatch_date=date(2026, 5, 1),
        dispatched_by=owner.id,
    )
    db_session.add(dist)
    db_session.flush()

    dist_item = DistributionItem(
        distribution_id=dist.id,
        product_id=product.id,
        quantity_sent=35,
    )
    db_session.add(dist_item)
    db_session.commit()

    response = client.get(
        "/api/v1/production/stock-summary",
        headers=_auth_headers(owner.id),
    )
    assert response.status_code == 200

    rows = response.json()
    target = next((row for row in rows if row["product_id"] == str(product.id)), None)
    assert target is not None
    assert target["produced_qty"] == 100
    assert target["dispatched_qty"] == 35
    assert target["remaining_qty"] == 65
