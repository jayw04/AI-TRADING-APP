"""SIP-CACHE-001 Implementation B3 — governed demand registry, leases, union, audit.

Every test states in its docstring the input that would make it fail. A test that cannot fail is
not evidence (contract §9, §17).
"""

from __future__ import annotations

import ast
import inspect
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.audit import AuditAction
from app.db.enums import StrategyStatus
from app.db.models.audit_log import AuditLog
from app.db.models.sip_demand import SipConsumerRegistration, SipDemandLease
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.market_data.sip.cache import SipOperationalCache
from app.market_data.sip.demand import (
    EOD_REASONS,
    LIVE_REASONS,
    ConsumerGrant,
    ConsumerRegistry,
    DemandLease,
    DemandPlaneConfig,
    DemandReason,
    DemandUnion,
    LeaseRejection,
    LeaseStatus,
    NoFreshnessPolicy,
    RegistryArtifactError,
    artifact_sha256,
)
from app.market_data.sip.identity import PRODUCER
from app.market_data.sip.profiles import SipProfile
from app.market_data.sip.schema import SipRecord

T0 = datetime(2026, 9, 2, 14, 0, tzinfo=UTC)
SHA = "a" * 64


class Clock:
    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: Any) -> None:
        self.now = self.now + timedelta(**kw)


class StaticPolicy:
    """TEST SEAM ONLY — stands in for a consumer's governed execution policy."""

    def __init__(self, bounds: dict[str, float | None]) -> None:
        self.bounds = bounds
        self.calls: list[tuple[str, str | None]] = []

    async def live_max_age_s(self, consumer_id: str, policy_ref: str | None) -> float | None:
        self.calls.append((consumer_id, policy_ref))
        return self.bounds.get(consumer_id)


def config(**overrides: Any) -> DemandPlaneConfig:
    base = dict(
        live_plane_symbol_cap=10,
        eod_plane_symbol_cap=50,
        live_max_lease_s=6 * 3600.0,
        eod_max_lease_days=5,
        live_min_interval_s=5.0,
        live_max_interval_s=60.0,
    )
    base.update(overrides)
    return DemandPlaneConfig(**base)


def entry(cid: str = "strategy:9", **kw: Any) -> dict[str, Any]:
    kind = cid.split(":")[0]
    e: dict[str, Any] = {
        "consumer_id": cid,
        "kind": kind,
        "strategy_id": 9 if kind == "strategy" else None,
        "user_id": 7,
        "allowed_profiles": ["SIP_EOD", "SIP_LIVE"],
        "allowed_reasons": [str(r) for r in DemandReason],
        "symbol_cap_eod": 20,
        "symbol_cap_live": 5,
        "freshness_policy_ref": "strategy9-execution-policy@test",
    }
    e.update(kw)
    return e


def artifact(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "consumers": list(entries)}


def lease(
    profile: SipProfile = SipProfile.LIVE,
    symbols: tuple[str, ...] = ("AAPL", "MSFT"),
    reason: DemandReason = DemandReason.HELD,
    *,
    expires_in: timedelta = timedelta(hours=1),
    reasons: dict[str, DemandReason] | None = None,
    clock: Clock | None = None,
    max_age_trading_days: int | None = None,
) -> DemandLease:
    now = clock.now if clock else T0
    return DemandLease(
        profile=profile,
        symbols=frozenset(symbols),
        reasons=reasons if reasons is not None else {s: reason for s in symbols},
        expires_at=now + expires_in,
        max_age_trading_days=max_age_trading_days,
    )


async def seed_users_and_strategy(session_factory: Any, *, status: StrategyStatus) -> None:
    async with session_factory() as s:
        s.add(User(id=7, email="combined-book@example.test", display_name="u7"))
        s.add(
            Strategy(
                id=9,
                user_id=7,
                name="strategy-9",
                status=status,
                code_path="x.py",
                params_json={},
                symbols_json=[],
                created_at=T0,
                updated_at=T0,
            )
        )
        await s.commit()


