"""P6 s1a: agent infrastructure schema

Two additive changes (Decisions 3 + 4 of the P6 Architectural Decisions doc):

  * ``trading_profiles.agent_envelope_json`` — the agent behavioral envelope
    (sixth JSON section). Added NOT NULL with a ``{}`` server_default so existing
    rows backfill cleanly. The default is kept (not dropped): dropping a column
    default on SQLite forces a table rebuild, and the ORM always supplies the
    value, so the default is harmless.
  * ``strategy_proposals`` — the agent's proposal records (lifecycle table).
    No row is written until §1b; §1a only creates the schema.

The composite-unique-per-minute index uses ``strftime`` (SQLite-only, matching
the project posture). The bare-string column-reference trap (correction #8) does
not apply to raw SQL — ``generated_at`` here is an unquoted column reference.

Revision ID: a3d9f1c4b7e2
Revises: b3f8c2d1e9a7
Create Date: 2026-06-02

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3d9f1c4b7e2"
down_revision: str | Sequence[str] | None = "b3f8c2d1e9a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. agent_envelope_json on trading_profiles (backfill {} for existing rows).
    with op.batch_alter_table("trading_profiles", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "agent_envelope_json",
                sa.JSON(),
                nullable=False,
                server_default="{}",
            )
        )

    # 2. strategy_proposals table.
    op.create_table(
        "strategy_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="DRAFT"),
        sa.Column("proposal_payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("evidence_bundle_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("evaluation_results_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transitioned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name="fk_strategy_proposals_strategy_id_strategies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_strategy_proposals_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_strategy_proposals"),
    )
    op.create_index("ix_proposals_strategy_id", "strategy_proposals", ["strategy_id"])
    op.create_index("ix_proposals_user_id", "strategy_proposals", ["user_id"])
    op.create_index(
        "ix_proposals_user_state", "strategy_proposals", ["user_id", "state"]
    )
    # Composite-unique-per-minute. Raw SQL so generated_at is a column reference
    # inside strftime (SQLite-only).
    op.execute(
        "CREATE UNIQUE INDEX ix_proposals_strategy_minute_unique "
        "ON strategy_proposals (strategy_id, strftime('%Y-%m-%d %H:%M', generated_at))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_proposals_strategy_minute_unique")
    op.drop_index("ix_proposals_user_state", table_name="strategy_proposals")
    op.drop_index("ix_proposals_user_id", table_name="strategy_proposals")
    op.drop_index("ix_proposals_strategy_id", table_name="strategy_proposals")
    op.drop_table("strategy_proposals")
    with op.batch_alter_table("trading_profiles", schema=None) as batch_op:
        batch_op.drop_column("agent_envelope_json")
