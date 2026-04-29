"""sales daily workflow phase7

Revision ID: 9a6e4f2b7d11
Revises: 5d7e8d3f1aa1
Create Date: 2026-04-28 15:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9a6e4f2b7d11"
down_revision = "5d7e8d3f1aa1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sales_records", schema=None) as batch_op:
        batch_op.add_column(sa.Column("wastage_qty", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("notes", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(
            "ix_sales_records_store_product_date",
            ["store_id", "product_id", "date"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("sales_records", schema=None) as batch_op:
        batch_op.drop_index("ix_sales_records_store_product_date")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("notes")
        batch_op.drop_column("closed_at")
        batch_op.drop_column("is_closed")
        batch_op.drop_column("wastage_qty")
