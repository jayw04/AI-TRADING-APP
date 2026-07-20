"""ADR 0043 §D3 — the immutable, DB-authoritative session baseline.

WHY THIS TABLE EXISTS
---------------------
The daily-loss control today reads ``accounts_state.day_change = equity − last_equity``, where
``last_equity`` is Alpaca's prior-close equity, **refreshed on every account-sync poll**. That
value is not a fact the application controls at market open — it is a broker field that can move
under a restart, which is exactly the spurious-trip failure class (a ~$24 move once tripped the
breaker after a baseline re-anchor).

The baseline must instead be a *contemporaneously persisted session fact*: captured once, from the
last reconciled equity immediately before the first sanctioned strategy activity of the session,
and then **immutable for the rest of that session**. A restart only ever *loads and verifies* it —
it must never create or replace one mid-session.

THE INVARIANT
-------------
Exactly one baseline per (account, ET market-session date), enforced by the unique constraint.
The absence of a valid baseline is never silently patched: the startup rule (implemented in a
later increment) turns "no baseline but activity already occurred" into an INTEGRITY_STOP, never a
fresh mid-session baseline.

PR 1 lands the table only. Capture/reuse/missing-after-activity behavior arrives in a later
increment; nothing reads this table yet.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# baseline_source values (recorded for audit; the reconciled-open capture is the norm).
BASELINE_SOURCE_RECONCILED_OPEN = "RECONCILED_OPEN"
BASELINE_SOURCE_OPERATOR = "OPERATOR"

# status values. The unique (account, session date) constraint means there is exactly one row
# per session; ``status``/``superseded_by`` exist for the exceptional, governed correction path
# and for audit legibility — never for a routine mid-session replacement.
BASELINE_STATUS_ACTIVE = "ACTIVE"
BASELINE_STATUS_SUPERSEDED = "SUPERSEDED"


class RiskSessionBaseline(Base):
    """One immutable baseline per (account_id, market_session_date)."""

    __tablename__ = "risk_session_baselines"
    __table_args__ = (
        # IDENTITY + immutability: one baseline per account per ET trading date. A second
        # capture for the same session cannot be inserted — the guard against a restart minting
        # a fresh favourable baseline.
        UniqueConstraint(
            "account_id",
            "market_session_date",
            name="uq_risk_session_baseline_account_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )

    # ET official trading date as an ISO calendar label "YYYY-MM-DD". Stored as a string, not a
    # timestamp: it is a pure session-day identity (America/New_York), free of any tz coercion.
    market_session_date: Mapped[str] = mapped_column(String(10), nullable=False)
    session_timezone: Mapped[str] = mapped_column(
        String(32), nullable=False, default="America/New_York"
    )

    # The reconciled account equity captured before the first sanctioned activity of the session.
    baseline_equity: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    baseline_source: Mapped[str] = mapped_column(String(32), nullable=False)

    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The broker snapshot the equity was reconciled against, so a baseline can be traced to the
    # exact broker view it was taken from.
    broker_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=BASELINE_STATUS_ACTIVE
    )
    created_by: Mapped[str] = mapped_column(String(32), nullable=False, default="SYSTEM")
    superseded_by: Mapped[int | None] = mapped_column(
        ForeignKey("risk_session_baselines.id", ondelete="SET NULL"), nullable=True
    )
