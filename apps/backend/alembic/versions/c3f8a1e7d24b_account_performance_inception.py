"""accounts.performance_inception_at — per-account performance-tracking inception marker.

Additive nullable column. NULL = inception is the earliest equity snapshot (the prior behaviour,
unchanged). When set, both the account's total-return window AND the dashboard's benchmark
comparison start from this timestamp — an audited one-way "production inception" marker, not a
rewrite of the equity/benchmark history. Safe to apply on the existing DB: it only adds a nullable
column.

Revision ID: c3f8a1e7d24b
Revises: d4e8f2a6c9b1
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c3f8a1e7d24b"
down_revision = "d4e8f2a6c9b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("performance_inception_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("accounts", "performance_inception_at")