async def audit_actions(session_factory: Any) -> list[str]:
    async with session_factory() as s:
        rows = (await s.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
    return [r.action for r in rows]


async def audit_rows(session_factory: Any, action: AuditAction) -> list[dict[str, Any]]:
    async with session_factory() as s:
        rows = (
            (await s.execute(select(AuditLog).where(AuditLog.action == action.value)))
            .scalars()
            .all()
        )
    return [json.loads(r.payload_json) for r in rows]


@pytest.fixture
async def registry(session_factory: Any) -> tuple[ConsumerRegistry, Clock, StaticPolicy]:
    await seed_users_and_strategy(session_factory, status=StrategyStatus.PAPER)
    clock = Clock()
    policy = StaticPolicy({"strategy:9": 30.0})
    reg = ConsumerRegistry(session_factory, config=config(), policy=policy, clock=clock)
    await reg.apply_artifact(artifact(entry()), artifact_sha256=SHA, applied_by="op", dry_run=False)
    return reg, clock, policy


# ============================================================================ requirement 1: identity


async def test_publish_requires_grant_not_consumer_id() -> None:
    """Fails if publish() grows a str/int consumer parameter or any trust-input parameter."""
    params = set(inspect.signature(ConsumerRegistry.publish).parameters) - {"self"}
    assert params == {"grant", "lease"}
    ann = inspect.signature(ConsumerRegistry.publish).parameters["grant"].annotation
    assert "ConsumerGrant" in str(ann)


async def test_grant_cannot_be_forged_from_consumer_id(registry, session_factory) -> None:
    """Fails if a ConsumerGrant assembled outside the registry is accepted."""
    reg, _, _ = registry
    forged = ConsumerGrant("strategy:9", b"\x00" * 16)
    receipt = await reg.publish(forged, lease())
    assert not receipt.accepted
    assert receipt.rejection is LeaseRejection.GRANT_INVALID
    assert AuditAction.SIP_DEMAND_REJECTED.value in await audit_actions(session_factory)


async def test_grant_for_unregistered_or_revoked_consumer_refused(registry) -> None:
    """Fails if grant() mints a capability for a consumer the artifact never named."""
    reg, _, _ = registry
    with pytest.raises(PermissionError):
        await reg.grant("strategy:42")


async def test_registry_applies_only_from_artifact_never_discovery(session_factory) -> None:
    """Fails if a registration appears for a strategy that exists in the DB but not the artifact."""
    await seed_users_and_strategy(session_factory, status=StrategyStatus.PAPER)
    reg = ConsumerRegistry(session_factory, config=config(), policy=NoFreshnessPolicy())
    await reg.apply_artifact(artifact(), artifact_sha256=SHA, applied_by="op", dry_run=False)
    async with session_factory() as s:
        rows = (await s.execute(select(SipConsumerRegistration))).scalars().all()
    assert rows == []
    src = Path(inspect.getfile(ConsumerRegistry)).read_text(encoding="utf-8")
    tree = ast.parse(src)
    # apply_artifact never selects Strategy rows: discovery is structurally absent from apply.
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "apply_artifact"
    )
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert "StrategyRow" not in names


async def test_registry_artifact_hash_mismatch_is_not_verified(registry) -> None:
    """Fails if verification passes when live registrations were applied from another artifact."""
    reg, _, _ = registry
    assert await reg.verify_artifact(SHA) is True
    assert await reg.verify_artifact("b" * 64) is False
    assert reg.registry_verified is False


async def test_registration_without_cap_is_invalid(session_factory) -> None:
    """Fails if an allowed profile with no positive cap is applied (B3 Decision 2)."""
    reg = ConsumerRegistry(session_factory, config=config(), policy=NoFreshnessPolicy())
    for bad in (
        entry(symbol_cap_live=None),
        entry(symbol_cap_live=0),
        entry(symbol_cap_eod=-1),
        entry(allowed_profiles=["SIP_EOD"], symbol_cap_live=5),  # cap on a non-allowed profile
    ):
        with pytest.raises(RegistryArtifactError):
            await reg.apply_artifact(artifact(bad), artifact_sha256=SHA, applied_by="op")


async def test_artifact_validation_is_all_or_nothing(session_factory) -> None:
    """Fails if a valid entry is applied when a sibling entry is invalid."""
    await seed_users_and_strategy(session_factory, status=StrategyStatus.PAPER)
    reg = ConsumerRegistry(session_factory, config=config(), policy=NoFreshnessPolicy())
    with pytest.raises(RegistryArtifactError):
        await reg.apply_artifact(
            artifact(entry(), entry("service:bad", allowed_profiles=["NOPE"])),
            artifact_sha256=SHA,
            applied_by="op",
            dry_run=False,
        )
    async with session_factory() as s:
        assert (await s.execute(select(SipConsumerRegistration))).scalars().all() == []


async def test_apply_revokes_consumers_absent_from_artifact(registry, session_factory) -> None:
    """Fails if a consumer dropped from the artifact keeps its registration or its leases."""
    reg, _, _ = registry
    g = await reg.grant("strategy:9")
    assert (await reg.publish(g, lease())).accepted
    await reg.apply_artifact(artifact(), artifact_sha256="c" * 64, applied_by="op", dry_run=False)
    async with session_factory() as s:
        row = await s.get(SipConsumerRegistration, "strategy:9")
        leases = (await s.execute(select(SipDemandLease))).scalars().all()
    assert row is not None and row.revoked_at is not None
    assert all(le.status == str(LeaseStatus.REVOKED) for le in leases)
    acts = await audit_actions(session_factory)
    assert AuditAction.SIP_CONSUMER_GRANT_REVOKED.value in acts
    assert AuditAction.SIP_DEMAND_REVOKED.value in acts


