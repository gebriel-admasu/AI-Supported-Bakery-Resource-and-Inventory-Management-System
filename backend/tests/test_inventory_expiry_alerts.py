from datetime import date, timedelta

from app.core.constants import RoleEnum
from app.core.security import create_access_token
from app.models.ingredient import Ingredient
from app.models.inventory import Inventory, InventoryStock
from app.models.product import Product
from app.models.recipe import Recipe, RecipeIngredient
from app.models.user import User


def _auth_headers(user_id) -> dict:
    token = create_access_token({"sub": str(user_id)})
    return {"Authorization": f"Bearer {token}"}


def _seed_owner(db_session: object) -> User:
    owner = User(
        username="owner_inventory_tester",
        email="owner_inventory_tester@example.com",
        password_hash="hashed",
        full_name="Owner Inventory Tester",
        role=RoleEnum.OWNER,
        is_active=True,
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner


def _seed_production_inventory(db_session: object) -> Inventory:
    inventory = Inventory(location_type="production", location_id=None)
    db_session.add(inventory)
    db_session.commit()
    db_session.refresh(inventory)
    return inventory


def test_inventory_expiry_alerts_return_near_and_expired_items(client, db_session):
    owner = _seed_owner(db_session)
    inventory = _seed_production_inventory(db_session)
    today = date.today()

    expired_ingredient = Ingredient(
        name="Expired Flour",
        unit="kg",
        unit_cost="20.00",
        expiry_date=today - timedelta(days=1),
        is_active=True,
    )
    near_expiry_ingredient = Ingredient(
        name="Near Expiry Yeast",
        unit="kg",
        unit_cost="55.00",
        expiry_date=today + timedelta(days=2),
        is_active=True,
    )
    far_expiry_ingredient = Ingredient(
        name="Fresh Sugar",
        unit="kg",
        unit_cost="30.00",
        expiry_date=today + timedelta(days=20),
        is_active=True,
    )
    db_session.add(expired_ingredient)
    db_session.add(near_expiry_ingredient)
    db_session.add(far_expiry_ingredient)
    db_session.flush()

    db_session.add(
        InventoryStock(
            inventory_id=inventory.id,
            ingredient_id=expired_ingredient.id,
            quantity="8.000",
            min_threshold="2.000",
        )
    )
    db_session.add(
        InventoryStock(
            inventory_id=inventory.id,
            ingredient_id=near_expiry_ingredient.id,
            quantity="4.000",
            min_threshold="1.000",
        )
    )
    db_session.add(
        InventoryStock(
            inventory_id=inventory.id,
            ingredient_id=far_expiry_ingredient.id,
            quantity="10.000",
            min_threshold="2.000",
        )
    )
    db_session.commit()

    response = client.get(
        "/api/v1/inventory/alerts/expiry",
        params={"near_expiry_days": 7},
        headers=_auth_headers(owner.id),
    )
    assert response.status_code == 200
    alerts = response.json()
    assert len(alerts) == 2

    by_name = {item["ingredient_name"]: item for item in alerts}
    assert by_name["Expired Flour"]["status"] == "expired"
    assert by_name["Near Expiry Yeast"]["status"] == "near_expiry"
    assert by_name["Expired Flour"]["days_to_expiry"] < 0
    assert by_name["Near Expiry Yeast"]["days_to_expiry"] >= 0


def test_inventory_expiry_alerts_include_new_expired_ingredient_without_stock(client, db_session):
    owner = _seed_owner(db_session)
    _seed_production_inventory(db_session)
    today = date.today()

    new_expired_ingredient = Ingredient(
        name="New Expired Ingredient",
        unit="kg",
        unit_cost="12.00",
        expiry_date=today - timedelta(days=1),
        is_active=True,
    )
    db_session.add(new_expired_ingredient)
    db_session.commit()

    response = client.get(
        "/api/v1/inventory/alerts/expiry",
        params={"near_expiry_days": 7},
        headers=_auth_headers(owner.id),
    )
    assert response.status_code == 200
    alerts = response.json()
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["ingredient_name"] == "New Expired Ingredient"
    assert alert["status"] == "expired"
    assert float(alert["quantity"]) == 0.0
    assert alert["inventory_stock_id"] == str(new_expired_ingredient.id)


def test_production_start_rejects_expired_ingredient(client, db_session):
    owner = _seed_owner(db_session)
    inventory = _seed_production_inventory(db_session)
    today = date.today()

    expired_ingredient = Ingredient(
        name="Expired Butter",
        unit="kg",
        unit_cost="180.00",
        expiry_date=today - timedelta(days=2),
        is_active=True,
    )
    db_session.add(expired_ingredient)
    db_session.flush()

    db_session.add(
        InventoryStock(
            inventory_id=inventory.id,
            ingredient_id=expired_ingredient.id,
            quantity="20.000",
            min_threshold="5.000",
        )
    )

    recipe = Recipe(
        name="Butter Bread Recipe",
        yield_qty=10,
        cost_per_unit="12.00",
        is_active=True,
    )
    db_session.add(recipe)
    db_session.flush()
    db_session.add(
        RecipeIngredient(
            recipe_id=recipe.id,
            ingredient_id=expired_ingredient.id,
            quantity_required="1.000",
        )
    )

    product = Product(
        name="Butter Bread",
        sku="BUTTER-BREAD",
        sale_price="25.00",
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
            "batch_size": 1,
            "production_date": today.isoformat(),
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
    assert start_response.status_code == 400
    assert "Cannot use expired ingredient" in start_response.json()["detail"]
