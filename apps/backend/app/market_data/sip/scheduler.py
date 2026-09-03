"""SIP-CACHE-001 Implementation B3 — the two refresh jobs and their (disabled) registration.

Two jobs, two semantics, never one cadence for both (Ruling 5):

``sip_eod_refresh``
    Tick-and-check on calendar trading days. Fires once per *completed* session, after the
    calendar-derived close plus a settle margin — never "16:00", so half-days are correct — and
    fetches the SIP_EOD union.

``sip_live_refresh``
    Interval during regular hours only. Cadence derives from the strictest admitted bound
    (``clamp(strictest / 2, floor, ceiling)``); with no LIVE leases the job issues no requests.

Both are **inert by default**: :func:`register_sip_jobs` registers nothing unless
``sip_cache_enabled`` and the per-profile flag are set *and* every required capacity value is
configured (:func:`scheduler_readiness`). "The job ran" is never readiness — after every write the
state is recomputed by :class:`SipReadinessEvaluator` from ``source_timestamp``, coverage and
entitlement, and only a transition is audited.

Failure semantics: an entitlement refusal by the designated producer latches ``ENTITLEMENT_FAIL``
plane-wide until a subsequent successful designated-producer request. No failover, no credential
substitution, no MDQ read, no IEX downgrade — those paths do not exist in this module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.market_data.sip.cache import SipOperationalCache
from app.market_data.sip.demand import ConsumerRegistry, DemandPlaneConfig, DemandUnion
from app.market_data.sip.producer import SipEntitlementError, SipProducer
from app.market_data.sip.profiles import SipProfile
from app.market_data.sip.readiness import SipReadinessEvaluator, SipReadinessState

logger = structlog.get_logger(__name__)

_ET = ZoneInfo("America/New_York")
_ACTOR = "sip_scheduler"

JOB_ID_EOD = "sip_eod_refresh"
JOB_ID_LIVE = "sip_live_refresh"


# ----------------------------------------------------------------------------- readiness


@dataclass(frozen=True)
class SchedulerReadiness:
    ready: bool
    missing: tuple[str, ...]


def scheduler_readiness(profile: SipProfile, settings: Any) -> SchedulerReadiness:
    """Every capacity value the profile's job needs must be configured. None ⇒ NOT READY."""
    required: list[tuple[str, Any]]
    if profile is SipProfile.LIVE:
        required = [
            ("sip_live_plane_symbol_cap", settings.sip_live_plane_symbol_cap),
            ("sip_live_max_lease_s", settings.sip_live_max_lease_s),
            ("sip_live_min_interval_s", settings.sip_live_min_interval_s),
            ("sip_live_max_interval_s", settings.sip_live_max_interval_s),
            ("sip_live_retention_hours", settings.sip_live_retention_hours),
        ]
    else:
        required = [
            ("sip_eod_plane_symbol_cap", settings.sip_eod_plane_symbol_cap),
            ("sip_eod_max_lease_days", settings.sip_eod_max_lease_days),
            ("sip_eod_settle_margin_s", settings.sip_eod_settle_margin_s),
            ("sip_eod_refresh_attempts", settings.sip_eod_refresh_attempts),
        ]
    missing = tuple(name for name, value in required if value is None)
    return SchedulerReadiness(ready=not missing, missing=missing)


def live_interval_seconds(
    strictest_bound_s: float | None, config: DemandPlaneConfig
) -> float | None:
    """``clamp(strictest / 2, floor, ceiling)``; ``None`` when there is nothing to promise."""
    if strictest_bound_s is None:
        return None
    floor = config.live_min_interval_s
    ceiling = config.live_max_interval_s
    if floor is None or ceiling is None:
        return None
    return max(floor, min(ceiling, strictest_bound_s / 2.0))


# ----------------------------------------------------------------------------- plane state


@dataclass
class SipPlaneLatch:
    """Process-local latch for the plane-wide entitlement state and last readiness per profile.

    Never persisted: readiness is recomputed from the cache on every evaluation, and a restart
    starts from "unknown", not from a stored verdict.
    """

    entitlement_ok: bool = True
    last_state: dict[str, SipReadinessState] = field(default_factory=dict)
    eod_attempts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RefreshOutcome:
    profile: SipProfile
    attempted: bool
    idle_reason: str | None
    symbols_requested: int
    records_written: int
    leases_served: int
    readiness_state: SipReadinessState | None
    readiness_reason: str | None
    failure_class: str | None = None


# ----------------------------------------------------------------------------- dependencies


@dataclass
class SipRefreshDeps:
    session_factory: Any
    registry: ConsumerRegistry
    union: DemandUnion
    producer: SipProducer
    cache: SipOperationalCache
    market_session: Any  # app.market.session.MarketSession
    config: DemandPlaneConfig
    latch: SipPlaneLatch = field(default_factory=SipPlaneLatch)
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    eod_settle_margin_s: int = 0
    eod_refresh_attempts: int = 1
    eod_min_coverage: float = 1.0
    live_retention_hours: int | None = None
    eod_retention_days: int | None = None
    scheduler: Any | None = None  # APScheduler; only for LIVE cadence rescheduling


