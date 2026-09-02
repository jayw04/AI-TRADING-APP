"""SIP-CACHE-001 B2 — one-shot proof harness tests.

These establish **harness behaviour and safety properties only**. They do not establish live SIP
acquisition, production cache persistence, current producer entitlement, production freshness, or
production restart behaviour — all of which remain future governed-execution evidence.

The offline verdict ``INCOMPLETE_REFUSED`` is the *correct complete* result for an offline run, not
a partial production proof. 12 PASS + 1 REFUSED is a finished offline qualification; the missing
assertion is intentionally missing because the governed network execution is not authorized.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.market_data.sip.identity import PRODUCER
from app.market_data.sip.profiles import SipProfile
from scripts.sip_oneshot_proof import (
    CUSTODIED_BROKER,
    CUSTODIED_FINGERPRINT,
    MAX_UNIVERSE,
    Check,
    OneShotProof,
    _run_offline_isolated,
    build_evidence,
    main,
    run_offline,
)


async def test_offline_run_is_a_complete_offline_qualification(session_factory) -> None:
    """Fails if: the offline run does not reach INCOMPLETE_REFUSED with exactly one refusal.

    The single refusal is the network assertion. Any other refusal means a safety premise broke.
    """
    ev = await run_offline(["AAPL", "MSFT"], SipProfile.LIVE, session_factory)
    refused = [c for c in ev.checks if c["refused"]]
    failed = [c for c in ev.checks if not c["passed"] and not c["refused"]]
    assert not failed, f"offline assertions failed: {[c['name'] for c in failed]}"
    assert len(refused) == 1, f"expected exactly one refusal, got {[c['name'] for c in refused]}"
    assert refused[0]["name"] == "03_sip_request_succeeds"
    assert ev.verdict == "INCOMPLETE_REFUSED"
    assert ev.executed_network is False


async def test_pin_is_asserted_against_custodied_literals(session_factory) -> None:
    """Fails if: a silent re-pin of the producer identity could pass unnoticed."""
    ev = await run_offline(["AAPL"], SipProfile.LIVE, session_factory)
    pin = next(c for c in ev.checks if c["name"] == "01_pin_matches_custodied_designation")
    assert pin["passed"]
    assert CUSTODIED_BROKER == "PA3BGKRLH2AP"
    assert CUSTODIED_FINGERPRINT == "b56421a28128"
    assert PRODUCER.broker_account == CUSTODIED_BROKER
    assert PRODUCER.key_fingerprint == CUSTODIED_FINGERPRINT


def test_execute_refuses_self_authorization(capsys) -> None:
    """Fails if: the harness can authorize its own production acquisition.

    §19 step 4 is a governed act. A flag is not authorization.
    """
    rc = main(["--execute"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "REFUSED" in out
    assert "requires separate owner authorization" in out


def test_universe_is_bounded() -> None:
    """Fails if: an unbounded universe can be requested."""
    with pytest.raises(ValueError, match="bounded"):
        OneShotProof(None, ["A"] * (MAX_UNIVERSE + 1), SipProfile.LIVE)


async def test_premise_refuses_rather_than_manufacturing_failure() -> None:
    """Fails if: an entitled negative identity yields a manufactured ENTITLEMENT_FAIL.

    This is the Ruling-4 property. If the credential chosen for the negative test turns out to be
    entitled at execution time, the harness must REFUSE — never damage an account to produce the
    failure it wants to observe.
    """
    proof = OneShotProof(None, ["AAPL"], SipProfile.LIVE)

    async def _entitled():
        return 200, "deadbeefcafe"

    c = await proof.check_negative_identity_premise(_entitled)
    assert c.refused is True and c.passed is False
    assert "REFUSED" in c.detail

    # And with the premise false, the dependent assertion refuses too rather than asserting.
    proof.check_entitlement_fail_reachable(premise_ok=False)
    dependent = proof.checks[-1]
    assert dependent.refused is True
    assert "not manufactured" in dependent.detail


async def test_premise_holds_when_identity_is_unentitled() -> None:
    """Fails if: a genuinely non-entitled identity does not establish the premise."""
    proof = OneShotProof(None, ["AAPL"], SipProfile.LIVE)

    async def _unentitled():
        return 403, "246b05e74804"

    c = await proof.check_negative_identity_premise(_unentitled)
    assert c.passed is True and c.refused is False


async def test_premise_refuses_on_indeterminate_status() -> None:
    """Fails if: an ambiguous provider response is treated as proof of non-entitlement."""
    proof = OneShotProof(None, ["AAPL"], SipProfile.LIVE)

    async def _indeterminate():
        return 500, "246b05e74804"

    c = await proof.check_negative_identity_premise(_indeterminate)
    assert c.refused is True


async def test_offline_mode_never_touches_the_production_database(monkeypatch) -> None:
    """Fails if: the offline path can reach the real sessionmaker.

    A local harness run must not read, write, or lock the live cache.
    """
    called: list[str] = []

    def _boom(*a, **k):
        called.append("get_sessionmaker")
        raise AssertionError("offline mode must not resolve the production sessionmaker")

    monkeypatch.setattr("app.db.session.get_sessionmaker", _boom)
    ev = await _run_offline_isolated(["AAPL"], SipProfile.LIVE)
    assert ev.verdict == "INCOMPLETE_REFUSED"
    assert called == []


async def test_evidence_artifact_contains_no_secret(tmp_path: Path, session_factory) -> None:
    """Fails if: the evidence artifact carries anything secret-shaped.

    Fingerprints, counts, timestamps and verdicts only.
    """
    ev = await run_offline(["AAPL"], SipProfile.LIVE, session_factory)
    blob = json.dumps(ev.__dict__, default=str)
    out = tmp_path / "evidence.json"
    out.write_text(blob, encoding="utf-8")
    text = out.read_text(encoding="utf-8")

    assert CUSTODIED_FINGERPRINT in text  # the non-secret reference IS expected
    assert len(CUSTODIED_FINGERPRINT) == 12
    for forbidden in ("api_key", "secret_key", "password", "APCA", "PK"):
        assert forbidden not in text, f"evidence artifact contains {forbidden!r}"


def test_verdict_classification() -> None:
    """Fails if: a refusal is scored as success, or a failure is softened into a refusal."""
    p = OneShotProof(None, ["AAPL"], SipProfile.LIVE)
    p.checks = [Check("a", True), Check("b", True)]
    assert build_evidence(p, executed=False).verdict == "PASS"

    p.checks = [Check("a", True), Check("b", False, refused=True)]
    assert build_evidence(p, executed=False).verdict == "INCOMPLETE_REFUSED"

    p.checks = [Check("a", False), Check("b", False, refused=True)]
    assert build_evidence(p, executed=False).verdict == "FAIL"


async def test_no_trading_client_and_no_mdq_access(session_factory) -> None:
    """Fails if: the harness constructs a trading client or reaches the MDQ archive."""
    ev = await run_offline(["AAPL"], SipProfile.LIVE, session_factory)
    by = {c["name"]: c for c in ev.checks}
    assert by["12_no_trading_client_constructed"]["passed"]
    assert by["13_mdq_archive_untouched"]["passed"]
    assert by["11_no_failover"]["passed"]


async def test_monotonic_and_retention_assertions_are_real(session_factory) -> None:
    """Fails if: the cache assertions pass vacuously on an empty store."""
    ev = await run_offline(["AAPL", "MSFT"], SipProfile.LIVE, session_factory)
    by = {c["name"]: c for c in ev.checks}
    assert by["04_rows_persist"]["detail"].startswith("2 row")
    assert by["09_retention_preserves_current_rows"]["detail"] == ("pruned=0 before=2 after=2")
    assert "PASS" in by["07_freshness_classification"]["detail"]
    assert "STALE" in by["07_freshness_classification"]["detail"]


def test_datetime_import_is_used_for_utc_now() -> None:
    """Sanity: the harness stamps evidence with an aware UTC timestamp."""
    p = OneShotProof(None, ["AAPL"], SipProfile.LIVE)
    p.checks = [Check("a", True)]
    ev = build_evidence(p, executed=False)
    parsed = datetime.fromisoformat(ev.started_at)
    assert parsed.tzinfo is not None
    assert parsed.tzinfo.utcoffset(parsed) == UTC.utcoffset(parsed)
