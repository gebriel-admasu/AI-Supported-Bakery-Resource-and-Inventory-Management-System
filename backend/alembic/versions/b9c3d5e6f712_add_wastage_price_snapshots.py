"""add wastage price snapshots

Revision ID: b9c3d5e6f712
Revises: a3d4f8c9b211
Create Date: 2026-05-01 16:20:00.000000
"""

from decimal import Decimal, ROUND_HALF_UP

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b9c3d5e6f712"
down_revision = "a3d4f8c9b211"
branch_labels = None
depends_on = None


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _to_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _backfill_wastage_price_snapshots(bind) -> None:
    metadata = sa.MetaData()
    wastage_records = sa.Table("wastage_records", metadata, autoload_with=bind)
    products = sa.Table("products", metadata, autoload_with=bind)

    rows = bind.execute(
        sa.select(
            wastage_records.c.id,
            wastage_records.c.quantity,
            wastage_records.c.product_id,
            wastage_records.c.unit_price_snapshot,
            wastage_records.c.total_price_snapshot,
            products.c.sale_price.label("product_sale_price"),
        ).select_from(
            wastage_records.outerjoin(products, wastage_records.c.product_id == products.c.id)
        )
    ).fetchall()

    for row in rows:
        data = row._mapping
        if data["product_id"] is None:
            continue

        qty = int(data["quantity"] or 0)
        updates: dict[str, object] = {}

        unit_price_snapshot = data["unit_price_snapshot"]
        if unit_price_snapshot is None:
            unit_price_snapshot = _to_money(_to_decimal(data["product_sale_price"]))
            updates["unit_price_snapshot"] = unit_price_snapshot
        else:
            unit_price_snapshot = _to_money(_to_decimal(unit_price_snapshot))

        if data["total_price_snapshot"] is None:
            updates["total_price_snapshot"] = _to_money(unit_price_snapshot * Decimal(qty))

        if updates:
            bind.execute(
                sa.update(wastage_records)
                .where(wastage_records.c.id == data["id"])
                .values(**updates)
            )


def upgrade() -> None:
    with op.batch_alter_table("wastage_records", schema=None) as batch_op:
        batch_op.add_column(sa.Column("unit_price_snapshot", sa.Numeric(12, 2), nullable=True))
        batch_op.add_column(sa.Column("total_price_snapshot", sa.Numeric(12, 2), nullable=True))

    bind = op.get_bind()
    _backfill_wastage_price_snapshots(bind)


def downgrade() -> None:
    with op.batch_alter_table("wastage_records", schema=None) as batch_op:
        batch_op.drop_column("total_price_snapshot")
        batch_op.drop_column("unit_price_snapshot")