async def test_dry_run_apply_changes_nothing(session_factory) -> None:
    """Fails if a dry run writes a registration or an audit row."""
    await seed_users_and_strategy(session_factory, status=StrategyStatus.PAPER)
    reg = ConsumerRegistry(session_factory, config=config(), policy=NoFreshnessPolicy())
    r = await reg.apply_artifact(artifact(entry()), artifact_sha256=SHA, applied_by="op")
    assert r.dry_run and r.issued == ("strategy:9",)
    async with session_factory() as s:
        assert (await s.execute(select(SipConsumerRegistration))).scalars().all() == []
    assert await audit_actions(session_factory) == []


# ============================================================================ trust inputs


def test_lease_surface_carries_no_trust_inputs() -> None:
    """Fails if any lease/grant/publish field is named like a credential, feed, account, clock,
    or a caller-supplied LIVE bound."""
    forbidden = (
        "key",
        "secret",
        "account",
        "credential",
        "entitlement",
        "feed",
        "producer",
        "now",
        "clock",
        "as_of",
        "timestamp",
        "max_age_s",
    )
    fields = set(DemandLease.__dataclass_fields__) | set(ConsumerGrant.__dataclass_fields__)
    fields |= set(inspect.signature(ConsumerRegistry.publish).parameters) - {"self"}
    for f in fields:
        for bad in forbidden:
            assert bad not in f.lower(), f"{f!r} names a trust input"
    assert set(DemandLease.__dataclass_fields__) == {
        "profile",
        "symbols",
        "reasons",
        "expires_at",
        "max_age_trading_days",
    }


# ============================================================================ requirement 3: need ≠ universe


async def test_live_lease_rejects_universe_reasons(registry) -> None:
    """Fails if SELECTION_UNIVERSE or EOD_FEATURE is admitted on SIP_LIVE."""
    reg, _, _ = registry
    g = await reg.grant("strategy:9")
    for r in (DemandReason.SELECTION_UNIVERSE, DemandReason.EOD_FEATURE):
        receipt = await reg.publish(g, lease(reason=r))
        assert receipt.rejection is LeaseRejection.REASON_NOT_ALLOWED_FOR_PROFILE
    assert LIVE_REASONS.isdisjoint({DemandReason.SELECTION_UNIVERSE, DemandReason.EOD_FEATURE})
    assert frozenset(DemandReason) == EOD_REASONS


async def test_eod_accepts_registered_selection_universe(registry) -> None:
    """Fails if a permitted consumer's EOD SELECTION_UNIVERSE lease is refused (Ruling 8)."""
    reg, _, _ = registry
    g = await reg.grant("strategy:9")
    receipt = await reg.publish(
        g, lease(SipProfile.EOD, ("AAPL", "MSFT", "NVDA"), DemandReason.SELECTION_UNIVERSE)
    )
    assert receipt.accepted and receipt.max_age_s is None


async def test_allowed_reasons_narrow_never_widen(session_factory) -> None:
    """Fails if a consumer registered without PENDING_EXIT gets a PENDING_EXIT lease admitted."""
    await seed_users_and_strategy(session_factory, status=StrategyStatus.PAPER)
    reg = ConsumerRegistry(
        session_factory, config=config(), policy=StaticPolicy({"strategy:9": 30.0}), clock=Clock()
    )
    await reg.apply_artifact(
        artifact(entry(allowed_reasons=["HELD"])),
        artifact_sha256=SHA,
        applied_by="op",
        dry_run=False,
    )
    g = await reg.grant("strategy:9")
    assert (await reg.publish(g, lease(reason=DemandReason.PENDING_EXIT))).rejection is (
        LeaseRejection.REASON_NOT_PERMITTED
    )
    assert (await reg.publish(g, lease(reason=DemandReason.HELD))).accepted


async def test_live_cap_makes_selection_universe_unrepresentable(registry) -> None:
    """Fails if a lease larger than the consumer's LIVE cap is admitted (cap = 5 here)."""
    reg, _, _ = registry
    g = await reg.grant("strategy:9")
    big = tuple(f"S{i}" for i in range(190))
    receipt = await reg.publish(g, lease(symbols=big))
    assert receipt.rejection is LeaseRejection.CONSUMER_CAP_EXCEEDED


async def test_reason_required_for_every_symbol_and_symbols_normalized(registry) -> None:
    """Fails if a symbol without a reason, or a malformed symbol, is admitted."""
    reg, _, _ = registry
    g = await reg.grant("strategy:9")
    assert (
        await reg.publish(g, lease(symbols=("AAPL", "MSFT"), reasons={"AAPL": DemandReason.HELD}))
    ).rejection is LeaseRejection.REASON_MISSING
    assert (await reg.publish(g, lease(symbols=("aapl",)))).rejection is (
        LeaseRejection.MALFORMED_SYMBOL
    )
    assert (await reg.publish(g, lease(symbols=()))).rejection is LeaseRejection.EMPTY_SYMBOL_SET


# ============================================================================ requirement 2: lease lifetime


