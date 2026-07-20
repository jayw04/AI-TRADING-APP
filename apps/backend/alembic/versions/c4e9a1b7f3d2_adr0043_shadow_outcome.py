"""ADR 0043 §D3 — persist the latest shadow-capture outcome per (account, session date)

Adds risk_session_baseline_shadow_outcomes so the enforcement basis selector (PR3b) can give a
specific fallback reason (MISSING_AFTER_ACTIVITY / CAPTURE_INDETERMINATE / NO_BASELINE_CAPTURED …)
instead of collapsing every "no baseline" into one bucket. Evidence only — never authoritative.

No change to any existing table. NOT wired to enforcement here; the enforcement flag is off by default.

Revision ID: c4e9a1b7f3d2
Revises: b6d2f4a9c1e7
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e9a1b7f3d2"
down_revision: str | Sequence[str] | None = "b6d2f4a9c1e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "risk_session_baseline_shadow_outcomes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("market_session_date", sa.String(length=10), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "market_session_date",
            name="uq_risk_session_baseline_shadow_outcome_account_date",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("risk_session_baseline_shadow_outcomes")
