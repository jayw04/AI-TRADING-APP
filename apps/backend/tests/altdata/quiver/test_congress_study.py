"""CONGRESS-001 study — Purchase-only clustering, cluster-materiality, exact entry, the
date-clustered bootstrap, and the verdict gate. Synthetic; no factor store."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.altdata.events.store import CorporateEvent
from app.altdata.quiver.congress_study import (
    HOLD_PRIMARY,
    build_clusters,
    cluster_tickers,
    run_primary,
)
from app.factor_data.evidence import block_bootstrap_ci, cluster_bootstrap_ci


def _avg(xs):
    return sum(xs) / len(xs)


def _ev(ticker: str, report: date, *, direction: str = "buy", range_low: float = 60_000.0,
        acc: str = "a") -> CorporateEvent:
    rd = datetime(report.year, report.month, report.day, tzinfo=UTC)
    return CorporateEvent(
        cik=1, ticker=ticker, event_type="congress_trade", source="quiver", accession=acc,
        filed_at=rd, event_date=report - timedelta(days=10),
        payload={"direction": direction, "range_low": range_low}, available_time=rd,
    )


# --- clustering + materiality + entry ---------------------------------------------------------

def test_only_the_requested_direction_is_clustered():
    evs = [_ev("AAA", date(2026, 3, 2), direction="buy"),
           _ev("BBB", date(2026, 3, 2), direction="sell", acc="b")]
    buys = build_clusters(evs, direction="buy")
    sells = build_clusters(evs, direction="sell")
    assert [c.ticker for c in buys] == ["AAA"]
    assert [c.ticker for c in sells] == ["BBB"]


def test_cluster_materiality_sums_range_floors_and_gates_at_50k():
    # two small same-ticker buys 3 days apart sum to $60k >= $50k -> ONE material cluster
    evs = [_ev("AAA", date(2026, 3, 2), range_low=30_000, acc="a"),
           _ev("AAA", date(2026, 3, 5), range_low=30_000, acc="b")]
    clusters = build_clusters(evs, direction="buy")
    assert len(clusters) == 1
    assert clusters[0].n_trades == 2
    assert clusters[0].range_low_sum == 60_000
    # a lone $40k buy is immaterial -> dropped
    assert build_clusters([_ev("BBB", date(2026, 3, 2), range_low=40_000)], direction="buy") == []


def test_far_apart_same_ticker_buys_are_separate_clusters():
    # gap >= hold*1.5 (30 days) -> two non-overlapping clusters (each must clear $50k on its own)
    evs = [_ev("AAA", date(2026, 1, 5), range_low=60_000, acc="a"),
           _ev("AAA", date(2026, 4, 5), range_low=60_000, acc="b")]
    clusters = build_clusters(evs, direction="buy")
    assert len(clusters) == 2


def test_entry_is_first_calendar_day_after_reportdate_anchor():
    # cluster anchors on the EARLIEST disclosure; entry = anchor + 1 (forward_return rolls to the
    # first trading day, tested in the engine — here we assert the PIT anchor + strict-after).
    evs = [_ev("AAA", date(2026, 3, 10), range_low=60_000, acc="b"),
           _ev("AAA", date(2026, 3, 2), range_low=60_000, acc="a")]
    (c,) = build_clusters(evs, direction="buy")
    assert c.available_time == date(2026, 3, 2)                 # earliest = PIT anchor
    assert c.entry_date == date(2026, 3, 3)                     # strictly after
    assert c.entry_date > c.available_time


def test_cluster_tickers_covers_both_directions():
    evs = [_ev("AAA", date(2026, 3, 2), direction="buy"),
           _ev("BBB", date(2026, 3, 2), direction="sell", acc="b"),
           _ev("CCC", date(2026, 3, 2), direction=None, acc="c")]  # non-directional excluded
    assert cluster_tickers(evs) == frozenset({"AAA", "BBB"})


# --- date-clustered bootstrap ----------------------------------------------------------------

def test_cluster_bootstrap_is_reproducible():
    vals = [0.1, -0.2, 0.3, 0.05, -0.1, 0.2]
    ids = ["d1", "d1", "d2", "d2", "d3", "d3"]
    a = cluster_bootstrap_ci(vals, ids, _avg, n_resamples=200, seed=7)
    b = cluster_bootstrap_ci(vals, ids, _avg, n_resamples=200, seed=7)
    assert (a.ci_low, a.ci_high, a.p_value) == (b.ci_low, b.ci_high, b.p_value)


def test_clustered_ci_is_wider_than_iid_when_within_cluster_correlated():
    """10 disclosure dates, each with 8 identical excesses (perfectly correlated within date). The
    effective sample is 10 clusters, not 80 — so the date-clustered CI must be WIDER than the pooled
    i.i.d. CI that pretends all 80 are independent (the RNG-001 over-confidence the design guards)."""
    per_date = [0.5, -0.3, 0.4, -0.2, 0.6, -0.4, 0.3, -0.1, 0.5, -0.2]
    vals, ids = [], []
    for i, v in enumerate(per_date):
        vals.extend([v] * 8)
        ids.extend([f"d{i}"] * 8)
    clustered = cluster_bootstrap_ci(vals, ids, _avg, n_resamples=500, seed=3)
    iid = block_bootstrap_ci(vals, _avg, n_resamples=500, seed=3, block=1)
    assert (clustered.ci_high - clustered.ci_low) > (iid.ci_high - iid.ci_low)


# --- study wiring + verdict gate (synthetic fns) ---------------------------------------------

_EVENT_TICKERS = [f"E{i:03d}" for i in range(120)]
_CONTROL_TICKERS = [f"C{i:03d}" for i in range(40)]


def _feature_fn():
    from app.altdata.matched_control import CandidateFeatures
    # events and controls share the same feature *values* (i % 10) so every decile band contains
    # both — each event then finds same-decile controls (the rank-based deciles otherwise separate
    # alphabetically-earlier controls from events).
    cands = [CandidateFeatures(t, "Tech", float(i % 10), float(i % 10), float(i % 10))
             for i, t in enumerate(_EVENT_TICKERS)]
    cands += [CandidateFeatures(t, "Tech", float(j % 10), float(j % 10), float(j % 10))
              for j, t in enumerate(_CONTROL_TICKERS)]
    return lambda _as_of: cands


def _price_fn(event_ret: float, control_ret: float):
    def price_fn(ticker, start, _end):
        r = event_ret if ticker.startswith("E") else control_ret
        return [(start + timedelta(days=i), 100.0 * (1 + r * i / HOLD_PRIMARY))
                for i in range(HOLD_PRIMARY + 5)]
    return price_fn


def _clusters(k: int):
    evs = [_ev(_EVENT_TICKERS[i], date(2026, 1, 5) + timedelta(days=i), range_low=60_000)
           for i in range(k)]
    return build_clusters(evs, direction="buy")


def _run(k: int, event_ret: float):
    exclude = frozenset(_EVENT_TICKERS)   # Congress-traded tickers never used as controls
    return run_primary(_clusters(k), price_fn=_price_fn(event_ret, 0.02), feature_fn=_feature_fn(),
                       exclude_fn=lambda _d: exclude, min_controls=3, n_resamples=300)


def test_approved_positive_edge_meets_cluster_gate():
    out = _run(120, 0.10)                       # gross ~+8%, net positive; 120 >= 100 clusters
    assert out["metrics"]["n_benchmarked"] == 120
    assert out["outcome"] == "Approved"
    assert out["metrics"]["mean_excess"] < out["metrics"]["mean_excess_gross"]   # cost applied


def test_insufficient_evidence_below_cluster_gate():
    out = _run(12, 0.10)                         # positive edge but only 12 clusters
    assert out["metrics"]["n_benchmarked"] == 12
    assert out["outcome"] == "Insufficient Evidence"