async def test_expiry_is_required_and_bounded(registry) -> None:
    """Fails if a past expiry or one beyond the configured maximum is admitted."""
    reg, clock, _ = registry
    g = await reg.grant("strategy:9")
    assert (await reg.publish(g, lease(expires_in=timedelta(0)))).rejection is (
        LeaseRejection.EXPIRY_IN_PAST
    )
    assert (await reg.publish(g, lease(expires_in=timedelta(hours=7)))).rejection is (
        LeaseRejection.EXPIRY_EXCEEDS_MAX
    )
    with pytest.raises(TypeError):
        DemandLease(profile=SipProfile.LIVE, symbols=frozenset({"AAPL"}), reasons={})  # type: ignore[call-arg]


async def test_lease_max_unconfigured_refuses(session_factory) -> None:
    """Fails if a lease is admitted while the profile's maximum duration is None."""
    await seed_users_and_strategy(session_factory, status=StrategyStatus.PAPER)
    reg = ConsumerRegistry(
        session_factory,
        config=config(live_max_lease_s=None),
        policy=StaticPolicy({"strategy:9": 30.0}),
        clock=Clock(),
    )
    await reg.apply_artifact(artifact(entry()), artifact_sha256=SHA, applied_by="op", dry_run=False)
    g = await reg.grant("strategy:9")
    assert (await reg.publish(g, lease())).rejection is LeaseRejection.LEASE_MAX_UNCONFIGURED


async def test_revoke_on_strategy_stop_removes_immediately(registry, session_factory) -> None:
    """Fails if revoke_for_strategy leaves the consumer's symbols in the union."""
    reg, clock, _ = registry
    g = await reg.grant("strategy:9")
    assert (await reg.publish(g, lease())).accepted
    union = DemandUnion(session_factory, clock=clock)
    assert (await union.for_profile(SipProfile.LIVE)).symbols == {"AAPL", "MSFT"}
    assert await reg.revoke_for_strategy(9, reason="strategy_unregistered:user_stop") == 1
    assert (await union.for_profile(SipProfile.LIVE)).symbols == frozenset()


async def test_engine_unregister_calls_revoke_hook() -> None:
    """Fails if StrategyEngine.unregister no longer routes through _revoke_demand."""
    from app.strategies.engine import StrategyEngine

    src = inspect.getsource(StrategyEngine.unregister)
    assert "_revoke_demand(strategy_id" in src
    assert callable(getattr(StrategyEngine, "set_demand_registry", None))


async def test_expiry_backstop_when_runtime_dies(registry, session_factory) -> None:
    """Fails if an expired lease still contributes to the union after expire_due()."""
    reg, clock, _ = registry
    g = await reg.grant("strategy:9")
    assert (await reg.publish(g, lease(expires_in=timedelta(minutes=10)))).accepted
    clock.advance(minutes=11)
    union = DemandUnion(session_factory, clock=clock)
    # Even before the tick the union ignores lapsed rows...
    assert (await union.for_profile(SipProfile.LIVE)).symbols == frozenset()
    # ...and the tick flips the row to EXPIRED with an audit row.
    assert await reg.expire_due() == 1
    async with session_factory() as s:
        row = (await s.execute(select(SipDemandLease))).scalars().one()
    assert row.status == str(LeaseStatus.EXPIRED)
    assert AuditAction.SIP_DEMAND_EXPIRED.value in await audit_actions(session_factory)


async def test_reconciliation_revokes_when_strategy_not_runnable(registry, session_factory) -> None:
    """Fails if a lease survives expire_due() after its strategy left the runnable statuses."""
    reg, _, _ = registry
    g = await reg.grant("strategy:9")
    assert (await reg.publish(g, lease())).accepted
    async with session_factory() as s:
        strat = await s.get(Strategy, 9)
        strat.status = StrategyStatus.HALTED
        await s.commit()
    assert await reg.expire_due() == 1
    rows = await audit_rows(session_factory, AuditAction.SIP_DEMAND_REVOKED)
    assert rows and rows[0]["reason"] == "strategy_not_runnable"


async def test_withdraw_is_consumer_scoped(registry, session_factory) -> None:
    """Fails if a grant can withdraw another consumer's lease, or a non-ACTIVE lease."""
    reg, _, _ = registry
    g = await reg.grant("strategy:9")
    r = await reg.publish(g, lease())
    assert r.accepted and r.lease_id is not None
    other = ConsumerGrant("strategy:9", b"\x01" * 16)
    assert await reg.withdraw(other, r.lease_id) is False
    assert await reg.withdraw(g, r.lease_id) is True
    assert await reg.withdraw(g, r.lease_id) is False
    assert AuditAction.SIP_DEMAND_WITHDRAWN.value in await audit_actions(session_factory)


# ============================================================================ requirement 4: strictest


