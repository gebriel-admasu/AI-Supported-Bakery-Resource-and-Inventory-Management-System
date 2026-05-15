"""End-to-end tests for Phase 9: Supplier & Procurement Management.

Covers:
  * Supplier CRUD (incl. RBAC and unique-name guard)
  * Purchase Order lifecycle (create -> approve -> send -> receive -> cancel)
  * State-machine guard rails (illegal transitions return 400)
  * Auto inventory credit on PO receipt
  * Low-stock alert auto-resolution after receipt
  * Reorder-suggestion ranking algorithm
"""

from datetime import date, timedelta
from decimal import Decimal

from app.core.constants import (
    AlertStatus,
    PurchaseOrderStatus,
    RoleEnum,
)
from app.core.security import create_access_token
from app.models.ingredient import Ingredient
from app.models.inventory import Inventory, InventoryStock, StockAlert
from app.models.supplier import PurchaseOrder, Supplier
from app.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth_headers(user_id) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"}


def _seed_user(db, *, role: RoleEnum, username: str) -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash="hashed",
        full_name=username.replace("_", " ").title(),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_ingredient(
    db, *, name: str = "Flour", unit: str = "kg", unit_cost: str = "10.00"
) -> Ingredient:
    ing = Ingredient(name=name, unit=unit, unit_cost=unit_cost, is_active=True)
    db.add(ing)
    db.commit()
    db.refresh(ing)
    return ing


def _seed_supplier(
    db,
    *,
    name: str = "Acme Mills",
    lead_time_days: int | None = 3,
    is_active: bool = True,
) -> Supplier:
    sup = Supplier(name=name, lead_time_days=lead_time_days, is_active=is_active)
    db.add(sup)
    db.commit()
    db.refresh(sup)
    return sup


def _create_po_via_api(client, owner, supplier_id, ingredient_id, qty=10, cost=5):
    return client.post(
        "/api/v1/purchase-orders/",
        json={
            "supplier_id": str(supplier_id),
            "ingredient_id": str(ingredient_id),
            "quantity": qty,
            "unit_cost": cost,
        },
        headers=_auth_headers(owner.id),
    )


# ---------------------------------------------------------------------------
# Supplier CRUD
# ---------------------------------------------------------------------------


