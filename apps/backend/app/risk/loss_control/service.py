"""ADR 0043 §D1.1/§D1.2 — the loss-control persistence service (the sole transition authority).

The pure state machine decides *what* a transition is; this service is the only thing that
*persists* one. It enforces the two properties the pure layer cannot:

* **§D1.1 authority.** Nothing else writes ``risk_loss_control_state`` or appends
  ``risk_control_events``. Controls (and, later, the engine) call ``request_transition`` — they
  emit a request; the service adjudicates and persists.
* **§D1.2 deterministic, serialized ordering.** Every applied transition is a database
  compare-and-swap on ``state_version`` (the guard lives in the WHERE clause, exactly as
  ``RiskDecisionService._claim_capacity`` does — a process-local lock is not authority across
  processes; the 2026-07-14 double-claim proved it). The per-account ``sequence_no`` is allocated
  *inside that same atomic update* (``last_sequence_no + 1``), never by a separate
  ``MAX(sequence_no) + 1`` read that two writers could both win. The state advance and the event
  append commit in one transaction.

Every request yields an EXPLICIT outcome — ``APPLIED`` or one of three non-applied reasons — never
an ambiguous success. Nothing here is wired into the order path (that is PR 4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models.risk_control_event import RiskControlEvent
from app.db.models.risk_loss_control_state import RiskLossControlState
from app.risk.loss_control import constants as C
from app.risk.loss_control import state_machine as sm

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

# --- request outcomes (explicit; a non-applied request is never a silent success) -------------
APPLIED = "APPLIED"
NOT_APPLIED_STALE = "NOT_APPLIED_STALE"  # expected_state_version did not match current
NOT_APPLIED_CONFLICT = "NOT_APPLIED_CONFLICT"  # lost the compare-and-swap to a concurrent writer
NOT_APPLIED_NO_CHANGE = "NOT_APPLIED_NO_CHANGE"  # the trigger has no edge from the current state


@dataclass(frozen=True)
class TransitionContext:
    """Optional causal context recorded on the event (§D4 taxonomy + provenance). All optional so
    early callers can pass only what they have; later increments fill the rest."""

    initiator_type: str = "SYSTEM"  # SYSTEM | USER | STRATEGY | AGENT
    initiator_id: str | None = None
    session_date: str | None = None
    trip_type: str | None = None
    trip_cause: str | None = None
    trip_evidence_status: str | None = None
    trigger_value: Decimal | None = None
    threshold_value: Decimal | None = None
    baseline_id: int | None = None
    equity_snapshot_id: str | None = None
    positions_snapshot_hash: str | None = None
    orders_snapshot_hash: str | None = None
    decision_ledger_id: int | None = None
    engine_commit: str | None = None
    config_hash: str | None = None


@dataclass(frozen=True)
class TransitionResult:
    """The explicit outcome of a transition request."""

    outcome: str
    account_id: int
    state: str  # resulting state if APPLIED, else the unchanged current state
    state_version: int  # resulting version if APPLIED, else the current version
    reason: str
    sequence_no: int | None = None  # the event's sequence, only when APPLIED
    event_id: int | None = None  # only when APPLIED

    @property
    def applied(self) -> bool:
        return self.outcome == APPLIED


class LossControlService:
    """Reads and advances the loss-control state machine for one or more accounts.

    ``request_transition`` is self-contained and atomic: it commits the state advance + event
    append together, so a returned ``APPLIED`` is durable. It is designed to be called with a
    session dedicated to the transition (as the engine will, mirroring ``_permits_verified_reduction``).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _ensure_state_row(self, account_id: int) -> None:
        """Materialize the account's NORMAL state row if absent — race-safe.

        INSERT ... ON CONFLICT DO NOTHING: if two writers bootstrap the same account concurrently,
        one inserts and the other's insert is a no-op; both then contend on the CAS below, where
        exactly one wins. (A plain read-then-insert could double-insert; the unique constraint would
        reject one, but ON CONFLICT avoids the error path entirely.)
        """
        stmt = (
            sqlite_insert(RiskLossControlState)
            .values(
                account_id=account_id,
                state=C.STATE_NORMAL,
                state_version=0,
                last_sequence_no=0,
                control_version=C.LOSS_CONTROL_STATE_VERSION,
                updated_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=["account_id"])
        )
        await self._session.execute(stmt)

    async def get_state_row(self, account_id: int) -> RiskLossControlState:
        """Return the account's materialized state row, creating a NORMAL one if needed."""
        await self._ensure_state_row(account_id)
        await self._session.commit()
        row = await self._session.scalar(
            select(RiskLossControlState).where(
                RiskLossControlState.account_id == account_id
            )
        )
        # _ensure guarantees existence; the cast documents that invariant for the type checker.
        return cast("RiskLossControlState", row)

    async def current_state(self, account_id: int) -> str:
        return (await self.get_state_row(account_id)).state

    async def request_transition(
        self,
        *,
        account_id: int,
        trigger: str,
        expected_state_version: int | None = None,
        recovery_origin_state: str | None = None,
        context: TransitionContext | None = None,
    ) -> TransitionResult:
        """Adjudicate and (if it applies and wins the CAS) persist one transition.

        Order of checks — each failure is an explicit, distinct non-applied outcome:
          1. STALE     — caller's ``expected_state_version`` no longer matches (idempotent replay /
                         a request built against a superseded view).
          2. NO_CHANGE — the pure machine says this trigger has no edge from the current state.
          3. CONFLICT  — the compare-and-swap updated zero rows: another writer advanced the state
                         between our read and our write. No event is written.
        Otherwise APPLIED: state + version + sequence advanced atomically and the event appended,
        all committed together.
        """
        ctx = context or TransitionContext()
        await self._ensure_state_row(account_id)
        row = await self._session.scalar(
            select(RiskLossControlState).where(
                RiskLossControlState.account_id == account_id
            )
        )
        row = cast("RiskLossControlState", row)
        current_state = row.state
        current_version = row.state_version
        next_sequence = row.last_sequence_no + 1

        if expected_state_version is not None and expected_state_version != current_version:
            await self._session.commit()  # persist the bootstrap row; no transition
            return TransitionResult(
                NOT_APPLIED_STALE,
                account_id,
                current_state,
                current_version,
                f"expected state_version {expected_state_version} != current {current_version}",
            )

        # ``recovery_origin_state`` is a PERSISTED input (§D5) — in PR 6 the caller reads it from the
        # from_state of the event that entered RECOVERY_PREFLIGHT. It is never inferred here.
        decision = sm.decide_transition(
            current_state, trigger, recovery_origin_state=recovery_origin_state
        )
        if not decision.applies:
            await self._session.commit()
            return TransitionResult(
                NOT_APPLIED_NO_CHANGE,
                account_id,
                current_state,
                current_version,
                decision.reason,
            )

        rows = await self._cas_advance(
            account_id=account_id,
            expected_version=current_version,
            to_state=cast("str", decision.to_state),
        )
        if rows != 1:
            # Lost the race — another writer advanced the version. Do NOT append an event.
            await self._session.rollback()
            return TransitionResult(
                NOT_APPLIED_CONFLICT,
                account_id,
                current_state,
                current_version,
                "compare-and-swap lost to a concurrent writer",
            )

        event = RiskControlEvent(
            account_id=account_id,
            session_date=ctx.session_date,
            sequence_no=next_sequence,
            control_type=cast("str", decision.control_type),
            from_state=current_state,
            to_state=decision.to_state,
            requested_transition=trigger,
            trip_type=ctx.trip_type,
            trip_cause=ctx.trip_cause,
            trip_evidence_status=ctx.trip_evidence_status,
            trigger_value=ctx.trigger_value,
            threshold_value=ctx.threshold_value,
            baseline_id=ctx.baseline_id,
            equity_snapshot_id=ctx.equity_snapshot_id,
            positions_snapshot_hash=ctx.positions_snapshot_hash,
            orders_snapshot_hash=ctx.orders_snapshot_hash,
            decision_ledger_id=ctx.decision_ledger_id,
            initiator_type=ctx.initiator_type,
            initiator_id=ctx.initiator_id,
            control_version=C.LOSS_CONTROL_STATE_VERSION,
            engine_commit=ctx.engine_commit,
            config_hash=ctx.config_hash,
            created_at=datetime.now(UTC),
        )
        self._session.add(event)
        await self._session.flush()
        event_id = event.id
        await self._session.commit()

        return TransitionResult(
            APPLIED,
            account_id,
            cast("str", decision.to_state),
            current_version + 1,
            decision.reason,
            sequence_no=next_sequence,
            event_id=event_id,
        )

    async def _cas_advance(
        self, *, account_id: int, expected_version: int, to_state: str
    ) -> int:
        """The atomic compare-and-swap. Returns the number of rows updated (1 = won, 0 = lost).

        The guard ``state_version == expected_version`` lives in the WHERE clause, so the database
        adjudicates: exactly one writer advances from a given version. ``last_sequence_no`` is
        incremented in the SAME statement, so the sequence a winner owns is allocated atomically
        with the state advance — never by a separate ``MAX(sequence_no) + 1`` two writers could
        both read.
        """
        stmt = (
            update(RiskLossControlState)
            .where(
                RiskLossControlState.account_id == account_id,
                RiskLossControlState.state_version == expected_version,
            )
            .values(
                state=to_state,
                state_version=RiskLossControlState.state_version + 1,
                last_sequence_no=RiskLossControlState.last_sequence_no + 1,
                updated_at=datetime.now(UTC),
            )
        )
        res = cast("CursorResult[Any]", await self._session.execute(stmt))
        return res.rowcount
