"""SIP-CACHE-001 Implementation B3 — the two refresh jobs and their inert registration.

No test here touches a network: the producer is a fake that records what it was asked and returns
authentic SIP records, or raises the entitlement error, on command.
"""

from __future__ import annotations

import ast
import inspect
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from app.audit import AuditAction
from app.db.enums import StrategyStatus
from app.db.models.audit_log import AuditLog
from app.db.models.sip_demand import SipDemandLease
from app.market_data.sip.cache import SipOperationalCache
from app.market_data.sip.demand import (
    ConsumerRegistry,
    DemandLease,
    DemandReason,
    DemandUnion,
    LeaseStatus,
)
from app.market_data.sip.identity import PRODUCER
from app.market_data.sip.producer import SipEntitlementError
from app.market_data.sip.profiles import SipProfile
from app.market_data.sip.readiness import SipReadinessState
from app.market_data.sip.scheduler import (
    JOB_ID_EOD,
    JOB_ID_LIVE,
    SipRefreshDeps,
    live_interval_seconds,
    register_sip_jobs,
    run_sip_eod_refresh,
    run_sip_live_refresh,
    scheduler_readiness,
)
from app.market_data.sip.schema import SipRecord
from tests.market_data.test_sip_demand import (
    SHA,
    Clock,
    StaticPolicy,
    artifact,
    config,
    entry,
    seed_users_and_strategy,
)

# A Wednesday. 15:00 UTC = 11:00 ET = regular hours; 21:00 UTC = 17:00 ET = after close.
RTH = datetime(2026, 9, 2, 15, 0, tzinfo=UTC)
AFTER = datetime(2026, 9, 2, 21, 0, tzinfo=UTC)
SAT = datetime(2026, 9, 5, 15, 0, tzinfo=UTC)


class FakeMarketSession:
    """Deterministic calendar: weekdays are sessions 13:30–20:00 UTC; Sep 4 is a half-day."""

    def classify(self, instant: datetime) -> Any:
        d = instant.astimezone(UTC).date()
        if d.weekday() >= 5:
            return SimpleNamespace(
                is_trading_day=False,
                is_half_day=False,
                regular_open=None,
                regular_close=None,
                is_regular=lambda: False,
            )
        close_h = 17 if d == date(2026, 9, 4) else 20
        open_ = datetime(d.year, d.month, d.day, 13, 30, tzinfo=UTC)
        close = datetime(d.year, d.month, d.day, close_h, 0, tzinfo=UTC)
        return SimpleNamespace(
            is_trading_day=True,
            is_half_day=close_h == 17,
            regular_open=open_,
            regular_close=close,
            is_regular=lambda: open_ <= instant < close,
        )


@dataclass
class FakeProducer:
    clock: Clock
    fail_entitlement: bool = False
    fail_transport: bool = False
    calls: list[tuple[SipProfile, list[str]]] | None = None
    stale_by_s: float = 0.0

    async def fetch_latest_quotes(
        self, symbols: list[str], *, profile: SipProfile, trading_date: date, session: str
    ) -> list[SipRecord]:
        if self.calls is None:
            self.calls = []
        self.calls.append((profile, list(symbols)))
        if self.fail_entitlement:
            raise SipEntitlementError("subscription does not permit querying recent SIP data")
        if self.fail_transport:
            raise ConnectionError("boom")
        ts = self.clock.now - timedelta(seconds=self.stale_by_s)
        return [
            SipRecord(
                symbol=s,
                profile=profile,
                trading_date=trading_date,
                session=session,
                source_timestamp=ts,
                received_at_utc=self.clock.now,
                price=Decimal("100"),
                bid=Decimal("99.9"),
                ask=Decimal("100.1"),
                entitlement_identity=PRODUCER.entitlement_identity,
                credential_identity_fingerprint=PRODUCER.key_fingerprint,
            )
            for s in symbols
        ]


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.rescheduled: list[tuple[str, float]] = []

    def add_job(self, fn: Any, trigger: str, id: str, **kw: Any) -> None:
        self.jobs[id] = {"fn": fn, "trigger": trigger, **kw}

    def get_job(self, job_id: str) -> Any:
        if job_id not in self.jobs:
            return None
        secs = self.jobs[job_id].get("seconds") or self.jobs[job_id].get("minutes", 0) * 60
        return SimpleNamespace(trigger=SimpleNamespace(interval=timedelta(seconds=secs)))

    def reschedule_job(self, job_id: str, trigger: str, seconds: float) -> None:
        self.jobs[job_id]["seconds"] = seconds
        self.rescheduled.append((job_id, seconds))


