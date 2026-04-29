"""add received_at to distributions for sales math

Revision ID: d4f1a8c2e991
Revises: b1f3c9a4d221
Create Date: 2026-04-29 00:07:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d4f1a8c2e991"
down_revision = "b1f3c9a4d221"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("distributions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE distributions
            SET received_at = updated_at
            WHERE status IN ('RECEIVED', 'CONFIRMED') AND received_at IS NULL
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("distributions", schema=None) as batch_op:
        batch_op.drop_column("received_at")