def test_supplier_create_and_list_works(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_a")

    create_resp = client.post(
        "/api/v1/suppliers/",
        json={
            "name": "Addis Flour Co.",
            "contact_person": "Hana",
            "phone": "+251911223344",
            "email": "hana@addisflour.et",
            "lead_time_days": 4,
        },
        headers=_auth_headers(owner.id),
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["name"] == "Addis Flour Co."
    assert created["lead_time_days"] == 4
    assert created["is_active"] is True

    list_resp = client.get("/api/v1/suppliers/", headers=_auth_headers(owner.id))
    assert list_resp.status_code == 200
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]["name"] == "Addis Flour Co."


def test_supplier_create_duplicate_name_returns_409(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_b")
    _seed_supplier(db_session, name="DupSupplier")

    resp = client.post(
        "/api/v1/suppliers/",
        json={"name": "DupSupplier"},
        headers=_auth_headers(owner.id),
    )
    assert resp.status_code == 409


def test_supplier_create_forbidden_for_store_manager(client, db_session):
    sm = _seed_user(db_session, role=RoleEnum.STORE_MANAGER, username="sm_a")

    resp = client.post(
        "/api/v1/suppliers/",
        json={"name": "ShouldNotExist"},
        headers=_auth_headers(sm.id),
    )
    assert resp.status_code == 403


def test_supplier_update_and_deactivate(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_c")
    sup = _seed_supplier(db_session, name="Edit Me")

    update_resp = client.put(
        f"/api/v1/suppliers/{sup.id}",
        json={"contact_person": "New Contact", "lead_time_days": 7},
        headers=_auth_headers(owner.id),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["contact_person"] == "New Contact"
    assert update_resp.json()["lead_time_days"] == 7

    del_resp = client.delete(
        f"/api/v1/suppliers/{sup.id}", headers=_auth_headers(owner.id)
    )
    assert del_resp.status_code == 204

    db_session.refresh(sup)
    assert sup.is_active is False


# ---------------------------------------------------------------------------
# Purchase Order — happy path
# ---------------------------------------------------------------------------


def test_po_full_happy_path_credits_inventory(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_d")
    sup = _seed_supplier(db_session, name="Full Path Supplier")
    ing = _seed_ingredient(db_session, name="Sugar", unit_cost="3.50")

    create_resp = _create_po_via_api(client, owner, sup.id, ing.id, qty=12, cost=4)
    assert create_resp.status_code == 201, create_resp.text
    po = create_resp.json()
    assert po["status"] == PurchaseOrderStatus.PENDING.value
    assert Decimal(str(po["total_cost"])) == Decimal("48.00")
    po_id = po["id"]

    approve = client.post(
        f"/api/v1/purchase-orders/{po_id}/approve",
        json={},
        headers=_auth_headers(owner.id),
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == PurchaseOrderStatus.APPROVED.value

    send = client.post(
        f"/api/v1/purchase-orders/{po_id}/send",
        json={},
        headers=_auth_headers(owner.id),
    )
    assert send.status_code == 200
    assert send.json()["status"] == PurchaseOrderStatus.SENT.value

    receive = client.post(
        f"/api/v1/purchase-orders/{po_id}/receive",
        json={},
        headers=_auth_headers(owner.id),
    )
    assert receive.status_code == 200
    received = receive.json()
    assert received["status"] == PurchaseOrderStatus.RECEIVED.value
    assert received["actual_delivery"] is not None

    # Production inventory must now hold the received quantity for this ingredient
    inv = (
        db_session.query(Inventory)
        .filter(Inventory.location_type == "production")
        .first()
    )
    assert inv is not None
    stock = (
        db_session.query(InventoryStock)
        .filter(
            InventoryStock.inventory_id == inv.id,
            InventoryStock.ingredient_id == ing.id,
        )
        .first()
    )
    assert stock is not None
    assert Decimal(str(stock.quantity)) == Decimal("12")


def test_po_receive_increments_existing_stock(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_e")
    sup = _seed_supplier(db_session, name="Increment Supplier")
    ing = _seed_ingredient(db_session, name="Salt")

    inv = Inventory(location_type="production", location_id=None)
    db_session.add(inv)
    db_session.flush()
    existing = InventoryStock(
        inventory_id=inv.id,
        ingredient_id=ing.id,
        quantity=Decimal("4.500"),
        min_threshold=Decimal("10"),
    )
    db_session.add(existing)
    db_session.commit()

    po_resp = _create_po_via_api(client, owner, sup.id, ing.id, qty=6, cost=2)
    po_id = po_resp.json()["id"]

    client.post(
        f"/api/v1/purchase-orders/{po_id}/approve",
        json={},
        headers=_auth_headers(owner.id),
    )
    client.post(
        f"/api/v1/purchase-orders/{po_id}/send",
        json={},
        headers=_auth_headers(owner.id),
    )
    receive = client.post(
        f"/api/v1/purchase-orders/{po_id}/receive",
        json={},
        headers=_auth_headers(owner.id),
    )
    assert receive.status_code == 200

    db_session.refresh(existing)
    assert Decimal(str(existing.quantity)) == Decimal("10.500")


def test_po_send_auto_fills_expected_delivery_from_lead_time(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_f")
    sup = _seed_supplier(db_session, name="Lead Time Supplier", lead_time_days=5)
    ing = _seed_ingredient(db_session, name="Yeast")

    po_resp = _create_po_via_api(client, owner, sup.id, ing.id)
    po_id = po_resp.json()["id"]

    client.post(
        f"/api/v1/purchase-orders/{po_id}/approve",
        json={},
        headers=_auth_headers(owner.id),
    )
    send = client.post(
        f"/api/v1/purchase-orders/{po_id}/send",
        json={},
        headers=_auth_headers(owner.id),
    )
    assert send.status_code == 200
    expected = date.fromisoformat(send.json()["expected_delivery"])
    order_date = date.fromisoformat(send.json()["order_date"])
    assert expected == order_date + timedelta(days=5)


# ---------------------------------------------------------------------------
# Purchase Order — guard rails
# ---------------------------------------------------------------------------


def test_po_approve_requires_owner(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_g")
    pm = _seed_user(db_session, role=RoleEnum.PRODUCTION_MANAGER, username="pm_a")
    sup = _seed_supplier(db_session, name="Gate Supplier")
    ing = _seed_ingredient(db_session, name="Butter")

    po_resp = _create_po_via_api(client, owner, sup.id, ing.id)
    po_id = po_resp.json()["id"]

    forbidden = client.post(
        f"/api/v1/purchase-orders/{po_id}/approve",
        json={},
        headers=_auth_headers(pm.id),
    )
    assert forbidden.status_code == 403


def test_po_send_requires_approved_state(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_h")
    sup = _seed_supplier(db_session, name="State Supplier")
    ing = _seed_ingredient(db_session, name="Eggs")

    po_resp = _create_po_via_api(client, owner, sup.id, ing.id)
    po_id = po_resp.json()["id"]

    bad_send = client.post(
        f"/api/v1/purchase-orders/{po_id}/send",
        json={},
        headers=_auth_headers(owner.id),
    )
    assert bad_send.status_code == 400
    assert "APPROVED" in bad_send.json()["detail"]


def test_po_creator_can_cancel_only_while_pending(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_i")
    pm = _seed_user(db_session, role=RoleEnum.PRODUCTION_MANAGER, username="pm_b")
    sup = _seed_supplier(db_session, name="Cancel Supplier")
    ing = _seed_ingredient(db_session, name="Milk")

    create_resp = _create_po_via_api(client, pm, sup.id, ing.id)
    po_id = create_resp.json()["id"]

    cancel_pending = client.post(
        f"/api/v1/purchase-orders/{po_id}/cancel",
        json={"reason": "changed my mind"},
        headers=_auth_headers(pm.id),
    )
    assert cancel_pending.status_code == 200
    assert cancel_pending.json()["status"] == PurchaseOrderStatus.CANCELLED.value

    # Now create a second PO and let the owner approve it; PM can no longer cancel.
    create2 = _create_po_via_api(client, pm, sup.id, ing.id)
    po2_id = create2.json()["id"]
    client.post(
        f"/api/v1/purchase-orders/{po2_id}/approve",
        json={},
        headers=_auth_headers(owner.id),
    )
    cancel_after_approve = client.post(
        f"/api/v1/purchase-orders/{po2_id}/cancel",
        json={},
        headers=_auth_headers(pm.id),
    )
    assert cancel_after_approve.status_code == 403


def test_po_owner_can_cancel_sent_order(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_j")
    sup = _seed_supplier(db_session, name="Owner Cancel Supplier")
    ing = _seed_ingredient(db_session, name="Cocoa")

    po_resp = _create_po_via_api(client, owner, sup.id, ing.id)
    po_id = po_resp.json()["id"]
    client.post(
        f"/api/v1/purchase-orders/{po_id}/approve",
        json={},
        headers=_auth_headers(owner.id),
    )
    client.post(
        f"/api/v1/purchase-orders/{po_id}/send",
        json={},
        headers=_auth_headers(owner.id),
    )

    cancel = client.post(
        f"/api/v1/purchase-orders/{po_id}/cancel",
        json={"reason": "supplier defaulted"},
        headers=_auth_headers(owner.id),
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == PurchaseOrderStatus.CANCELLED.value


def test_po_cancel_received_returns_400(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_k")
    sup = _seed_supplier(db_session, name="Terminal Supplier")
    ing = _seed_ingredient(db_session, name="Vanilla")

    po_resp = _create_po_via_api(client, owner, sup.id, ing.id)
    po_id = po_resp.json()["id"]
    for action in ("approve", "send", "receive"):
        client.post(
            f"/api/v1/purchase-orders/{po_id}/{action}",
            json={},
            headers=_auth_headers(owner.id),
        )

    cancel = client.post(
        f"/api/v1/purchase-orders/{po_id}/cancel",
        json={},
        headers=_auth_headers(owner.id),
    )
    assert cancel.status_code == 400


def test_po_create_for_inactive_supplier_returns_400(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_l")
    sup = _seed_supplier(db_session, name="Inactive Supplier", is_active=False)
    ing = _seed_ingredient(db_session, name="Olive Oil")

    resp = _create_po_via_api(client, owner, sup.id, ing.id)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Inventory side-effects
# ---------------------------------------------------------------------------


def test_po_receipt_resolves_active_low_stock_alert(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_m")
    sup = _seed_supplier(db_session, name="Alert Supplier")
    ing = _seed_ingredient(db_session, name="Baking Powder")

    inv = Inventory(location_type="production", location_id=None)
    db_session.add(inv)
    db_session.flush()
    stock = InventoryStock(
        inventory_id=inv.id,
        ingredient_id=ing.id,
        quantity=Decimal("1"),
        min_threshold=Decimal("5"),
    )
    db_session.add(stock)
    db_session.flush()
    alert = StockAlert(
        inventory_stock_id=stock.id,
        ingredient_id=ing.id,
        current_qty=Decimal("1"),
        min_qty=Decimal("5"),
        status=AlertStatus.ACTIVE,
    )
    db_session.add(alert)
    db_session.commit()

    po_resp = _create_po_via_api(client, owner, sup.id, ing.id, qty=10, cost=2)
    po_id = po_resp.json()["id"]
    for action in ("approve", "send", "receive"):
        r = client.post(
            f"/api/v1/purchase-orders/{po_id}/{action}",
            json={},
            headers=_auth_headers(owner.id),
        )
        assert r.status_code == 200, (action, r.text)

    db_session.refresh(stock)
    db_session.refresh(alert)
    assert Decimal(str(stock.quantity)) == Decimal("11")
    assert alert.status == AlertStatus.RESOLVED


# ---------------------------------------------------------------------------
# Reorder suggestions
# ---------------------------------------------------------------------------


def _make_low_stock(db, ing: Ingredient, *, current: str, threshold: str) -> InventoryStock:
    inv = (
        db.query(Inventory).filter(Inventory.location_type == "production").first()
    )
    if inv is None:
        inv = Inventory(location_type="production", location_id=None)
        db.add(inv)
        db.flush()
    stock = InventoryStock(
        inventory_id=inv.id,
        ingredient_id=ing.id,
        quantity=Decimal(current),
        min_threshold=Decimal(threshold),
    )
    db.add(stock)
    db.commit()
    return stock


def test_reorder_returns_only_low_stock_ingredients(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_n")
    healthy = _seed_ingredient(db_session, name="Healthy Stock")
    low = _seed_ingredient(db_session, name="Low Stock")

    _make_low_stock(db_session, healthy, current="20", threshold="5")
    _make_low_stock(db_session, low, current="2", threshold="10")

    resp = client.get(
        "/api/v1/reorder-suggestions/", headers=_auth_headers(owner.id)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["ingredient_name"] == "Low Stock"
    assert Decimal(str(item["shortage_qty"])) == Decimal("8")
    # suggested = 2 * 10 - 2 = 18
    assert Decimal(str(item["suggested_qty"])) == Decimal("18")


def test_reorder_ranks_history_then_lead_time(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_o")
    ing = _seed_ingredient(db_session, name="Ranked Ingredient")
    _make_low_stock(db_session, ing, current="0", threshold="20")

    sup_history = _seed_supplier(
        db_session, name="History Supplier", lead_time_days=5
    )
    sup_fast_no_history = _seed_supplier(
        db_session, name="Fast No-History Supplier", lead_time_days=1
    )
    sup_slow_no_history = _seed_supplier(
        db_session, name="Slow No-History Supplier", lead_time_days=3
    )

    # Give sup_history an order history for this ingredient
    historic_po = PurchaseOrder(
        supplier_id=sup_history.id,
        ingredient_id=ing.id,
        quantity=Decimal("5"),
        unit_cost=Decimal("2.50"),
        total_cost=Decimal("12.50"),
        order_date=date(2026, 4, 1),
        status=PurchaseOrderStatus.RECEIVED,
        created_by=owner.id,
    )
    db_session.add(historic_po)
    db_session.commit()

    resp = client.get(
        "/api/v1/reorder-suggestions/", headers=_auth_headers(owner.id)
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    suppliers = items[0]["suppliers"]
    assert len(suppliers) == 3
    # Tier 1: history; Tier 2: no-history sorted by lead_time asc
    assert suppliers[0]["supplier_name"] == "History Supplier"
    assert suppliers[0]["has_history"] is True
    assert suppliers[1]["supplier_name"] == "Fast No-History Supplier"
    assert suppliers[2]["supplier_name"] == "Slow No-History Supplier"
    # last_unit_cost from history must surface for the historic supplier
    assert Decimal(str(suppliers[0]["last_unit_cost"])) == Decimal("2.50")


def test_reorder_excludes_inactive_ingredients(client, db_session):
    owner = _seed_user(db_session, role=RoleEnum.OWNER, username="owner_p")
    ing = _seed_ingredient(db_session, name="Discontinued")
    _make_low_stock(db_session, ing, current="0", threshold="10")
    ing.is_active = False
    db_session.commit()

    resp = client.get(
        "/api/v1/reorder-suggestions/", headers=_auth_headers(owner.id)
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []
