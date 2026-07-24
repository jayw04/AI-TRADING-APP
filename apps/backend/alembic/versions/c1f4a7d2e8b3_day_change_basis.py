"""accounts_state.day_change_basis — provenance for the cached day-change figure

Additive and narrow: one nullable-free string column with a conservative server default, no change
to any existing column. Rows that predate this column had no basis recorded, so they default to
``UNAVAILABLE`` rather than asserting a provenance nobody captured; the next account-sync poll
overwrites each row with its real basis.

Revision ID: c1f4a7d2e8b3
Revises: a4c7e1b93d20
Create Date: 2026-07-24

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1f4a7d2e8b3"
down_revision: str | Sequence[str] | None = "a4c7e1b93d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "accounts_state",
        sa.Column(
            "day_change_basis",
            sa.String(length=32),
            nullable=False,
            server_default="UNAVAILABLE",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("accounts_state", "day_change_basis")
