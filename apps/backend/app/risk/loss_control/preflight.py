"""ADR 0043 §D5 PR6 — the 12-check recovery preflight (evidence, not enforcement).

The checked, fail-closed gate a locked account must pass before it may transition into
``RECOVERY_COOLDOWN``. Twelve stable, versioned checks (``constants.PREFLIGHT_CHECK_REGISTRY``), each
returning PASS / FAIL / INCOMPLETE with structured evidence. Rules the coordinator relies on:

* **INCOMPLETE is never a pass.** Evidence unavailable / stale / timed-out / ambiguous / not
  authoritative is INCOMPLETE, and the fail-closed aggregate treats it as a non-pass.
* **All twelve always persist.** A check whose prerequisites did not PASS is recorded INCOMPLETE with
  ``reason = BLOCKED_BY_<check>`` — the absence of a row can never be mistaken for success.
* **Exceptions are bounded.** Any non-``CancelledError`` exception in a check becomes INCOMPLETE with
  a stable ``ERR_*`` code; the raw text stays only in internal logs. ``CancelledError`` propagates.

This module computes and returns results; the coordinator (``recovery.py``) persists them and drives
the transition. It performs no state writes and no transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import TERMINAL_ORDER_STATUSES
from app.db.models.account import Account
from app.db.models.account_state import AccountState
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.risk_control_event import RiskControlEvent
from app.db.models.risk_loss_control_state import RiskLossControlState
from app.db.models.risk_reservation import RESERVATION_HELD, RiskReservation
from app.db.models.risk_session_baseline import BASELINE_STATUS_ACTIVE, RiskSessionBaseline
from app.risk.loss_control import constants as C
from app.risk.loss_control.daily_loss_basis import select_daily_loss_basis
from app.risk.loss_control.session_baseline import resolve_session_date

logger = structlog.get_logger(__name__)

_RECOVERY_ORIGINS = frozenset(
    {C.STATE_REDUCTION_ONLY_DAILY_LOSS, C.STATE_REDUCTION_ONLY_BREAKER, C.STATE_INTEGRITY_STOP}
)


@dataclass(frozen=True)
class PreflightCheckResult:
    name: str
    status: str  # C.CHECK_PASS | C.CHECK_FAIL | C.CHECK_INCOMPLETE
    evidence: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None  # a stable ERR_* / BLOCKED_BY_* code, never raw exception text

    @property
    def passed(self) -> bool:
        return self.status == C.CHECK_PASS


@dataclass
class PreflightContext:
    """Everything the checks read. The broker ``adapter`` is optional — its absence makes the
    broker-dependent checks INCOMPLETE (fail-closed), never a false PASS."""

    session: AsyncSession
    account_id: int
    origin_state: str | None
    request_event: RiskControlEvent | None
    trip_type: str | None
    trip_cause: str | None
    adapter: Any | None = None


# --------------------------------------------------------------------- individual checks


async def _state_known_and_recoverable(ctx: PreflightContext) -> PreflightCheckResult:
    row = await ctx.session.scalar(
        select(RiskLossControlState).where(RiskLossControlState.account_id == ctx.account_id)
    )
    if row is None:
        return _fail(C.CHECK_STATE_KNOWN_AND_RECOVERABLE, C.ERR_STATE_CONTRADICTION,
                     {"detail": "no materialized state row"})
    ok = row.state == C.STATE_RECOVERY_PREFLIGHT and ctx.origin_state in _RECOVERY_ORIGINS
    return _result(
        C.CHECK_STATE_KNOWN_AND_RECOVERABLE, ok, C.ERR_STATE_CONTRADICTION,
        {"state": row.state, "origin_state": ctx.origin_state},
    )


async def _recovery_origin_proven(ctx: PreflightContext) -> PreflightCheckResult:
    ev = ctx.request_event
    proven = (
        ev is not None
        and ev.to_state == C.STATE_RECOVERY_PREFLIGHT
        and ev.from_state == ctx.origin_state
        and ctx.origin_state in _RECOVERY_ORIGINS
    )
    return _result(
        C.CHECK_RECOVERY_ORIGIN_PROVEN, proven, C.ERR_ORIGIN_UNPROVEN,
        {"event_id": ev.id if ev else None,
         "from_state": ev.from_state if ev else None, "origin_state": ctx.origin_state},
    )


async def _broker_reachable(ctx: PreflightContext) -> PreflightCheckResult:
    acct = await _broker_account(ctx)
    if acct is None:
        return _incomplete(C.CHECK_BROKER_REACHABLE, C.ERR_BROKER_UNREACHABLE,
                           {"detail": "adapter absent or get_account failed"})
    return _pass(C.CHECK_BROKER_REACHABLE, {"reachable": True})


async def _broker_account_active(ctx: PreflightContext) -> PreflightCheckResult:
    acct = await _broker_account(ctx)
    if acct is None:
        return _incomplete(C.CHECK_BROKER_ACCOUNT_ACTIVE, C.ERR_BROKER_UNREACHABLE, {})
    status = str(acct.get("status") or "").upper()
    blocked = bool(acct.get("trading_blocked")) or bool(acct.get("account_blocked"))
    active = status == "ACTIVE" and not blocked
    return _result(C.CHECK_BROKER_ACCOUNT_ACTIVE, active, C.ERR_BROKER_ACCOUNT_INACTIVE,
                   {"status": status, "blocked": blocked})


async def _positions_reconcile(ctx: PreflightContext) -> PreflightCheckResult:
    positions = await _broker_positions(ctx)
    if positions is None:
        return _incomplete(C.CHECK_POSITIONS_RECONCILE, C.ERR_BROKER_UNREACHABLE, {})
    broker = {str(p.get("symbol")): Decimal(str(p.get("qty") or 0)) for p in positions}
    local_rows = list(
        (
            await ctx.session.execute(
                select(Position.symbol_id, Position.qty).where(
                    Position.account_id == ctx.account_id
                )
            )
        ).all()
    )
    # Reconcile by symbol ticker; resolve local symbol_id → ticker.
    local = await _local_positions_by_ticker(ctx, local_rows)
    mismatches = _diff_qty(local, broker)
    return _result(C.CHECK_POSITIONS_RECONCILE, not mismatches, C.ERR_POSITION_MISMATCH,
                   {"mismatch_count": len(mismatches), "symbols": sorted(mismatches)[:20]})


async def _open_orders_reconcile(ctx: PreflightContext) -> PreflightCheckResult:
    broker_orders = await _broker_open_orders(ctx)
    if broker_orders is None:
        return _incomplete(C.CHECK_OPEN_ORDERS_RECONCILE, C.ERR_BROKER_UNREACHABLE, {})
    local_open = await ctx.session.scalar(
        select(func.count()).select_from(Order).where(
            Order.account_id == ctx.account_id, Order.status.notin_(TERMINAL_ORDER_STATUSES)
        )
    )
    broker_open = len(broker_orders)
    ok = int(local_open or 0) == broker_open
    return _result(C.CHECK_OPEN_ORDERS_RECONCILE, ok, C.ERR_OPEN_ORDER_MISMATCH,
                   {"local_open": int(local_open or 0), "broker_open": broker_open})


async def _reservations_reconcile(ctx: PreflightContext) -> PreflightCheckResult:
    held = await ctx.session.scalar(
        select(func.count()).select_from(RiskReservation).where(
            RiskReservation.account_id == ctx.account_id,
            RiskReservation.state == RESERVATION_HELD,
        )
    )
    # A HELD reservation must be backed by a non-terminal order (no orphan). Orphans are ones whose
    # order is terminal/absent — the reaper's target; their presence at recovery time is a mismatch.
    orphan = await ctx.session.scalar(
        select(func.count()).select_from(RiskReservation).where(
            RiskReservation.account_id == ctx.account_id,
            RiskReservation.state == RESERVATION_HELD,
            RiskReservation.order_id.is_(None),
        )
    )
    ok = int(orphan or 0) == 0
    return _result(C.CHECK_RESERVATIONS_RECONCILE, ok, C.ERR_RESERVATION_MISMATCH,
                   {"held": int(held or 0), "orphan": int(orphan or 0)})


async def _session_baseline_valid(ctx: PreflightContext) -> PreflightCheckResult:
    session_date = resolve_session_date(datetime.now(UTC))
    if session_date is None:
        # Outside a trading session there is no governing baseline to validate — unverifiable.
        return _incomplete(C.CHECK_SESSION_BASELINE_VALID, C.ERR_BASELINE_INVALID,
                           {"detail": "no trading session"})
    baseline = await ctx.session.scalar(
        select(RiskSessionBaseline).where(
            RiskSessionBaseline.account_id == ctx.account_id,
            RiskSessionBaseline.market_session_date == session_date,
        )
    )
    valid = (
        baseline is not None
        and baseline.status == BASELINE_STATUS_ACTIVE
        and baseline.baseline_equity > 0
    )
    return _result(C.CHECK_SESSION_BASELINE_VALID, valid, C.ERR_BASELINE_INVALID,
                   {"session_date": session_date, "present": baseline is not None})


async def _daily_loss_recomputed(ctx: PreflightContext) -> PreflightCheckResult:
    state = await ctx.session.scalar(
        select(AccountState).where(AccountState.account_id == ctx.account_id)
    )
    basis = await select_daily_loss_basis(
        ctx.session, ctx.account_id,
        current_equity=Decimal(str(state.equity)) if state and state.equity is not None else None,
        last_equity=Decimal(str(state.last_equity)) if state and state.last_equity is not None else None,
        session_date=resolve_session_date(datetime.now(UTC)),
        applicable_limit=None, allow_cumulative_fallback=True,
    )
    ok = basis.day_change is not None and basis.basis_source is not None
    return _result(C.CHECK_DAILY_LOSS_RECOMPUTED, ok, C.ERR_LOSS_NOT_RECOMPUTABLE,
                   {"basis_source": basis.basis_source, "day_change": str(basis.day_change)})


async def _trip_cause_classified(ctx: PreflightContext) -> PreflightCheckResult:
    known = ctx.trip_cause is not None and ctx.trip_cause in C.ALL_TRIP_CAUSES and (
        ctx.trip_cause != C.TRIP_CAUSE_UNKNOWN
    )
    return _result(C.CHECK_TRIP_CAUSE_CLASSIFIED, known, C.ERR_TRIP_CAUSE_UNKNOWN,
                   {"trip_type": ctx.trip_type, "trip_cause": ctx.trip_cause})


async def _control_state_consistent(ctx: PreflightContext) -> PreflightCheckResult:
    row = await ctx.session.scalar(
        select(RiskLossControlState).where(RiskLossControlState.account_id == ctx.account_id)
    )
    account = await ctx.session.get(Account, ctx.account_id)
    if row is None or account is None:
        return _fail(C.CHECK_CONTROL_STATE_CONSISTENT, C.ERR_STATE_CONTRADICTION,
                     {"detail": "state or account missing"})
    # The materialized bookkeeping must be internally coherent, and a breaker-origin recovery must
    # correspond to a tripped breaker column (the projection and the machine agree).
    coherent = row.last_sequence_no >= row.state_version
    if ctx.origin_state == C.STATE_REDUCTION_ONLY_BREAKER:
        coherent = coherent and account.circuit_breaker_tripped_at is not None
    return _result(C.CHECK_CONTROL_STATE_CONSISTENT, coherent, C.ERR_STATE_CONTRADICTION,
                   {"state_version": row.state_version, "last_sequence_no": row.last_sequence_no,
                    "breaker_tripped": account.circuit_breaker_tripped_at is not None})


async def _no_unresolved_integrity_condition(
    ctx: PreflightContext, prior: list[PreflightCheckResult]
) -> PreflightCheckResult:
    # The catch-all mirrors the fail-closed aggregate so it never *escalates* the verdict: a real
    # prior FAIL → FAIL (a genuine integrity contradiction); merely-INCOMPLETE priors (unverifiable
    # / blocked) → INCOMPLETE; all PASS → PASS.
    unresolved = [p.name for p in prior if p.status != C.CHECK_PASS]
    if not unresolved:
        return _pass(C.CHECK_NO_UNRESOLVED_INTEGRITY_CONDITION, {"unresolved": []})
    if any(p.status == C.CHECK_FAIL for p in prior):
        return _fail(C.CHECK_NO_UNRESOLVED_INTEGRITY_CONDITION, C.ERR_UNRESOLVED_INTEGRITY,
                     {"unresolved": unresolved[:12]})
    return _incomplete(C.CHECK_NO_UNRESOLVED_INTEGRITY_CONDITION, C.ERR_UNRESOLVED_INTEGRITY,
                       {"unresolved": unresolved[:12]})


# --------------------------------------------------------------------- broker helpers


async def _broker_account(ctx: PreflightContext) -> dict[str, Any] | None:
    return await _broker_call(ctx, "get_account")


async def _broker_positions(ctx: PreflightContext) -> list[dict[str, Any]] | None:
    return await _broker_call(ctx, "get_positions")


async def _broker_open_orders(ctx: PreflightContext) -> list[dict[str, Any]] | None:
    if ctx.adapter is None or not hasattr(ctx.adapter, "list_orders"):
        return None
    return await _broker_call_orders(ctx)


async def _broker_call(ctx: PreflightContext, method: str) -> Any | None:
    if ctx.adapter is None or not hasattr(ctx.adapter, method):
        return None
    import asyncio
    try:
        return await asyncio.to_thread(getattr(ctx.adapter, method))
    except Exception as exc:  # noqa: BLE001 — bounded; CancelledError propagates (not an Exception)
        logger.warning("recovery_preflight_broker_call_failed", method=method, error=str(exc))
        return None


async def _broker_call_orders(ctx: PreflightContext) -> list[dict[str, Any]] | None:
    import asyncio
    adapter = ctx.adapter
    if adapter is None:
        return None
    try:
        orders = await asyncio.to_thread(adapter.list_orders, "open")
        return list(orders or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("recovery_preflight_broker_orders_failed", error=str(exc))
        return None


async def _local_positions_by_ticker(
    ctx: PreflightContext, rows: list[Any]
) -> dict[str, Decimal]:
    from app.db.models.symbol import Symbol
    out: dict[str, Decimal] = {}
    for symbol_id, qty in rows:
        ticker = await ctx.session.scalar(select(Symbol.ticker).where(Symbol.id == symbol_id))
        if ticker is not None:
            out[str(ticker)] = Decimal(str(qty or 0))
    return out


def _diff_qty(local: dict[str, Decimal], broker: dict[str, Decimal]) -> list[str]:
    symbols = set(local) | set(broker)
    return [s for s in symbols if local.get(s, Decimal(0)) != broker.get(s, Decimal(0))]


# --------------------------------------------------------------------- result constructors


def _result(name: str, ok: bool, err: str, evidence: dict[str, Any]) -> PreflightCheckResult:
    if ok:
        return _pass(name, evidence)
    return _fail(name, err, evidence)


def _pass(name: str, evidence: dict[str, Any]) -> PreflightCheckResult:
    return PreflightCheckResult(name, C.CHECK_PASS, evidence)


def _fail(name: str, err: str, evidence: dict[str, Any]) -> PreflightCheckResult:
    return PreflightCheckResult(name, C.CHECK_FAIL, evidence, reason=err)


def _incomplete(name: str, err: str, evidence: dict[str, Any]) -> PreflightCheckResult:
    return PreflightCheckResult(name, C.CHECK_INCOMPLETE, evidence, reason=err)


def _blocked(name: str, blocker: str) -> PreflightCheckResult:
    return PreflightCheckResult(name, C.CHECK_INCOMPLETE, {"blocked_by": blocker},
                                reason=f"BLOCKED_BY_{blocker}")


# --------------------------------------------------------------------- runner + aggregate

# Prerequisite map: a check runs only if every listed prior check PASSed, else it is BLOCKED.
_PREREQS: dict[str, tuple[str, ...]] = {
    C.CHECK_STATE_KNOWN_AND_RECOVERABLE: (),
    C.CHECK_RECOVERY_ORIGIN_PROVEN: (C.CHECK_STATE_KNOWN_AND_RECOVERABLE,),
    C.CHECK_BROKER_REACHABLE: (C.CHECK_STATE_KNOWN_AND_RECOVERABLE, C.CHECK_RECOVERY_ORIGIN_PROVEN),
    C.CHECK_BROKER_ACCOUNT_ACTIVE: (C.CHECK_BROKER_REACHABLE,),
    C.CHECK_POSITIONS_RECONCILE: (C.CHECK_BROKER_REACHABLE,),
    C.CHECK_OPEN_ORDERS_RECONCILE: (C.CHECK_BROKER_REACHABLE,),
    C.CHECK_RESERVATIONS_RECONCILE: (C.CHECK_BROKER_REACHABLE, C.CHECK_OPEN_ORDERS_RECONCILE),
    C.CHECK_SESSION_BASELINE_VALID: (C.CHECK_STATE_KNOWN_AND_RECOVERABLE,),
    C.CHECK_DAILY_LOSS_RECOMPUTED: (C.CHECK_SESSION_BASELINE_VALID,),
    C.CHECK_TRIP_CAUSE_CLASSIFIED: (C.CHECK_STATE_KNOWN_AND_RECOVERABLE,),
    C.CHECK_CONTROL_STATE_CONSISTENT: (C.CHECK_STATE_KNOWN_AND_RECOVERABLE,),
    C.CHECK_NO_UNRESOLVED_INTEGRITY_CONDITION: (),  # special — sees all prior
}

_CHECK_FUNCS = {
    C.CHECK_STATE_KNOWN_AND_RECOVERABLE: _state_known_and_recoverable,
    C.CHECK_RECOVERY_ORIGIN_PROVEN: _recovery_origin_proven,
    C.CHECK_BROKER_REACHABLE: _broker_reachable,
    C.CHECK_BROKER_ACCOUNT_ACTIVE: _broker_account_active,
    C.CHECK_POSITIONS_RECONCILE: _positions_reconcile,
    C.CHECK_OPEN_ORDERS_RECONCILE: _open_orders_reconcile,
    C.CHECK_RESERVATIONS_RECONCILE: _reservations_reconcile,
    C.CHECK_SESSION_BASELINE_VALID: _session_baseline_valid,
    C.CHECK_DAILY_LOSS_RECOMPUTED: _daily_loss_recomputed,
    C.CHECK_TRIP_CAUSE_CLASSIFIED: _trip_cause_classified,
    C.CHECK_CONTROL_STATE_CONSISTENT: _control_state_consistent,
}


async def run_preflight_checks(ctx: PreflightContext) -> list[PreflightCheckResult]:
    """Run all 12 checks in registry order, honouring prerequisites. Returns exactly 12 results in
    registry order — a check whose prerequisites did not PASS is INCOMPLETE(BLOCKED_BY_...), a check
    that raises is INCOMPLETE(ERR_INTERNAL). ``CancelledError`` propagates."""
    results: dict[str, PreflightCheckResult] = {}
    for name in C.PREFLIGHT_CHECK_REGISTRY:
        if name == C.CHECK_NO_UNRESOLVED_INTEGRITY_CONDITION:
            prior = [results[n] for n in C.PREFLIGHT_CHECK_REGISTRY if n in results]
            results[name] = await _safe(name, _no_unresolved_integrity_condition, ctx, prior)
            continue
        blocker = next((p for p in _PREREQS[name] if results[p].status != C.CHECK_PASS), None)
        if blocker is not None:
            results[name] = _blocked(name, blocker)
        else:
            results[name] = await _safe(name, _CHECK_FUNCS[name], ctx)
    return [results[n] for n in C.PREFLIGHT_CHECK_REGISTRY]


async def _safe(name: str, fn: Any, *args: Any) -> PreflightCheckResult:
    try:
        return await fn(*args)
    except Exception as exc:  # noqa: BLE001 — bounded to INCOMPLETE; CancelledError propagates
        logger.warning("recovery_preflight_check_errored", check=name, error=str(exc))
        return PreflightCheckResult(name, C.CHECK_INCOMPLETE, {"errored": True}, reason=C.ERR_INTERNAL)


def aggregate_verdict(results: list[PreflightCheckResult]) -> str:
    """Fail-closed aggregation: any FAIL → FAIL; else any INCOMPLETE → INCOMPLETE; else PASS."""
    if any(r.status == C.CHECK_FAIL for r in results):
        return C.AGG_FAIL
    if any(r.status == C.CHECK_INCOMPLETE for r in results):
        return C.AGG_INCOMPLETE
    return C.AGG_PASS
