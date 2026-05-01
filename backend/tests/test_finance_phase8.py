from datetime import date
from uuid import UUID

from app.core.constants import RoleEnum, WastageReason, WastageSourceType
from app.core.security import create_access_token
from app.models.ingredient import Ingredient
from app.models.inventory import Inventory, InventoryStock
from app.models.product import Product
from app.models.recipe import Recipe, RecipeIngredient
from app.models.sales import SalesRecord
from app.models.store import Store
from app.models.user import User
from app.models.wastage import WastageRecord


def _auth_headers(user_id) -> dict:
    token = create_access_token({"sub": str(user_id)})
    return {"Authorization": f"Bearer {token}"}


def _seed_owner(db_session: object) -> User:
    owner = User(
        username="owner_tester",
        email="owner_tester@example.com",
        password_hash="hashed",
        full_name="Owner Tester",
        role=RoleEnum.OWNER,
        is_active=True,
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner


def _seed_store(db_session: object) -> Store:
    store = Store(name="Test Store", location="Addis", is_active=True)
    db_session.add(store)
    db_session.commit()
    db_session.refresh(store)
    return store


def _seed_product_with_recipe(db_session: object, *, sku: str, recipe_cost: str, sale_price: str) -> Product:
    recipe = Recipe(
        name=f"Recipe-{sku}",
        yield_qty=10,
        cost_per_unit=recipe_cost,
        is_active=True,
    )
    db_session.add(recipe)
    db_session.flush()
    product = Product(
        name=f"Product-{sku}",
        sku=sku,
        sale_price=sale_price,
        recipe_id=recipe.id,
        is_active=True,
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


def _seed_ingredient(db_session: object, *, name: str, unit: str, unit_cost: str) -> Ingredient:
    ingredient = Ingredient(
        name=name,
        unit=unit,
        unit_cost=unit_cost,
        is_active=True,
    )
    db_session.add(ingredient)
    db_session.commit()
    db_session.refresh(ingredient)
    return ingredient


def test_finance_summary_uses_sales_snapshots_after_recipe_change(client, db_session):
    owner = _seed_owner(db_session)
    store = _seed_store(db_session)
    product = _seed_product_with_recipe(db_session, sku="SNAP-1", recipe_cost="2.00", sale_price="10.00")

    record = SalesRecord(
        store_id=store.id,
        product_id=product.id,
        date=date(2026, 4, 29),
        opening_stock=10,
        quantity_sold=5,
        closing_stock=5,
        wastage_qty=0,
        total_amount="50.00",
        sale_price_snapshot="10.00",
        unit_cogs_snapshot="2.00",
        cogs_amount="10.00",
        is_closed=True,
        recorded_by=owner.id,
    )
    db_session.add(record)
    db_session.commit()

    # Recipe change must not rewrite closed historical P&L when snapshots exist.
    recipe = db_session.query(Recipe).filter(Recipe.id == product.recipe_id).first()
    recipe.cost_per_unit = "9.00"
    db_session.commit()

    response = client.get(
        "/api/v1/finance/summary",
        params={"date_from": "2026-04-29", "date_to": "2026-04-29"},
        headers=_auth_headers(owner.id),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_revenue"] == 50.0
    assert data["total_cogs"] == 10.0
    assert data["gross_profit"] == 40.0
    assert data["estimated_cost_rows"] == 0


def test_finance_summary_defaults_to_finalized_only(client, db_session):
    owner = _seed_owner(db_session)
    store = _seed_store(db_session)
    product = _seed_product_with_recipe(db_session, sku="FIN-ONLY", recipe_cost="3.00", sale_price="10.00")

    closed_record = SalesRecord(
        store_id=store.id,
        product_id=product.id,
        date=date(2026, 4, 28),
        opening_stock=5,
        quantity_sold=1,
        closing_stock=4,
        wastage_qty=0,
        total_amount="10.00",
        sale_price_snapshot="10.00",
        unit_cogs_snapshot="3.00",
        cogs_amount="3.00",
        is_closed=True,
        recorded_by=owner.id,
    )
    open_record = SalesRecord(
        store_id=store.id,
        product_id=product.id,
        date=date(2026, 4, 28),
        opening_stock=10,
        quantity_sold=5,
        closing_stock=5,
        wastage_qty=0,
        total_amount="50.00",
        sale_price_snapshot="10.00",
        unit_cogs_snapshot="3.00",
        cogs_amount="15.00",
        is_closed=False,
        recorded_by=owner.id,
    )
    db_session.add(closed_record)
    db_session.add(open_record)
    db_session.commit()

    finalized = client.get(
        "/api/v1/finance/summary",
        params={"date_from": "2026-04-28", "date_to": "2026-04-28"},
        headers=_auth_headers(owner.id),
    )
    assert finalized.status_code == 200
    assert finalized.json()["total_revenue"] == 10.0

    realtime = client.get(
        "/api/v1/finance/summary",
        params={
            "date_from": "2026-04-28",
            "date_to": "2026-04-28",
            "finalized_only": "false",
        },
        headers=_auth_headers(owner.id),
    )
    assert realtime.status_code == 200
    assert realtime.json()["total_revenue"] == 60.0


def test_product_margin_respects_product_filter(client, db_session):
    owner = _seed_owner(db_session)
    store = _seed_store(db_session)
    product_a = _seed_product_with_recipe(db_session, sku="P-A", recipe_cost="2.00", sale_price="8.00")
    product_b = _seed_product_with_recipe(db_session, sku="P-B", recipe_cost="4.00", sale_price="12.00")

    db_session.add(
        SalesRecord(
            store_id=store.id,
            product_id=product_a.id,
            date=date(2026, 4, 27),
            opening_stock=10,
            quantity_sold=2,
            closing_stock=8,
            wastage_qty=0,
            total_amount="16.00",
            sale_price_snapshot="8.00",
            unit_cogs_snapshot="2.00",
            cogs_amount="4.00",
            is_closed=True,
            recorded_by=owner.id,
        )
    )
    db_session.add(
        SalesRecord(
            store_id=store.id,
            product_id=product_b.id,
            date=date(2026, 4, 27),
            opening_stock=10,
            quantity_sold=1,
            closing_stock=9,
            wastage_qty=0,
            total_amount="12.00",
            sale_price_snapshot="12.00",
            unit_cogs_snapshot="4.00",
            cogs_amount="4.00",
            is_closed=True,
            recorded_by=owner.id,
        )
    )
    db_session.commit()

    response = client.get(
        "/api/v1/finance/product-margins",
        params={
            "date_from": "2026-04-27",
            "date_to": "2026-04-27",
            "product_id": str(product_a.id),
        },
        headers=_auth_headers(owner.id),
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["product_id"] == str(product_a.id)


def test_finance_summary_splits_wastage_costs_without_changing_net_profit(client, db_session):
    owner = _seed_owner(db_session)
    store = _seed_store(db_session)
    product = _seed_product_with_recipe(db_session, sku="SPLIT-1", recipe_cost="4.00", sale_price="20.00")
    ingredient = _seed_ingredient(
        db_session,
        name="Ingredient-SPLIT-1",
        unit="kg",
        unit_cost="3.00",
    )

    db_session.add(
        SalesRecord(
            store_id=store.id,
            product_id=product.id,
            date=date(2026, 4, 30),
            opening_stock=10,
            quantity_sold=5,
            closing_stock=5,
            wastage_qty=0,
            total_amount="100.00",
            sale_price_snapshot="20.00",
            unit_cogs_snapshot="4.00",
            cogs_amount="20.00",
            is_closed=True,
            recorded_by=owner.id,
        )
    )
    db_session.add(
        WastageRecord(
            source_type=WastageSourceType.STORE,
            store_id=store.id,
            product_id=product.id,
            date=date(2026, 4, 30),
            quantity=2,
            unit_price_snapshot="20.00",
            total_price_snapshot="40.00",
            unit_cost_snapshot="3.00",
            total_cost_snapshot="6.00",
            reason=WastageReason.DAMAGE,
            recorded_by=owner.id,
        )
    )
    db_session.add(
        WastageRecord(
            source_type=WastageSourceType.PRODUCTION,
            ingredient_id=ingredient.id,
            date=date(2026, 4, 30),
            quantity=3,
            unit_cost_snapshot="3.00",
            total_cost_snapshot="9.00",
            reason=WastageReason.PRODUCTION_LOSS,
            recorded_by=owner.id,
        )
    )
    db_session.add(
        WastageRecord(
            source_type=WastageSourceType.PRODUCTION,
            product_id=product.id,
            date=date(2026, 4, 30),
            quantity=1,
            unit_price_snapshot="20.00",
            total_price_snapshot="20.00",
            unit_cost_snapshot="4.00",
            total_cost_snapshot="4.00",
            reason=WastageReason.PRODUCTION_LOSS,
            recorded_by=owner.id,
        )
    )
    db_session.commit()

    summary_response = client.get(
        "/api/v1/finance/summary",
        params={"date_from": "2026-04-30", "date_to": "2026-04-30"},
        headers=_auth_headers(owner.id),
    )
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["store_wastage_cost"] == 40.0
    assert summary["ingredient_wastage_cost"] == 9.0
    assert summary["production_product_wastage_cost"] == 20.0
    assert summary["production_wastage_cost"] == 29.0
    assert summary["total_wastage_cost"] == 69.0
    assert summary["gross_profit"] == 80.0
    assert summary["estimated_net_profit"] == 11.0

    trend_response = client.get(
        "/api/v1/finance/pnl-trend",
        params={"date_from": "2026-04-30", "date_to": "2026-04-30"},
        headers=_auth_headers(owner.id),
    )
    assert trend_response.status_code == 200
    trend = trend_response.json()
    assert trend["total_store_wastage_cost"] == 40.0
    assert trend["total_ingredient_wastage_cost"] == 9.0
    assert trend["total_production_product_wastage_cost"] == 20.0
    assert trend["total_production_wastage_cost"] == 29.0
    assert trend["total_wastage_cost"] == 69.0
    assert trend["estimated_net_profit"] == 11.0
    assert trend["points"][0]["store_wastage_cost"] == 40.0
    assert trend["points"][0]["ingredient_wastage_cost"] == 9.0
    assert trend["points"][0]["production_product_wastage_cost"] == 20.0
    assert trend["points"][0]["production_wastage_cost"] == 29.0
    assert trend["points"][0]["wastage_cost"] == 69.0
    assert trend["points"][0]["estimated_net_profit"] == 11.0


def test_open_sales_day_allows_missing_recipe_cogs(client, db_session):
    owner = _seed_owner(db_session)
    store = _seed_store(db_session)
    product = _seed_product_with_recipe(
        db_session,
        sku="COGS-REQ",
        recipe_cost="0.00",
        sale_price="10.00",
    )

    response = client.post(
        "/api/v1/sales/open",
        json={
            "store_id": str(store.id),
            "product_id": str(product.id),
            "date": "2026-05-01",
            "opening_stock": 10,
        },
        headers=_auth_headers(owner.id),
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["product_id"] == str(product.id)
    assert payload["opening_stock"] == 0
    assert payload["quantity_sold"] == 0


def test_finance_summary_uses_unit_snapshot_when_cogs_amount_is_zero(client, db_session):
    owner = _seed_owner(db_session)
    store = _seed_store(db_session)
    product = _seed_product_with_recipe(
        db_session,
        sku="COGS-ZERO",
        recipe_cost="4.00",
        sale_price="12.00",
    )
    db_session.add(
        SalesRecord(
            store_id=store.id,
            product_id=product.id,
            date=date(2026, 5, 1),
            opening_stock=10,
            quantity_sold=3,
            closing_stock=7,
            wastage_qty=0,
            total_amount="36.00",
            sale_price_snapshot="12.00",
            unit_cogs_snapshot="4.00",
            cogs_amount="0.00",
            is_closed=True,
            recorded_by=owner.id,
        )
    )
    db_session.commit()

    response = client.get(
        "/api/v1/finance/summary",
        params={"date_from": "2026-05-01", "date_to": "2026-05-01"},
        headers=_auth_headers(owner.id),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_revenue"] == 36.0
    assert payload["total_cogs"] == 12.0
    assert payload["gross_profit"] == 24.0
    assert payload["estimated_cost_rows"] == 1


def test_finance_summary_uses_computed_recipe_cost_when_stored_cost_is_null(client, db_session):
    owner = _seed_owner(db_session)
    store = _seed_store(db_session)
    ingredient = _seed_ingredient(db_session, name="Flour Dynamic", unit="kg", unit_cost="10.00")

    recipe = Recipe(
        name="Dynamic Cost Recipe",
        yield_qty=5,
        cost_per_unit=None,
        is_active=True,
    )
    db_session.add(recipe)
    db_session.flush()
    db_session.add(
        RecipeIngredient(
            recipe_id=recipe.id,
            ingredient_id=ingredient.id,
            quantity_required="2.000",
        )
    )
    product = Product(
        name="Dynamic Product",
        sku="DYN-COST",
        sale_price="12.00",
        recipe_id=recipe.id,
        is_active=True,
    )
    db_session.add(product)
    db_session.flush()
    db_session.add(
        SalesRecord(
            store_id=store.id,
            product_id=product.id,
            date=date(2026, 5, 2),
            opening_stock=10,
            quantity_sold=3,
            closing_stock=7,
            wastage_qty=0,
            total_amount="36.00",
            sale_price_snapshot="12.00",
            unit_cogs_snapshot="0.00",
            cogs_amount="0.00",
            is_closed=True,
            recorded_by=owner.id,
        )
    )
    db_session.commit()

    response = client.get(
        "/api/v1/finance/summary",
        params={"date_from": "2026-05-02", "date_to": "2026-05-02"},
        headers=_auth_headers(owner.id),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_cogs"] == 12.0
    assert payload["gross_profit"] == 24.0
    assert payload["estimated_cost_rows"] == 1


def test_open_sales_day_uses_computed_recipe_cost_when_stored_cost_is_null(client, db_session):
    owner = _seed_owner(db_session)
    store = _seed_store(db_session)
    ingredient = _seed_ingredient(db_session, name="Milk Dynamic", unit="ltr", unit_cost="9.00")

    recipe = Recipe(
        name="Dynamic Open Recipe",
        yield_qty=3,
        cost_per_unit=None,
        is_active=True,
    )
    db_session.add(recipe)
    db_session.flush()
    db_session.add(
        RecipeIngredient(
            recipe_id=recipe.id,
            ingredient_id=ingredient.id,
            quantity_required="2.000",
        )
    )
    product = Product(
        name="Dynamic Open Product",
        sku="DYN-OPEN",
        sale_price="20.00",
        recipe_id=recipe.id,
        is_active=True,
    )
    db_session.add(product)
    db_session.commit()

    response = client.post(
        "/api/v1/sales/open",
        json={
            "store_id": str(store.id),
            "product_id": str(product.id),
            "date": "2026-05-03",
            "opening_stock": 5,
        },
        headers=_auth_headers(owner.id),
    )

    assert response.status_code == 201
    created_id = UUID(response.json()["id"])
    record = db_session.query(SalesRecord).filter(SalesRecord.id == created_id).first()
    assert record is not None
    assert float(record.unit_cogs_snapshot) == 6.0


def test_open_sales_day_forces_zero_opening_after_previous_zero_closing(client, db_session):
    owner = _seed_owner(db_session)
    store = _seed_store(db_session)
    product = _seed_product_with_recipe(
        db_session,
        sku="OPEN-ZERO",
        recipe_cost="2.00",
        sale_price="8.00",
    )
    db_session.add(
        SalesRecord(
            store_id=store.id,
            product_id=product.id,
            date=date(2026, 5, 4),
            opening_stock=2,
            quantity_sold=2,
            closing_stock=0,
            wastage_qty=0,
            total_amount="16.00",
            sale_price_snapshot="8.00",
            unit_cogs_snapshot="2.00",
            cogs_amount="4.00",
            is_closed=True,
            recorded_by=owner.id,
        )
    )
    db_session.commit()

    response = client.post(
        "/api/v1/sales/open",
        json={
            "store_id": str(store.id),
            "product_id": str(product.id),
            "date": "2026-05-05",
            "opening_stock": 9,
        },
        headers=_auth_headers(owner.id),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["opening_stock"] == 0
    assert payload["total_product_qty"] == 0


def test_finance_summary_includes_expired_ingredient_inventory_cost(client, db_session):
    owner = _seed_owner(db_session)
    ingredient = _seed_ingredient(
        db_session,
        name="Expiry Finance Ingredient",
        unit="kg",
        unit_cost="4.00",
    )
    ingredient.expiry_date = date(2026, 5, 6)
    db_session.add(ingredient)
    db_session.flush()

    inventory = Inventory(location_type="production", location_id=None)
    db_session.add(inventory)
    db_session.flush()
    db_session.add(
        InventoryStock(
            inventory_id=inventory.id,
            ingredient_id=ingredient.id,
            quantity="3.500",
        )
    )
    db_session.commit()

    summary_response = client.get(
        "/api/v1/finance/summary",
        params={"date_from": "2026-05-06", "date_to": "2026-05-06"},
        headers=_auth_headers(owner.id),
    )
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["ingredient_wastage_cost"] == 14.0
    assert summary["production_wastage_cost"] == 14.0
    assert summary["total_wastage_cost"] == 14.0
    assert summary["estimated_net_profit"] == -14.0
    assert summary["estimated_cost_rows"] == 1

    trend_response = client.get(
        "/api/v1/finance/pnl-trend",
        params={"date_from": "2026-05-06", "date_to": "2026-05-06"},
        headers=_auth_headers(owner.id),
    )
    assert trend_response.status_code == 200
    trend = trend_response.json()
    assert trend["total_ingredient_wastage_cost"] == 14.0
    assert trend["total_production_wastage_cost"] == 14.0
    assert trend["total_wastage_cost"] == 14.0
    assert trend["estimated_net_profit"] == -14.0
    assert trend["points"][0]["ingredient_wastage_cost"] == 14.0
    assert trend["points"][0]["wastage_cost"] == 14.0