def settings(**over: Any) -> SimpleNamespace:
    base: dict[str, Any] = dict(
        sip_cache_enabled=False,
        sip_eod_refresh_enabled=False,
        sip_live_refresh_enabled=False,
        sip_live_plane_symbol_cap=None,
        sip_eod_plane_symbol_cap=None,
        sip_live_max_lease_s=None,
        sip_eod_max_lease_days=None,
        sip_live_min_interval_s=None,
        sip_live_max_interval_s=None,
        sip_live_retention_hours=None,
        sip_eod_settle_margin_s=None,
        sip_eod_refresh_attempts=None,
        scheduler_enabled=True,
    )
    base.update(over)
    return SimpleNamespace(**base)


FULL = dict(
    sip_cache_enabled=True,
    sip_live_plane_symbol_cap=10,
    sip_eod_plane_symbol_cap=50,
    sip_live_max_lease_s=21600.0,
    sip_eod_max_lease_days=5,
    sip_live_min_interval_s=5.0,
    sip_live_max_interval_s=60.0,
    sip_live_retention_hours=24,
    sip_eod_settle_margin_s=1200,
    sip_eod_refresh_attempts=3,
)


@pytest.fixture
async def plane(session_factory: Any):
    await seed_users_and_strategy(session_factory, status=StrategyStatus.PAPER)
    clock = Clock(RTH)
    cfg = config()
    reg = ConsumerRegistry(
        session_factory, config=cfg, policy=StaticPolicy({"strategy:9": 30.0}), clock=clock
    )
    await reg.apply_artifact(artifact(entry()), artifact_sha256=SHA, applied_by="op", dry_run=False)
    producer = FakeProducer(clock)
    deps = SipRefreshDeps(
        session_factory=session_factory,
        registry=reg,
        union=DemandUnion(session_factory, clock=clock),
        producer=producer,  # type: ignore[arg-type]
        cache=SipOperationalCache(session_factory),
        market_session=FakeMarketSession(),
        config=cfg,
        clock=clock,
        eod_settle_margin_s=1200,
        eod_refresh_attempts=2,
        live_retention_hours=24,
        eod_retention_days=30,
    )
    return deps, reg, clock, producer


async def _publish(
    reg: ConsumerRegistry,
    clock: Clock,
    profile: SipProfile,
    *symbols: str,
    expires_in: timedelta | None = None,
) -> None:
    g = await reg.grant("strategy:9")
    reason = DemandReason.HELD if profile is SipProfile.LIVE else DemandReason.EOD_FEATURE
    r = await reg.publish(
        g,
        DemandLease(
            profile=profile,
            symbols=frozenset(symbols),
            reasons={s: reason for s in symbols},
            # EOD leases outlive the close by default; LIVE leases are one-hour test leases.
            expires_at=clock.now
            + (
                expires_in
                or (timedelta(hours=12) if profile is SipProfile.EOD else timedelta(hours=1))
            ),
        ),
    )
    assert r.accepted, r


async def _actions(session_factory: Any) -> list[str]:
    async with session_factory() as s:
        return [
            r.action for r in (await s.execute(select(AuditLog).order_by(AuditLog.id))).scalars()
        ]


# ============================================================================ inert by default


def test_flags_default_false_and_jobs_absent() -> None:
    """Fails if the jobs register under default settings (or with only sip_cache_enabled)."""
    from app.config import Settings

    fields = Settings.model_fields
    assert fields["sip_eod_refresh_enabled"].default is False
    assert fields["sip_live_refresh_enabled"].default is False
    for name in (
        "sip_live_plane_symbol_cap",
        "sip_eod_plane_symbol_cap",
        "sip_live_max_lease_s",
        "sip_eod_max_lease_days",
        "sip_live_min_interval_s",
        "sip_live_max_interval_s",
        "sip_live_retention_hours",
        "sip_eod_settle_margin_s",
        "sip_eod_refresh_attempts",
    ):
        assert fields[name].default is None, name
    sched = FakeScheduler()
    assert register_sip_jobs(sched, settings(), None) == []  # type: ignore[arg-type]
    assert register_sip_jobs(sched, settings(sip_cache_enabled=True), None) == []  # type: ignore[arg-type]
    assert sched.jobs == {}


def test_jobs_refuse_to_register_while_capacity_unconfigured() -> None:
    """Fails if a job registers with a required capacity value still None."""
    sched = FakeScheduler()
    s = settings(
        sip_cache_enabled=True, sip_live_refresh_enabled=True, sip_eod_refresh_enabled=True
    )
    assert register_sip_jobs(sched, s, None) == []  # type: ignore[arg-type]
    rd = scheduler_readiness(SipProfile.LIVE, s)
    assert not rd.ready and "sip_live_plane_symbol_cap" in rd.missing
    assert not scheduler_readiness(SipProfile.EOD, s).ready


def test_jobs_register_only_when_every_condition_holds() -> None:
    """Fails if the fully configured, explicitly enabled case registers nothing."""
    sched = FakeScheduler()
    s = settings(**FULL, sip_live_refresh_enabled=True, sip_eod_refresh_enabled=True)
    assert register_sip_jobs(sched, s, None) == [JOB_ID_EOD, JOB_ID_LIVE]  # type: ignore[arg-type]
    assert sched.jobs[JOB_ID_LIVE]["seconds"] == 60.0  # starts at the ceiling
    assert sched.jobs[JOB_ID_EOD]["max_instances"] == 1 and sched.jobs[JOB_ID_EOD]["coalesce"]


def test_only_scheduler_module_constructs_refresh_jobs() -> None:
    """Fails if any module besides sip/scheduler.py and lifespan.py names the job ids."""
    root = Path(inspect.getfile(run_sip_live_refresh)).resolve().parents[2]  # .../app
    offenders: list[str] = []
    for py in root.rglob("*.py"):
        rel = py.relative_to(root).as_posix()
        if rel in {"market_data/sip/scheduler.py", "lifespan.py"}:
            continue
        text = py.read_text(encoding="utf-8")
        # The job-id *string literal*, not a substring (config.py's flag names contain it).
        if f'"{JOB_ID_EOD}"' in text or f'"{JOB_ID_LIVE}"' in text:
            offenders.append(rel)
    assert offenders == []


def test_scheduler_module_has_no_fallback_paths() -> None:
    """Fails if the scheduler imports IEX bar cache, MDQ capture, or credential resolution."""
    src = Path(inspect.getfile(run_sip_live_refresh)).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    for bad in (
        "app.market_data.bar_cache",
        "app.research",
        "app.security.credential_store",
        "alpaca.trading",
    ):
        assert not any(m.startswith(bad) for m in imported), bad


# ============================================================================ cadence


def test_cadence_derives_from_strictest_and_respects_floor() -> None:
    """Fails if interval ≠ clamp(strictest/2, floor, ceiling), or exists with no bound."""
    cfg = config()
    assert live_interval_seconds(None, cfg) is None
    assert live_interval_seconds(30.0, cfg) == 15.0
    assert live_interval_seconds(4.0, cfg) == 5.0
    assert live_interval_seconds(1000.0, cfg) == 60.0
    assert live_interval_seconds(30.0, config(live_min_interval_s=None)) is None


async def test_live_tick_reschedules_toward_strictest(plane) -> None:
    """Fails if a LIVE tick with a 30 s strictest bound does not move the job to 15 s."""
    deps, reg, clock, _ = plane
    sched = FakeScheduler()
    sched.add_job(run_sip_live_refresh, "interval", JOB_ID_LIVE, seconds=60.0)
    deps.scheduler = sched
    await _publish(reg, clock, SipProfile.LIVE, "AAPL")
    out = await run_sip_live_refresh(deps)
    assert out.attempted
    assert sched.rescheduled == [(JOB_ID_LIVE, 15.0)]
    await run_sip_live_refresh(deps)
    assert len(sched.rescheduled) == 1  # unchanged cadence is not rescheduled again


# ============================================================================ LIVE job


async def test_scheduler_idle_with_no_live_leases(plane) -> None:
    """Fails if the LIVE job issues any producer call with an empty union."""
    deps, _, _, producer = plane
    out = await run_sip_live_refresh(deps)
    assert not out.attempted and out.idle_reason == "no_live_leases"
    assert not producer.calls


