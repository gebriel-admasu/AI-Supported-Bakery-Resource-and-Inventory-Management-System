"""distribution discrepancy and delivery staff support

Revision ID: c8f7dd4bb0e1
Revises: 386af79a01e8
Create Date: 2026-04-28 11:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c8f7dd4bb0e1"
down_revision = "386af79a01e8"
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

    with op.batch_alter_table("distributions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("delivery_person_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("has_discrepancy", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(
            sa.Column(
                "discrepancy_status",
                sa.Enum(
                    "NONE",
                    "PENDING_APPROVAL",
                    "APPROVED",
                    "REJECTED",
                    name="discrepancystatus",
                    native_enum=False,
                    create_constraint=True,
                ),
                server_default="NONE",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("reviewed_by", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("review_note", sa.String(length=255), nullable=True))
        batch_op.create_foreign_key(
            "fk_distributions_delivery_person_id_users",
            "users",
            ["delivery_person_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_distributions_reviewed_by_users",
            "users",
            ["reviewed_by"],
            ["id"],
        )

    with op.batch_alter_table("distribution_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("discrepancy_qty", sa.Integer(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("discrepancy_reason", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("discrepancy_note", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("distribution_items", schema=None) as batch_op:
        batch_op.drop_column("discrepancy_note")
        batch_op.drop_column("discrepancy_reason")
        batch_op.drop_column("discrepancy_qty")

    with op.batch_alter_table("distributions", schema=None) as batch_op:
        batch_op.drop_constraint("fk_distributions_reviewed_by_users", type_="foreignkey")
        batch_op.drop_constraint("fk_distributions_delivery_person_id_users", type_="foreignkey")
        batch_op.drop_column("review_note")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by")
        batch_op.drop_column("discrepancy_status")
        batch_op.drop_column("has_discrepancy")
        batch_op.drop_column("delivery_person_id")

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
                "PRODUCTION_MANAGER",
                "STORE_MANAGER",
                name="roleenum",
                native_enum=False,
                create_constraint=True,
            ),
            existing_nullable=False,
        )
