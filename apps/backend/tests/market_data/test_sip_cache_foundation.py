"""SIP-CACHE-001 Implementation A — producer/cache foundation tests.

The negative set (``test_negative_*``) is mandatory per the tranche scope. It proves behaviourally
that acquisition authority resolves only through ``SIP-CACHE-001-PRODUCER-001`` — that a credential
which *happens* to return SIP 200 confers no producer role.

For every test below, the failing input is stated in the docstring. A readiness test that cannot
fail is not evidence.
"""

from __future__ import annotations

import ast
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.market_data.sip.cache import SipOperationalCache
from app.market_data.sip.identity import (
    PRODUCER,
    ProducerIdentityError,
    key_fingerprint,
)
from app.market_data.sip.producer import SipProducer
from app.market_data.sip.profiles import SipProfile
from app.market_data.sip.readiness import (
    SipNotReadyError,
    SipReadinessEvaluator,
    SipReadinessState,
)
from app.market_data.sip.schema import SipRecord

TD = date(2026, 9, 1)


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


# --------------------------------------------------------------------------- provenance


def test_record_requires_full_provenance() -> None:
    """Fails if: a record is constructed without entitlement or credential provenance."""
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="entitlement_identity"):
        SipRecord(
            symbol="AAPL",
            profile=SipProfile.LIVE,
            trading_date=TD,
            session="regular",
            source_timestamp=now,
            received_at_utc=now,
            credential_identity_fingerprint="abc",
        )
    with pytest.raises(ValueError, match="credential_identity_fingerprint"):
        SipRecord(
            symbol="AAPL",
            profile=SipProfile.LIVE,
            trading_date=TD,
            session="regular",
            source_timestamp=now,
            received_at_utc=now,
            entitlement_identity="x",
        )


def test_record_refuses_naive_timestamp() -> None:
    """Fails if: a naive source_timestamp is accepted (freshness would need an invented zone)."""
    with pytest.raises(ValueError, match="timezone-aware"):
        SipRecord(
            symbol="AAPL",
            profile=SipProfile.LIVE,
            trading_date=TD,
            session="regular",
            source_timestamp=datetime(2026, 9, 1, 12, 0, 0),
            received_at_utc=datetime.now(UTC),
            entitlement_identity="x",
            credential_identity_fingerprint="y",
        )


def test_record_refuses_non_sip_feed() -> None:
    """Fails if: an IEX row could be stored in the SIP plane by relabelling."""
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="must be 'sip'"):
        SipRecord(
            symbol="AAPL",
            profile=SipProfile.LIVE,
            trading_date=TD,
            session="regular",
            source_timestamp=now,
            received_at_utc=now,
            feed="iex",
            entitlement_identity="x",
            credential_identity_fingerprint="y",
        )


# --------------------------------------------------------------------------- cache


async def test_cache_roundtrip_preserves_provenance(session_factory) -> None:
    """Fails if: any provenance field is lost across a write/read cycle."""
    cache = SipOperationalCache(session_factory)
    now = datetime.now(UTC)
    assert await cache.upsert([_rec("AAPL", ts=now)]) == 1
    got = await cache.get("AAPL", SipProfile.LIVE)
    assert got is not None
    assert got.feed == "sip"
    assert got.source_feed_identity == "sip"
    assert got.provider == "alpaca"
    assert got.entitlement_identity == PRODUCER.entitlement_identity
    assert got.credential_identity_fingerprint == PRODUCER.key_fingerprint
    assert got.cache_schema_version >= 1
    assert got.source_timestamp.tzinfo is not None


async def test_cache_never_moves_backwards_in_time(session_factory) -> None:
    """Fails if: a late/replayed response overwrites a newer observation."""
    cache = SipOperationalCache(session_factory)
    new = datetime.now(UTC)
    old = new - timedelta(seconds=60)
    await cache.upsert([_rec("AAPL", ts=new)])
    await cache.upsert([_rec("AAPL", ts=old)])
    got = await cache.get("AAPL", SipProfile.LIVE)
    assert got is not None
    assert got.source_timestamp == new


async def test_cache_rejects_feed_substitution(session_factory) -> None:
    """Fails if: a record whose served feed contradicts its requested feed is stored."""
    cache = SipOperationalCache(session_factory)
    now = datetime.now(UTC)
    bad = SipRecord(
        symbol="AAPL",
        profile=SipProfile.LIVE,
        trading_date=TD,
        session="regular",
        source_timestamp=now,
        received_at_utc=now,
        source_feed_identity="iex",  # provider served something else
        entitlement_identity="x",
        credential_identity_fingerprint="y",
    )
    assert await cache.upsert([bad]) == 0
    assert await cache.get("AAPL", SipProfile.LIVE) is None