async def test_live_idle_outside_regular_hours(plane) -> None:
    """Fails if the LIVE job fetches after the close or on a weekend."""
    deps, reg, clock, producer = plane
    await _publish(reg, clock, SipProfile.LIVE, "AAPL")
    for when in (AFTER, SAT):
        clock.now = when
        out = await run_sip_live_refresh(deps)
        assert not out.attempted and out.idle_reason == "outside_regular_hours"
    assert not producer.calls


async def test_live_refresh_serves_leases_and_reaches_pass(plane, session_factory) -> None:
    """Fails if a fresh fetch does not persist, SERVE the lease, and evaluate PASS."""
    deps, reg, clock, producer = plane
    await _publish(reg, clock, SipProfile.LIVE, "AAPL", "MSFT")
    out = await run_sip_live_refresh(deps)
    assert out.attempted and out.records_written == 2 and out.leases_served == 1
    assert out.readiness_state is SipReadinessState.PASS
    assert producer.calls == [(SipProfile.LIVE, ["AAPL", "MSFT"])]
    acts = await _actions(session_factory)
    assert AuditAction.SIP_DEMAND_UNION_MATERIALIZED.value in acts
    assert AuditAction.SIP_DEMAND_SERVED.value in acts
    assert AuditAction.SIP_READINESS_TRANSITION.value in acts


async def test_job_ran_is_not_readiness(plane) -> None:
    """Fails if a refresh that wrote stale rows yields PASS."""
    deps, reg, clock, producer = plane
    producer.stale_by_s = 120.0  # bound is 30 s
    await _publish(reg, clock, SipProfile.LIVE, "AAPL")
    out = await run_sip_live_refresh(deps)
    assert out.attempted and out.records_written == 1
    assert out.readiness_state is SipReadinessState.STALE


async def _failure_count(session_factory: Any) -> int:
    return sum(
        1
        for r in (await _actions(session_factory))
        if r == AuditAction.SIP_ACQUISITION_FAILURE.value
    )


# The entitlement latch has three distinct lifecycle transitions. They are tested separately,
# each with a monotonic clock, so that lease expiry (a correct, unrelated event) can never be
# mistaken for — or mask — entitlement recovery:
#   1. latched, LIVE demand still admitted, designated producer still refusing  → stays latched
#   2. latched, LIVE demand still admitted, designated producer succeeds          → clears
#   3. latched, LIVE demand lapses (no request possible)                          → stays latched


async def test_entitlement_fail_latches_plane_wide_no_failover(plane, session_factory) -> None:
    """Fails if a 403 yields more than one designated attempt per tick, if any tick reaches PASS on
    either profile while the designated producer keeps refusing, or if the latch clears without a
    successful request (transition 1, plane-wide)."""
    deps, reg, clock, producer = plane
    producer.fail_entitlement = True
    await _publish(reg, clock, SipProfile.LIVE, "AAPL")  # one-hour lease: ACTIVE until 16:00Z
    await _publish(reg, clock, SipProfile.EOD, "AAPL")  # twelve-hour lease: ACTIVE through AFTER
    out = await run_sip_live_refresh(deps)
    assert out.failure_class == "entitlement"
    assert out.readiness_state is SipReadinessState.ENTITLEMENT_FAIL
    assert len(producer.calls) == 1  # exactly one designated attempt; no retry with anything else
    assert deps.latch.entitlement_ok is False
    # Next LIVE tick, lease still ACTIVE, producer still refusing: one more attempt, still latched.
    clock.advance(minutes=1)
    again = await run_sip_live_refresh(deps)
    assert again.attempted and again.readiness_state is SipReadinessState.ENTITLEMENT_FAIL
    assert len(producer.calls) == 2 and deps.latch.entitlement_ok is False
    # Plane-wide: after the close the EOD job (its own lease still ACTIVE) shares the latch and its
    # own designated request is refused too. The LIVE lease has lapsed by now — correct, and covered
    # by test_live_lease_expiry_removes_demand_but_does_not_clear_the_latch, not here.
    clock.now = AFTER
    eod = await run_sip_eod_refresh(deps)
    assert eod.attempted and eod.readiness_state is SipReadinessState.ENTITLEMENT_FAIL
    assert [p for p, _ in producer.calls] == [SipProfile.LIVE, SipProfile.LIVE, SipProfile.EOD]
    assert await _failure_count(session_factory) == 3
    assert deps.latch.entitlement_ok is False


