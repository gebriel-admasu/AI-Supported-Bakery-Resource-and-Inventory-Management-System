"""End-to-end tests for Phase 10 — Reports & Dashboards.

Covers all 6 endpoints under /api/v1/reports/* plus role-scoping logic.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.core.constants import (
    AlertStatus,
    BatchStatus,
    RoleEnum,
    WastageReason,
    WastageSourceType,
)
from app.core.security import create_access_token
from app.models.ingredient import Ingredient
from app.models.inventory import Inventory, InventoryStock, StockAlert
from app.models.product import Product
from app.models.production import ProductionBatch
from app.models.recipe import Recipe, RecipeIngredient
from app.models.sales import SalesRecord
from app.models.store import Store
from app.models.user import User
from app.models.wastage import WastageRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth_headers(user_id) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"}


def _seed_user(db, *, role: RoleEnum, username: str, store_id=None) -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash="hashed",
        full_name=username.replace("_", " ").title(),
        role=role,
        is_active=True,
        store_id=store_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_store(db, name: str = "Main Store") -> Store:
    s = Store(name=name, location="Addis", is_active=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _seed_ingredient(
    db, *, name: str = "Flour", unit: str = "kg", unit_cost: str = "10.00"
) -> Ingredient:
    ing = Ingredient(name=name, unit=unit, unit_cost=unit_cost, is_active=True)
    db.add(ing)
    db.commit()
    db.refresh(ing)
    return ing


def _seed_recipe_with_ingredient(
    db,
    *,
    name: str = "Bread Recipe",
    yield_qty: int = 10,
    ingredient: Ingredient,
    qty_required: str = "2.000",
) -> Recipe:
    recipe = Recipe(
        name=name, yield_qty=yield_qty, cost_per_unit="3.00", is_active=True
    )
    db.add(recipe)
    db.flush()
    line = RecipeIngredient(
        recipe_id=recipe.id,
        ingredient_id=ingredient.id,
        quantity_required=qty_required,
    )
    db.add(line)
    db.commit()
    db.refresh(recipe)
    return recipe


def _seed_product(db, *, name: str = "Bread", sku: str = "BR-1", recipe_id=None) -> Product:
    p = Product(
        name=name,
        sku=sku,
        sale_price="10.00",
        recipe_id=recipe_id,
        is_active=True,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _seed_sale(
    db,
    *,
    store: Store,
    product: Product,
    on: date,
    quantity_sold: int,
    sale_price: str,
    unit_cogs: str = "3.00",
) -> SalesRecord:
    total = Decimal(sale_price) * Decimal(quantity_sold)
    cogs = Decimal(unit_cogs) * Decimal(quantity_sold)
    rec = SalesRecord(
        store_id=store.id,
        product_id=product.id,
        date=on,
        opening_stock=quantity_sold,
        quantity_sold=quantity_sold,
        closing_stock=0,
        wastage_qty=0,
        total_amount=str(total),
        sale_price_snapshot=sale_price,
        unit_cogs_snapshot=unit_cogs,
        cogs_amount=str(cogs),
        is_closed=True,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def test_dashboard_owner_returns_full_payload(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_dash")
    store = _seed_store(db_session)
    ing = _seed_ingredient(db_session, name="Flour-A")
    recipe = _seed_recipe_with_ingredient(db_session, ingredient=ing)
    product = _seed_product(db_session, name="Bread-A", sku="BR-A", recipe_id=recipe.id)

    today = date.today()
    _seed_sale(db_session, store=store, product=product, on=today, quantity_sold=5, sale_price="10.00")
    _seed_sale(db_session, store=store, product=product, on=today - timedelta(days=1), quantity_sold=2, sale_price="10.00")

    resp = client.get("/api/v1/reports/dashboard", headers=_auth_headers(owner.id))
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "owner"
    assert data["revenue_today"] == 50.0
    assert data["revenue_week"] == 70.0
    assert data["units_sold_today"] == 5
    assert data["top_product_today"]["product_name"] == "Bread-A"
    assert data["top_product_today"]["units_sold"] == 5
    assert len(data["revenue_sparkline"]) == 7
    # Operational fields are populated for owner
    assert data["active_stock_alerts"] is not None
    assert data["pending_purchase_orders"] is not None


def test_dashboard_store_manager_is_scoped_to_their_store(client, db_session):
    store_a = _seed_store(db_session, name="Store A")
    store_b = _seed_store(db_session, name="Store B")
    sm = _seed_user(
        db_session, role=RoleEnum.STORE_MANAGER, username="sm_a", store_id=store_a.id
    )

    ing = _seed_ingredient(db_session, name="Flour-Scope")
    recipe = _seed_recipe_with_ingredient(db_session, ingredient=ing)
    product = _seed_product(db_session, name="Bread-Scope", sku="BR-SC", recipe_id=recipe.id)

    today = date.today()
    _seed_sale(db_session, store=store_a, product=product, on=today, quantity_sold=3, sale_price="10.00")
    _seed_sale(db_session, store=store_b, product=product, on=today, quantity_sold=99, sale_price="10.00")

    resp = client.get("/api/v1/reports/dashboard", headers=_auth_headers(sm.id))
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "store_manager"
    assert data["scoped_store_id"] == str(store_a.id)
    assert data["scoped_store_name"] == "Store A"
    # Must reflect only store A's 3 units
    assert data["revenue_today"] == 30.0
    assert data["units_sold_today"] == 3


def test_dashboard_production_manager_sees_ops_but_not_revenue(client, db_session):
    pm = _seed_user(db_session, role=RoleEnum.PRODUCTION_MANAGER, username="pm_dash")
    ing = _seed_ingredient(db_session, name="Sugar-Dash")
    recipe = _seed_recipe_with_ingredient(db_session, ingredient=ing)
    product = _seed_product(db_session, name="Cake-Dash", sku="CK-D", recipe_id=recipe.id)

    today = date.today()
    db_session.add_all(
        [
            ProductionBatch(
                recipe_id=recipe.id,
                product_id=product.id,
                batch_size=10,
                actual_yield=10,
                production_date=today,
                status=BatchStatus.COMPLETED,
            ),
            ProductionBatch(
                recipe_id=recipe.id,
                product_id=product.id,
                batch_size=5,
                production_date=today,
                status=BatchStatus.PLANNED,
            ),
        ]
    )
    db_session.commit()

    resp = client.get("/api/v1/reports/dashboard", headers=_auth_headers(pm.id))
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "production_manager"
    assert data["revenue_today"] is None
    assert data["production_batches_today"] == 2
    assert data["active_stock_alerts"] is not None
    assert len(data["batches_sparkline"]) == 7


def test_dashboard_forbidden_for_delivery_staff(client, db_session):
    ds = _seed_user(db_session, role=RoleEnum.DELIVERY_STAFF, username="ds_dash")
    resp = client.get("/api/v1/reports/dashboard", headers=_auth_headers(ds.id))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Sales trends + top sellers
# ---------------------------------------------------------------------------


def test_sales_trends_aggregates_by_day(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_st")
    store = _seed_store(db_session)
    ing = _seed_ingredient(db_session, name="Yeast-T")
    recipe = _seed_recipe_with_ingredient(db_session, ingredient=ing)
    product = _seed_product(db_session, name="Roll", sku="RL", recipe_id=recipe.id)

    base = date(2026, 5, 1)
    for offset, qty in enumerate([2, 3, 0, 5]):
        if qty > 0:
            _seed_sale(db_session, store=store, product=product, on=base + timedelta(days=offset), quantity_sold=qty, sale_price="4.00")

    resp = client.get(
        "/api/v1/reports/sales-trends",
        params={"date_from": "2026-05-01", "date_to": "2026-05-04"},
        headers=_auth_headers(owner.id),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["granularity"] == "day"
    assert data["total_units"] == 10
    assert data["total_revenue"] == 40.0
    assert len(data["points"]) == 3  # the zero-sale day is skipped (no row exists)


def test_sales_trends_week_granularity_buckets_correctly(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_wk")
    store = _seed_store(db_session)
    ing = _seed_ingredient(db_session, name="Salt-T")
    recipe = _seed_recipe_with_ingredient(db_session, ingredient=ing)
    product = _seed_product(db_session, name="Bun", sku="BN", recipe_id=recipe.id)

    # Two days in the same ISO week, two days in the next ISO week.
    days = [date(2026, 5, 4), date(2026, 5, 6), date(2026, 5, 11), date(2026, 5, 13)]
    for d in days:
        _seed_sale(db_session, store=store, product=product, on=d, quantity_sold=1, sale_price="5.00")

    resp = client.get(
        "/api/v1/reports/sales-trends",
        params={
            "date_from": "2026-05-04",
            "date_to": "2026-05-17",
            "granularity": "week",
        },
        headers=_auth_headers(owner.id),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["granularity"] == "week"
    assert len(data["points"]) == 2
    assert data["points"][0]["units_sold"] == 2
    assert data["points"][1]["units_sold"] == 2


def test_top_sellers_ordering(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_top")
    store = _seed_store(db_session)
    ing = _seed_ingredient(db_session, name="Butter-T")
    recipe = _seed_recipe_with_ingredient(db_session, ingredient=ing)

    cheap = _seed_product(db_session, name="Cheap Roll", sku="CR", recipe_id=recipe.id)
    pricey = _seed_product(db_session, name="Pricey Cake", sku="PC", recipe_id=recipe.id)

    today = date.today()
    _seed_sale(db_session, store=store, product=cheap, on=today, quantity_sold=20, sale_price="2.00")
    _seed_sale(db_session, store=store, product=pricey, on=today, quantity_sold=5, sale_price="20.00")

    by_units = client.get(
        "/api/v1/reports/top-sellers",
        params={"date_from": today.isoformat(), "date_to": today.isoformat(), "order_by": "units"},
        headers=_auth_headers(owner.id),
    ).json()
    assert by_units["items"][0]["product_name"] == "Cheap Roll"

    by_revenue = client.get(
        "/api/v1/reports/top-sellers",
        params={"date_from": today.isoformat(), "date_to": today.isoformat(), "order_by": "revenue"},
        headers=_auth_headers(owner.id),
    ).json()
    assert by_revenue["items"][0]["product_name"] == "Pricey Cake"
    assert by_revenue["items"][0]["revenue"] == 100.0


# ---------------------------------------------------------------------------
# Wastage trends
# ---------------------------------------------------------------------------


def test_wastage_trends_group_by_reason_and_source(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_w")
    store = _seed_store(db_session)
    ing = _seed_ingredient(db_session, name="Sugar-W")
    product = _seed_product(db_session, name="Donut", sku="DN")

    today = date.today()
    db_session.add_all(
        [
            WastageRecord(
                source_type=WastageSourceType.STORE,
                store_id=store.id,
                product_id=product.id,
                date=today,
                quantity=3,
                total_cost_snapshot="9.00",
                reason=WastageReason.SPOILAGE,
            ),
            WastageRecord(
                source_type=WastageSourceType.STORE,
                store_id=store.id,
                product_id=product.id,
                date=today,
                quantity=2,
                total_cost_snapshot="6.00",
                reason=WastageReason.EXPIRY,
            ),
            WastageRecord(
                source_type=WastageSourceType.PRODUCTION,
                ingredient_id=ing.id,
                date=today,
                quantity=1,
                total_cost_snapshot="10.00",
                reason=WastageReason.PRODUCTION_LOSS,
            ),
        ]
    )
    db_session.commit()

    by_reason = client.get(
        "/api/v1/reports/wastage-trends",
        params={"date_from": today.isoformat(), "date_to": today.isoformat(), "group_by": "reason"},
        headers=_auth_headers(owner.id),
    ).json()
    assert by_reason["group_by"] == "reason"
    keys = {b["key"] for b in by_reason["buckets"]}
    assert keys == {"spoilage", "expiry", "production_loss"}
    assert by_reason["total_qty"] == 6
    assert by_reason["total_cost"] == 25.0

    by_source = client.get(
        "/api/v1/reports/wastage-trends",
        params={"date_from": today.isoformat(), "date_to": today.isoformat(), "group_by": "source"},
        headers=_auth_headers(owner.id),
    ).json()
    keys = {b["key"] for b in by_source["buckets"]}
    assert keys == {"store", "production"}


def test_wastage_trends_group_by_date(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_wd")
    store = _seed_store(db_session)
    product = _seed_product(db_session, name="Cookie", sku="CK")

    db_session.add_all(
        [
            WastageRecord(
                source_type=WastageSourceType.STORE,
                store_id=store.id,
                product_id=product.id,
                date=date(2026, 5, 1),
                quantity=1,
                total_cost_snapshot="3.00",
                reason=WastageReason.SPOILAGE,
            ),
            WastageRecord(
                source_type=WastageSourceType.STORE,
                store_id=store.id,
                product_id=product.id,
                date=date(2026, 5, 2),
                quantity=4,
                total_cost_snapshot="12.00",
                reason=WastageReason.DAMAGE,
            ),
        ]
    )
    db_session.commit()

    resp = client.get(
        "/api/v1/reports/wastage-trends",
        params={"date_from": "2026-05-01", "date_to": "2026-05-02", "group_by": "date"},
        headers=_auth_headers(owner.id),
    )
    data = resp.json()
    assert len(data["buckets"]) == 2
    assert data["total_qty"] == 5
    assert data["total_cost"] == 15.0


# ---------------------------------------------------------------------------
# Ingredient consumption
# ---------------------------------------------------------------------------


def test_ingredient_consumption_only_counts_completed_batches(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_ic")
    ing = _seed_ingredient(db_session, name="Flour-IC", unit_cost="5.00")
    recipe = _seed_recipe_with_ingredient(
        db_session, ingredient=ing, yield_qty=10, qty_required="2.000"
    )
    product = _seed_product(db_session, name="Loaf", sku="LF", recipe_id=recipe.id)

    today = date.today()
    db_session.add_all(
        [
            # Completed: 20 units produced -> uses 2 kg per 10-unit yield * 2 = 4 kg
            ProductionBatch(
                recipe_id=recipe.id,
                product_id=product.id,
                batch_size=20,
                actual_yield=20,
                production_date=today,
                status=BatchStatus.COMPLETED,
            ),
            # Cancelled — must be ignored
            ProductionBatch(
                recipe_id=recipe.id,
                product_id=product.id,
                batch_size=100,
                actual_yield=100,
                production_date=today,
                status=BatchStatus.CANCELLED,
            ),
            # Planned — must be ignored
            ProductionBatch(
                recipe_id=recipe.id,
                product_id=product.id,
                batch_size=50,
                production_date=today,
                status=BatchStatus.PLANNED,
            ),
        ]
    )
    db_session.commit()

    resp = client.get(
        "/api/v1/reports/ingredient-consumption",
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
        headers=_auth_headers(owner.id),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["ingredient_name"] == "Flour-IC"
    assert Decimal(str(item["total_qty_consumed"])) == Decimal("4.000")
    assert Decimal(str(item["total_cost"])) == Decimal("20.00")  # 4 kg * 5.00/kg
    assert item["batch_count"] == 1


def test_ingredient_consumption_uses_actual_yield_when_set(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_ay")
    ing = _seed_ingredient(db_session, name="Salt-AY", unit_cost="4.00")
    recipe = _seed_recipe_with_ingredient(
        db_session, ingredient=ing, yield_qty=10, qty_required="1.000"
    )
    product = _seed_product(db_session, name="Cracker", sku="CR", recipe_id=recipe.id)

    today = date.today()
    db_session.add(
        ProductionBatch(
            recipe_id=recipe.id,
            product_id=product.id,
            batch_size=20,
            actual_yield=15,  # underproduction
            production_date=today,
            status=BatchStatus.COMPLETED,
        )
    )
    db_session.commit()

    resp = client.get(
        "/api/v1/reports/ingredient-consumption",
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
        headers=_auth_headers(owner.id),
    )
    data = resp.json()
    # 1 kg per 10 yield, actual 15 -> 1.5 kg
    assert Decimal(str(data["items"][0]["total_qty_consumed"])) == Decimal("1.500")
    assert Decimal(str(data["items"][0]["total_cost"])) == Decimal("6.00")


# ---------------------------------------------------------------------------
# Production efficiency
# ---------------------------------------------------------------------------


def test_production_efficiency_overall_and_per_recipe(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_pe")
    ing = _seed_ingredient(db_session, name="Flour-PE")
    recipe = _seed_recipe_with_ingredient(db_session, ingredient=ing)
    product = _seed_product(db_session, name="Pie", sku="PI", recipe_id=recipe.id)

    today = date.today()
    db_session.add_all(
        [
            ProductionBatch(
                recipe_id=recipe.id,
                product_id=product.id,
                batch_size=10,
                actual_yield=12,  # +20%
                production_date=today,
                status=BatchStatus.COMPLETED,
            ),
            ProductionBatch(
                recipe_id=recipe.id,
                product_id=product.id,
                batch_size=10,
                actual_yield=8,  # -20%
                production_date=today,
                status=BatchStatus.COMPLETED,
            ),
            ProductionBatch(
                recipe_id=recipe.id,
                product_id=product.id,
                batch_size=5,
                production_date=today,
                status=BatchStatus.PLANNED,
            ),
            ProductionBatch(
                recipe_id=recipe.id,
                product_id=product.id,
                batch_size=5,
                production_date=today,
                status=BatchStatus.CANCELLED,
            ),
        ]
    )
    db_session.commit()

    resp = client.get(
        "/api/v1/reports/production-efficiency",
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
        headers=_auth_headers(owner.id),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["planned_count"] == 1
    assert data["completed_count"] == 2
    assert data["cancelled_count"] == 1
    assert data["total_batches"] == 4
    # completed / (completed + cancelled) = 2 / 3 = 66.67%
    assert abs(data["completion_rate"] - (2 / 3 * 100)) < 0.01
    # Avg yield variance: (+20% + -20%) / 2 = 0
    assert abs(data["avg_yield_variance_pct"]) < 0.01
    assert len(data["by_recipe"]) == 1
    assert data["by_recipe"][0]["completed_batches"] == 2


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


def test_sales_trends_forbidden_for_production_manager(client, db_session):
    pm = _seed_user(db_session, role=RoleEnum.PRODUCTION_MANAGER, username="pm_rbac")
    resp = client.get("/api/v1/reports/sales-trends", headers=_auth_headers(pm.id))
    assert resp.status_code == 403


def test_ingredient_consumption_forbidden_for_store_manager(client, db_session):
    store = _seed_store(db_session)
    sm = _seed_user(
        db_session, role=RoleEnum.STORE_MANAGER, username="sm_rbac", store_id=store.id
    )
    resp = client.get(
        "/api/v1/reports/ingredient-consumption", headers=_auth_headers(sm.id)
    )
    assert resp.status_code == 403