async def test_union_takes_strictest_bound(session_factory) -> None:
    """Fails if two leases naming AAPL with 30 s and 10 s yield anything but 10 s."""
    await seed_users_and_strategy(session_factory, status=StrategyStatus.PAPER)
    clock = Clock()
    reg = ConsumerRegistry(
        session_factory,
        config=config(),
        policy=StaticPolicy({"strategy:9": 30.0, "service:risk-reference": 10.0}),
        clock=clock,
    )
    await reg.apply_artifact(
        artifact(entry(), entry("service:risk-reference", strategy_id=None)),
        artifact_sha256=SHA,
        applied_by="op",
        dry_run=False,
    )
    g9 = await reg.grant("strategy:9")
    gs = await reg.grant("service:risk-reference")
    assert (await reg.publish(g9, lease(symbols=("AAPL", "MSFT")))).accepted
    assert (await reg.publish(gs, lease(symbols=("AAPL",)))).accepted
    d = await DemandUnion(session_factory, clock=clock).for_profile(SipProfile.LIVE)
    assert d.symbols == {"AAPL", "MSFT"}
    assert d.per_symbol_bound_s == {"AAPL": 10.0, "MSFT": 30.0}
    assert d.strictest_bound_s == 10.0
    assert d.lease_count == 2 and d.consumer_ids == {"strategy:9", "service:risk-reference"}


async def test_live_bound_comes_from_policy_not_lease(registry, session_factory) -> None:
    """Fails if the persisted LIVE bound differs from what the governed policy returned."""
    reg, _, policy = registry
    g = await reg.grant("strategy:9")
    r = await reg.publish(g, lease())
    assert r.accepted and r.max_age_s == 30.0
    assert policy.calls == [("strategy:9", "strategy9-execution-policy@test")]
    async with session_factory() as s:
        row = (await s.execute(select(SipDemandLease))).scalars().one()
    assert row.max_age_s == Decimal("30.000")
    admitted = await audit_rows(session_factory, AuditAction.SIP_DEMAND_ADMITTED)
    assert admitted[0]["max_age_s"] == 30.0


async def test_freshness_unbound_refused_no_default_no_inheritance(session_factory) -> None:
    """Fails if a consumer whose policy returns None gets a LIVE lease, or if another consumer's
    bound is borrowed."""
    await seed_users_and_strategy(session_factory, status=StrategyStatus.PAPER)
    policy = StaticPolicy({"strategy:9": None, "service:risk-reference": 10.0})
    reg = ConsumerRegistry(session_factory, config=config(), policy=policy, clock=Clock())
    await reg.apply_artifact(
        artifact(entry(), entry("service:risk-reference", strategy_id=None)),
        artifact_sha256=SHA,
        applied_by="op",
        dry_run=False,
    )
    gs = await reg.grant("service:risk-reference")
    assert (await reg.publish(gs, lease(symbols=("AAPL",)))).accepted
    g9 = await reg.grant("strategy:9")
    r = await reg.publish(g9, lease(symbols=("AAPL",)))
    assert r.rejection is LeaseRejection.FRESHNESS_UNBOUND
    # The other consumer's admitted bound did not leak: strategy:9 has no lease row at all.
    async with session_factory() as s:
        rows = (await s.execute(select(SipDemandLease))).scalars().all()
    assert {r_.consumer_id for r_ in rows} == {"service:risk-reference"}


async def test_no_freshness_policy_refuses_every_live_lease(session_factory) -> None:
    """Fails if the production provider admits any LIVE lease (B3 Decision 5)."""
    await seed_users_and_strategy(session_factory, status=StrategyStatus.PAPER)
    reg = ConsumerRegistry(
        session_factory, config=config(), policy=NoFreshnessPolicy(), clock=Clock()
    )
    await reg.apply_artifact(artifact(entry()), artifact_sha256=SHA, applied_by="op", dry_run=False)
    g = await reg.grant("strategy:9")
    assert (await reg.publish(g, lease())).rejection is LeaseRejection.FRESHNESS_UNBOUND
    assert (await reg.publish(g, lease(SipProfile.EOD))).accepted  # EOD is trading-day governed


