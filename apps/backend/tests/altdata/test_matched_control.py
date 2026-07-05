"""Matched-control benchmark engine (ADR 0037 §3.2) — matching layer + excess-return study.
Pure/synthetic; no factor store, no network."""

from __future__ import annotations

from datetime import date, timedelta

from app.altdata.matched_control import (
    CandidateFeatures,
    EventPoint,
    run_matched_excess_study,
    select_matched_controls,
)

HOLD = 20


def _cands(n: int = 20, sector: str = "Tech") -> list[CandidateFeatures]:
    # features = index → deterministic deciles: decile(Ti) = i // 2 for n=20
    return [CandidateFeatures(f"T{i:02d}", sector, float(i), float(i), float(i)) for i in range(n)]


# --- matching layer ---------------------------------------------------------------------------

def test_selects_same_sector_within_decile_band():
    mc = select_matched_controls("T10", _cands(20), min_controls=3)
    # T10 → decile 5; band {4,5,6} → i in {8,9,10,11,12,13}; minus the event itself
    assert set(mc.controls) == {"T08", "T09", "T11", "T12", "T13"}
    assert mc.sufficient and mc.reason is None


def test_excludes_out_of_band_and_other_sector():
    cands = _cands(20)
    cands[9] = CandidateFeatures("T09", "Health", 9.0, 9.0, 9.0)   # same deciles, wrong sector
    mc = select_matched_controls("T10", cands, min_controls=3)
    assert "T09" not in mc.controls                                # sector mismatch
    assert "T00" not in mc.controls and "T14" not in mc.controls   # out of decile band
    assert set(mc.controls) == {"T08", "T11", "T12", "T13"}


def test_exclude_set_drops_unclean_names():
    mc = select_matched_controls("T10", _cands(20), min_controls=3, exclude=frozenset({"T08"}))
    assert "T08" not in mc.controls


def test_thin_controls_flagged():
    mc = select_matched_controls("T10", _cands(20), min_controls=6)   # only 5 available
    assert not mc.sufficient and mc.reason == "thin_controls" and mc.n == 5


def test_incomplete_event_features():
    cands = _cands(20)
    cands[10] = CandidateFeatures("T10", "Tech", None, 10.0, 10.0)    # missing market cap
    mc = select_matched_controls("T10", cands, min_controls=3)
    assert not mc.sufficient and mc.reason == "event_features_incomplete"


# --- excess-return study ----------------------------------------------------------------------

def _price_fn(event_ticker: str, event_ret: float, control_ret: float):
    def price_fn(ticker, start, _end):
        r = event_ret if ticker == event_ticker else control_ret
        return [(start + timedelta(days=i), 100.0 * (1 + r * i / HOLD)) for i in range(HOLD + 5)]
    return price_fn


def _feature_fn():
    cands = _cands(20)
    return lambda _as_of: cands


def _events(ticker: str, k: int) -> list[EventPoint]:
    return [EventPoint(ticker, date(2026, 1, 1) + timedelta(days=30 * i)) for i in range(k)]


def test_excess_study_detects_positive_edge():
    res = run_matched_excess_study(
        _events("T10", 3), price_fn=_price_fn("T10", 0.10, 0.02), feature_fn=_feature_fn(),
        hold_days=HOLD, min_controls=3, n_resamples=500)
    assert res.n_benchmarked == 3 and res.n_thin == 0
    assert abs(res.mean_excess - 0.08) < 1e-6      # event +10% − control +2%
    assert res.excludes_zero_positive


def test_excess_study_no_edge_spans_zero():
    res = run_matched_excess_study(
        _events("T10", 3), price_fn=_price_fn("T10", 0.02, 0.02), feature_fn=_feature_fn(),
        hold_days=HOLD, min_controls=3, n_resamples=500)
    assert res.n_benchmarked == 3
    assert abs(res.mean_excess) < 1e-9 and not res.excludes_zero_positive


def test_thin_events_are_counted_not_benchmarked():
    res = run_matched_excess_study(
        _events("T10", 2), price_fn=_price_fn("T10", 0.10, 0.02), feature_fn=_feature_fn(),
        hold_days=HOLD, min_controls=6, n_resamples=200)   # 5 controls < 6 → thin
    assert res.n_benchmarked == 0 and res.n_thin == 2
