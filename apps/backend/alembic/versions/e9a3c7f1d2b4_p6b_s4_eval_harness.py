"""P6b s4: eval_harness + eval_harness_decisions + strategies.harness_role

ADR 0006 v2 §4 eval-harness backend: two tables for the three-mode run + the
per-signal decision record, plus a ``harness_role`` discriminator on strategies
(mode_a = the running LLM-wrapped clone, mode_b = the IDLE source_id bucket).

The new ``AuditAction.EVAL_HARNESS_STARTED`` value is app-level only (StrEnum;
no DB change).

Revision ID: e9a3c7f1d2b4
Revises: d7f4a9c2e1b8
Create Date: 2026-06-04

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e9a3c7f1d2b4"
down_revision: str | Sequence[str] | None = "d7f4a9c2e1b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("strategies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("harness_role", sa.String(16), nullable=True))

    op.create_table(
        "eval_harness",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_strategy_id",
            sa.Integer(),
            sa.ForeignKey("strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mode_a_strategy_id",
            sa.Integer(),
            sa.ForeignKey("strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mode_b_strategy_id",
            sa.Integer(),
            sa.ForeignKey("strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminated_reason", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_eval_harness_parent_strategy_id", "eval_harness", ["parent_strategy_id"]
    )
    op.create_index("ix_eval_harness_user_id", "eval_harness", ["user_id"])

    op.create_table(
        "eval_harness_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "harness_id",
            sa.Integer(),
            sa.ForeignKey("eval_harness.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signal_uuid", sa.String(36), nullable=False),
        sa.Column("signal_payload_json", sa.JSON(), nullable=False),
        sa.Column("mode_a_decision", sa.String(8), nullable=False),
        sa.Column("mode_b_decision", sa.String(8), nullable=False),
        sa.Column("mode_b_rationale", sa.Text(), nullable=True),
        sa.Column(
            "mode_a_order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "mode_b_order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("llm_cost_cents", sa.Numeric(20, 4), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_eval_harness_decisions_harness_recorded",
        "eval_harness_decisions",
        ["harness_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_eval_harness_decisions_harness_recorded",
        table_name="eval_harness_decisions",
    )
    op.drop_table("eval_harness_decisions")
    op.drop_index("ix_eval_harness_user_id", table_name="eval_harness")
    op.drop_index("ix_eval_harness_parent_strategy_id", table_name="eval_harness")
    op.drop_table("eval_harness")
    with op.batch_alter_table("strategies", schema=None) as batch_op:
        batch_op.drop_column("harness_role")
