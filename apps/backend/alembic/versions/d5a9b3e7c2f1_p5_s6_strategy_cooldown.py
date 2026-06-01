"""P5 s6: strategies.cooldown_until

Adds a nullable cooldown_until datetime to strategies. When set and > now(),
the strategy is in cooldown (set after a failed order submission) and cannot
submit orders until it expires or is manually cleared.

Revision ID: d5a9b3e7c2f1
Revises: c4d8e2f1a6b9
Create Date: 2026-05-31

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd5a9b3e7c2f1'
down_revision: str | Sequence[str] | None = 'c4d8e2f1a6b9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("strategies", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("strategies", schema=None) as batch_op:
        batch_op.drop_column("cooldown_until")
