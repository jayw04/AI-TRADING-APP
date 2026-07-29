"""WP9 AMD-19 — quote provenance as structured evidence (hermetic; no broker)."""

from __future__ import annotations

from app.risk.loss_control.phase0_contracts import TIER_D_DISPLAYED_SPREAD
from app.risk.loss_control.phase0_quote_provenance import (
    REQUIRED_FIELDS,
    ProvenanceRefuseReason,
    assert_no_order_path_imports,
    build_provenanced_quote,
    hash_raw_payload,
    iex_displayed_spread_example,
    refuse_string_only_source,
    validate_provenance_dict,
    verify_payload_hash,
)


def test_required_amd19_fields_present() -> None:
    assert {
        "provider",
        "feed_type",
        "venue_scope",
        "subscription_entitlement",
        "raw_payload_hash",
        "normalization_version",
    } <= REQUIRED_FIELDS


def test_string_only_iex_displayed_spread_refused() -> None:
    r = refuse_string_only_source("IEX displayed spread")
    assert not r.accepted
    assert r.reason is ProvenanceRefuseReason.STRING_ONLY_SOURCE


def test_structured_iex_quote_accepted() -> None:
    payload = {"S": "KOKU", "bp": "128.09", "ap": "131.03", "t": "…"}
    r = iex_displayed_spread_example(
        symbol="KOKU",
        bid="128.09",
        ask="131.03",
        age_s="2",
        raw_payload=payload,
        sequence_number="42",
    )
    assert r.accepted and r.quote is not None
    assert r.quote.evidence_tier_hint == TIER_D_DISPLAYED_SPREAD
    assert r.quote.provenance.provider == "alpaca"
    assert r.quote.provenance.feed_type == "iex"
    assert r.quote.provenance.raw_payload_hash == hash_raw_payload(payload)
    assert "condition_codes" in r.quote.provenance.as_dict()


def test_missing_required_field_refused() -> None:
    assert (
        validate_provenance_dict({"provider": "alpaca"})
        is ProvenanceRefuseReason.MISSING_REQUIRED_FIELDS
    )


def test_invalid_venue_scope_refused() -> None:
    data = {
        "provider": "alpaca",
        "feed_type": "iex",
        "venue_scope": "mystery",
        "subscription_entitlement": "x",
        "raw_payload_hash": "sha256:" + "a" * 64,
        "normalization_version": "v1",
    }
    assert validate_provenance_dict(data) is ProvenanceRefuseReason.INVALID_VENUE_SCOPE


def test_payload_hash_verification() -> None:
    payload = {"bid": "1", "ask": "2"}
    built = build_provenanced_quote(
        symbol="X",
        bid="1",
        ask="2",
        age_s="1",
        provider="alpaca",
        feed_type="iex",
        venue_scope="venue",
        subscription_entitlement="alpaca_iex_free",
        raw_payload=payload,
    )
    assert built.accepted and built.quote is not None
    ok = verify_payload_hash(built.quote.provenance, payload)
    assert ok.accepted
    bad = verify_payload_hash(built.quote.provenance, {"bid": "9", "ask": "2"})
    assert not bad.accepted
    assert bad.reason is ProvenanceRefuseReason.HASH_MISMATCH


def test_empty_payload_refused() -> None:
    r = build_provenanced_quote(
        symbol="X",
        bid="1",
        ask="2",
        age_s="1",
        provider="alpaca",
        feed_type="iex",
        venue_scope="venue",
        subscription_entitlement="alpaca_iex_free",
        raw_payload=b"",
    )
    assert not r.accepted
    assert r.reason is ProvenanceRefuseReason.EMPTY_PAYLOAD


def test_no_order_path_imports() -> None:
    assert_no_order_path_imports()
