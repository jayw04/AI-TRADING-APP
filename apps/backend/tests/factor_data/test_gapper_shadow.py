"""GAPPER-001 shadow ledger — primary-design outcome logic on synthetic 1-min bars."""

from __future__ import annotations

import pandas as pd

from app.factor_data.gapper_shadow import candidate_outcome, day_book


def _bars(rows: list[tuple], day: str = "2026-07-08") -> pd.DataFrame:
    """rows = [(et_hh:mm, o, h, l, c, v), ...] → a bar frame with a UTC 't'."""
    recs = []
    for hhmm, o, h, lo, c, v in rows:
        t = pd.Timestamp(f"{day} {hhmm}", tz="America/New_York").tz_convert("UTC")
        recs.append({"t": t, "o": o, "h": h, "l": lo, "c": c, "v": v})
    return pd.DataFrame(recs)


_SPY_UP = _bars([("09:31", 401, 401, 401, 401, 100), ("10:05", 402, 402, 402, 402, 100)])
_SEC_UP = _bars([("09:31", 201, 201, 201, 201, 100), ("10:05", 202, 202, 202, 202, 100)])


def test_triggers_and_computes_gross() -> None:
    cand = _bars([
        ("09:31", 99, 100, 98, 99.5, 1000),   # opening range → OR high = 100
        ("10:05", 100, 101, 100, 100.5, 1000),  # break of 100, close above VWAP
        ("15:59", 104, 105, 104, 105.0, 1000),  # close
    ])
    r = candidate_outcome(cand, _SPY_UP, _SEC_UP, spy_prev_close=400, sector_prev_close=200)
    assert r["triggered"] is True
    assert r["entry_px"] == 100.0
    assert r["exit_px"] == 105.0
    assert r["gross_bps"] == 500.0  # (105/100 - 1) * 1e4


def test_no_break_not_triggered() -> None:
    cand = _bars([("09:31", 99, 100, 98, 99.5, 1000), ("10:05", 99, 99.9, 98, 99, 1000),
                  ("15:59", 99, 99, 98, 99, 1000)])
    r = candidate_outcome(cand, _SPY_UP, _SEC_UP, spy_prev_close=400, sector_prev_close=200)
    assert r["triggered"] is False
    assert r["reason"] == "no_or_break"


def test_break_but_market_negative_not_triggered() -> None:
    cand = _bars([("09:31", 99, 100, 98, 99.5, 1000), ("10:05", 100, 101, 100, 100.5, 1000),
                  ("15:59", 104, 105, 104, 105, 1000)])
    r = candidate_outcome(cand, _SPY_UP, _SEC_UP, spy_prev_close=999, sector_prev_close=200)
    assert r["triggered"] is False
    assert "market_not_positive" in r["reason"]


def test_day_book_equal_weight_and_slippage() -> None:
    outs = [
        {"ticker": "A", "triggered": True, "gross_bps": 400.0},
        {"ticker": "B", "triggered": True, "gross_bps": 200.0},
        {"ticker": "C", "triggered": False, "gross_bps": -50.0},
    ]
    book = day_book(outs)
    assert book["n_triggered"] == 2
    assert book["book_gross_bps"] == 300.0            # (400 + 200) / 2
    assert book["net_by_slippage_per_side"]["10bps"] == 280.0   # 300 - 2*10
    assert book["breakeven_slippage_per_side_bps"] == 150.0     # 300 / 2


def test_day_book_idle_day_is_zero() -> None:
    book = day_book([{"ticker": "A", "triggered": False, "gross_bps": 10.0}])
    assert book["n_triggered"] == 0
    assert book["book_gross_bps"] == 0.0
    assert book["breakeven_slippage_per_side_bps"] == 0.0