async def test_no_platform_level_live_freshness_fallback_exists() -> None:
    """Fails if ANY platform-side SIP_LIVE freshness value reappears: a Settings field, a module
    constant in the sip package, a second FreshnessPolicyProvider under app/, a NoFreshnessPolicy
    that returns anything but None, or a production ConsumerRegistry wired to a different provider.

    Owner ruling 2026-09-02 (B3 Decision 5): NULL LIVE freshness = REFUSED, no default, no
    inheritance, no best effort. The bound may originate only from the consumer's governed
    execution policy. This test makes that structural, so a "temporary" default cannot land quietly.
    """
    from app.config import Settings
    from app.market_data.sip import profiles

    # 1. No Settings field expresses a LIVE freshness/age value for the SIP plane.
    offenders = [
        name
        for name in Settings.model_fields
        if name.startswith("sip_")
        and any(tok in name for tok in ("max_age", "freshness", "default", "staleness"))
    ]
    assert offenders == [], offenders

    # 2. No module-level LIVE age constant in the sip package (the Implementation-A placeholder is
    #    gone and must not return under another name).
    sip_root = Path(inspect.getfile(ConsumerRegistry)).resolve().parent
    consts: list[str] = []
    for py in sip_root.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in tree.body:
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            for t in targets:
                if isinstance(t, ast.Name) and "LIVE" in t.id and "AGE" in t.id:
                    consts.append(f"{py.name}:{t.id}")
    assert consts == [], consts
    assert not hasattr(profiles, "DEFAULT_LIVE_MAX_AGE_S")

    # 3. Exactly one provider implementation exists under app/, and it returns None unconditionally.
    app_root = sip_root.parents[1]  # .../app
    providers: dict[str, ast.AST] = {}
    for py in app_root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for fn in node.body:
                    if (
                        isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef)
                        and fn.name == "live_max_age_s"
                    ):
                        providers[node.name] = fn
    assert set(providers) == {"NoFreshnessPolicy", "FreshnessPolicyProvider"}, sorted(providers)
    body = [n for n in providers["NoFreshnessPolicy"].body if not isinstance(n, ast.Expr)]
    assert len(body) == 1 and isinstance(body[0], ast.Return)
    assert isinstance(body[0].value, ast.Constant) and body[0].value.value is None
    assert await NoFreshnessPolicy().live_max_age_s("strategy:9", "any-policy-ref") is None

    # 4. The production wiring constructs ConsumerRegistry with NoFreshnessPolicy() and nothing else.
    lifespan_src = (app_root / "lifespan.py").read_text(encoding="utf-8")
    policies: list[str] = []
    for node in ast.walk(ast.parse(lifespan_src)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ConsumerRegistry"
        ):
            kw = {k.arg: k.value for k in node.keywords}
            assert "policy" in kw, "ConsumerRegistry constructed without an explicit policy"
            value = kw["policy"]
            assert isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
            policies.append(value.func.id)
    assert policies == ["NoFreshnessPolicy"], policies


async def test_bound_below_producer_floor_rejected(session_factory) -> None:
    """Fails if a 4 s bound is admitted with a 5 s floor, or admitted with no floor at all."""
    await seed_users_and_strategy(session_factory, status=StrategyStatus.PAPER)
    policy = StaticPolicy({"strategy:9": 4.0})
    reg = ConsumerRegistry(session_factory, config=config(), policy=policy, clock=Clock())
    await reg.apply_artifact(artifact(entry()), artifact_sha256=SHA, applied_by="op", dry_run=False)
    g = await reg.grant("strategy:9")
    assert (await reg.publish(g, lease())).rejection is LeaseRejection.BOUND_BELOW_PRODUCER_FLOOR
    reg2 = ConsumerRegistry(
        session_factory,
        config=config(live_min_interval_s=None),
        policy=StaticPolicy({"strategy:9": 30.0}),
        clock=Clock(),
    )
    g2 = await reg2.grant("strategy:9")
    assert (await reg2.publish(g2, lease())).rejection is LeaseRejection.PRODUCER_FLOOR_UNCONFIGURED


# ============================================================================ requirement 5: caps


async def test_plane_cap_unconfigured_refuses(session_factory) -> None:
    """Fails if a LIVE lease is admitted while sip_live_plane_symbol_cap is None."""
    await seed_users_and_strategy(session_factory, status=StrategyStatus.PAPER)
    reg = ConsumerRegistry(
        session_factory,
        config=config(live_plane_symbol_cap=None),
        policy=StaticPolicy({"strategy:9": 30.0}),
        clock=Clock(),
    )
    await reg.apply_artifact(artifact(entry()), artifact_sha256=SHA, applied_by="op", dry_run=False)
    g = await reg.grant("strategy:9")
    assert (await reg.publish(g, lease())).rejection is LeaseRejection.PLANE_CAP_UNCONFIGURED


async def test_plane_cap_rejects_submission_not_truncates(session_factory) -> None:
    """Fails if the union changes after an overflowing submission, or if a strict subset of the
    submitted symbols is admitted."""
    await seed_users_and_strategy(session_factory, status=StrategyStatus.PAPER)
    clock = Clock()
    reg = ConsumerRegistry(
        session_factory,
        config=config(live_plane_symbol_cap=6),
        policy=StaticPolicy({"strategy:9": 30.0, "service:risk-reference": 30.0}),
        clock=clock,
    )
    await reg.apply_artifact(
        artifact(entry(), entry("service:risk-reference", strategy_id=None)),
        artifact_sha256=SHA,
        applied_by="op",
        dry_run=False,
    )
    g9 = await reg.grant("strategy:9")
    gs = await reg.grant("service:risk-reference")
    assert (await reg.publish(g9, lease(symbols=("A", "B", "C", "D")))).accepted
    before = (await DemandUnion(session_factory, clock=clock).for_profile(SipProfile.LIVE)).symbols
    r = await reg.publish(gs, lease(symbols=("E", "F", "G")))  # 4 + 3 = 7 > 6
    assert r.rejection is LeaseRejection.PLANE_CAP_EXCEEDED
    after = (await DemandUnion(session_factory, clock=clock).for_profile(SipProfile.LIVE)).symbols
    assert after == before == {"A", "B", "C", "D"}
    # A renewal replaces the consumer's own prior lease, so it is counted once, not twice.
    assert (await reg.publish(g9, lease(symbols=("A", "B", "C", "D", "E")))).accepted
    rejected = await audit_rows(session_factory, AuditAction.SIP_DEMAND_REJECTED)
    assert rejected[-1]["rejection"] == "PLANE_CAP_EXCEEDED"


