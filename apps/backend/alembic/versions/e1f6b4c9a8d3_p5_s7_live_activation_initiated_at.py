"""P5 s7: strategies.live_activation_initiated_at

Adds the activation-cooldown timestamp. status=PENDING_LIVE is a new string
enum value on the existing generic `status` column — no DDL needed for it.

Revision ID: e1f6b4c9a8d3
Revises: d5a9b3e7c2f1
Create Date: 2026-05-31

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e1f6b4c9a8d3'
down_revision: str | Sequence[str] | None = 'd5a9b3e7c2f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("strategies", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "live_activation_initiated_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("strategies", schema=None) as batch_op:
        batch_op.drop_column("live_activation_initiated_at")
