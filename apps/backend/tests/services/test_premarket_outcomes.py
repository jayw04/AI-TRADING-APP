"""SCAN-001 premarket-data gate — increment (C) back-fill tests (ADR 0024).

Covers the pure realized-outcome math (compute_outcome), the record back-fill with the
candidate-vs-field edge + coverage (backfill_record), and the thin Alpaca read (fetch_realized_bars
against a fake BarCache).
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import pandas as pd

from app.services import premarket_outcomes as po


def test_compute_outcome_matches_engine_math() -> None:
    # open 100, high 110, low 95, close 105, ATR 4% → range 15%, E 3.75, CM 10, NM 5
    o = po.compute_outcome(4.0, {"open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0})
    assert o == {"E": 3.75, "CM": 10.0, "NM": 5.0, "range_pct": 15.0}


def test_compute_outcome_bad_open_is_none() -> None:
    assert po.compute_outcome(4.0, {"open": 0.0, "high": 1, "low": 1, "close": 1}) is None


def test_backfill_record_fills_edge_and_coverage() -> None:
    record = {
        "asof": "2024-03-01",
        "candidates": [{"symbol": "AAA", "atr_pct": 4.0}],
        "eligible": [{"symbol": "AAA", "atr_pct": 4.0}, {"symbol": "BBB", "atr_pct": 5.0}],
        "outcome_status": "pending", "outcomes": None,
    }
    bars = {
        "AAA": {"open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0},   # E 3.75
        "BBB": {"open": 100.0, "high": 105.0, "low": 100.0, "close": 102.0},  # range 5/5%→E 1.0
    }
    out = po.backfill_record(record, bars)
    assert out["outcome_status"] == "filled"
    oc = out["outcomes"]
    assert oc["candidate_mean_E"] == 3.75
    assert oc["baseline_mean_E"] == round((3.75 + 1.0) / 2, 4)   # AAA + BBB
    assert oc["edge_E"] == round(3.75 - (3.75 + 1.0) / 2, 4)     # candidate beats the field
    assert oc["coverage"] == {"candidates_covered": 1, "candidates_total": 1,
                              "eligible_covered": 2, "eligible_total": 2}


def test_backfill_record_uncovered_when_no_bars() -> None:
    record = {
        "asof": "2024-03-01",
        "candidates": [{"symbol": "AAA", "atr_pct": 4.0}],
        "eligible": [{"symbol": "AAA", "atr_pct": 4.0}],
        "outcome_status": "pending", "outcomes": None,
    }
    out = po.backfill_record(record, {})           # Alpaca covered nothing
    assert out["outcome_status"] == "uncovered"
    assert out["outcomes"]["coverage"]["candidates_covered"] == 0


class _FakeBarCache:
    """Async get_bars returning a 1-row daily frame, or raising for an uncovered symbol."""

    def __init__(self, covered: dict[str, dict[str, float]]) -> None:
        self._covered = covered

    async def get_bars(self, symbol: str, timeframe: str, start: Any, end: Any) -> pd.DataFrame:
        if symbol not in self._covered:
            raise RuntimeError("not covered")
        b = self._covered[symbol]
        return pd.DataFrame([{"t": start, "o": b["o"], "h": b["h"], "l": b["l"],
                              "c": b["c"], "v": 1_000_000.0}])


def test_fetch_realized_bars_skips_uncovered() -> None:
    cache = _FakeBarCache({"AAA": {"o": 100.0, "h": 110.0, "l": 95.0, "c": 105.0}})
    bars = asyncio.run(po.fetch_realized_bars(cache, ["AAA", "ZZZ"], date(2024, 3, 1)))
    assert set(bars) == {"AAA"}                     # ZZZ raised → omitted (uncovered)
    assert bars["AAA"] == {"open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0}
