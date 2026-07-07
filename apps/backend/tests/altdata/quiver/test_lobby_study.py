"""LOBBY-001 study — de-overlap, entry timing, and the verdict gate, over multiple deadline-date
clusters (so the date-clustered bootstrap has real clusters). Synthetic fns; no factor store."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.altdata.events.store import CorporateEvent
from app.altdata.quiver.lobby_study import dedupe_overlapping, run_primary

# 12 distinct quarterly-deadline dates → the events cluster onto these (the LOBBY reality).
_DEADLINES = [date(y, m, 20) for y in (2021, 2022, 2023) for m in (4, 7, 10, 1)]


def _ev(ticker: str, dl: date) -> CorporateEvent:
    dt = datetime(dl.year, dl.month, dl.day, tzinfo=UTC)
    return CorporateEvent(
        cik=1, ticker=ticker, event_type="lobby_spike", source="quiver", accession=f"qlob_{ticker}_{dl}",
        filed_at=dt, event_date=date(dl.year, 1, 1), payload={"quarter": "x"}, available_time=dt,
    )


# --- de-overlap -------------------------------------------------------------------------------

def test_dedupe_collapses_overlapping_same_firm_and_keeps_far_apart():
    close = [_ev("AAA", date(2024, 4, 20)), _ev("AAA", date(2024, 5, 5))]   # 15d < 20*1.5 -> collapse
    kept, tickers = dedupe_overlapping(close, hold_days=20)
    assert len(kept) == 1 and tickers == frozenset({"AAA"})
    far = [_ev("AAA", date(2024, 4, 20)), _ev("AAA", date(2024, 10, 20))]   # a quarter apart -> both
    assert len(dedupe_overlapping(far, hold_days=20)[0]) == 2


# --- verdict gate (synthetic fns) -------------------------------------------------------------

_EVENT_TICKERS = [f"E{i:03d}" for i in range(120)]
_CONTROL_TICKERS = [f"C{i:03d}" for i in range(40)]


def _feature_fn():
    from app.altdata.matched_control import CandidateFeatures
    cands = [CandidateFeatures(t, "Tech", float(i % 10), float(i % 10), float(i % 10))
             for i, t in enumerate(_EVENT_TICKERS)]
    cands += [CandidateFeatures(t, "Tech", float(j % 10), float(j % 10), float(j % 10))
              for j, t in enumerate(_CONTROL_TICKERS)]
    return lambda _as_of: cands


def _price_fn(event_ret: float, control_ret: float):
    def price_fn(ticker, start, _end):
        r = event_ret if ticker.startswith("E") else control_ret
        return [(start + timedelta(days=i), 100.0 * (1 + r * i / 20)) for i in range(25)]
    return price_fn


def _events(k: int):
    # spread across the 12 deadline dates so the date-clustered bootstrap sees ~12 clusters
    return [_ev(_EVENT_TICKERS[i], _DEADLINES[i % len(_DEADLINES)]) for i in range(k)]


def _run(k: int, event_ret: float):
    exclude = frozenset(_EVENT_TICKERS)
    return run_primary(_events(k), price_fn=_price_fn(event_ret, 0.02), feature_fn=_feature_fn(),
                       exclude_fn=lambda _d: exclude, min_controls=3, n_resamples=300)


def test_approved_positive_edge_meets_gate():
    out = _run(120, 0.10)
    assert out["metrics"]["n_benchmarked"] == 120
    assert out["outcome"] == "Approved"
    assert out["metrics"]["mean_excess"] < out["metrics"]["mean_excess_gross"]   # cost applied


def test_insufficient_evidence_below_gate():
    out = _run(12, 0.10)
    assert out["metrics"]["n_benchmarked"] == 12
    assert out["outcome"] == "Insufficient Evidence"
