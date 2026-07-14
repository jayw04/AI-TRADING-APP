"""ADR 0042 § D — the DURABLE, cross-process capacity claim.

WHY THIS TABLE EXISTS
---------------------
The first implementation guarded classify → reserve → persist with a per-account
``asyncio.Lock``. That lock is **process-local**. On 2026-07-14 two independent Python processes
(an operator script running twice) each read ``reserved = 0``, each saw ``available_reducible_qty
= 183``, and each received ``ALLOW / VERIFIED_REDUCTION`` for the same 183 KOKU shares, 139 ms
apart. Only the broker stopped the second order — ``available: 0, held_for_orders: 183``.

**The broker is not a safety mechanism.** It is the last thing that should ever notice.

An interpreter-local lock cannot be the authority. The guarantee has to survive multiple Python
processes, multiple Uvicorn workers, operator scripts, the scheduler, container restarts and any
future horizontal scaling. That means the database has to enforce it.

THE INVARIANT, stated once
--------------------------
For every (account, symbol):

    sum of active reserved reduction quantity  <=  current reducible capacity

No two decisions may consume the same unit of capacity.

HOW IT IS ENFORCED
------------------
A single conditional UPDATE — an atomic compare-and-swap:

    UPDATE risk_capacity_state
       SET reserved_qty = reserved_qty + :qty,
           state_version = state_version + 1
     WHERE account_id = :account_id
       AND symbol = :symbol
       AND snapshot_version = :expected_snapshot_version
       AND reserved_qty + :qty <= reducible_capacity_qty

The claim succeeds **only if exactly one row is updated**. Zero rows means the capacity was gone
or the snapshot moved underneath us, and it can never produce ALLOW.

⚠ ``reserved_qty`` is an AUTHORITATIVE ACCUMULATOR. It is incremented on claim and decremented on
release/consume, and it is **never recomputed from the reservations table**. That is not a stylistic
choice — recomputing it during a snapshot refresh would let two processes each reset it to zero
before the other commits, which reintroduces exactly the race this table exists to close. A
snapshot refresh may update ``reducible_capacity_qty`` and ``snapshot_version``; it must never
touch ``reserved_qty``.

A uniqueness constraint cannot express this: uniqueness controls identity, not an aggregate
quantity. The conditional update is the aggregate-quantity backstop.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskCapacityState(Base):
    """One row per (account_id, symbol). The authoritative reducible-capacity ledger."""

    __tablename__ = "risk_capacity_state"
    __table_args__ = (
        UniqueConstraint("account_id", "symbol", name="uq_risk_capacity_account_symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)

    # The broker-snapshot identity the capacity was derived from. A claim pins this, so a claim
    # computed against a stale view of the account cannot silently succeed.
    snapshot_version: Mapped[str] = mapped_column(String(64), nullable=False)

    # Reducible capacity implied by that snapshot: long qty minus quantity already promised to
    # open reducing orders AT THE BROKER.
    reducible_capacity_qty: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal(0)
    )

    # Quantity promised to approvals that have NOT yet reached the broker. Accumulator — see the
    # module docstring. Never recomputed from risk_reservations.
    reserved_qty: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal(0)
    )

    # Monotonic, incremented on every claim/release. Bound onto the reservation and ledger rows
    # so an audit can reconstruct which capacity version a decision consumed.
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