# ----------------------------------------------------------------------------- jobs


async def _audit_transition(
    deps: SipRefreshDeps, profile: SipProfile, state: SipReadinessState, reason: str
) -> None:
    prev = deps.latch.last_state.get(str(profile))
    if prev == state:
        return
    deps.latch.last_state[str(profile)] = state
    async with deps.session_factory() as s:
        AuditLogger.write(
            s,
            actor_type=AuditActorType.SYSTEM,
            actor_id=_ACTOR,
            action=AuditAction.SIP_READINESS_TRANSITION,
            target_type="sip_profile",
            target_id=str(profile),
            payload={"from": str(prev) if prev else None, "to": str(state), "reason": reason},
        )
        await s.commit()


async def _audit_failure(
    deps: SipRefreshDeps,
    profile: SipProfile,
    *,
    failure_class: str,
    lease_ids: frozenset[int],
    symbol_count: int,
) -> None:
    async with deps.session_factory() as s:
        AuditLogger.write(
            s,
            actor_type=AuditActorType.SYSTEM,
            actor_id=_ACTOR,
            action=AuditAction.SIP_ACQUISITION_FAILURE,
            target_type="sip_profile",
            target_id=str(profile),
            payload={
                "failure_class": failure_class,
                "affected_lease_ids": sorted(lease_ids),
                "symbol_count": symbol_count,
                # The credential is never in this payload; the producer pins it and never
                # substitutes it, so there is nothing to record beyond the classification.
            },
        )
        await s.commit()


async def _recompute(
    deps: SipRefreshDeps,
    profile: SipProfile,
    *,
    expected_symbols: int,
    live_max_age_s: float | None,
    eod_expected: date | None,
) -> tuple[SipReadinessState, str]:
    records = await deps.cache.latest_for_profile(profile)
    evaluator = SipReadinessEvaluator(
        expected_symbols=expected_symbols,
        live_max_age_s=live_max_age_s if live_max_age_s is not None else 0.0,
        eod_expected_trading_date=eod_expected,
        min_coverage=deps.eod_min_coverage,
    )
    r = evaluator.evaluate(
        profile,
        records,
        entitlement_ok=deps.latch.entitlement_ok,
        store_available=True,
        now=deps.clock(),
    )
    await _audit_transition(deps, profile, r.state, r.reason)
    return r.state, r.reason


async def _acquire(
    deps: SipRefreshDeps,
    profile: SipProfile,
    symbols: list[str],
    *,
    trading_date: date,
    lease_ids: frozenset[int],
) -> tuple[int, int, str | None]:
    """Fetch → upsert → SERVED. Returns (written, leases_served, failure_class)."""
    try:
        records = await deps.producer.fetch_latest_quotes(
            symbols, profile=profile, trading_date=trading_date, session="regular"
        )
    except SipEntitlementError:
        deps.latch.entitlement_ok = False
        await _audit_failure(
            deps,
            profile,
            failure_class="entitlement",
            lease_ids=lease_ids,
            symbol_count=len(symbols),
        )
        return 0, 0, "entitlement"
    except Exception as exc:  # transport / provider / SDK — classified, never echoed wholesale
        await _audit_failure(
            deps,
            profile,
            failure_class=type(exc).__name__,
            lease_ids=lease_ids,
            symbol_count=len(symbols),
        )
        return 0, 0, type(exc).__name__
    deps.latch.entitlement_ok = True
    written = await deps.cache.upsert(records)
    served = await deps.registry.mark_served(
        profile, [r.symbol for r in records], trading_date=trading_date
    )
    return written, served, None


