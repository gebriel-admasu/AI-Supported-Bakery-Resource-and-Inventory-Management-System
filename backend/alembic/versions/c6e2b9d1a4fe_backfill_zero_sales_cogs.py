"""backfill zero sales cogs

Revision ID: c6e2b9d1a4fe
Revises: b9c3d5e6f712
Create Date: 2026-05-01 16:45:00.000000
"""

from decimal import Decimal, ROUND_HALF_UP

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c6e2b9d1a4fe"
down_revision = "b9c3d5e6f712"
branch_labels = None
depends_on = None


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _to_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _backfill_zero_sales_cogs(bind) -> None:
    metadata = sa.MetaData()
    sales_records = sa.Table("sales_records", metadata, autoload_with=bind)
    products = sa.Table("products", metadata, autoload_with=bind)
    recipes = sa.Table("recipes", metadata, autoload_with=bind)

    rows = bind.execute(
        sa.select(
            sales_records.c.id,
            sales_records.c.quantity_sold,
            sales_records.c.unit_cogs_snapshot,
            sales_records.c.cogs_amount,
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
        unit_cogs_snapshot = _to_decimal(data["unit_cogs_snapshot"])
        cogs_amount = _to_decimal(data["cogs_amount"])
        recipe_unit_cogs = _to_money(_to_decimal(data["recipe_unit_cogs"]))

        resolved_unit_cogs = Decimal("0")
        if unit_cogs_snapshot > 0:
            resolved_unit_cogs = _to_money(unit_cogs_snapshot)
        elif sold_qty > 0 and cogs_amount > 0:
            resolved_unit_cogs = _to_money(cogs_amount / Decimal(sold_qty))
        elif recipe_unit_cogs > 0:
            resolved_unit_cogs = recipe_unit_cogs

        updates: dict[str, object] = {}
        if resolved_unit_cogs > 0 and (
            data["unit_cogs_snapshot"] is None or unit_cogs_snapshot <= 0
        ):
            updates["unit_cogs_snapshot"] = resolved_unit_cogs

        if sold_qty > 0 and resolved_unit_cogs > 0 and (
            data["cogs_amount"] is None or cogs_amount <= 0
        ):
            updates["cogs_amount"] = _to_money(resolved_unit_cogs * Decimal(sold_qty))

        if updates:
            bind.execute(
                sa.update(sales_records)
                .where(sales_records.c.id == data["id"])
                .values(**updates)
            )


def upgrade() -> None:
    bind = op.get_bind()
    _backfill_zero_sales_cogs(bind)


def downgrade() -> None:
    # Data backfill is intentionally not reversed.
    return None
