"""P7 s5: strategy_revisions

P7 §5 — the authoring conversation history: one row per generation/refinement
turn, persisted at save time, linked to the saved strategy (Direction Decision 3).

Revision ID: b6d1f4a8c3e2
Revises: a4c7e9b2f1d6
Create Date: 2026-06-06

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6d1f4a8c3e2"
down_revision: str | Sequence[str] | None = "a4c7e9b2f1d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "strategy_id",
            sa.Integer(),
            sa.ForeignKey("strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("assumptions_json", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("backtest_json", sa.JSON(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(20, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_strategy_revisions_strategy_seq",
        "strategy_revisions",
        ["strategy_id", "seq"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_strategy_revisions_strategy_seq", table_name="strategy_revisions"
    )
    op.drop_table("strategy_revisions")
