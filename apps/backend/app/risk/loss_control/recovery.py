"""ADR 0043 §D5 PR6 — the recovery coordinator (control-plane, NOT the order path).

The one sanctioned way out of a loss-control lock:

    authorized request → committed RECOVERY_REQUEST → durable origin → 12 checks (persisted) →
    fail-closed aggregate → authority decision → PREFLIGHT_PASS (→ RECOVERY_COOLDOWN) or
    PREFLIGHT_FAIL (→ origin / INTEGRITY_STOP)

PR6 stops at RECOVERY_COOLDOWN; cooldown completion, dwell, hysteresis, and re-arm to NORMAL are
PR7. This coordinator NEVER writes the materialized loss-control state directly — every transition
goes through ``LossControlService.request_transition`` on a dedicated session. It lives outside
``RiskEngine`` on purpose: recovery is a control-plane workflow, not an order decision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models.risk_control_event import RiskControlEvent
from app.db.models.risk_loss_control_state import RiskLossControlState
from app.db.models.risk_recovery_preflight import RiskRecoveryPreflight
from app.db.models.risk_recovery_preflight_check import RiskRecoveryPreflightCheck
from app.risk.loss_control import constants as C
from app.risk.loss_control import preflight as pf
from app.risk.loss_control.service import LossControlService, TransitionContext
from app.risk.loss_control.state_machine import (
    TRIGGER_PREFLIGHT_FAIL,
    TRIGGER_PREFLIGHT_PASS,
    TRIGGER_RECOVERY_REQUEST,
)

logger = structlog.get_logger(__name__)

_ORIGIN_TRIP_TYPE = {
    C.STATE_REDUCTION_ONLY_DAILY_LOSS: C.TRIP_TYPE_DAILY_LOSS,
    C.STATE_REDUCTION_ONLY_BREAKER: C.TRIP_TYPE_CIRCUIT_BREAKER,
    C.STATE_INTEGRITY_STOP: C.TRIP_TYPE_CONTROL_INTEGRITY,
}
_ORIGIN_AUTHORITY_CLASS = {
    C.STATE_REDUCTION_ONLY_DAILY_LOSS: C.AUTHORITY_CLASS_OWNER_OR_OPERATOR,
    C.STATE_REDUCTION_ONLY_BREAKER: C.AUTHORITY_CLASS_OPERATOR_OR_OWNER_IF_DAILY_LOSS,
    C.STATE_INTEGRITY_STOP: C.AUTHORITY_CLASS_OPERATOR_HUMAN_APPROVAL,
}
_ELIGIBLE_ORIGINS = frozenset(_ORIGIN_TRIP_TYPE)


# ------------------------------------------------------------------ authority matrix (§D5)


def actor_role(user_id: int, account_owner_id: int) -> str | None:
    """OWNER / RISK_OPERATOR for this account, or None if the actor may not act at all.

    RISK_OPERATOR authority is the explicit config allowlist (there is no operator role in the user
    model); it outranks ownership. An actor who is neither operator nor owner cannot act."""
    if user_id in set(get_settings().risk_operator_user_ids):
        return C.ACTOR_RISK_OPERATOR
    if user_id == account_owner_id:
        return C.ACTOR_OWNER
    return None


def may_request(origin: str, role: str) -> bool:
    if origin == C.STATE_INTEGRITY_STOP:
        return role in (C.ACTOR_RISK_OPERATOR, C.ACTOR_SYSTEM)  # owner cannot request integrity recovery
    return role in (C.ACTOR_OWNER, C.ACTOR_RISK_OPERATOR, C.ACTOR_SYSTEM)


def requires_explicit_approval(origin: str) -> bool:
    """INTEGRITY_STOP recovery always needs a separate, explicit human approval (never same-request,
    never system-authorized)."""
    return origin == C.STATE_INTEGRITY_STOP


def may_authorize_pass(origin: str, trip_cause: str | None, role: str) -> bool:
    if role == C.ACTOR_SYSTEM:
        return False  # system may run checks but NEVER self-authorizes a pass (any origin)
    if origin == C.STATE_INTEGRITY_STOP:
        return role == C.ACTOR_RISK_OPERATOR
    if origin == C.STATE_REDUCTION_ONLY_DAILY_LOSS:
        return role in (C.ACTOR_OWNER, C.ACTOR_RISK_OPERATOR)
    if origin == C.STATE_REDUCTION_ONLY_BREAKER:
        if role == C.ACTOR_RISK_OPERATOR:
            return True
        return role == C.ACTOR_OWNER and trip_cause == C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS
    return False


# ------------------------------------------------------------------ structured result


@dataclass(frozen=True)
class RecoveryOutcome:
    accepted: bool
    status: str  # a PREFLIGHT_STATUS_* value, or a reject sentinel below
    preflight_id: int | None
    resulting_state: str | None
    aggregate_verdict: str | None
    reason: str | None = None

    @property
    def rejected(self) -> bool:
        return not self.accepted


def _reject(status: str, reason: str) -> RecoveryOutcome:
    return RecoveryOutcome(accepted=False, status=status, preflight_id=None,
                           resulting_state=None, aggregate_verdict=None, reason=reason)


class RecoveryPreflightService:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    # ---- transitions (each on a dedicated session; request_transition commits it) ----

    async def _transition(
        self, *, account_id: int, trigger: str, expected_version: int,
        origin: str | None = None,
    ) -> object | None:
        """Fire one transition on a fresh session. Returns the TransitionResult, or None if the
        write RAISED (COMMIT_FAILED — the caller must not read a possibly-stale row and continue)."""
        try:
            async with self._session_factory() as s:
                return await LossControlService(s).request_transition(
                    account_id=account_id, trigger=trigger,
                    expected_state_version=expected_version,
                    recovery_origin_state=origin,
                    context=TransitionContext(initiator_type="SYSTEM"),
                )
        except Exception:  # noqa: BLE001 — CancelledError propagates; any other = COMMIT_FAILED
            logger.warning("recovery_transition_failed", account_id=account_id, trigger=trigger,
                           exc_info=True)
            return None

    # ---- request ----

    async def request_recovery(
        self, *, account_id: int, account_owner_id: int, idempotency_key: str,
        requester_user_id: int, adapter: object | None = None,
    ) -> RecoveryOutcome:
        role = actor_role(requester_user_id, account_owner_id)
        if role is None:
            return _reject(C.PREFLIGHT_STATUS_FAILED, C.ERR_NOT_AUTHORIZED)

        async with self._session_factory() as s:
            # Idempotency FIRST — a retry returns the existing workflow, whatever the current state.
            existing = await self._load_by_key(s, account_id, idempotency_key)
            if existing is not None:
                if existing.requested_by_actor_id != str(requester_user_id):
                    return _reject(existing.status, C.ERR_IDEMPOTENCY_CONFLICT)
                return _outcome_from(existing)

            state_row = await LossControlService(s).load_state_row(account_id)  # NO bootstrap
            if state_row is None or state_row.state not in _ELIGIBLE_ORIGINS:
                if state_row is not None and state_row.state == C.STATE_RECOVERY_PREFLIGHT:
                    # A recovery is already in flight — return its active preflight idempotently.
                    active = await self._load_active(s, account_id)
                    if active is not None:
                        return _outcome_from(active)
                return _reject(C.PREFLIGHT_STATUS_FAILED, C.ERR_NOT_ELIGIBLE)

            origin_candidate = state_row.state
            if not may_request(origin_candidate, role):
                return _reject(C.PREFLIGHT_STATUS_FAILED, C.ERR_NOT_AUTHORIZED)

            # One active preflight per account (a different in-flight key).
            active = await self._load_active(s, account_id)
            if active is not None:
                return _reject(C.PREFLIGHT_STATUS_FAILED, C.ERR_ACTIVE_PREFLIGHT_EXISTS)

            expected_version = state_row.state_version

        # Commit RECOVERY_REQUEST → RECOVERY_PREFLIGHT (dedicated session).
        result = await self._transition(
            account_id=account_id, trigger=TRIGGER_RECOVERY_REQUEST,
            expected_version=expected_version,
        )
        if result is None:
            return await self._persist_commit_failed(
                account_id, idempotency_key, requester_user_id, role, expected_version,
                origin_candidate,
            )
        if not getattr(result, "applied", False):
            # Stale / conflict / no-edge — state moved under us; do not run authoritative checks.
            return _reject(C.PREFLIGHT_STATUS_FAILED, C.ERR_NOT_ELIGIBLE)

        event_id = result.event_id  # type: ignore[attr-defined]
        # Now run the authoritative workflow.
        return await self._run_workflow(
            account_id=account_id, idempotency_key=idempotency_key,
            requester_user_id=requester_user_id, role=role,
            origin=origin_candidate, expected_version=expected_version,
            request_event_id=event_id, adapter=adapter,
        )

    async def _run_workflow(
        self, *, account_id: int, idempotency_key: str, requester_user_id: int, role: str,
        origin: str, expected_version: int, request_event_id: int | None, adapter: object | None,
    ) -> RecoveryOutcome:
        async with self._session_factory() as s:
            request_event = (
                await s.get(RiskControlEvent, request_event_id) if request_event_id else None
            )
            # Durable origin = the committed RECOVERY_REQUEST event's from_state (never inferred).
            durable_origin = request_event.from_state if request_event is not None else None
            trip_type = _ORIGIN_TRIP_TYPE.get(origin)
            trip_cause = await self._lock_trip_cause(s, account_id, origin, request_event_id)
            now = datetime.now(UTC)
            authority_class = _ORIGIN_AUTHORITY_CLASS[origin]

            parent = RiskRecoveryPreflight(
                account_id=account_id, idempotency_key=idempotency_key,
                requested_transition=TRIGGER_RECOVERY_REQUEST,
                expected_state_version=expected_version,
                requested_by_actor_type=role, requested_by_actor_id=str(requester_user_id),
                requested_at=now, origin_state=durable_origin,
                origin_state_version=expected_version, request_event_id=request_event_id,
                trip_type=trip_type, trip_cause=trip_cause, authority_class=authority_class,
                status=C.PREFLIGHT_STATUS_RUNNING, result=C.PREFLIGHT_STATUS_RUNNING,
                initiator_type=role, initiator_id=str(requester_user_id),
                control_version=C.LOSS_CONTROL_STATE_VERSION,
                evidence_version=C.RECOVERY_EVIDENCE_VERSION,
                created_at=now, started_at=now,
            )
            try:
                s.add(parent)
                await s.flush()
            except IntegrityError:  # concurrent duplicate — reload the winner
                await s.rollback()
                winner = await self._load_by_key(s, account_id, idempotency_key)
                return _outcome_from(winner) if winner else _reject(
                    C.PREFLIGHT_STATUS_FAILED, C.ERR_ACTIVE_PREFLIGHT_EXISTS
                )
            preflight_id = parent.id

            ctx = pf.PreflightContext(
                session=s, account_id=account_id, origin_state=durable_origin,
                request_event=request_event, trip_type=trip_type, trip_cause=trip_cause,
                adapter=adapter,
            )
            results = await pf.run_preflight_checks(ctx)
            for r in results:
                s.add(RiskRecoveryPreflightCheck(
                    preflight_id=preflight_id, check_name=r.name, status=r.status,
                    evidence=json.dumps({**r.evidence, "reason": r.reason}), created_at=now,
                ))
            verdict = pf.aggregate_verdict(results)
            parent.aggregate_verdict = verdict
            first_non_pass = next((r for r in results if r.status != C.CHECK_PASS), None)
            await s.commit()

        # Drive the transition off the verdict + authority.
        if verdict != C.AGG_PASS:
            return await self._finalize_fail(
                account_id, preflight_id, origin, expected_version, verdict,
                first_non_pass.reason if first_non_pass else None,
            )
        return await self._finalize_pass_or_await(
            account_id, preflight_id, origin, trip_cause, role, expected_version,
        )

    # ---- finalizers ----

    async def _finalize_fail(
        self, account_id: int, preflight_id: int, origin: str, expected_version: int,
        verdict: str, reason: str | None,
    ) -> RecoveryOutcome:
        result = await self._transition(
            account_id=account_id, trigger=TRIGGER_PREFLIGHT_FAIL,
            expected_version=expected_version + 1,  # RECOVERY_REQUEST already bumped it once
            origin=origin,
        )
        status = (
            C.PREFLIGHT_STATUS_FAILED if verdict == C.AGG_FAIL else C.PREFLIGHT_STATUS_INCOMPLETE
        )
        return await self._close_parent(
            account_id, preflight_id, status=status, verdict=verdict,
            transition=result, failure_reason=reason,
        )

    async def _finalize_pass_or_await(
        self, account_id: int, preflight_id: int, origin: str, trip_cause: str | None,
        role: str, expected_version: int,
    ) -> RecoveryOutcome:
        # INTEGRITY_STOP always awaits an explicit human approval; otherwise the requester may
        # self-authorize iff the matrix permits it. System never self-authorizes.
        if requires_explicit_approval(origin) or not may_authorize_pass(origin, trip_cause, role):
            return await self._close_parent(
                account_id, preflight_id, status=C.PREFLIGHT_STATUS_AUTHORIZATION_REQUIRED,
                verdict=C.AGG_PASS, transition=None, failure_reason=C.ERR_AUTHORIZATION_REQUIRED,
                authorized_by=None,
            )
        return await self._commit_pass(
            account_id, preflight_id, expected_version, authorizer_type=role,
            authorizer_id=None,
        )

    async def _commit_pass(
        self, account_id: int, preflight_id: int, expected_version: int,
        authorizer_type: str, authorizer_id: str | None,
    ) -> RecoveryOutcome:
        result = await self._transition(
            account_id=account_id, trigger=TRIGGER_PREFLIGHT_PASS,
            expected_version=expected_version + 1,  # after RECOVERY_REQUEST's bump
        )
        if result is None or not getattr(result, "applied", False):
            # Do NOT claim recovery on a failed/blocked pass transition.
            return await self._close_parent(
                account_id, preflight_id, status=C.PREFLIGHT_STATUS_COMMIT_FAILED,
                verdict=C.AGG_PASS, transition=None,
                failure_reason=C.ERR_TRANSITION_COMMIT_FAILED,
            )
        return await self._close_parent(
            account_id, preflight_id, status=C.PREFLIGHT_STATUS_PASSED, verdict=C.AGG_PASS,
            transition=result, failure_reason=None, authorized_by=(authorizer_type, authorizer_id),
        )

    async def _close_parent(
        self, account_id: int, preflight_id: int, *, status: str, verdict: str,
        transition: object | None, failure_reason: str | None,
        authorized_by: tuple[str, str | None] | None = None,
    ) -> RecoveryOutcome:
        async with self._session_factory() as s:
            parent = await s.get(RiskRecoveryPreflight, preflight_id)
            if parent is None:
                return _reject(status, C.ERR_INTERNAL)
            now = datetime.now(UTC)
            parent.status = status
            parent.result = status
            parent.aggregate_verdict = verdict
            parent.failure_reason = failure_reason
            if authorized_by is not None:
                parent.authorized_by_actor_type, parent.authorized_by_actor_id = authorized_by
            if transition is not None and getattr(transition, "applied", False):
                parent.transition_event_id = transition.event_id  # type: ignore[attr-defined]
            if status in (C.PREFLIGHT_STATUS_PASSED, C.PREFLIGHT_STATUS_FAILED,
                          C.PREFLIGHT_STATUS_INCOMPLETE, C.PREFLIGHT_STATUS_COMMIT_FAILED):
                parent.completed_at = now
                parent.resolved_at = now
            await s.commit()
            resulting_state = getattr(transition, "state", None) if transition is not None else None
            return RecoveryOutcome(
                accepted=True, status=status, preflight_id=preflight_id,
                resulting_state=resulting_state, aggregate_verdict=verdict, reason=failure_reason,
            )

    async def _persist_commit_failed(
        self, account_id: int, idempotency_key: str, requester_user_id: int, role: str,
        expected_version: int, origin: str,
    ) -> RecoveryOutcome:
        async with self._session_factory() as s:
            now = datetime.now(UTC)
            parent = RiskRecoveryPreflight(
                account_id=account_id, idempotency_key=idempotency_key,
                requested_transition=TRIGGER_RECOVERY_REQUEST,
                expected_state_version=expected_version,
                requested_by_actor_type=role, requested_by_actor_id=str(requester_user_id),
                requested_at=now, origin_state=None, origin_state_version=expected_version,
                trip_type=_ORIGIN_TRIP_TYPE.get(origin),
                authority_class=_ORIGIN_AUTHORITY_CLASS[origin],
                status=C.PREFLIGHT_STATUS_COMMIT_FAILED, result=C.PREFLIGHT_STATUS_COMMIT_FAILED,
                failure_reason=C.ERR_TRANSITION_COMMIT_FAILED,
                initiator_type=role, initiator_id=str(requester_user_id),
                control_version=C.LOSS_CONTROL_STATE_VERSION,
                evidence_version=C.RECOVERY_EVIDENCE_VERSION, created_at=now, completed_at=now,
                resolved_at=now,
            )
            try:
                s.add(parent)
                await s.commit()
            except IntegrityError:
                await s.rollback()
                winner = await self._load_by_key(s, account_id, idempotency_key)
                if winner:
                    return _outcome_from(winner)
            return RecoveryOutcome(
                accepted=True, status=C.PREFLIGHT_STATUS_COMMIT_FAILED, preflight_id=parent.id,
                resulting_state=None, aggregate_verdict=None,
                reason=C.ERR_TRANSITION_COMMIT_FAILED,
            )

    # ---- approve (explicit human authorization for AUTHORIZATION_REQUIRED preflights) ----

    async def approve(
        self, *, account_id: int, account_owner_id: int, preflight_id: int, approver_user_id: int,
    ) -> RecoveryOutcome:
        role = actor_role(approver_user_id, account_owner_id)
        if role is None:
            return _reject(C.PREFLIGHT_STATUS_AUTHORIZATION_REQUIRED, C.ERR_NOT_AUTHORIZED)
        async with self._session_factory() as s:
            parent = await s.get(RiskRecoveryPreflight, preflight_id)
            if parent is None or parent.account_id != account_id:
                return _reject(C.PREFLIGHT_STATUS_FAILED, C.ERR_NOT_ELIGIBLE)
            if parent.status == C.PREFLIGHT_STATUS_PASSED:
                return _outcome_from(parent)  # idempotent
            if parent.status != C.PREFLIGHT_STATUS_AUTHORIZATION_REQUIRED or (
                parent.aggregate_verdict != C.AGG_PASS
            ):
                return _reject(parent.status, C.ERR_NOT_ELIGIBLE)
            origin = parent.origin_state or ""
            if not may_authorize_pass(origin, parent.trip_cause, role):
                return _reject(parent.status, C.ERR_NOT_AUTHORIZED)
            expected_version = parent.expected_state_version
            state_row = await s.scalar(
                select(RiskLossControlState).where(
                    RiskLossControlState.account_id == account_id
                )
            )
            # Staleness: the account must still be sitting in RECOVERY_PREFLIGHT at the expected
            # version+1 (RECOVERY_REQUEST already bumped once). If it moved, the evidence is stale.
            if state_row is None or state_row.state != C.STATE_RECOVERY_PREFLIGHT:
                return _reject(parent.status, C.ERR_NOT_ELIGIBLE)

        return await self._commit_pass(
            account_id, preflight_id, expected_version, authorizer_type=role,
            authorizer_id=str(approver_user_id),
        )

    # ---- reads ----

    async def get(
        self, account_id: int, preflight_id: int
    ) -> tuple[RiskRecoveryPreflight, list[RiskRecoveryPreflightCheck]] | None:
        async with self._session_factory() as s:
            parent = await s.get(RiskRecoveryPreflight, preflight_id)
            if parent is None or parent.account_id != account_id:
                return None
            checks = list(
                (
                    await s.execute(
                        select(RiskRecoveryPreflightCheck)
                        .where(RiskRecoveryPreflightCheck.preflight_id == preflight_id)
                        .order_by(RiskRecoveryPreflightCheck.id)
                    )
                ).scalars().all()
            )
            return parent, checks

    async def _load_by_key(
        self, s: AsyncSession, account_id: int, key: str
    ) -> RiskRecoveryPreflight | None:
        return await s.scalar(
            select(RiskRecoveryPreflight).where(
                RiskRecoveryPreflight.account_id == account_id,
                RiskRecoveryPreflight.idempotency_key == key,
            )
        )

    async def _load_active(
        self, s: AsyncSession, account_id: int
    ) -> RiskRecoveryPreflight | None:
        return await s.scalar(
            select(RiskRecoveryPreflight).where(
                RiskRecoveryPreflight.account_id == account_id,
                RiskRecoveryPreflight.status.in_(C.ACTIVE_PREFLIGHT_STATUSES),
            )
        )

    async def _lock_trip_cause(
        self, s: AsyncSession, account_id: int, origin: str, before_event_id: int | None
    ) -> str | None:
        """The DURABLE trip cause from the event that entered the lock — never invented. The latest
        event whose to_state == origin, before the RECOVERY_REQUEST event."""
        q = (
            select(RiskControlEvent.trip_cause)
            .where(
                RiskControlEvent.account_id == account_id,
                RiskControlEvent.to_state == origin,
            )
            .order_by(RiskControlEvent.id.desc())
        )
        if before_event_id is not None:
            q = q.where(RiskControlEvent.id < before_event_id)
        return await s.scalar(q)


def _outcome_from(parent: RiskRecoveryPreflight) -> RecoveryOutcome:
    return RecoveryOutcome(
        accepted=True, status=parent.status, preflight_id=parent.id, resulting_state=None,
        aggregate_verdict=parent.aggregate_verdict, reason=parent.failure_reason,
    )
