"""Cold-start seed reconciliation — the single, safety-critical state machine.

P7 §7-A.2a (momentum-daily cold-start repair). Pure function over *normalized
observations* (fills, open orders, positions), callable identically from the
strategy's ``on_bar`` (7-A) and from order/fill ingestion (7-B) — one
implementation, no event-specific fork.

Design rules (owner refinements):
- **Qualify on ``filled_quantity > 0``, NOT order status.** The order model has no
  fill-void/reversal concept; a fill stays valid even if its order later reached a
  terminal ``CANCELED`` (partial-fill-then-cancel).
- **The qualifying fill is the deployment AUTHORITY; positions only corroborate or
  contradict — they never prove attribution.** On a shared account, account-level
  positions can be netted by other sources, so a qualifying fill establishes
  ``DEPLOYED`` and a position anomaly becomes a NON-BLOCKING alert. Full blocking
  (``RECONCILIATION_REQUIRED``) is reserved for genuine ambiguity: a position with
  NO attributed fill (no authority to establish deployment).
- **Two lifecycles, distinct questions.** ``deployment_state`` answers "has the
  strategy ever established attributable exposure?"; ``seed_attempt_status`` answers
  "has the initial order set reached a terminal reconciled condition?" A book can be
  ``DEPLOYED`` while its attempt is still ``PARTIALLY_FILLED`` — the caller MUST keep
  reconciling the attempt after deployment.
- **Cursor split.** ``observed_cursor`` = highest fill read; ``committed_cursor`` =
  highest fill fully incorporated. The caller persists ``committed_cursor``, so an
  unresolved fill (attributed but exposure not yet visible) is re-read on a later
  poll and re-evaluated once position state catches up. ``unresolved_fill_ids`` is
  carried for durability.
- **Terminal attempts are archived, not erased.** ``should_clear_attempt`` means
  "archive the active attempt to history, then clear it" — never physically delete
  (forensics for risk rejections, sizing-to-zero, broker/config failures).
- The result carries next-state PLUS explicit actions and mutates nothing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.strategies.context import FillEvent, OpenOrderObs

__all__ = [
    "DeploymentState",
    "SeedAttemptStatus",
    "OpenOrderObs",
    "SeedAttempt",
    "ReconciliationResult",
    "reconcile_seed_attempt",
]


class DeploymentState(StrEnum):
    NEVER_DEPLOYED = "NEVER_DEPLOYED"
    DEPLOYMENT_PENDING = "DEPLOYMENT_PENDING"
    DEPLOYED = "DEPLOYED"
    INTENTIONALLY_FLAT = "INTENTIONALLY_FLAT"


class SeedAttemptStatus(StrEnum):
    PREPARED = "PREPARED"
    SUBMITTING = "SUBMITTING"
    ORDERS_OPEN = "ORDERS_OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    TERMINALLY_UNFILLED = "TERMINALLY_UNFILLED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass
class SeedAttempt:
    """Durable write-ahead record of one initial_seed attempt (persisted as JSON in
    ``strategy_state``). The cursor is the last COMMITTED ``(filled_at, fill_id)``."""

    attempt_id: str
    created_at: datetime
    intended_symbols: tuple[str, ...]
    client_order_id_prefix: str
    submitted_order_ids: tuple[int, ...] = ()
    status: SeedAttemptStatus = SeedAttemptStatus.PREPARED
    last_reconciled_fill_at: datetime | None = None
    last_reconciled_fill_id: int | None = None


@dataclass(frozen=True)
class ReconciliationResult:
    """Next state + explicit actions. Mutates nothing; the caller applies it.

    ``alerts`` is a NON-BLOCKING channel and may accompany a ``DEPLOYED`` result
    (e.g. an unrelated unattributed position). ``RECONCILIATION_REQUIRED`` is the
    blocking status, reserved for genuine ambiguity.
    """

    deployment_state: DeploymentState
    seed_attempt_status: SeedAttemptStatus
    qualifying_fill_ids: tuple[int, ...] = ()
    first_deployed_at: datetime | None = None
    observed_cursor: tuple[datetime, int] | None = None
    committed_cursor: tuple[datetime, int] | None = None
    unresolved_fill_ids: tuple[int, ...] = ()
    alerts: tuple[str, ...] = ()
    should_clear_attempt: bool = False


def _is_attributable(fill: FillEvent, attempt: SeedAttempt) -> bool:
    """Attribution = fill->order relationship + strategy scope (already enforced by
    ``recent_fills``) AND this attempt's tag: the order id was one we submitted, or
    the client_order_id carries our attempt prefix. A malformed/user client-order id
    alone cannot qualify because the fills were scoped to this strategy+account
    upstream."""
    if fill.order_id in attempt.submitted_order_ids:
        return True
    coid = fill.client_order_id or ""
    return bool(attempt.client_order_id_prefix) and coid.startswith(
        attempt.client_order_id_prefix
    )


def _prior_cursor(attempt: SeedAttempt) -> tuple[datetime, int] | None:
    if attempt.last_reconciled_fill_at is None:
        return None
    return (attempt.last_reconciled_fill_at, attempt.last_reconciled_fill_id or 0)


def _watermark(
    fills: Sequence[FillEvent],
    unresolved: Sequence[FillEvent],
    prior: tuple[datetime, int] | None,
) -> tuple[tuple[datetime, int] | None, tuple[int, ...]]:
    """committed cursor = highest fill strictly below the earliest unresolved fill,
    so every unresolved fill is re-read next poll (``since = committed_cursor``)."""
    if not unresolved:
        obs = max(((f.filled_at, f.fill_id) for f in fills), default=prior)
        return obs, ()
    earliest = min((f.filled_at, f.fill_id) for f in unresolved)
    below = [(f.filled_at, f.fill_id) for f in fills if (f.filled_at, f.fill_id) < earliest]
    committed = max(below, default=prior)
    return committed, tuple(sorted(f.fill_id for f in unresolved))


def reconcile_seed_attempt(
    attempt: SeedAttempt,
    fills: Sequence[FillEvent],
    open_orders: Sequence[OpenOrderObs],
    positions: Mapping[str, Decimal],
) -> ReconciliationResult:
    """Decide the deployment lifecycle transition for ``attempt`` from observations.

    ``fills`` are ALL fills for this strategy+account since the attempt cursor
    (already scoped by ``recent_fills``); ``open_orders`` are this strategy's
    still-open orders; ``positions`` maps symbol -> current qty for the account.
    Idempotent: re-running with the same/superset observations yields the same
    terminal decision, ``first_deployed_at`` is stable (taken from the earliest
    qualifying fill, not "now"), and the committed cursor only advances past
    incorporated fills.
    """
    # Idempotency: dedup replayed fill rows by fill_id (first occurrence wins), so a
    # re-poll or an overlapping event+poll never double-counts a fill.
    seen_ids: set[int] = set()
    deduped: list[FillEvent] = []
    for f in fills:
        if f.fill_id in seen_ids:
            continue
        seen_ids.add(f.fill_id)
        deduped.append(f)
    fills = deduped

    pos = {s.upper(): q for s, q in positions.items()}
    qfills = [f for f in fills if f.qty > 0 and _is_attributable(f, attempt)]
    qsymbols = {f.symbol.upper() for f in qfills}
    has_open = bool(open_orders)

    # symbol-level: qualifying fills whose OWN symbol shows no attributable exposure
    unexposed = [f for f in qfills if pos.get(f.symbol.upper(), Decimal(0)) <= 0]
    # a position in a symbol with NO qualifying fill is unattributed
    unattributed = {s for s, q in pos.items() if q > 0 and s not in qsymbols}

    observed = max(((f.filled_at, f.fill_id) for f in fills), default=_prior_cursor(attempt))

    if qfills:
        # Qualifying fill is the deployment AUTHORITY (positions corroborate only).
        alerts: list[str] = []
        if unattributed:
            alerts.append("unattributed_position_during_seed")
        if unexposed:
            alerts.append("fill_without_exposure")
        committed, unresolved_ids = _watermark(fills, unexposed, _prior_cursor(attempt))
        clean_done = (not has_open) and (not unexposed)
        status = SeedAttemptStatus.FILLED if clean_done else SeedAttemptStatus.PARTIALLY_FILLED
        return ReconciliationResult(
            deployment_state=DeploymentState.DEPLOYED,
            seed_attempt_status=status,
            qualifying_fill_ids=tuple(sorted(f.fill_id for f in qfills)),
            first_deployed_at=min(f.filled_at for f in qfills),
            observed_cursor=observed,
            committed_cursor=committed,
            unresolved_fill_ids=unresolved_ids,
            alerts=tuple(alerts),
            should_clear_attempt=clean_done,
        )

    # No qualifying fills yet.
    if unattributed:
        # Genuine ambiguity: a position we cannot attribute, and no fill authority to
        # establish deployment. Block, and do NOT advance the committed cursor.
        return ReconciliationResult(
            deployment_state=DeploymentState.DEPLOYMENT_PENDING,
            seed_attempt_status=SeedAttemptStatus.RECONCILIATION_REQUIRED,
            observed_cursor=observed,
            committed_cursor=_prior_cursor(attempt),
            alerts=("unattributed_position_during_seed",),
        )
    if has_open:
        return ReconciliationResult(
            deployment_state=DeploymentState.DEPLOYMENT_PENDING,
            seed_attempt_status=SeedAttemptStatus.ORDERS_OPEN,
            observed_cursor=observed,
            committed_cursor=observed,
        )
    # No fills, no open orders => terminally unfilled; roll back to NEVER_DEPLOYED so
    # the next eligible review can retry. The caller ARCHIVES the attempt (not delete).
    return ReconciliationResult(
        deployment_state=DeploymentState.NEVER_DEPLOYED,
        seed_attempt_status=SeedAttemptStatus.TERMINALLY_UNFILLED,
        observed_cursor=observed,
        committed_cursor=observed,
        should_clear_attempt=True,
    )
