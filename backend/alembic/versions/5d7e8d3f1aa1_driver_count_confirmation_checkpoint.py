"""driver count confirmation checkpoint

Revision ID: 5d7e8d3f1aa1
Revises: c8f7dd4bb0e1
Create Date: 2026-04-28 14:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5d7e8d3f1aa1"
down_revision = "c8f7dd4bb0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("distributions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("driver_count_confirmed", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column("driver_count_confirmed_by", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("driver_count_confirmed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_distributions_driver_count_confirmed_by_users",
            "users",
            ["driver_count_confirmed_by"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("distributions", schema=None) as batch_op:
        batch_op.drop_constraint("fk_distributions_driver_count_confirmed_by_users", type_="foreignkey")
        batch_op.drop_column("driver_count_confirmed_at")
        batch_op.drop_column("driver_count_confirmed_by")
        batch_op.drop_column("driver_count_confirmed")
