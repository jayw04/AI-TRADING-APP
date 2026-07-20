"""ADR 0043 — loss-control architecture persistence foundation

Creates the five tables the durable loss-control architecture stands on, with NO behavior change:
nothing in the order path reads or writes them yet (that arrives in later increments).

  * risk_session_baselines        — immutable per-(account, ET session date) baseline (§D3)
  * risk_loss_control_state        — materialized current state, one row/account, CAS-guarded (§D1)
  * risk_control_events            — append-only, ordered event log = the source of truth (§D1/§D4)
  * risk_recovery_preflights       — a checked, authority-gated recovery attempt (§D5)
  * risk_recovery_preflight_checks — the individual checks + evidence of a preflight (§D5)

Deliberately does NOT touch ``accounts.circuit_breaker_tripped_at`` — its demotion to a projection
is a later, behavior-changing increment. Tables are created baseline → state → events →
preflight → checks so every foreign-key target exists before the referencing table.

Revision ID: b6d2f4a9c1e7
Revises: c3f8a1e7d24b
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6d2f4a9c1e7"
down_revision: str | Sequence[str] | None = "c3f8a1e7d24b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- risk_session_baselines (§D3) --------------------------------------------------------
    op.create_table(
        "risk_session_baselines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("market_session_date", sa.String(length=10), nullable=False),
        sa.Column(
            "session_timezone",
            sa.String(length=32),
            nullable=False,
            server_default="America/New_York",
        ),
        sa.Column("baseline_equity", sa.Numeric(20, 4), nullable=False),
        sa.Column("baseline_source", sa.String(length=32), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("broker_snapshot_id", sa.String(length=64), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="ACTIVE"
        ),
        sa.Column(
            "created_by", sa.String(length=32), nullable=False, server_default="SYSTEM"
        ),
        sa.Column("superseded_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["superseded_by"], ["risk_session_baselines.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        # One immutable baseline per account per ET trading date.
        sa.UniqueConstraint(
            "account_id",
            "market_session_date",
            name="uq_risk_session_baseline_account_date",
        ),
    )

    # --- risk_loss_control_state (§D1) -------------------------------------------------------
    op.create_table(
        "risk_loss_control_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column(
            "state", sa.String(length=32), nullable=False, server_default="NORMAL"
        ),
        sa.Column(
            "state_version", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "last_sequence_no", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("control_version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id", name="uq_risk_loss_control_state_account"
        ),
    )

    # --- risk_control_events (§D1/§D4) -------------------------------------------------------
    op.create_table(
        "risk_control_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("session_date", sa.String(length=10), nullable=True),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("control_type", sa.String(length=24), nullable=False),
        sa.Column("from_state", sa.String(length=32), nullable=True),
        sa.Column("to_state", sa.String(length=32), nullable=False),
        sa.Column("requested_transition", sa.String(length=48), nullable=True),
        sa.Column("trip_type", sa.String(length=24), nullable=True),
        sa.Column("trip_cause", sa.String(length=48), nullable=True),
        sa.Column("trip_evidence_status", sa.String(length=24), nullable=True),
        sa.Column("trigger_value", sa.Numeric(20, 4), nullable=True),
        sa.Column("threshold_value", sa.Numeric(20, 4), nullable=True),
        sa.Column("baseline_id", sa.Integer(), nullable=True),
        sa.Column("equity_snapshot_id", sa.String(length=64), nullable=True),
        sa.Column("positions_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("orders_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("decision_ledger_id", sa.Integer(), nullable=True),
        sa.Column("initiator_type", sa.String(length=16), nullable=False),
        sa.Column("initiator_id", sa.String(length=64), nullable=True),
        sa.Column("control_version", sa.Integer(), nullable=False),
        sa.Column("engine_commit", sa.String(length=64), nullable=True),
        sa.Column("config_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["baseline_id"], ["risk_session_baselines.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["decision_ledger_id"], ["risk_decisions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        # Monotonic per account — no two events share a sequence number.
        sa.UniqueConstraint(
            "account_id", "sequence_no", name="uq_risk_control_event_account_seq"
        ),
    )
    op.create_index(
        "ix_risk_control_events_account_created",
        "risk_control_events",
        ["account_id", "created_at"],
    )

    # --- risk_recovery_preflights (§D5) ------------------------------------------------------
    op.create_table(
        "risk_recovery_preflights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("requested_transition", sa.String(length=48), nullable=False),
        sa.Column("expected_state_version", sa.Integer(), nullable=False),
        sa.Column("trip_type", sa.String(length=24), nullable=True),
        sa.Column("trip_cause", sa.String(length=48), nullable=True),
        sa.Column("authority_class", sa.String(length=32), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("initiator_type", sa.String(length=16), nullable=False),
        sa.Column("initiator_id", sa.String(length=64), nullable=True),
        sa.Column("control_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_risk_recovery_preflights_account_created",
        "risk_recovery_preflights",
        ["account_id", "created_at"],
    )

    # --- risk_recovery_preflight_checks (§D5) ------------------------------------------------
    op.create_table(
        "risk_recovery_preflight_checks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("preflight_id", sa.Integer(), nullable=False),
        sa.Column("check_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["preflight_id"], ["risk_recovery_preflights.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_risk_recovery_preflight_checks_preflight",
        "risk_recovery_preflight_checks",
        ["preflight_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Reverse creation order so a table is dropped before the tables it references.
    op.drop_index(
        "ix_risk_recovery_preflight_checks_preflight",
        table_name="risk_recovery_preflight_checks",
    )
    op.drop_table("risk_recovery_preflight_checks")

    op.drop_index(
        "ix_risk_recovery_preflights_account_created",
        table_name="risk_recovery_preflights",
    )
    op.drop_table("risk_recovery_preflights")

    op.drop_index(
        "ix_risk_control_events_account_created", table_name="risk_control_events"
    )
    op.drop_table("risk_control_events")

    op.drop_table("risk_loss_control_state")
    op.drop_table("risk_session_baselines")