async def test_cache_prune_is_bounded(session_factory) -> None:
    """Fails if: retention does not bound the store."""
    cache = SipOperationalCache(session_factory)
    now = datetime.now(UTC)
    old = SipRecord(
        symbol="OLD",
        profile=SipProfile.EOD,
        trading_date=date(2026, 1, 1),
        session="regular",
        source_timestamp=now - timedelta(days=200),
        received_at_utc=now,
        entitlement_identity="x",
        credential_identity_fingerprint="y",
    )
    await cache.upsert([old, _rec("NEW", ts=now)])
    assert await cache.prune(retention_days=30, now=now) == 1
    assert await cache.get("OLD", SipProfile.EOD) is None
    assert await cache.get("NEW", SipProfile.LIVE) is not None


async def test_restart_recomputes_readiness_never_inherits(session_factory) -> None:
    """Fails if: a restart could promote a stale cache to PASS by inheriting a verdict."""
    cache = SipOperationalCache(session_factory)
    stale_ts = datetime.now(UTC) - timedelta(hours=6)
    await cache.upsert([_rec("AAPL", ts=stale_ts)])
    # Simulate a fresh process: brand-new evaluator, nothing carried over.
    ev = SipReadinessEvaluator(expected_symbols=1, live_max_age_s=30)
    got = ev.evaluate(SipProfile.LIVE, await cache.latest_for_profile(SipProfile.LIVE))
    assert got.state is SipReadinessState.STALE


# --------------------------------------------------------------------------- readiness


def _ev(**kw) -> SipReadinessEvaluator:
    kw.setdefault("expected_symbols", 2)
    kw.setdefault("live_max_age_s", 30)
    return SipReadinessEvaluator(**kw)


def test_readiness_pass() -> None:
    """Fails if: a fresh, complete profile is not PASS."""
    now = datetime.now(UTC)
    recs = [_rec("A", ts=now), _rec("B", ts=now)]
    assert _ev().evaluate(SipProfile.LIVE, recs, now=now).state is SipReadinessState.PASS


def test_readiness_stale_uses_oldest_symbol() -> None:
    """Fails if: one fresh symbol masks a stale one (a profile is as fresh as its stalest row)."""
    now = datetime.now(UTC)
    recs = [_rec("A", ts=now), _rec("B", ts=now - timedelta(seconds=600))]
    assert _ev().evaluate(SipProfile.LIVE, recs, now=now).state is SipReadinessState.STALE


def test_readiness_incomplete() -> None:
    """Fails if: partial coverage is reported as PASS."""
    now = datetime.now(UTC)
    got = _ev(expected_symbols=5).evaluate(SipProfile.LIVE, [_rec("A", ts=now)], now=now)
    assert got.state is SipReadinessState.INCOMPLETE
    assert got.coverage == pytest.approx(0.2)


def test_readiness_entitlement_fail_outranks_staleness() -> None:
    """Fails if: an unacquirable plane is reported merely STALE, understating it."""
    now = datetime.now(UTC)
    got = _ev().evaluate(SipProfile.LIVE, [_rec("A", ts=now)], entitlement_ok=False, now=now)
    assert got.state is SipReadinessState.ENTITLEMENT_FAIL


def test_readiness_absent() -> None:
    """Fails if: an unavailable store or empty profile is not ABSENT."""
    now = datetime.now(UTC)
    assert _ev().evaluate(SipProfile.LIVE, [], now=now).state is SipReadinessState.ABSENT
    assert (
        _ev().evaluate(SipProfile.LIVE, [_rec("A", ts=now)], store_available=False, now=now).state
        is SipReadinessState.ABSENT
    )


def test_readiness_profiles_are_independent() -> None:
    """Fails if: a single global verdict is emitted — EOD PASS must not imply LIVE PASS."""
    now = datetime.now(UTC)
    ev = SipReadinessEvaluator(expected_symbols=1, live_max_age_s=30, eod_expected_trading_date=TD)
    eod = ev.evaluate(SipProfile.EOD, [_rec("A", ts=now, profile=SipProfile.EOD)], now=now)
    live = ev.evaluate(SipProfile.LIVE, [_rec("A", ts=now - timedelta(seconds=900))], now=now)
    assert eod.state is SipReadinessState.PASS
    assert live.state is SipReadinessState.STALE


def test_readiness_eod_missing_expected_session_is_stale() -> None:
    """Fails if: an EOD profile missing the expected completed session reads PASS."""
    now = datetime.now(UTC)
    ev = SipReadinessEvaluator(
        expected_symbols=1,
        live_max_age_s=30,
        eod_expected_trading_date=date(2026, 9, 2),
    )
    got = ev.evaluate(SipProfile.EOD, [_rec("A", ts=now, profile=SipProfile.EOD)], now=now)
    assert got.state is SipReadinessState.STALE


# --------------------------------------------------------------------------- NEGATIVE SET


def test_negative_n1_producer_identity_is_pinned() -> None:
    """N1 — fails if: a non-designated credential is accepted.

    The refusal happens before any network call: entitlement is not authority.
    """
    with pytest.raises(ProducerIdentityError, match="not the designated SIP producer"):
        PRODUCER.verify("PKNOTTHEDESIGNATED1")
    # The pin is a fingerprint comparison, so the refusal is provable without ever holding the
    # real key: any key whose fingerprint differs is refused, and only the designated one is not.
    assert PRODUCER.key_fingerprint == "b56421a28128"
    assert key_fingerprint("PKNOTTHEDESIGNATED1") != PRODUCER.key_fingerprint


