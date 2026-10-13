"""users.market_access — per-user US / China A-share grants.

Additive. Existing rows receive ``us,cn`` so the current owner keeps both markets.
An empty or unknown value grants nothing; that rule lives in app.auth.market_access.

This is one of several Alembic heads. Apply it with ``upgrade heads``, and do not
apply it to the live AWS database during this development phase.

Revision ID: b8c1d4e2a7f3
Revises: f3a1c7e9b2d4
Create Date: 2026-10-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b8c1d4e2a7f3"
down_revision = "f3a1c7e9b2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "market_access",
                sa.String(length=32),
                nullable=False,
                server_default="us,cn",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("market_access")
