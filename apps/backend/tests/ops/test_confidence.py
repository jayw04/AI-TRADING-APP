"""Production Confidence Score (P13.5) — pure scoring."""

from __future__ import annotations

from dataclasses import replace

from app.ops.confidence import ConfidenceSignals, compute_confidence


def _clean(days: int = 90) -> ConfidenceSignals:
    """A clean, exercised book: gates fired, breaker recovered, replay+reconcile clean."""
    return ConfidenceSignals(
        track_record_days=days,
        replay_mismatches=0, reconciliation_discrepancies=0, reconciliation_runs=40,
        breaker_trips=1, breaker_resets=1,
        orders_risk_passed=8, orders_rejected_by_risk=2, orders_rejected_by_broker=0,
        fills_ingested=7,
    )


def test_clean_mature_book_scores_high_and_in_range():
    r = compute_confidence(_clean(120))
    assert 0 <= r["score"] <= 100
    assert r["score"] >= 80
    assert r["band"] in ("Strong", "Production-ready")


def test_fresh_book_scores_low():
    fresh = ConfidenceSignals(
        track_record_days=0, replay_mismatches=0, reconciliation_discrepancies=0,
        reconciliation_runs=0, breaker_trips=0, breaker_resets=0,
        orders_risk_passed=0, orders_rejected_by_risk=0, orders_rejected_by_broker=0,
        fills_ingested=0,
    )
    r = compute_confidence(fresh)
    assert r["score"] < 60  # no track record, gates unexercised, reconciliation unproven
    assert r["band"] in ("Provisional", "Early", "Building")


def test_maturity_is_monotonic_in_time():
    scores = [compute_confidence(_clean(d))["score"] for d in (0, 30, 90, 200)]
    assert scores == sorted(scores)
    assert scores[0] < scores[-1]  # strictly rises with the track record


def test_replay_mismatch_cuts_verifiability_and_score():
    base = compute_confidence(_clean())
    dinged = compute_confidence(replace(_clean(), replay_mismatches=1))
    assert dinged["components"]["verifiability"] < base["components"]["verifiability"]
    assert dinged["score"] < base["score"]
    assert "replay mismatch" in " ".join(dinged["rationale"])


def test_unrecovered_breaker_cuts_safety():
    dinged = compute_confidence(replace(_clean(), breaker_trips=2, breaker_resets=1))
    assert dinged["components"]["safety"] < compute_confidence(_clean())["components"]["safety"]
    assert "unrecovered breaker" in " ".join(dinged["rationale"])


def test_components_and_weights_present_and_normalized():
    r = compute_confidence(_clean())
    assert set(r["components"]) == {"verifiability", "safety", "maturity", "operational"}
    assert abs(sum(r["weights"].values()) - 1.0) < 1e-9
