"""P6b s5: llm_opt_in

ADR 0006 v2 §5 — the LLM-driven LIVE trading opt-in. One row per
(user, strategy, version): the ``LLM_OPT_IN_ALLOWED`` runtime bypass of the
no-LLM-in-order-path invariant. Version-pinned so a parameter tweak silently
invalidates it.

The four new ``AuditAction`` values (LLM_OPT_IN_INITIATED / _ACTIVATED /
LLM_OPT_OUT / LLM_LIVE_DECISION) are app-level only (StrEnum; no DB change).

Revision ID: f1b8d3e6a2c7
Revises: e9a3c7f1d2b4
Create Date: 2026-06-05

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1b8d3e6a2c7"
down_revision: str | Sequence[str] | None = "e9a3c7f1d2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_opt_in",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "strategy_id",
            sa.Integer(),
            sa.ForeignKey("strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("strategy_version", sa.String(32), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("acknowledgment_text", sa.Text(), nullable=False),
        sa.Column("daily_cap_cents", sa.Integer(), nullable=False),
        sa.Column("initiated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opted_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opted_out_reason", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_llm_opt_in_strategy_id", "llm_opt_in", ["strategy_id"])
    op.create_index("ix_llm_opt_in_user_id", "llm_opt_in", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_opt_in_user_id", table_name="llm_opt_in")
    op.drop_index("ix_llm_opt_in_strategy_id", table_name="llm_opt_in")
    op.drop_table("llm_opt_in")
