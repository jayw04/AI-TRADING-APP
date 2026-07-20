"""ADR 0043 PR6 — recovery preflight workflow columns + idempotency constraints

Extends the PR1 ``risk_recovery_preflights`` table with the workflow columns the recovery
coordinator needs: idempotency key, durable recovery origin + its event, requested/authorized
actors, aggregate verdict, lifecycle status, transition-commit outcome, and timing. Adds the two
idempotency guards — UNIQUE(account_id, idempotency_key) and a partial unique index enforcing at
most one ACTIVE preflight per account.

No behaviour change on its own: the recovery service is default-inert until an authorized request
arrives, and LOSS_CONTROL_MODE stays OFF.

Revision ID: e7b3f2a9c4d1
Revises: c4e9a1b7f3d2
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7b3f2a9c4d1"
down_revision: str | Sequence[str] | None = "c4e9a1b7f3d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_COLUMNS = (
    sa.Column("idempotency_key", sa.String(64), nullable=False, server_default=""),
    sa.Column("requested_by_actor_type", sa.String(16), nullable=False, server_default="SYSTEM"),
    sa.Column("requested_by_actor_id", sa.String(64), nullable=True),
    sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.text("CURRENT_TIMESTAMP")),
    sa.Column("origin_state", sa.String(32), nullable=True),
    sa.Column("origin_state_version", sa.Integer(), nullable=True),
    sa.Column("request_event_id", sa.Integer(), nullable=True),
    sa.Column("aggregate_verdict", sa.String(16), nullable=True),
    sa.Column("authorized_by_actor_type", sa.String(16), nullable=True),
    sa.Column("authorized_by_actor_id", sa.String(64), nullable=True),
    sa.Column("status", sa.String(24), nullable=False, server_default="REQUESTED"),
    sa.Column("transition_event_id", sa.Integer(), nullable=True),
    sa.Column("failure_reason", sa.String(48), nullable=True),
    sa.Column("evidence_version", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
)


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("risk_recovery_preflights") as batch:
        for col in _NEW_COLUMNS:
            batch.add_column(col)
        batch.create_unique_constraint(
            "uq_risk_recovery_preflight_account_idem", ["account_id", "idempotency_key"]
        )
        batch.create_foreign_key(
            "fk_risk_recovery_preflight_request_event", "risk_control_events",
            ["request_event_id"], ["id"], ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_risk_recovery_preflight_transition_event", "risk_control_events",
            ["transition_event_id"], ["id"], ondelete="SET NULL",
        )
    # At most one ACTIVE preflight per account — a partial unique index (SQLite WHERE clause).
    op.create_index(
        "uq_risk_recovery_preflight_one_active",
        "risk_recovery_preflights",
        ["account_id"],
        unique=True,
        sqlite_where=sa.text(
            "status IN ('REQUESTED', 'RUNNING', 'AUTHORIZATION_REQUIRED')"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_risk_recovery_preflight_one_active", table_name="risk_recovery_preflights"
    )
    with op.batch_alter_table("risk_recovery_preflights") as batch:
        batch.drop_constraint(
            "fk_risk_recovery_preflight_transition_event", type_="foreignkey"
        )
        batch.drop_constraint(
            "fk_risk_recovery_preflight_request_event", type_="foreignkey"
        )
        batch.drop_constraint(
            "uq_risk_recovery_preflight_account_idem", type_="unique"
        )
        for col in reversed(_NEW_COLUMNS):
            batch.drop_column(col.name)