async def test_entitlement_latch_clears_only_on_designated_success_with_live_demand_active(
    plane, session_factory
) -> None:
    """Fails if the latch clears before a successful designated-producer request (by time, config,
    or restored upstream entitlement alone), or if a success while the LIVE lease is still ACTIVE
    does not clear it and re-evaluate PASS (transition 2)."""
    deps, reg, clock, producer = plane
    producer.fail_entitlement = True
    await _publish(reg, clock, SipProfile.LIVE, "AAPL")  # ACTIVE until 16:00Z
    first = await run_sip_live_refresh(deps)
    assert first.readiness_state is SipReadinessState.ENTITLEMENT_FAIL
    # Entitlement is restored upstream. Nothing on the plane can observe that until the next
    # designated request, so the latch must still be set.
    producer.fail_entitlement = False
    clock.advance(minutes=1)  # 15:01Z: regular hours, lease ACTIVE
    assert deps.latch.entitlement_ok is False
    out = await run_sip_live_refresh(deps)
    assert out.attempted and out.records_written == 1 and out.leases_served == 1
    assert out.readiness_state is SipReadinessState.PASS and deps.latch.entitlement_ok is True
    assert producer.calls == [(SipProfile.LIVE, ["AAPL"]), (SipProfile.LIVE, ["AAPL"])]
    async with session_factory() as s:
        rows = (
            (
                await s.execute(
                    select(AuditLog)
                    .where(AuditLog.action == AuditAction.SIP_READINESS_TRANSITION.value)
                    .order_by(AuditLog.id)
                )
            )
            .scalars()
            .all()
        )
    transitions = [json.loads(r.payload_json)["to"] for r in rows]
    assert transitions == ["ENTITLEMENT_FAIL", "PASS"]


async def test_live_lease_expiry_removes_demand_but_does_not_clear_the_latch(
    plane, session_factory
) -> None:
    """Fails if a lapsed LIVE lease still drives a fetch, if an empty LIVE union clears the latch
    (recovery without a successful request), or if recovery after demand lapsed does not require
    NEW admitted demand plus a designated success (transition 3, then recovery)."""
    deps, reg, clock, producer = plane
    producer.fail_entitlement = True
    await _publish(reg, clock, SipProfile.LIVE, "AAPL", expires_in=timedelta(minutes=30))
    assert (await run_sip_live_refresh(deps)).readiness_state is SipReadinessState.ENTITLEMENT_FAIL
    producer.fail_entitlement = False
    clock.advance(minutes=31)  # 15:31Z: regular hours; the only LIVE lease has lapsed
    idle = await run_sip_live_refresh(deps)
    assert not idle.attempted and idle.idle_reason == "no_live_leases"
    assert len(producer.calls) == 1  # no demand ⇒ no request ⇒ no recovery evidence
    assert deps.latch.entitlement_ok is False
    acts = await _actions(session_factory)
    assert AuditAction.SIP_DEMAND_EXPIRED.value in acts
    async with session_factory() as s:
        lease_row = (await s.execute(select(SipDemandLease))).scalars().one()
    assert lease_row.status == str(LeaseStatus.EXPIRED)
    # Recovery from here needs a newly admitted lease AND a successful designated request.
    await _publish(reg, clock, SipProfile.LIVE, "AAPL")
    recovered = await run_sip_live_refresh(deps)
    assert recovered.attempted and recovered.readiness_state is SipReadinessState.PASS
    assert deps.latch.entitlement_ok is True and len(producer.calls) == 2


async def test_transport_failure_is_classified_not_echoed(plane, session_factory) -> None:
    """Fails if a transport error is unhandled or its message is copied into the audit payload."""
    deps, reg, clock, producer = plane
    producer.fail_transport = True
    await _publish(reg, clock, SipProfile.LIVE, "AAPL")
    out = await run_sip_live_refresh(deps)
    assert out.failure_class == "ConnectionError"
    async with session_factory() as s:
        row = (
            (
                await s.execute(
                    select(AuditLog).where(
                        AuditLog.action == AuditAction.SIP_ACQUISITION_FAILURE.value
                    )
                )
            )
            .scalars()
            .one()
        )
    assert (
        "boom" not in row.payload_json and '"failure_class": "ConnectionError"' in row.payload_json
    )


