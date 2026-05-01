"""phase8 finance snapshot stability

Revision ID: f2a9c1e4b7d0
Revises: e7c2a1d9f314
Create Date: 2026-04-30 16:58:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f2a9c1e4b7d0"
down_revision = "e7c2a1d9f314"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sales_records", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sale_price_snapshot", sa.Numeric(12, 2), nullable=True))
        batch_op.add_column(sa.Column("unit_cogs_snapshot", sa.Numeric(12, 2), nullable=True))
        batch_op.add_column(sa.Column("cogs_amount", sa.Numeric(12, 2), nullable=True))

    with op.batch_alter_table("wastage_records", schema=None) as batch_op:
        batch_op.add_column(sa.Column("unit_cost_snapshot", sa.Numeric(12, 2), nullable=True))
        batch_op.add_column(sa.Column("total_cost_snapshot", sa.Numeric(12, 2), nullable=True))
        batch_op.add_column(sa.Column("cost_source", sa.String(length=50), nullable=True))
        batch_op.add_column(
            sa.Column(
                "is_estimated_cost",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    with op.batch_alter_table("wastage_records", schema=None) as batch_op:
        batch_op.alter_column("is_estimated_cost", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("wastage_records", schema=None) as batch_op:
        batch_op.drop_column("is_estimated_cost")
        batch_op.drop_column("cost_source")
        batch_op.drop_column("total_cost_snapshot")
        batch_op.drop_column("unit_cost_snapshot")

    with op.batch_alter_table("sales_records", schema=None) as batch_op:
        batch_op.drop_column("cogs_amount")
        batch_op.drop_column("unit_cogs_snapshot")
        batch_op.drop_column("sale_price_snapshot")
