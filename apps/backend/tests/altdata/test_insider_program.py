"""INSIDER-001 §4 reproduction runner — the verdict tree (data) + the end-to-end study."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.altdata.insider_program import (
    INSIDER_VERDICT,
    render_evidence,
    run_insider_reproduction,
)
from app.altdata.signal import ConvictionHit
from app.research.factor_lab.verdict import classify

D0 = date(2024, 1, 2)


def _day(i: int) -> date:
    return D0 + timedelta(days=i)


# --- verdict tree (declared as data) ---------------------------------------

def _m(**kw):
    base = {"n_taken": 50, "h1_ci_low": None, "h1_ci_high": None,
            "mean_event_return": 0.0, "total_return": 0.0}
    base.update(kw)
    return base


def test_verdict_inconclusive_when_too_few_events():
    assert classify(_m(n_taken=5), INSIDER_VERDICT)[0] == "D - Inconclusive"


def test_verdict_validated_when_edge_excludes_zero():
    out, _ = classify(_m(h1_ci_low=0.2, mean_event_return=0.05), INSIDER_VERDICT)
    assert out == "A - Validated standalone edge"


def test_verdict_rejected_when_ci_below_zero():
    out, _ = classify(_m(h1_ci_high=-0.1, mean_event_return=-0.02, total_return=-0.1),
                      INSIDER_VERDICT)
    assert out == "C - Rejected"


def test_verdict_diversifier_when_positive_but_not_significant():
    # CI straddles zero (no standalone edge) but a real positive per-event tilt -> the expected B
    out, _ = classify(_m(h1_ci_low=-0.1, h1_ci_high=0.3, mean_event_return=0.03), INSIDER_VERDICT)
    assert out == "B - Diversifier / factor tilt"


# --- end-to-end runner over a fake SEP store -------------------------------

class _FakeStore:
    def __init__(self, paths: dict[str, list[tuple[date, float]]]) -> None:
        self.paths = paths

    def get_prices(self, ticker, start, end, *, adjusted=True):  # noqa: ARG002
        rows = [(d, c) for d, c in self.paths.get(ticker, []) if start <= d <= end]
        return pd.DataFrame({"date": [d for d, _ in rows], "close": [c for _, c in rows]})


def test_reproduction_runs_end_to_end_and_verdicts():
    # one name on a long monotonic up-path; conviction hits spaced past the hold so each re-enters
    path = [(_day(i), 100.0 * (1.002 ** i)) for i in range(400)]
    store = _FakeStore({"AAA": path})
    hits = [
        ConvictionHit(ticker="AAA", event_date=_day(i), filed_at=_day(i), value=120_000.0,
                      owner_name="Exec", n_cluster_insiders=1, is_cluster=False, is_big_solo=True)
        for i in range(0, 360, 8)  # 45 hits, 8 days apart, hold 5 -> all re-enter
    ]
    repro = run_insider_reproduction(
        hits, store, universe=["AAA"], start=_day(0), end=_day(399),
        hold_trading_days=5, n_resamples=300,
    )
    assert repro.metrics["n_taken"] >= 30
    assert repro.verdict[0] in {"A", "B", "C", "D"}
    assert repro.metrics["mean_event_return"] > 0  # the synthetic up-path is profitable
    md = render_evidence(repro)
    assert repro.verdict in md and "INSIDER-001 §4" in md
