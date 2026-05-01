"""backfill finance snapshots phase8

Revision ID: a3d4f8c9b211
Revises: f2a9c1e4b7d0
Create Date: 2026-04-30 17:58:00.000000
"""

from decimal import Decimal, ROUND_HALF_UP

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a3d4f8c9b211"
down_revision = "f2a9c1e4b7d0"
branch_labels = None
depends_on = None


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _to_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _backfill_sales_snapshots(bind) -> None:
    metadata = sa.MetaData()
    sales_records = sa.Table("sales_records", metadata, autoload_with=bind)
    products = sa.Table("products", metadata, autoload_with=bind)
    recipes = sa.Table("recipes", metadata, autoload_with=bind)

    rows = bind.execute(
        sa.select(
            sales_records.c.id,
            sales_records.c.quantity_sold,
            sales_records.c.total_amount,
            sales_records.c.sale_price_snapshot,
            sales_records.c.unit_cogs_snapshot,
            sales_records.c.cogs_amount,
            products.c.sale_price.label("product_sale_price"),
            recipes.c.cost_per_unit.label("recipe_unit_cogs"),
        ).select_from(
            sales_records.outerjoin(products, sales_records.c.product_id == products.c.id).outerjoin(
                recipes, products.c.recipe_id == recipes.c.id
            )
        )
    ).fetchall()

    for row in rows:
        data = row._mapping
        sold_qty = int(data["quantity_sold"] or 0)
        updates: dict[str, object] = {}

        if data["sale_price_snapshot"] is None:
            if sold_qty > 0:
                sale_price_snapshot = _to_money(_to_decimal(data["total_amount"]) / Decimal(sold_qty))
            else:
                sale_price_snapshot = _to_money(_to_decimal(data["product_sale_price"]))
            updates["sale_price_snapshot"] = sale_price_snapshot

        if data["unit_cogs_snapshot"] is None:
            updates["unit_cogs_snapshot"] = _to_money(_to_decimal(data["recipe_unit_cogs"]))

        if data["cogs_amount"] is None:
            unit_cogs_for_calc = _to_money(
                _to_decimal(updates.get("unit_cogs_snapshot", data["unit_cogs_snapshot"]))
            )
            updates["cogs_amount"] = _to_money(unit_cogs_for_calc * Decimal(sold_qty))

        if updates:
            bind.execute(
                sa.update(sales_records)
                .where(sales_records.c.id == data["id"])
                .values(**updates)
            )


def _backfill_wastage_snapshots(bind) -> None:
    metadata = sa.MetaData()
    wastage_records = sa.Table("wastage_records", metadata, autoload_with=bind)
    ingredients = sa.Table("ingredients", metadata, autoload_with=bind)
    products = sa.Table("products", metadata, autoload_with=bind)
    recipes = sa.Table("recipes", metadata, autoload_with=bind)

    rows = bind.execute(
        sa.select(
            wastage_records.c.id,
            wastage_records.c.quantity,
            wastage_records.c.ingredient_id,
            wastage_records.c.product_id,
            wastage_records.c.unit_cost_snapshot,
            wastage_records.c.total_cost_snapshot,
            wastage_records.c.cost_source,
            wastage_records.c.is_estimated_cost,
            ingredients.c.unit_cost.label("ingredient_unit_cost"),
            recipes.c.cost_per_unit.label("product_unit_cogs"),
        ).select_from(
            wastage_records.outerjoin(ingredients, wastage_records.c.ingredient_id == ingredients.c.id)
            .outerjoin(products, wastage_records.c.product_id == products.c.id)
            .outerjoin(recipes, products.c.recipe_id == recipes.c.id)
        )
    ).fetchall()

    for row in rows:
        data = row._mapping
        qty = int(data["quantity"] or 0)
        updates: dict[str, object] = {}

        unit_cost_snapshot = data["unit_cost_snapshot"]
        cost_source = data["cost_source"]

        if unit_cost_snapshot is None:
            ingredient_unit_cost = data["ingredient_unit_cost"]
            product_unit_cogs = data["product_unit_cogs"]
            if ingredient_unit_cost is not None:
                unit_cost_snapshot = _to_money(_to_decimal(ingredient_unit_cost))
                cost_source = "ingredient_unit_cost"
            elif product_unit_cogs is not None:
                unit_cost_snapshot = _to_money(_to_decimal(product_unit_cogs))
                cost_source = "product_recipe_cost"
            else:
                unit_cost_snapshot = Decimal("0.00")
                cost_source = "fallback_zero"
            updates["unit_cost_snapshot"] = unit_cost_snapshot
        else:
            unit_cost_snapshot = _to_money(_to_decimal(unit_cost_snapshot))

        if data["total_cost_snapshot"] is None:
            updates["total_cost_snapshot"] = _to_money(unit_cost_snapshot * Decimal(qty))

        if data["cost_source"] is None:
            if cost_source is None:
                if data["ingredient_id"] is not None:
                    cost_source = "ingredient_unit_cost"
                elif data["product_id"] is not None:
                    cost_source = "product_recipe_cost"
                else:
                    cost_source = "fallback_zero"
            updates["cost_source"] = cost_source

        if (
            data["unit_cost_snapshot"] is None
            or data["total_cost_snapshot"] is None
            or data["cost_source"] is None
        ):
            resolved_source = updates.get("cost_source", data["cost_source"]) or "fallback_zero"
            is_estimated_cost = bool(unit_cost_snapshot <= 0 or resolved_source == "fallback_zero")
            updates["is_estimated_cost"] = is_estimated_cost

        if updates:
            bind.execute(
                sa.update(wastage_records)
                .where(wastage_records.c.id == data["id"])
                .values(**updates)
            )


def upgrade() -> None:
    bind = op.get_bind()
    _backfill_sales_snapshots(bind)
    _backfill_wastage_snapshots(bind)


def downgrade() -> None:
    # Data backfill is intentionally not reversed.
    return None
