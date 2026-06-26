"""Replay service (P11 §4, ADR 0021) — re-verify automated decisions, READ-ONLY.

Reconstructs an automated decision from its DURABLE audit fingerprint and recomputes the
decision rule from the *recorded inputs*, asserting the recorded *decision* reproduces. It
validates **the decision, not the broker outcome**: the broker may legitimately fill
differently — replay proves the automation *decided correctly given its inputs*.

> Replay is a **verification service, not a simulation service.** It never re-executes
> strategy code, never calls the broker, never touches the order path, and never mutates
> state beyond appending its own `replay_runs` row + any `REPLAY_MISMATCH` audit entry.

**Determinism invariant.** Given the same audit fingerprint, the same `ALGORITHM_VERSION`,
and the same audit schema, replay always produces the same verdict — the recompute functions
are pure (no clock, no I/O, no randomness, no ambient state). That is what makes a historical
`replay_runs` row reproducible after future code evolves.

Pipeline: audit row → REPLAY_REGISTRY → ReplayVerifier.replay() → ReplayVerdict
          → metrics → audit_log (REPLAY_MISMATCH on mismatch) → replay_runs.

Extensibility: a new replayable decision = one new ``ReplayVerifier`` + one ``REPLAY_REGISTRY``
/ ``CAPABILITY`` entry (bump ``REGISTRY_VERSION``). The dispatcher is registry-driven, never
if/elif. ``CAPABILITY`` distinguishes ``unsupported`` (not built yet) from ``unreplayable``
(the fingerprint is missing required inputs — a different engineering problem); the overlay
and risk-check decisions are ``unreplayable`` pending the durable-fingerprint follow-on.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Protocol

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit.logger import AuditAction, AuditActorType, AuditLogger
from app.db.models.audit_log import AuditLog
from app.db.models.replay_run import ReplayRun
from app.observability.metrics import (
    replay_consistency_ratio,
    replay_coverage_ratio,
    replay_duration_seconds,
    replay_verifications_total,
)

logger = structlog.get_logger(__name__)

ALGORITHM_VERSION = "1.0"  # the recompute contract (see determinism invariant)
REGISTRY_VERSION = "1.0"   # the verifier-set version


class Verdict(StrEnum):
    MATCH = "match"        # decision reproduces from its recorded inputs
    MISMATCH = "mismatch"  # recorded decision is NOT justified by its recorded inputs (CRITICAL)
    SKIPPED = "skipped"    # intentionally unsupported (no verifier / unverifiable variant)
    ERROR = "error"        # the replay engine failed on this row (malformed payload, etc.)


@dataclass(frozen=True)
class ReplayVerdict:
    audit_log_id: int
    decision_type: str
    verdict: Verdict
    recorded: dict[str, Any]
    recomputed: dict[str, Any]
    note: str = ""


class ReplayVerifier(Protocol):
    decision_type: str  # the AuditAction value it handles
    capability: str     # 'supported' | 'unsupported' | 'unreplayable'

    def replay(self, audit_log_id: int, payload: dict[str, Any]) -> ReplayVerdict: ...


def _dec(v: Any) -> Decimal:
    return Decimal(str(v))


class BreakerTripVerifier:
    """Recompute the daily-loss circuit-breaker trip: net_pnl = realized + unrealized, and
    the trip rule net_pnl <= -max_daily_loss (app/risk/circuit_breaker.py). MATCH iff the
    recomputed net_pnl reproduces the recorded one AND the trip condition holds (the row
    exists because it tripped). A recorded trip whose recorded inputs do not satisfy the rule
    is the spurious-trip class — exactly what this catches."""

    decision_type = AuditAction.CIRCUIT_BREAKER_TRIPPED.value
    capability = "supported"

    def replay(self, audit_log_id: int, payload: dict[str, Any]) -> ReplayVerdict:
        realized = _dec(payload["realized_pnl_today"])
        unrealized = _dec(payload["unrealized_pnl_now"])
        recorded_net = _dec(payload["net_pnl"])
        max_loss = _dec(payload["max_daily_loss"])
        recomputed_net = realized + unrealized
        net_reproduces = recomputed_net == recorded_net
        rule_holds = recomputed_net <= -max_loss
        recorded = {"net_pnl": str(recorded_net), "max_daily_loss": str(max_loss), "tripped": True}
        recomputed = {
            "net_pnl": str(recomputed_net),
            "tripped": rule_holds,
            "net_reproduces": net_reproduces,
        }
        if net_reproduces and rule_holds:
            return ReplayVerdict(audit_log_id, self.decision_type, Verdict.MATCH, recorded, recomputed)
        note = (
            "recomputed net_pnl != recorded" if not net_reproduces
            else "recorded trip does not satisfy net_pnl <= -max_daily_loss"
        )
        return ReplayVerdict(audit_log_id, self.decision_type, Verdict.MISMATCH, recorded, recomputed, note)


class ReconciliationDiscrepancyVerifier:
    """Recompute a reconciliation discrepancy's classification from the recorded local/broker
    quantities (app/services/reconciliation.py diff_positions). MATCH iff the recomputed
    `kind` equals the recorded one. Position domain only; the intent domain is deferred
    (SKIPPED) until durable overlay-target persistence lands — same gap as §3 intent."""

    decision_type = AuditAction.RECONCILIATION_DISCREPANCY.value
    capability = "supported"

    def replay(self, audit_log_id: int, payload: dict[str, Any]) -> ReplayVerdict:
        domain = payload.get("domain")
        recorded_kind = payload.get("kind")
        recorded = {"domain": domain, "kind": recorded_kind}
        if domain != "position":
            return ReplayVerdict(
                audit_log_id, self.decision_type, Verdict.SKIPPED, recorded, {},
                f"{domain} domain not replayable yet (needs durable fingerprint)",
            )
        local = payload.get("local")
        broker = payload.get("broker")
        if local is not None and broker is None:
            kind = "missing_broker"
        elif broker is not None and local is None:
            kind = "missing_local"
        elif local is not None and broker is not None and _dec(local) != _dec(broker):
            kind = "qty_mismatch"
        else:
            # Both None, or equal — a discrepancy row should not exist for this state.
            kind = None
        recomputed = {"kind": kind}
        if kind == recorded_kind:
            return ReplayVerdict(audit_log_id, self.decision_type, Verdict.MATCH, recorded, recomputed)
        return ReplayVerdict(
            audit_log_id, self.decision_type, Verdict.MISMATCH, recorded, recomputed,
            "recomputed classification does not match recorded kind",
        )


REPLAY_REGISTRY: dict[str, ReplayVerifier] = {
    BreakerTripVerifier.decision_type: BreakerTripVerifier(),
    ReconciliationDiscrepancyVerifier.decision_type: ReconciliationDiscrepancyVerifier(),
}

# Capability catalog — single source of truth for replay coverage. SUPPORTED decisions have a
# registered verifier; UNREPLAYABLE decisions are blocked on a durable fingerprint (not merely
# unbuilt). Keep this aligned with the session doc's capability table.
CAPABILITY: dict[str, str] = {
    AuditAction.CIRCUIT_BREAKER_TRIPPED.value: "supported",
    AuditAction.RECONCILIATION_DISCREPANCY.value: "supported",
    "OVERLAY_SCALING": "unreplayable",        # overlay fingerprint not durably persisted
    AuditAction.ORDER_REJECTED_BY_RISK.value: "unreplayable",  # point-in-time inputs not persisted
}


class RegistryInconsistencyError(RuntimeError):
    """REPLAY_REGISTRY and CAPABILITY disagree — a programming error (someone shipped one half of a
    verifier), never a runtime-data condition. Raised at startup so the inconsistency can never reach
    a replay pass that would silently miscount coverage."""


def validate_registry() -> None:
    """Fail fast iff the registry and the capability catalog drift: every ``supported`` capability
    MUST have a registered ``ReplayVerifier`` and every registered verifier MUST be catalogued
    ``supported`` (and expose a matching ``capability`` attribute). Called at app startup (lifespan);
    a drift here is a bug to fix at boot, not to discover mid-pass."""
    supported = {dt for dt, cap in CAPABILITY.items() if cap == "supported"}
    registered = set(REPLAY_REGISTRY)
    missing_verifier = supported - registered          # supported but no verifier wired
    uncatalogued = registered - supported              # verifier wired but not catalogued supported
    mislabeled = {dt for dt, v in REPLAY_REGISTRY.items() if v.capability != "supported"}
    if missing_verifier or uncatalogued or mislabeled:
        raise RegistryInconsistencyError(
            "replay registry drift: "
            f"supported_without_verifier={sorted(missing_verifier)}, "
            f"registered_not_supported={sorted(uncatalogued)}, "
            f"verifier_capability_not_supported={sorted(mislabeled)}"
        )


def coverage_ratio() -> float:
    """Replayable (SUPPORTED) decision types / total catalogued."""
    supported = sum(1 for c in CAPABILITY.values() if c == "supported")
    return supported / len(CAPABILITY) if CAPABILITY else 0.0


def replay_audit_row(row: AuditLog) -> ReplayVerdict:
    """Dispatch one audit row through the registry. Unknown action → SKIPPED; a verifier that
    raises → ERROR (never propagates — one bad record must not abort the run)."""
    verifier = REPLAY_REGISTRY.get(row.action)
    if verifier is None:
        return ReplayVerdict(row.id, row.action, Verdict.SKIPPED, {}, {}, "no verifier for action")
    try:
        return verifier.replay(row.id, json.loads(row.payload_json or "{}"))
    except (KeyError, ValueError, InvalidOperation, TypeError) as e:
        return ReplayVerdict(row.id, row.action, Verdict.ERROR, {}, {}, repr(e))


async def run_replay(
    session: AsyncSession,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int | None = None,
) -> ReplayRun:
    """Replay every replayable audit row in [since, until]: verify each, persist a `replay_runs`
    row, audit each MISMATCH (REPLAY_MISMATCH, CRITICAL), and emit metrics. Read-only beyond its
    own rows; never the order path."""
    started = time.monotonic()
    stmt = select(AuditLog).where(AuditLog.action.in_(list(REPLAY_REGISTRY.keys())))
    if since is not None:
        stmt = stmt.where(AuditLog.ts >= since)
    if until is not None:
        stmt = stmt.where(AuditLog.ts <= until)
    stmt = stmt.order_by(AuditLog.id)
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = (await session.execute(stmt)).scalars().all()

    verdicts = [replay_audit_row(r) for r in rows]
    tally = {v: 0 for v in Verdict}
    for vd in verdicts:
        tally[vd.verdict] += 1
        replay_verifications_total.labels(
            decision_type=vd.decision_type, verdict=vd.verdict.value
        ).inc()

    matched, mismatched = tally[Verdict.MATCH], tally[Verdict.MISMATCH]
    decided = matched + mismatched
    consistency = (matched / decided) if decided else 1.0
    non_match = [vd for vd in verdicts if vd.verdict is not Verdict.MATCH]
    duration_ms = int((time.monotonic() - started) * 1000)

    run = ReplayRun(
        ran_at=datetime.now(UTC), window_start=since, window_end=until,
        n_checked=len(rows), n_matched=matched, n_mismatched=mismatched,
        n_skipped=tally[Verdict.SKIPPED], n_error=tally[Verdict.ERROR],
        duration_ms=duration_ms, algorithm_version=ALGORITHM_VERSION,
        registry_version=REGISTRY_VERSION,
        detail_json=json.dumps([asdict(vd) for vd in non_match], default=str) if non_match else None,
    )
    session.add(run)

    for vd in verdicts:
        if vd.verdict is Verdict.MISMATCH:
            AuditLogger.write(
                session, actor_type=AuditActorType.SYSTEM, actor_id="replay",
                action=AuditAction.REPLAY_MISMATCH, target_type="audit_log",
                target_id=vd.audit_log_id,
                payload={
                    "audit_log_id": vd.audit_log_id, "decision_type": vd.decision_type,
                    "recorded": vd.recorded, "recomputed": vd.recomputed, "note": vd.note,
                },
            )

    replay_consistency_ratio.set(consistency)
    replay_coverage_ratio.set(coverage_ratio())
    replay_duration_seconds.observe(time.monotonic() - started)
    await session.commit()
    return run


async def run_daily_replay(
    session_factory: async_sessionmaker[AsyncSession], *, window_hours: int = 24
) -> None:
    """Scheduler entrypoint (P11 §4): replay the last ``window_hours`` of decisions so the
    consistency + coverage KPIs stay fed. Best-effort; never raises into the scheduler."""
    try:
        since = datetime.now(UTC) - timedelta(hours=window_hours)
        async with session_factory() as session:
            run = await run_replay(session, since=since)
        if run.n_mismatched:
            logger.error("replay_mismatch_detected", n_mismatched=run.n_mismatched)
    except Exception:
        logger.exception("replay_daily_pass_failed")