async def test_restart_recomputes_readiness_not_inherits(plane, session_factory) -> None:
    """Fails if a new latch/deps instance reports PASS from a stored verdict instead of the cache."""
    deps, reg, clock, producer = plane
    await _publish(reg, clock, SipProfile.LIVE, "AAPL")
    assert (await run_sip_live_refresh(deps)).readiness_state is SipReadinessState.PASS
    # "Restart": fresh latch, data now 5 minutes old, producer silent (raises) so nothing refreshes.
    clock.advance(minutes=5)
    producer.fail_transport = True
    fresh = SipRefreshDeps(**{**deps.__dict__, "latch": type(deps.latch)()})
    out = await run_sip_live_refresh(fresh)
    assert out.readiness_state is SipReadinessState.STALE


# ============================================================================ EOD job


async def test_eod_fires_once_per_completed_session_from_calendar(plane, session_factory) -> None:
    """Fails if it fires before settle, fires on a Saturday, fires twice for one session, or uses
    16:00 on a half-day."""
    deps, reg, clock, producer = plane
    await _publish(reg, clock, SipProfile.EOD, "AAPL")
    out = await run_sip_eod_refresh(deps)  # 15:00 UTC, regular hours
    assert not out.attempted and out.idle_reason == "session_not_settled"
    clock.now = datetime(2026, 9, 2, 20, 10, tzinfo=UTC)  # close + 10 min < 20 min margin
    assert (await run_sip_eod_refresh(deps)).idle_reason == "session_not_settled"
    clock.now = AFTER
    out = await run_sip_eod_refresh(deps)
    assert out.attempted and out.records_written == 1
    assert out.readiness_state is SipReadinessState.PASS
    assert (await run_sip_eod_refresh(deps)).idle_reason == "session_already_complete"
    assert len(producer.calls) == 1
    clock.now = SAT
    assert (await run_sip_eod_refresh(deps)).idle_reason == "not_a_trading_day"
    # Half-day: close 17:00 UTC ⇒ ready at 17:20, so 17:30 fires while 16:30 would not.
    await _publish(reg, clock, SipProfile.EOD, "AAPL")
    clock.now = datetime(2026, 9, 4, 16, 30, tzinfo=UTC)
    assert (await run_sip_eod_refresh(deps)).idle_reason == "session_not_settled"
    clock.now = datetime(2026, 9, 4, 17, 30, tzinfo=UTC)
    assert (await run_sip_eod_refresh(deps)).attempted


async def test_eod_attempts_are_bounded_within_session(plane) -> None:
    """Fails if a failing EOD refresh retries beyond the configured attempts for one session."""
    deps, reg, clock, producer = plane
    producer.fail_transport = True
    await _publish(reg, clock, SipProfile.EOD, "AAPL")
    clock.now = AFTER
    assert (await run_sip_eod_refresh(deps)).attempted
    assert (await run_sip_eod_refresh(deps)).attempted
    out = await run_sip_eod_refresh(deps)
    assert not out.attempted and out.idle_reason == "attempts_exhausted"
    assert len(producer.calls) == 2


async def test_eod_never_backfills_a_prior_session(plane) -> None:
    """Fails if the EOD job requests a trading_date other than the session it is completing."""
    deps, reg, clock, producer = plane
    await _publish(reg, clock, SipProfile.EOD, "AAPL")
    clock.now = AFTER
    await run_sip_eod_refresh(deps)
    src = inspect.getsource(run_sip_eod_refresh)
    assert "previous_trading_day" not in src
    assert producer.calls == [(SipProfile.EOD, ["AAPL"])]


async def test_eod_idle_with_no_eod_leases(plane) -> None:
    """Fails if the EOD job fetches with an empty EOD union (even with LIVE leases present)."""
    deps, reg, clock, producer = plane
    await _publish(reg, clock, SipProfile.LIVE, "AAPL")
    clock.now = AFTER
    out = await run_sip_eod_refresh(deps)
    assert not out.attempted and out.idle_reason == "no_eod_leases"
    assert not producer.calls


async def test_tick_expires_lapsed_leases_first(plane) -> None:
    """Fails if a lapsed lease is still fetched by the tick that should have expired it."""
    deps, reg, clock, producer = plane
    await _publish(reg, clock, SipProfile.LIVE, "AAPL")
    clock.advance(hours=2)
    out = await run_sip_live_refresh(deps)
    assert out.idle_reason == "no_live_leases" and not producer.calls