async def run_sip_live_refresh(deps: SipRefreshDeps) -> RefreshOutcome:
    """One LIVE tick. Idle outside regular hours and whenever the LIVE union is empty."""
    now = deps.clock()
    await deps.registry.expire_due()
    info = deps.market_session.classify(now)
    if not info.is_regular():
        return RefreshOutcome(SipProfile.LIVE, False, "outside_regular_hours", 0, 0, 0, None, None)
    demand = await deps.union.for_profile(SipProfile.LIVE)
    if not demand.symbols:
        return RefreshOutcome(SipProfile.LIVE, False, "no_live_leases", 0, 0, 0, None, None)

    interval = live_interval_seconds(demand.strictest_bound_s, deps.config)
    if deps.scheduler is not None and interval is not None:
        _maybe_reschedule(deps.scheduler, JOB_ID_LIVE, interval)

    trading_date = now.astimezone(_ET).date()
    symbols = sorted(demand.symbols)
    written, served, failure = await _acquire(
        deps, SipProfile.LIVE, symbols, trading_date=trading_date, lease_ids=demand.lease_ids
    )
    state, reason = await _recompute(
        deps,
        SipProfile.LIVE,
        expected_symbols=len(symbols),
        live_max_age_s=demand.strictest_bound_s,
        eod_expected=None,
    )
    if deps.live_retention_hours is not None:
        # Rows are one-per-(symbol, trading_date), so retention is whole days, minimum one.
        days = max(1, -(-deps.live_retention_hours // 24))
        await deps.cache.prune(days, now=now, keep_newest_for=demand.symbols)
    return RefreshOutcome(
        SipProfile.LIVE, True, None, len(symbols), written, served, state, reason, failure
    )


async def run_sip_eod_refresh(deps: SipRefreshDeps) -> RefreshOutcome:
    """One EOD tick. Fires once per completed session, from the calendar, after the settle margin."""
    now = deps.clock()
    await deps.registry.expire_due()
    info = deps.market_session.classify(now)
    if not info.is_trading_day or info.regular_close is None:
        return RefreshOutcome(SipProfile.EOD, False, "not_a_trading_day", 0, 0, 0, None, None)
    ready_at = info.regular_close + timedelta(seconds=deps.eod_settle_margin_s)
    if now < ready_at:
        return RefreshOutcome(SipProfile.EOD, False, "session_not_settled", 0, 0, 0, None, None)
    trading_date = now.astimezone(_ET).date()
    key = trading_date.isoformat()
    demand = await deps.union.for_profile(SipProfile.EOD)
    if not demand.symbols:
        return RefreshOutcome(SipProfile.EOD, False, "no_eod_leases", 0, 0, 0, None, None)
    # Already complete for this session? Then this tick is idle (once per completed session).
    existing = await deps.cache.latest_for_profile(SipProfile.EOD)
    have = {r.symbol for r in existing if r.trading_date == trading_date}
    if demand.symbols <= have:
        return RefreshOutcome(
            SipProfile.EOD, False, "session_already_complete", 0, 0, 0, None, None
        )
    attempts = deps.latch.eod_attempts.get(key, 0)
    if attempts >= deps.eod_refresh_attempts:
        return RefreshOutcome(SipProfile.EOD, False, "attempts_exhausted", 0, 0, 0, None, None)
    deps.latch.eod_attempts[key] = attempts + 1

    symbols = sorted(demand.symbols - have)
    written, served, failure = await _acquire(
        deps, SipProfile.EOD, symbols, trading_date=trading_date, lease_ids=demand.lease_ids
    )
    state, reason = await _recompute(
        deps,
        SipProfile.EOD,
        expected_symbols=len(demand.symbols),
        live_max_age_s=None,
        eod_expected=trading_date,
    )
    if deps.eod_retention_days is not None:
        await deps.cache.prune(deps.eod_retention_days, now=now, keep_newest_for=demand.symbols)
    return RefreshOutcome(
        SipProfile.EOD, True, None, len(symbols), written, served, state, reason, failure
    )


def _maybe_reschedule(scheduler: Any, job_id: str, interval_s: float) -> None:
    try:
        job = scheduler.get_job(job_id)
        current = getattr(getattr(job, "trigger", None), "interval", None)
        if current is not None and abs(current.total_seconds() - interval_s) < 1e-6:
            return
        scheduler.reschedule_job(job_id, trigger="interval", seconds=interval_s)
        logger.info("sip_live_cadence_rescheduled", interval_s=interval_s)
    except Exception:
        logger.exception("sip_live_reschedule_failed", job_id=job_id)


# ----------------------------------------------------------------------------- registration


def register_sip_jobs(scheduler: Any, settings: Any, deps: SipRefreshDeps) -> list[str]:
    """Register the refresh jobs **only** when every enablement condition holds.

    Returns the job ids registered — an empty list under default settings. This is the single
    place the jobs enter the scheduler, and it never registers a job whose capacity policy is
    unconfigured.
    """
    registered: list[str] = []
    if not settings.sip_cache_enabled:
        logger.info("sip_scheduler_inert", reason="sip_cache_enabled=False")
        return registered

    if settings.sip_eod_refresh_enabled:
        rd = scheduler_readiness(SipProfile.EOD, settings)
        if rd.ready:
            scheduler.add_job(
                run_sip_eod_refresh,
                trigger="interval",
                minutes=15,
                id=JOB_ID_EOD,
                max_instances=1,
                coalesce=True,
                replace_existing=True,
                kwargs={"deps": deps},
            )
            registered.append(JOB_ID_EOD)
        else:
            logger.error("sip_scheduler_not_ready", profile="SIP_EOD", missing=rd.missing)

    if settings.sip_live_refresh_enabled:
        rd = scheduler_readiness(SipProfile.LIVE, settings)
        if rd.ready:
            # Initial cadence = the ceiling; the job tightens toward strictest/2 once leases exist.
            scheduler.add_job(
                run_sip_live_refresh,
                trigger="interval",
                seconds=float(settings.sip_live_max_interval_s),
                id=JOB_ID_LIVE,
                max_instances=1,
                coalesce=True,
                replace_existing=True,
                kwargs={"deps": deps},
            )
            registered.append(JOB_ID_LIVE)
        else:
            logger.error("sip_scheduler_not_ready", profile="SIP_LIVE", missing=rd.missing)

    if registered:
        logger.info("sip_scheduler_registered", jobs=registered)
    else:
        logger.info("sip_scheduler_inert", reason="no profile enabled or not ready")
    return registered
