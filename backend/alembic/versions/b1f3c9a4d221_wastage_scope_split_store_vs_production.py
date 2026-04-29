"""wastage scope split store vs production

Revision ID: b1f3c9a4d221
Revises: 9a6e4f2b7d11
Create Date: 2026-04-28 16:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b1f3c9a4d221"
down_revision = "9a6e4f2b7d11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("wastage_records", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_type",
                sa.Enum(
                    "STORE",
                    "PRODUCTION",
                    name="wastagesourcetype",
                    native_enum=False,
                    create_constraint=True,
                ),
                nullable=False,
                server_default="STORE",
            )
        )
        batch_op.add_column(sa.Column("ingredient_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_wastage_records_ingredient_id_ingredients",
            "ingredients",
            ["ingredient_id"],
            ["id"],
        )
        batch_op.alter_column("store_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.alter_column("product_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("wastage_records", schema=None) as batch_op:
        batch_op.alter_column("product_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.alter_column("store_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.drop_constraint("fk_wastage_records_ingredient_id_ingredients", type_="foreignkey")
        batch_op.drop_column("ingredient_id")
        batch_op.drop_column("source_type")
