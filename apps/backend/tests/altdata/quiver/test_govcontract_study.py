"""GOVCONTRACT-001 study wiring — the pre-registered verdict tree over the matched-control study.
Synthetic; no factor store."""

from __future__ import annotations

from datetime import date, timedelta

from app.altdata.matched_control import CandidateFeatures, EventPoint
from app.altdata.quiver.govcontract_study import run_govcontract_study

HOLD = 20


def _cands():
    return [CandidateFeatures(f"T{i:02d}", "Tech", float(i), float(i), float(i)) for i in range(20)]


def _feature_fn():
    cands = _cands()
    return lambda _as_of: cands


def _price_fn(event_ticker, event_ret, control_ret):
    def price_fn(ticker, start, _end):
        r = event_ret if ticker == event_ticker else control_ret
        return [(start + timedelta(days=i), 100.0 * (1 + r * i / HOLD)) for i in range(HOLD + 5)]
    return price_fn


def _events(ticker, k):
    return [EventPoint(ticker, date(2026, 1, 1) + timedelta(days=15 * i)) for i in range(k)]


def _run(ret, k):
    return run_govcontract_study(
        _events("T10", k), price_fn=_price_fn("T10", ret, 0.02), feature_fn=_feature_fn(),
        hold_days=HOLD, min_controls=3, n_resamples=300)


def test_approved_positive_edge_meets_floor():
    out = _run(0.10, 120)                      # excess +8%, 120 ≥ 100 events
    assert out["metrics"]["n_benchmarked"] == 120
    assert out["outcome"].startswith("A")      # Approved


def test_insufficient_data_below_event_floor():
    out = _run(0.10, 10)                        # positive but only 10 events
    assert out["outcome"].startswith("D")      # Insufficient-Data


def test_rejected_negative_edge():
    out = _run(-0.05, 120)                      # excess −7%
    assert out["outcome"].startswith("C")      # Rejected
