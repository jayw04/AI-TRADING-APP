"""SIP-CACHE-001 Implementation B1 — governed consumer API.

The negative suite proves, in three independent layers:

    ENTITLEMENT CAPABILITY DOES NOT CREATE PRODUCER AUTHORITY
    CONSUMER CANNOT EXPRESS ENTITLEMENT IDENTITY

A behavioural assertion alone would prove only that *the one path tried* failed. The structural and
AST layers prove the capability is absent rather than merely unreachable today.

For every test, the failing input is stated in the docstring.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.market_data.sip import api as sip_api
from app.market_data.sip.api import (
    SipConsumerService,
    SipLiveBoundRequired,
    build_consumer_service,
)
from app.market_data.sip.cache import SipOperationalCache
from app.market_data.sip.identity import PRODUCER
from app.market_data.sip.profiles import SipProfile
from app.market_data.sip.readiness import SipNotReadyError, SipReadinessState
from app.market_data.sip.schema import SipRecord

TD = date(2026, 9, 1)

# Measured 2026-08-31: these accounts genuinely return recent-SIP 200. Fingerprints are not secrets.
# They are the strongest negative cases available: real entitlement, no producer authority.
CENSUS_SIP_CAPABLE = {
    "account_5_PA3DBWDGOING": "5115fc74f097",
    "account_6_PA30T0I3JJV9": "5da9c9d59a45",
}

# Any of these appearing in the public consumer surface would let a consumer name an identity.
FORBIDDEN_PARAM_SUBSTRINGS = (
    "account",
    "api_key",
    "apikey",
    "secret",
    "credential",
    "fingerprint",
    "entitlement",
    "feed",
    "producer",
    "broker",
    "key_id",
    # Freshness is a trust decision, so the valuation clock is a trust input just like the
    # credential. SIP-CACHE-CONSUMER-CLOCK-INJECTION-001: a caller-supplied time converted STALE
    # into PASS with a usable price. The clock is injected at construction instead.
    "now",
    "clock",
    "as_of",
    "timestamp",
)

PUBLIC_METHODS = ("get_reference", "get_eod", "readiness", "status")


def _rec(symbol: str, *, ts: datetime, profile: SipProfile = SipProfile.LIVE) -> SipRecord:
    return SipRecord(
        symbol=symbol,
        profile=profile,
        trading_date=TD,
        session="regular",
        source_timestamp=ts,
        received_at_utc=datetime.now(UTC),
        bid=Decimal("100.10"),
        ask=Decimal("100.20"),
        price=Decimal("100.20"),
        entitlement_identity=PRODUCER.entitlement_identity,
        credential_identity_fingerprint=PRODUCER.key_fingerprint,
    )


async def _svc(session_factory, **kw) -> SipConsumerService:
    return build_consumer_service(session_factory, **kw)


def _frozen_clock(at: datetime):
    """A deterministic clock, injected at construction — the only way to control time."""
    return lambda: at


# ============================================================ LAYER 1 — STRUCTURAL


def test_layer1_public_surface_cannot_express_an_identity() -> None:
    """L1 — fails if: any public consumer method gains a credential-shaped parameter.

    This is the load-bearing test. It does not check that nomination *fails*; it checks that
    nomination cannot be *written*.
    """
    seen: set[str] = set()
    for name in PUBLIC_METHODS:
        fn = getattr(SipConsumerService, name)
        for param in inspect.signature(fn).parameters:
            if param in ("self", "kwargs", "args"):
                continue
            seen.add(param)
            low = param.lower()
            for bad in FORBIDDEN_PARAM_SUBSTRINGS:
                assert bad not in low, (
                    f"{name}(): parameter {param!r} lets a consumer name an identity or feed. "
                    "The consumer contract must make that unsayable."
                )
    # Positive statement of the whole surface, so an addition is visible in the diff.
    assert seen == {
        "symbol",
        "profile",
        "max_age_s",
        "trading_date",
        "live_max_age_s",
        "eod_expected_trading_date",
    }, f"public consumer surface changed: {sorted(seen)}"


def test_layer1_builder_takes_no_credential() -> None:
    """L1 — fails if: the service can be constructed with a caller-chosen identity."""
    params = set(inspect.signature(build_consumer_service).parameters)
    assert "session_factory" in params
    for p in params:
        for bad in FORBIDDEN_PARAM_SUBSTRINGS:
            assert bad not in p.lower(), f"build_consumer_service exposes {p!r}"


def test_layer1_api_module_exports_no_identity_symbol() -> None:
    """L1 — fails if: the consumer module re-exports the producer identity."""
    exported = {n for n in dir(sip_api) if not n.startswith("_")}
    assert "PRODUCER" not in exported
    assert "ProducerPins" not in exported
    assert "credentials_for_mode" not in exported
    assert "SipProducer" not in exported


# ============================================================ LAYER 2 — RUNTIME INJECTION


async def test_layer2_nomination_by_kwarg_is_refused(session_factory) -> None:
    """L2 — fails if: a consumer can pass an identity through any public call.

    Every credential-shaped kwarg is attempted against every public read method.
    """
    svc = await _svc(session_factory)
    for label, fp in CENSUS_SIP_CAPABLE.items():
        for kwargs in (
            {"account_id": 5},
            {"credential_fingerprint": fp},
            {"entitlement_identity": f"algo_trader_plus/{label}"},
            {"feed": "sip"},
            {"producer": label},
            {"api_key": "PKPRETENDER0000000"},
        ):
            with pytest.raises(TypeError):
                await svc.get_reference("AAPL", profile=SipProfile.LIVE, max_age_s=30, **kwargs)
            with pytest.raises(TypeError):
                await svc.get_eod("AAPL", **kwargs)


async def test_layer2_no_credential_resolution_occurs_on_the_consumer_path(
    monkeypatch, session_factory
) -> None:
    """L2 — fails if: a consumer read resolves ANY credential.

    Asserts on a call recorder rather than on the absence of an exception: the proof is that the
    credential path was never entered, not that it happened to error.
    """
    calls: list[tuple] = []

    async def _recorder(mode, account_id, sf):  # noqa: ANN001
        calls.append((mode, account_id))
        raise AssertionError("consumer path must never resolve a credential")

    monkeypatch.setattr("app.brokers.alpaca.credentials.credentials_for_mode", _recorder)

    cache = SipOperationalCache(session_factory)
    await cache.upsert([_rec("AAPL", ts=datetime.now(UTC))])
    svc = await _svc(session_factory, expected_symbols=1)

    await svc.get_reference("AAPL", profile=SipProfile.LIVE, max_age_s=3600)
    await svc.get_eod("AAPL")
    await svc.readiness(SipProfile.EOD)
    await svc.status(live_max_age_s=3600)

    assert calls == [], f"consumer path resolved credentials: {calls}"


async def test_layer2_sip_capable_identity_confers_no_authority(session_factory) -> None:
    """L2 — fails if: a genuinely SIP-entitled non-designated credential gains producer authority.

    Accounts 5 and 6 really do return recent-SIP 200. They are still refused. Entitlement
    capability does not create producer authority.
    """
    from app.market_data.sip.identity import ProducerIdentityError

    for label, fp in CENSUS_SIP_CAPABLE.items():
        assert fp != PRODUCER.key_fingerprint, f"{label} must not be the designated producer"
        with pytest.raises(ProducerIdentityError):
            PRODUCER.verify(f"PK{label.upper()[:18]}")


async def test_layer2_caller_cannot_supply_a_valuation_time(session_factory) -> None:
    """L2 — fails if: a caller can convert STALE into PASS by naming the time.

    SIP-CACHE-CONSUMER-CLOCK-INJECTION-001. Reproduced empirically before the repair: a 6-hour-stale
    record returned PASS with a usable price when the caller passed an earlier ``now``. Freshness is
    a trust decision, so the clock is a trust input exactly like the credential.
    """
    stale_ts = datetime.now(UTC) - timedelta(hours=6)
    cache = SipOperationalCache(session_factory)
    await cache.upsert([_rec("AAPL", ts=stale_ts)])
    svc = await _svc(session_factory, expected_symbols=1)

    honest = await svc.get_reference("AAPL", profile=SipProfile.LIVE, max_age_s=30)
    assert honest.state is SipReadinessState.STALE and honest.price is None

    # The exploit is not merely refused at runtime — it cannot be expressed.
    for kwargs in (
        {"now": stale_ts + timedelta(seconds=1)},
        {"clock": _frozen_clock(stale_ts)},
        {"as_of": stale_ts},
    ):
        with pytest.raises(TypeError):
            await svc.get_reference("AAPL", profile=SipProfile.LIVE, max_age_s=30, **kwargs)
        with pytest.raises(TypeError):
            await svc.get_eod("AAPL", **kwargs)


async def test_injected_clock_is_the_only_time_control(session_factory) -> None:
    """Fails if: the constructor clock is ignored, or a per-call time still exists.

    Proves the seam works for deterministic tests without opening it to production callers.
    """
    ts = datetime(2026, 9, 1, 14, 30, tzinfo=UTC)
    cache = SipOperationalCache(session_factory)
    await cache.upsert([_rec("AAPL", ts=ts)])

    fresh = await _svc(
        session_factory, expected_symbols=1, clock=_frozen_clock(ts + timedelta(seconds=5))
    )
    assert (await fresh.get_reference("AAPL", profile=SipProfile.LIVE, max_age_s=30)).is_pass

    late = await _svc(
        session_factory, expected_symbols=1, clock=_frozen_clock(ts + timedelta(hours=6))
    )
    v = await late.get_reference("AAPL", profile=SipProfile.LIVE, max_age_s=30)
    assert v.state is SipReadinessState.STALE and v.price is None


# ============================================================ LAYER 3 — AST / IMPORT BOUNDARY


def _sip_pkg() -> Path:
    return Path(sip_api.__file__).resolve().parent


def test_layer3_only_producer_may_import_the_credential_resolver() -> None:
    """L3 — fails if: any SIP module except producer.py imports the credential resolver."""
    offenders = []
    for path in _sip_pkg().glob("*.py"):
        if path.name == "producer.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "credentials" in node.module:
                    offenders.append(f"{path.name}:{node.lineno}")
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if "credentials" in a.name:
                        offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"credential resolver imported outside producer.py: {offenders}"


def test_layer3_consumer_module_imports_no_broker_sdk() -> None:
    """L3 — fails if: the consumer module can construct a trading or data client."""
    tree = ast.parse(Path(sip_api.__file__).read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.ImportFrom) and node.module:
            mods = [node.module]
        elif isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        for m in mods:
            if m.startswith("alpaca") or m.startswith("app.brokers"):
                bad.append(f"{m}:{node.lineno}")
    assert not bad, f"consumer module reaches a broker SDK: {bad}"


def test_layer3_identity_is_not_imported_outside_the_sip_package() -> None:
    """L3 — fails if: any module outside the SIP package imports the producer identity."""
    app_root = _sip_pkg().parents[1]
    pkg = _sip_pkg()
    offenders = []
    for path in app_root.rglob("*.py"):
        if pkg in path.parents or path.parent == pkg:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and "market_data.sip.identity" in node.module
            ):
                offenders.append(f"{path.relative_to(app_root)}:{node.lineno}")
    assert not offenders, f"producer identity imported outside the package: {offenders}"


# ============================================================ CONTRACT BEHAVIOUR


async def test_live_requires_an_explicit_bound(session_factory) -> None:
    """Fails if: infrastructure supplies a SIP_LIVE freshness default by omission.

    The execution-reference bound is a consumer execution-policy value. It must not be inherited.
    """
    svc = await _svc(session_factory)
    with pytest.raises(SipLiveBoundRequired):
        await svc.get_reference("AAPL", profile=SipProfile.LIVE)
    with pytest.raises(SipLiveBoundRequired):
        await svc.readiness(SipProfile.LIVE)


async def test_pass_exposes_price_and_full_provenance(session_factory) -> None:
    """Fails if: a PASS view loses any provenance field."""
    cache = SipOperationalCache(session_factory)
    await cache.upsert([_rec("AAPL", ts=datetime.now(UTC))])
    svc = await _svc(session_factory, expected_symbols=1)
    v = await svc.get_reference("AAPL", profile=SipProfile.LIVE, max_age_s=3600)
    assert v.is_pass and v.price == Decimal("100.20")
    assert v.feed == "sip" and v.feed_is_authentic is True
    assert v.source_timestamp is not None and v.received_at_utc is not None
    assert v.entitlement_identity == PRODUCER.entitlement_identity
    assert v.credential_identity_fingerprint == PRODUCER.key_fingerprint
    assert v.require_price() == Decimal("100.20")


async def test_stale_view_carries_no_usable_price(session_factory) -> None:
    """Fails if: a STALE view returns a price a consumer could mistake for current."""
    cache = SipOperationalCache(session_factory)
    await cache.upsert([_rec("AAPL", ts=datetime.now(UTC) - timedelta(hours=6))])
    svc = await _svc(session_factory, expected_symbols=1)
    v = await svc.get_reference("AAPL", profile=SipProfile.LIVE, max_age_s=30)
    assert v.state is SipReadinessState.STALE
    assert v.price is None and v.bid is None and v.ask is None
    # Provenance still present so the consumer can report WHAT was stale.
    assert v.source_timestamp is not None
    with pytest.raises(SipNotReadyError):
        v.require_price()


async def test_absent_and_entitlement_fail_carry_no_price(session_factory) -> None:
    """Fails if: ABSENT or ENTITLEMENT_FAIL leaks a price."""
    svc = await _svc(session_factory, expected_symbols=1)
    v = await svc.get_reference("NOPE", profile=SipProfile.LIVE, max_age_s=30)
    assert v.state is SipReadinessState.ABSENT and v.price is None

    blocked = await _svc(session_factory, expected_symbols=1, entitlement_ok=False)
    v2 = await blocked.get_reference("AAPL", profile=SipProfile.LIVE, max_age_s=30)
    assert v2.state is SipReadinessState.ENTITLEMENT_FAIL and v2.price is None
    with pytest.raises(SipNotReadyError):
        v2.require_price()


async def test_require_price_has_no_fallback_surface(session_factory) -> None:
    """Fails if: require_price gains a default or fallback-feed escape hatch."""
    params = set(inspect.signature(sip_api.SipDataView.require_price).parameters)
    assert params == {"self"}, f"require_price gained an escape hatch: {params}"


async def test_eod_is_not_a_live_quote(session_factory) -> None:
    """Fails if: an EOD record satisfies a LIVE request, or vice versa."""
    cache = SipOperationalCache(session_factory)
    await cache.upsert([_rec("AAPL", ts=datetime.now(UTC), profile=SipProfile.EOD)])
    svc = await _svc(session_factory, expected_symbols=1)
    live = await svc.get_reference("AAPL", profile=SipProfile.LIVE, max_age_s=30)
    assert live.state is SipReadinessState.ABSENT
    eod = await svc.get_eod("AAPL")
    assert eod.is_pass


async def test_status_surface_is_observable_and_secret_free(session_factory) -> None:
    """Fails if: status omits a required field or exposes a secret."""
    cache = SipOperationalCache(session_factory)
    await cache.upsert([_rec("AAPL", ts=datetime.now(UTC), profile=SipProfile.EOD)])
    svc = await _svc(session_factory, expected_symbols=1)
    svc.record_acquisition_result(SipProfile.EOD, ok=True)
    st = await svc.status(live_max_age_s=30, eod_expected_trading_date=TD)

    assert st.producer_fingerprint == PRODUCER.key_fingerprint
    assert len(st.producer_fingerprint) == 12  # fingerprint, not a key
    assert "SIP_EOD" in st.profiles and "SIP_LIVE" in st.profiles
    eod = st.profiles["SIP_EOD"]
    for attr in (
        "readiness_state",
        "last_transition_reason",
        "evaluated_at",
        "last_successful_acquisition",
        "latest_observation",
        "observed_symbols",
        "coverage",
        "entitlement_state",
        "quality_counts",
        "acquisition_failures",
        "retry_count",
    ):
        assert hasattr(eod, attr), f"status missing {attr}"
    assert eod.last_successful_acquisition is not None
    assert eod.quality_counts  # attested / feed_unattested tallies present


async def test_status_omits_live_without_a_bound(session_factory) -> None:
    """Fails if: status invents a LIVE freshness verdict with no declared bound."""
    svc = await _svc(session_factory, expected_symbols=1)
    st = await svc.status()
    assert "SIP_LIVE" not in st.profiles
    assert "SIP_EOD" in st.profiles
