"""P5 s5: circuit_breaker_tripped_at + max_orders_per_day + LIVE risk defaults

Adds:
  - accounts.circuit_breaker_tripped_at (nullable datetime)
  - risk_limits.max_orders_per_day (nullable int)

Data migration:
  - Seed a LIVE-scoped GLOBAL risk_limits row per user with tight defaults,
    if none exists (max_position_qty=10, max_position_notional=5000,
    max_gross_exposure=25000, max_daily_loss=500, max_orders_per_minute=3,
    max_orders_per_day=20).
  - Backfill existing PAPER rows with max_orders_per_day=200 (was unlimited).

StrategyStatus.HALTED already exists in the enum (non-native string column),
so no DDL is needed for it.

Revision ID: c4d8e2f1a6b9
Revises: b7e3c1a9f5d2
Create Date: 2026-05-31

"""
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c4d8e2f1a6b9'
down_revision: str | Sequence[str] | None = 'b7e3c1a9f5d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("circuit_breaker_tripped_at", sa.DateTime(timezone=True), nullable=True)
        )
    with op.batch_alter_table("risk_limits", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("max_orders_per_day", sa.Integer(), nullable=True)
        )

    # Data migration.
    conn = op.get_bind()
    now = datetime.now(UTC).isoformat()

    users = conn.execute(sa.text("SELECT id FROM users")).fetchall()
    for u in users:
        # NOTE: scope_type is a non-native SQLEnum that persists the enum
        # *name* ("GLOBAL"), not the value ("global"). Existing rows store
        # "GLOBAL"; the engine queries scope_type == RiskScopeType.GLOBAL which
        # compiles to "GLOBAL". The raw SQL here must match that exactly or the
        # seeded LIVE row would be invisible to _load_global_limits.
        existing = conn.execute(
            sa.text(
                "SELECT id FROM risk_limits "
                "WHERE user_id = :uid AND broker_mode = 'live' "
                "AND scope_type = 'GLOBAL'"
            ),
            {"uid": u.id},
        ).fetchone()
        if existing is None:
            conn.execute(
                sa.text(
                    "INSERT INTO risk_limits ("
                    "user_id, scope_type, scope_id, broker_mode, "
                    "max_position_qty, max_position_notional, max_gross_exposure, "
                    "max_daily_loss, max_orders_per_minute, max_orders_per_day, "
                    "allow_short, created_at, updated_at"
                    ") VALUES ("
                    ":uid, 'GLOBAL', NULL, 'live', "
                    "10, 5000.0, 25000.0, "
                    "500.0, 3, 20, "
                    "0, :ts, :ts"
                    ")"
                ),
                {"uid": u.id, "ts": now},
            )

    # Backfill existing PAPER rows with a default per-day cap (was unlimited).
    conn.execute(
        sa.text(
            "UPDATE risk_limits SET max_orders_per_day = 200 "
            "WHERE broker_mode = 'paper' AND max_orders_per_day IS NULL"
        )
    )


def downgrade() -> None:
    """Downgrade schema. Drops the seeded LIVE rows' new column and the
    circuit-breaker column; leaves any seeded LIVE risk_limits rows in place
    (they are harmless and a downgrade shouldn't delete user-editable config)."""
    with op.batch_alter_table("risk_limits", schema=None) as batch_op:
        batch_op.drop_column("max_orders_per_day")
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.drop_column("circuit_breaker_tripped_at")