# ============================================================================ requirement 6: malformed


async def test_malformed_lease_contributes_nothing(session_factory) -> None:
    """Fails if a rejected lease has a row, or if another consumer's union changes because of it."""
    await seed_users_and_strategy(session_factory, status=StrategyStatus.PAPER)
    clock = Clock()
    reg = ConsumerRegistry(
        session_factory,
        config=config(),
        policy=StaticPolicy({"strategy:9": 30.0, "service:risk-reference": 30.0}),
        clock=clock,
    )
    await reg.apply_artifact(
        artifact(entry(), entry("service:risk-reference", strategy_id=None)),
        artifact_sha256=SHA,
        applied_by="op",
        dry_run=False,
    )
    g9 = await reg.grant("strategy:9")
    gs = await reg.grant("service:risk-reference")
    assert (await reg.publish(g9, lease(symbols=("AAPL",)))).accepted
    assert (await reg.publish(gs, lease(symbols=("bad symbol",)))).rejection is (
        LeaseRejection.MALFORMED_SYMBOL
    )
    async with session_factory() as s:
        rows = (await s.execute(select(SipDemandLease))).scalars().all()
    assert [r.consumer_id for r in rows] == ["strategy:9"]
    assert (
        await DemandUnion(session_factory, clock=clock).for_profile(SipProfile.LIVE)
    ).symbols == {"AAPL"}
    assert reg.rejected_count == 1 and reg.last_rejection == "MALFORMED_SYMBOL"


async def test_every_rejection_reason_is_audited(registry, session_factory) -> None:
    """Fails if any produced LeaseRejection lacks a SIP_DEMAND_REJECTED row carrying its name."""
    reg, _, _ = registry
    g = await reg.grant("strategy:9")
    produced: list[str] = []
    for bad in (
        lease(symbols=()),
        lease(symbols=("x",)),
        lease(reason=DemandReason.EOD_FEATURE),
        lease(expires_in=timedelta(0)),
        lease(symbols=tuple(f"S{i}" for i in range(6))),
    ):
        r = await reg.publish(g, bad)
        assert r.rejection is not None
        produced.append(str(r.rejection))
    audited = [
        p["rejection"] for p in await audit_rows(session_factory, AuditAction.SIP_DEMAND_REJECTED)
    ]
    assert audited == produced
    assert len(set(produced)) == 5


# ============================================================================ audit contract


async def test_audit_requested_admitted_served_are_distinct(registry, session_factory) -> None:
    """Fails if ADMITTED lacks its REQUESTED row, or SERVED is written on admission rather than on
    a cache write."""
    reg, clock, _ = registry
    g = await reg.grant("strategy:9")
    r = await reg.publish(g, lease(symbols=("AAPL",)))
    assert r.accepted
    acts = await audit_actions(session_factory)
    assert acts[-2:] == [
        AuditAction.SIP_DEMAND_REQUESTED.value,
        AuditAction.SIP_DEMAND_ADMITTED.value,
    ]
    assert AuditAction.SIP_DEMAND_SERVED.value not in acts
    admitted = (await audit_rows(session_factory, AuditAction.SIP_DEMAND_ADMITTED))[0]
    requested_ids = {row["request_audit_id"] for row in [admitted]}
    async with session_factory() as s:
        req = (
            (
                await s.execute(
                    select(AuditLog).where(
                        AuditLog.action == AuditAction.SIP_DEMAND_REQUESTED.value
                    )
                )
            )
            .scalars()
            .one()
        )
    assert requested_ids == {req.id}
    # SERVED appears only when the scheduler reports a cache write for a demanded symbol.
    assert await reg.mark_served(SipProfile.LIVE, ["AAPL"], trading_date=date(2026, 9, 2)) == 1
    served = await audit_rows(session_factory, AuditAction.SIP_DEMAND_SERVED)
    assert served[0]["served"] == ["AAPL"] and served[0]["missing"] == []
    # A write for a symbol nobody leased serves nobody.
    assert await reg.mark_served(SipProfile.LIVE, ["ZZZ"], trading_date=date(2026, 9, 2)) == 0


