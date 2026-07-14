"""StrategyState — durable per-strategy key/value state (Workstream B prerequisite).

Strategies had NO durable state: the only thing they carried between ticks was in-memory
(`_last_rebalance_week`), lost on every restart and reload. That is fine for a book that recomputes
its whole target each tick, but Workstream B's daily-evaluation policy needs to remember things
ACROSS ticks and ACROSS restarts:

  * the rebalance lifecycle (signal_date / attempted_at / completed_at) so a transient failure
    retries rather than waiting a full week (proposal A4);
  * the last completed-review date, to fire the "no review in 10 trading days" backstop (§5.1 #6);
  * the last daily-evaluation date, so the once-per-day latch survives a restart.

An in-memory counter for any of these is silently reset by a reload — and reloads are routine — so
the state must be durable. This table is that store. It is deliberately generic (one row per
`(strategy_id, key)`, JSON value) rather than a bespoke column per need, so a new lifecycle field is
a new key, not a migration.

The value is a JSON scalar/object. State is OPERATIONAL bookkeeping, not a consequential trading
action, so the row itself is the record and it is not independently audit-logged — the orders and
signals it gates already are. A strategy row's deletion cascades its state away.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base


class StrategyState(Base):
    __tablename__ = "strategy_state"
    __table_args__ = (
        # One value per (strategy, key). The CAS-free upsert in StrategyContext relies on it.
        UniqueConstraint("strategy_id", "key", name="uq_strategy_state_strategy_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    # A JSON scalar or object. None is a legitimate stored value; absence of the row means "unset".
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
