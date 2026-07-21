"""ADR 0043 §D6 / §D1.4 (PR7) — the recovery-cooldown evaluator (control-plane, NOT the order path).

The sanctioned production path OUT of ``RECOVERY_COOLDOWN``: it gathers DURABLE evidence for an
account sitting in cooldown, runs the pure §D1.4 policy (``state_machine.evaluate_cooldown``), and
maps the verdict onto exactly one transition through ``LossControlService`` —

    COOLDOWN_COMPLETE  → TRIGGER_COOLDOWN_COMPLETE → NORMAL
    COOLDOWN_REGRESSED → TRIGGER_HEALTH_REGRESSED  → INTEGRITY_STOP
    COOLDOWN_HOLD      → no transition (stay in cooldown)

It lives OUTSIDE ``RiskEngine`` on purpose (a control-plane job, not an order decision) and NEVER
writes loss-control state directly — every transition goes through ``request_transition`` on a
dedicated session, with the state version it read as the compare-and-swap guard. It is safe to retry:
a duplicate run finds the account already advanced (state ≠ RECOVERY_COOLDOWN or a bumped version)
and no-ops. It FAILS CLOSED: missing/ambiguous cooldown provenance regresses to INTEGRITY_STOP,
unavailable health evidence HOLDs, and an unexpected exception never advances the account to NORMAL.

Time / broker / loss-velocity are IMPURE inputs the pure policy must not read: this evaluator
supplies them (a wall-clock instant, a broker adapter, an optional velocity reading); absent, they
fail closed. The pure decision itself stays in ``state_machine.py``.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.risk_control_event import RiskControlEvent
from app.db.models.risk_loss_control_state import RiskLossControlState
from app.db.models.risk_recovery_preflight import RiskRecoveryPreflight
from app.risk.loss_control import constants as C
from app.risk.loss_control import preflight as pf
from app.risk.loss_control import state_machine as sm
from app.risk.loss_control.service import LossControlService, TransitionContext
from app.risk.loss_control.session_baseline import resolve_session_date
from app.risk.loss_control.state_machine import (
    TRIGGER_COOLDOWN_COMPLETE,
    TRIGGER_HEALTH_REGRESSED,
)

logger = structlog.get_logger(__name__)

# Event control_type values that represent a fresh TRIP (as opposed to recovery-flow bookkeeping).
_TRIP_CONTROL_TYPES = frozenset({"DAILY_LOSS", "CIRCUIT_BREAKER", "INTEGRITY"})
_INTEGRITY_CONTROL_TYPE = "INTEGRITY"


@dataclass(frozen=True)
class VelocityReading:
    """An authoritative loss-velocity sample supplied by the caller (there is no in-module tracker).
    Absent ⇒ a velocity-class cooldown cannot prove recovery and HOLDs (fail closed)."""

    current: Decimal
    trip_limit: Decimal
    sustained_seconds: int


@dataclass(frozen=True)
class AccountEvidence:
    """The PER-ACCOUNT live evidence a caller supplies for one account's evaluation. Never share one
    account's broker adapter or velocity reading across accounts — each account has its own broker
    connection and its own loss velocity."""

    adapter: object | None = None
    velocity: VelocityReading | None = None


# A provider yields the evidence for ONE account (sync or async). ``evaluate_all`` calls it per
# account so broker/velocity evidence is never reused across accounts.
EvidenceProvider = Callable[[int], "AccountEvidence | Awaitable[AccountEvidence]"]


@dataclass(frozen=True)
class CooldownEvaluation:
    account_id: int
    verdict: str  # a C.COOLDOWN_* value, or "NO_OP" when the account is not (any longer) in cooldown
    transitioned_to: str | None  # resulting state iff a transition committed
    reason: str


class CooldownEvaluator:
    """Evaluate accounts in RECOVERY_COOLDOWN and (idempotently) advance or regress them. An explicit
    callable — invoke it from a scheduled job, an admin action, or PR8's canary."""

    NO_OP = "NO_OP"

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def accounts_in_cooldown(self) -> list[int]:
        async with self._session_factory() as s:
            rows = (
                await s.execute(
                    select(RiskLossControlState.account_id).where(
                        RiskLossControlState.state == C.STATE_RECOVERY_COOLDOWN
                    )
                )
            ).scalars().all()
        return list(rows)

    async def evaluate_all(
        self, *, provider: EvidenceProvider | None = None, now: datetime | None = None,
    ) -> list[CooldownEvaluation]:
        """Evaluate every account currently in cooldown, each with its OWN evidence.

        ``provider(account_id)`` supplies that account's broker adapter + velocity reading (never one
        shared across accounts — that would reconcile account B against account A's broker). Absent, a
        default (no adapter / no velocity) is used, which fails closed. Account-isolated: one account's
        failure never affects another (each is caught and reported)."""
        out: list[CooldownEvaluation] = []
        for account_id in await self.accounts_in_cooldown():
            evidence = await self._resolve_evidence(provider, account_id)
            out.append(await self.evaluate(
                account_id, adapter=evidence.adapter, velocity=evidence.velocity, now=now))
        return out

    @staticmethod
    async def _resolve_evidence(
        provider: EvidenceProvider | None, account_id: int
    ) -> AccountEvidence:
        if provider is None:
            return AccountEvidence()
        result = provider(account_id)
        if inspect.isawaitable(result):
            result = await result
        return result

    async def evaluate(
        self, account_id: int, *, adapter: object | None = None,
        velocity: VelocityReading | None = None, now: datetime | None = None,
    ) -> CooldownEvaluation:
        instant = now or datetime.now(UTC)
        try:
            return await self._evaluate(account_id, adapter, velocity, instant)
        except Exception:  # noqa: BLE001 — CancelledError propagates; any other never advances state
            logger.warning("cooldown_evaluate_errored", account_id=account_id, exc_info=True)
            return CooldownEvaluation(account_id, self.NO_OP, None, C.ERR_INTERNAL)

    # ------------------------------------------------------------------ internals

    async def _evaluate(
        self, account_id: int, adapter: object | None, velocity: VelocityReading | None,
        instant: datetime,
    ) -> CooldownEvaluation:
        async with self._session_factory() as s:
            state_row = await s.scalar(
                select(RiskLossControlState).where(
                    RiskLossControlState.account_id == account_id
                )
            )
            if state_row is None or state_row.state != C.STATE_RECOVERY_COOLDOWN:
                return CooldownEvaluation(
                    account_id, self.NO_OP, None, "account is not in RECOVERY_COOLDOWN")
            expected_version = state_row.state_version

            entry = await self._cooldown_entry_event(s, account_id)
            if entry is None:
                # Missing / ambiguous provenance → never guess; fail closed to INTEGRITY_STOP.
                return await self._regress(
                    account_id, expected_version,
                    f"{C.ERR_ORIGIN_UNPROVEN}: cooldown-entry provenance missing or ambiguous")

            preflight = await s.scalar(
                select(RiskRecoveryPreflight).where(
                    RiskRecoveryPreflight.transition_event_id == entry.id
                )
            )
            if preflight is None:
                return await self._regress(
                    account_id, expected_version,
                    f"{C.ERR_ORIGIN_UNPROVEN}: no passed preflight bound to the cooldown-entry event")

            evidence_status = await self._trip_evidence_status(
                s, account_id, preflight.origin_state, entry.id)
            dwell_class = sm.dwell_class_for_trip(preflight.trip_cause, evidence_status)

            post_entry = await self._events_after(s, account_id, entry.sequence_no)
            inputs = sm.CooldownInputs(
                dwell_class=dwell_class,
                dwell_elapsed_seconds=self._elapsed_seconds(entry.created_at, instant),
                new_session_started=self._new_session_started(entry.session_date, instant),
                manual_repair_complete=preflight.authorized_by_actor_id is not None,
                integrity_alerts_active=any(
                    e.control_type == _INTEGRITY_CONTROL_TYPE for e in post_entry),
                broker_reconciled=await self._broker_reconciled(s, account_id, preflight, adapter),
                state_unchanged_since_cooldown=len(post_entry) == 0,
                velocity_healthy=self._velocity_healthy(dwell_class, velocity),
            )

        verdict = sm.evaluate_cooldown(inputs)
        if verdict.verdict == C.COOLDOWN_COMPLETE:
            return await self._transition(
                account_id, TRIGGER_COOLDOWN_COMPLETE, expected_version,
                C.COOLDOWN_COMPLETE, verdict.reason)
        if verdict.verdict == C.COOLDOWN_REGRESSED:
            return await self._regress(account_id, expected_version, verdict.reason)
        return CooldownEvaluation(account_id, C.COOLDOWN_HOLD, None, verdict.reason)

    async def _cooldown_entry_event(
        self, s: AsyncSession, account_id: int
    ) -> RiskControlEvent | None:
        """The committed transition that entered the CURRENT cooldown: the most recent event whose
        to_state is RECOVERY_COOLDOWN. It is valid provenance only if it came from RECOVERY_PREFLIGHT
        via a PREFLIGHT_PASS — otherwise the provenance is unusable (None → fail closed)."""
        ev = await s.scalar(
            select(RiskControlEvent).where(
                RiskControlEvent.account_id == account_id,
                RiskControlEvent.to_state == C.STATE_RECOVERY_COOLDOWN,
            ).order_by(RiskControlEvent.id.desc())
        )
        if ev is None:
            return None
        if ev.from_state != C.STATE_RECOVERY_PREFLIGHT or ev.requested_transition != "PREFLIGHT_PASS":
            return None
        return ev

    async def _trip_evidence_status(
        self, s: AsyncSession, account_id: int, origin_state: str | None, before_event_id: int
    ) -> str | None:
        """The durable trip-evidence status of the lock this recovery came from — the latest event
        that entered ``origin_state`` carrying an evidence status, before the cooldown entry."""
        if origin_state is None:
            return None
        return await s.scalar(
            select(RiskControlEvent.trip_evidence_status).where(
                RiskControlEvent.account_id == account_id,
                RiskControlEvent.to_state == origin_state,
                RiskControlEvent.trip_evidence_status.is_not(None),
                RiskControlEvent.id < before_event_id,
            ).order_by(RiskControlEvent.id.desc())
        )

    async def _events_after(
        self, s: AsyncSession, account_id: int, sequence_no: int
    ) -> list[RiskControlEvent]:
        return list(
            (
                await s.execute(
                    select(RiskControlEvent).where(
                        RiskControlEvent.account_id == account_id,
                        RiskControlEvent.sequence_no > sequence_no,
                    )
                )
            ).scalars().all()
        )

    async def _broker_reconciled(
        self, s: AsyncSession, account_id: int, preflight: RiskRecoveryPreflight,
        adapter: object | None,
    ) -> bool:
        """Reuse the preflight's AUTHORITATIVE reconciliation (positions / open orders / reservations).
        No adapter ⇒ cannot verify ⇒ not reconciled (fail closed)."""
        if adapter is None:
            return False
        ctx = pf.PreflightContext(
            session=s, account_id=account_id, origin_state=preflight.origin_state,
            request_event=None, trip_type=preflight.trip_type, trip_cause=preflight.trip_cause,
            adapter=adapter,
        )
        for check in (pf._positions_reconcile, pf._open_orders_reconcile, pf._reservations_reconcile):
            if not (await check(ctx)).passed:
                return False
        return True

    def _velocity_healthy(self, dwell_class: str, velocity: VelocityReading | None) -> bool:
        if dwell_class != C.DWELL_CLASS_RATE_VELOCITY:
            return True  # not a velocity trip — irrelevant to the decision
        if velocity is None:
            return False  # velocity trip with no authoritative reading → fail closed
        return sm.velocity_is_healthy(
            velocity.current, velocity.trip_limit, velocity.sustained_seconds)

    @staticmethod
    def _elapsed_seconds(entered_at: datetime, instant: datetime) -> int:
        entered = entered_at if entered_at.tzinfo is not None else entered_at.replace(tzinfo=UTC)
        return max(0, int((instant - entered).total_seconds()))

    @staticmethod
    def _new_session_started(entry_session_date: str | None, instant: datetime) -> bool:
        if entry_session_date is None:
            return False
        current = resolve_session_date(instant)
        return current is not None and current > entry_session_date

    # ------------------------------------------------------------------ transitions (via service)

    async def _transition(
        self, account_id: int, trigger: str, expected_version: int, verdict: str, reason: str,
    ) -> CooldownEvaluation:
        async with self._session_factory() as s:
            result = await LossControlService(s).request_transition(
                account_id=account_id, trigger=trigger, expected_state_version=expected_version,
                context=TransitionContext(initiator_type="SYSTEM"),
            )
        # A stale version / lost CAS / no-edge means a concurrent run already advanced it — no double
        # transition, and never a silent NORMAL.
        to_state = result.state if result.applied else None
        return CooldownEvaluation(
            account_id, verdict, to_state,
            reason if result.applied else f"{reason} (not applied: {result.outcome})")

    async def _regress(
        self, account_id: int, expected_version: int, reason: str,
    ) -> CooldownEvaluation:
        return await self._transition(
            account_id, TRIGGER_HEALTH_REGRESSED, expected_version, C.COOLDOWN_REGRESSED, reason)
