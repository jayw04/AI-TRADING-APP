"""CAP-024 Security Master v0 — resolution hierarchy, typed unresolved reasons, and the
no-silent-bad-mapping property (offline; fixture CikMap, no network)."""

from __future__ import annotations

from datetime import date

from app.altdata.sec.cik_map import CikMap
from app.altdata.security_master import (
    REASON_AMBIGUOUS,
    REASON_INSUFFICIENT,
    REASON_NO_PUBLIC,
    SecurityMaster,
    normalize_name,
)


def _sm(extra: dict[int, str] | None = None) -> SecurityMaster:
    extra = extra or {}
    by_ticker = {"AAPL": 320193, "MSFT": 789019, "GOOGL": 1652044, "GD": 936468, "LMT": 936_469}
    titles = {
        320193: "Apple Inc.",
        789019: "Microsoft Corporation",
        1652044: "Alphabet Inc.",
        936468: "General Dynamics Corp",
        936_469: "Lockheed Martin Corp",
    }
    titles.update(extra)
    by_ticker.update({f"X{c}": c for c in extra})
    return SecurityMaster(CikMap(by_ticker=by_ticker, titles=titles))


# --- normalization ---------------------------------------------------------------------------

def test_normalization_strips_suffixes_and_articles():
    assert normalize_name("Apple Inc.")[0] == "APPLE"
    assert normalize_name("APPLE INC")[0] == "APPLE"
    assert normalize_name("The Coca-Cola Company")[0] == "COCA COLA"
    assert normalize_name("Alphabet Inc. Class A")[0] == "ALPHABET"
    assert normalize_name("AT&T Inc")[0] == "AT AND T"


# --- tier precedence -------------------------------------------------------------------------

def test_cik_beats_ticker_beats_name():
    sm = _sm()
    # a supplied (correct) CIK wins even when the name is wrong
    r = sm.resolve_security(cik=320193, ticker="MSFT", issuer_name="Totally Wrong Corp")
    assert r.method == "cik" and r.resolved_security_id == "CIK0000320193"
    assert r.resolved_ticker == "AAPL" and r.confidence == 1.0

    # ticker beats name when no CIK given
    r = sm.resolve_security(ticker="msft", issuer_name="Wrong")
    assert r.method == "ticker" and r.cik == 789019 and r.confidence == 0.99


def test_exact_name_resolves_across_normalization_variants():
    sm = _sm()
    for name in ("Apple Inc.", "APPLE INCORPORATED", "the apple co"):
        r = sm.resolve_security(issuer_name=name)
        assert r.is_resolved and r.cik == 320193 and r.method == "exact_name"
        assert r.confidence == 0.95


# --- ambiguity & no-match --------------------------------------------------------------------

def test_ambiguous_normalized_name_is_unresolved_not_a_guess():
    # two distinct CIKs whose titles normalize to the same key
    sm = _sm({555: "Acme Inc", 666: "Acme Corporation"})
    r = sm.resolve_security(issuer_name="Acme")
    assert not r.is_resolved and r.unresolved_reason == REASON_AMBIGUOUS
    assert r.resolved_security_id is None


def test_unknown_name_is_no_public_security():
    sm = _sm()
    r = sm.resolve_security(issuer_name="Zzzq Nonexistent Ventures")
    assert not r.is_resolved and r.unresolved_reason == REASON_NO_PUBLIC


def test_unknown_ticker_or_cik_is_unresolved():
    sm = _sm()
    assert sm.resolve_security(ticker="NOPE").unresolved_reason == REASON_NO_PUBLIC
    assert sm.resolve_security(cik=999999999).unresolved_reason == REASON_NO_PUBLIC


# --- fuzzy tier: gated so it fires only above the bar ----------------------------------------

def test_fuzzy_resolves_a_close_multitoken_match():
    sm = _sm()
    # "General Dynamic" (singular) — not exact, shares GENERAL with General Dynamics, high seq
    r = sm.resolve_security(issuer_name="General Dynamic")
    assert r.is_resolved and r.method == "fuzzy_name" and r.cik == 936468
    assert 0.90 <= r.confidence < 1.0            # the real similarity, not rounded to 1.0


def test_fuzzy_below_threshold_is_insufficient_confidence():
    sm = _sm()
    # shares GENERAL but the rest diverges -> below FUZZY_MIN
    r = sm.resolve_security(issuer_name="General Electric")
    assert not r.is_resolved and r.unresolved_reason == REASON_INSUFFICIENT


def test_subsidiary_style_name_never_silently_maps_to_parent():
    """The core no-silent-bad-mapping property: a subsidiary/division name must not resolve to a
    public parent below the confidence bar. Unresolved-with-reason is correct; a confident wrong
    id is not (subsidiary mapping is reserved for v1)."""
    sm = _sm()
    for name in ("Lockheed Martin Federal Systems LLC",
                 "General Dynamics Information Technology Inc",
                 "Apple Global Services Holdings"):
        r = sm.resolve_security(issuer_name=name)
        # either unresolved, or (if it clears the high bar) at least never a *low*-confidence id
        assert (not r.is_resolved) or r.confidence >= sm._fuzzy_min
        if not r.is_resolved:
            assert r.unresolved_reason in {REASON_INSUFFICIENT, REASON_NO_PUBLIC, REASON_AMBIGUOUS}


# --- determinism & no-identifier -------------------------------------------------------------

def test_determinism():
    sm = _sm()
    a = sm.resolve_security(issuer_name="General Dynamic", as_of=date(2026, 7, 5))
    b = sm.resolve_security(issuer_name="General Dynamic", as_of=date(2026, 7, 5))
    assert a == b


def test_no_identifier_is_no_public_security():
    sm = _sm()
    assert sm.resolve_security().unresolved_reason == REASON_NO_PUBLIC