async def test_renewal_supersedes_and_audits(registry, session_factory) -> None:
    """Fails if a second lease for the same consumer+profile leaves the first ACTIVE."""
    reg, _, _ = registry
    g = await reg.grant("strategy:9")
    a = await reg.publish(g, lease(symbols=("AAPL",)))
    b = await reg.publish(g, lease(symbols=("MSFT",)))
    assert a.accepted and b.accepted and b.superseded_lease_id == a.lease_id
    async with session_factory() as s:
        first = await s.get(SipDemandLease, a.lease_id)
    assert first.status == str(LeaseStatus.SUPERSEDED) and first.superseded_by == b.lease_id
    assert AuditAction.SIP_DEMAND_RENEWED.value in await audit_actions(session_factory)


async def test_audit_payloads_carry_no_secret_shaped_values(registry, session_factory) -> None:
    """Fails if any B3 audit payload contains the producer key fingerprint or a key-like field."""
    reg, _, _ = registry
    g = await reg.grant("strategy:9")
    await reg.publish(g, lease())
    await reg.revoke(g, reason="test")
    async with session_factory() as s:
        rows = (await s.execute(select(AuditLog))).scalars().all()
    for row in rows:
        payload = json.loads(row.payload_json)
        assert "api_key" not in payload and "secret" not in payload
        assert PRODUCER.key_fingerprint not in row.payload_json


# ============================================================================ restart / retention


async def test_restart_reloads_leases_from_db(registry, session_factory) -> None:
    """Fails if a fresh registry/union instance cannot see ACTIVE unexpired leases."""
    reg, clock, _ = registry
    g = await reg.grant("strategy:9")
    assert (await reg.publish(g, lease())).accepted
    fresh_union = DemandUnion(session_factory, clock=clock)
    assert (await fresh_union.for_profile(SipProfile.LIVE)).symbols == {"AAPL", "MSFT"}
    # A fresh registry has no grants: the old capability does not survive the process.
    fresh_reg = ConsumerRegistry(
        session_factory, config=config(), policy=StaticPolicy({"strategy:9": 30.0}), clock=clock
    )
    assert (await fresh_reg.publish(g, lease())).rejection is LeaseRejection.GRANT_INVALID


async def test_prune_preserves_newest_row_under_active_lease(session_factory) -> None:
    """Fails if retention deletes the only (old) row of a leased symbol."""
    cache = SipOperationalCache(session_factory)
    old = date(2026, 7, 1)
    rec = SipRecord(
        symbol="AAPL",
        profile=SipProfile.EOD,
        trading_date=old,
        session="regular",
        source_timestamp=datetime(2026, 7, 1, 20, 0, tzinfo=UTC),
        received_at_utc=datetime(2026, 7, 1, 20, 0, tzinfo=UTC),
        price=Decimal("1"),
        entitlement_identity=PRODUCER.entitlement_identity,
        credential_identity_fingerprint=PRODUCER.key_fingerprint,
    )
    other = SipRecord(**{**rec.__dict__, "symbol": "MSFT"})
    await cache.upsert([rec, other])
    removed = await cache.prune(30, now=T0, keep_newest_for={"AAPL"})
    assert removed == 1
    assert await cache.get("AAPL", SipProfile.EOD) is not None
    assert await cache.get("MSFT", SipProfile.EOD) is None
    # Without protection the default behaviour is unchanged.
    await cache.upsert([other])
    assert await cache.prune(30, now=T0) == 2


async def test_status_surface_reports_plane_without_secrets(registry, session_factory) -> None:
    """Fails if the demand status omits cap headroom / rejection counters or carries secrets."""
    reg, clock, _ = registry
    g = await reg.grant("strategy:9")
    await reg.publish(g, lease(symbols=("AAPL",)))
    await reg.publish(g, lease(symbols=("x",)))
    await reg.verify_artifact(SHA)
    st = await DemandUnion(session_factory, clock=clock).status(reg)
    live = st.profiles["SIP_LIVE"]
    assert st.registry_verified and st.artifact_sha256 == SHA and st.registered_consumers == 1
    assert live.union_size == 1 and live.plane_cap == 10 and live.cap_headroom == 9
    assert live.strictest_bound_s == 30.0
    assert st.rejected_count == 1 and st.last_rejection == "MALFORMED_SYMBOL"
    assert "key" not in repr(st).lower()


def test_artifact_sha256_is_over_raw_bytes() -> None:
    """Fails if the digest is computed over anything but the file bytes."""
    import hashlib

    raw = b'{"schema_version": 1, "consumers": []}\n'
    assert artifact_sha256(raw) == hashlib.sha256(raw).hexdigest()


def test_shipped_artifact_is_valid_and_empty() -> None:
    """Fails if the shipped registry artifact names a consumer (no governed caps exist yet)."""
    root = Path(__file__).resolve().parents[2]
    raw = (root / "config" / "sip_consumer_registry.v1.json").read_bytes()
    art = json.loads(raw)
    assert ConsumerRegistry.validate_artifact(art) == []