def test_negative_n2_consumer_cannot_use_its_own_sip_capable_credential() -> None:
    """N2 — fails if: an account whose credential really does return SIP 200 is accepted.

    The 2026-08-31 census measured accounts 5 (PA3DBWDGOING) and 6 (PA30T0I3JJV9) *also* returning
    recent-SIP 200. This is the test that stops "my broker credential happens to work, so use it"
    from becoming architecture. Their access is an access-topology observation and confers no
    producer role.
    """
    # Fingerprints measured 2026-08-31. Fingerprints are not secrets.
    census_sip_capable = {
        "acct5_PA3DBWDGOING": "5115fc74f097",
        "acct6_PA30T0I3JJV9": "5da9c9d59a45",
    }
    for label, fp in census_sip_capable.items():
        assert fp != PRODUCER.key_fingerprint, f"{label} must not be the designated producer"

    class _Pretender:
        """A credential that would succeed at the provider."""

        api_key = "PKACCOUNT5SIPCAPABLE"

    with pytest.raises(ProducerIdentityError):
        PRODUCER.verify(_Pretender.api_key)


async def test_negative_n3_no_failover_when_producer_not_designated(
    monkeypatch, session_factory
) -> None:
    """N3 — fails if: any request is issued under a fingerprint other than the designated one.

    Asserts on *captured call fingerprints*, not on the absence of an exception.
    """
    attempted: list[str] = []

    class _Creds:
        api_key = "PKSOMEOTHERACCOUNT99"
        api_secret = "s"

    async def _fake_creds(mode, account_id, sf):  # noqa: ANN001
        attempted.append(key_fingerprint(_Creds.api_key))
        return _Creds()

    monkeypatch.setattr("app.brokers.alpaca.credentials.credentials_for_mode", _fake_creds)
    producer = SipProducer(session_factory)
    with pytest.raises(ProducerIdentityError):
        await producer.fetch_latest_quotes(
            ["AAPL"], profile=SipProfile.LIVE, trading_date=TD, session="regular"
        )
    # Exactly one credential was resolved, and it was never used for a request.
    assert attempted == [key_fingerprint(_Creds.api_key)]
    assert PRODUCER.key_fingerprint not in attempted


def test_negative_n5_no_silent_sip_to_iex_downgrade() -> None:
    """N5 — fails if: a non-PASS readiness yields anything other than a refusal.

    There is deliberately no fallback_feed parameter to pass.
    """
    now = datetime.now(UTC)
    import inspect

    for state_kwargs in ({"entitlement_ok": False}, {"store_available": False}):
        got = _ev().evaluate(SipProfile.LIVE, [_rec("A", ts=now)], now=now, **state_kwargs)
        with pytest.raises(SipNotReadyError, match="Failing closed"):
            got.raise_if_not_pass("strategy-9")
    # There is no parameter through which a caller could request IEX instead.
    params = set(inspect.signature(got.raise_if_not_pass).parameters)
    assert params == {"consumer"}, f"unexpected fallback surface: {params}"


def test_negative_n6_only_producer_module_constructs_sip_requests() -> None:
    """N6 — static: fails if: any module outside the SIP producer builds a SIP data request.

    AST-based rather than grep: a string literal or a comment must never count as a call. Scoped to
    the operational plane; ``app/research/**`` is the evidence plane with its own governed
    collector, and is deliberately out of scope here.
    """
    app_root = Path(__file__).resolve().parents[2] / "app"
    allowed = app_root / "market_data" / "sip" / "producer.py"
    # MARKET-PROJECTION-SIP-READER-001 — a pre-existing, owner-TRACKED non-MDQ SIP reader:
    # training-only by docstring (live inference is IEX), persistence in a research script. It is
    # recorded as a finding with two open qualification questions and is deliberately NOT
    # adjudicated as a defect here, so this test does not fail on it. Naming it explicitly keeps
    # the exception visible: anything NEW still fails, and this entry cannot silently widen.
    known_tracked = {"services/market_projection/dataset.py"}
    offenders: list[str] = []

    for path in app_root.rglob("*.py"):
        rel = path.relative_to(app_root).as_posix()
        if rel.startswith("research/"):
            continue
        if path == allowed:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg != "feed":
                    continue
                v = kw.value
                is_sip = (isinstance(v, ast.Attribute) and v.attr.upper() == "SIP") or (
                    isinstance(v, ast.Constant) and str(v.value).lower() == "sip"
                )
                if is_sip:
                    offenders.append(f"{rel}:{node.lineno}")

    unexpected = [o for o in offenders if o.rsplit(":", 1)[0] not in known_tracked]
    assert not unexpected, (
        "SIP acquisition must resolve only through app/market_data/sip/producer.py; "
        f"found NEW feed=SIP construction in: {unexpected}. If this is intentional, it needs a "
        "governed decision — acquisition outside the designated producer is what "
        "SIP-CACHE-001 §7.1 exists to prevent."
    )
