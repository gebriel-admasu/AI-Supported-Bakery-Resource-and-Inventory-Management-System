"""add finance manager role

Revision ID: e7c2a1d9f314
Revises: d4f1a8c2e991
Create Date: 2026-04-29 23:18:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e7c2a1d9f314"
down_revision = "d4f1a8c2e991"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "role",
            existing_type=sa.Enum(
                "ADMIN",
                "OWNER",
                "PRODUCTION_MANAGER",
                "STORE_MANAGER",
                "DELIVERY_STAFF",
                name="roleenum",
                native_enum=False,
            ),
            type_=sa.Enum(
                "ADMIN",
                "OWNER",
                "FINANCE_MANAGER",
                "PRODUCTION_MANAGER",
                "STORE_MANAGER",
                "DELIVERY_STAFF",
                name="roleenum",
                native_enum=False,
                create_constraint=True,
            ),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "role",
            existing_type=sa.Enum(
                "ADMIN",
                "OWNER",
                "FINANCE_MANAGER",
                "PRODUCTION_MANAGER",
                "STORE_MANAGER",
                "DELIVERY_STAFF",
                name="roleenum",
                native_enum=False,
            ),
            type_=sa.Enum(
                "ADMIN",
                "OWNER",
                "PRODUCTION_MANAGER",
                "STORE_MANAGER",
                "DELIVERY_STAFF",
                name="roleenum",
                native_enum=False,
                create_constraint=True,
            ),
            existing_nullable=False,
        )
