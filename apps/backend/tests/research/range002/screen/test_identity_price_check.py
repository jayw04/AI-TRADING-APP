"""Cross-source identity gate: SIP last regular close vs the vendor's unadjusted daily close.

Synthetic only. The function must emit counts, never prices."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import run_descriptive_screen as rds  # noqa: E402

DAYS = [date(2016, 1, 4), date(2016, 1, 5), date(2016, 1, 6), date(2016, 1, 7)]


def _stores(
    tmp: Path, sip_close: dict[str, float], daily_close: dict[str, float]
) -> tuple[Path, Any]:
    store = tmp / "m.duckdb"
    m = duckdb.connect(str(store))
    m.execute(
        "CREATE TABLE minute_bars(symbol VARCHAR, ts TIMESTAMP, open DOUBLE, high DOUBLE, "
        "low DOUBLE, close DOUBLE, volume BIGINT, basis VARCHAR)"
    )
    for sym, px in sip_close.items():
        for d in DAYS:
            # 15:59 ET bar (20:59 UTC in January); an earlier bar with a different close
            m.execute(
                "INSERT INTO minute_bars VALUES (?, ?, 1, 1, 1, ?, 1, 'raw')",
                [sym, datetime(d.year, d.month, d.day, 15, 0), px * 0.5],
            )
            m.execute(
                "INSERT INTO minute_bars VALUES (?, ?, 1, 1, 1, ?, 1, 'raw')",
                [sym, datetime(d.year, d.month, d.day, 20, 59), px],
            )
    m.close()
    daily = duckdb.connect(":memory:")
    daily.execute('CREATE TABLE "sep"(ticker VARCHAR, date DATE, closeunadj DOUBLE)')
    for sym, px in daily_close.items():
        for d in DAYS:
            daily.execute('INSERT INTO "sep" VALUES (?, ?, ?)', [sym, d, px])
    return store, daily


def test_matching_series_pass_and_a_different_company_is_flagged(tmp_path: Path) -> None:
    store, daily = _stores(
        tmp_path,
        sip_close={"GOOD": 100.0, "WRONG": 50.0, "NEAR": 100.0},
        daily_close={"GOOD": 100.2, "WRONG": 100.0, "NEAR": 103.0},  # 0.2%, 100%, 3%
    )
    out = rds.identity_price_check(daily, store, ["GOOD", "WRONG", "NEAR", "ABSENT"])
    assert out["symbols_exceeding_fraction"] == ["WRONG"]
    assert out["symbols_with_any_disagreement"] == {"WRONG": [4, 4]}
    assert out["symbols_without_any_comparable_day"] == ["ABSENT"]
    assert out["symbol_days_compared"] == 12
    text = json.dumps(out)
    for needle in ("100.2", "103.0", "50.0"):  # no price value leaves the function
        assert needle not in text


def test_a_symbol_below_the_bad_fraction_is_not_refused(tmp_path: Path) -> None:
    store, daily = _stores(tmp_path, {"A": 100.0}, {"A": 100.0})
    daily.execute("UPDATE \"sep\" SET closeunadj = 150.0 WHERE date = DATE '2016-01-04'")
    out = rds.identity_price_check(daily, store, ["A"], max_bad_fraction=0.5)
    assert out["symbols_with_any_disagreement"] == {"A": [4, 1]}
    assert out["symbols_exceeding_fraction"] == []
