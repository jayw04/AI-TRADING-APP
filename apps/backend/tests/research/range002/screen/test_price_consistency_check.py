"""Cross-source PRICE CONSISTENCY (vendor unadjusted close vs SIP last regular-session close).

Synthetic only. It is a screening aid, not an identity proof, and it must emit counts and dates,
never prices."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import run_descriptive_screen as rds  # noqa: E402

DAYS = [date(2016, 1, 4), date(2016, 1, 5), date(2016, 1, 6), date(2016, 1, 7)]
FROM, TO = date(2016, 1, 1), date(2016, 3, 31)


def _stores(
    tmp: Path,
    sip_close: dict[str, float],
    daily_close: dict[str, float],
    actions: list[tuple[str, date, str]] | None = None,
) -> tuple[Path, Any]:
    store = tmp / "m.duckdb"
    m = duckdb.connect(str(store))
    m.execute(
        "CREATE TABLE minute_bars(symbol VARCHAR, ts TIMESTAMP, open DOUBLE, high DOUBLE, "
        "low DOUBLE, close DOUBLE, volume BIGINT, basis VARCHAR)"
    )
    for sym, px in sip_close.items():
        for d in DAYS:
            # an early bar with a different close, then the 15:59 ET bar (20:59 UTC in January)
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
    daily.execute('CREATE TABLE "actions"(date DATE, action VARCHAR, ticker VARCHAR)')
    for sym, px in daily_close.items():
        for d in DAYS:
            daily.execute('INSERT INTO "sep" VALUES (?, ?, ?)', [sym, d, px])
    for tkr, day, act in actions or []:
        daily.execute('INSERT INTO "actions" VALUES (?, ?, ?)', [day, act, tkr])
    return store, daily


def _check(daily: Any, store: Path, symbols: list[str], **kw: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "tolerance": 0.05,
        "max_mismatch_fraction": 0.10,
        "date_from": FROM,
        "date_to": TO,
    }
    args.update(kw)
    return rds.price_consistency_check(daily, store, symbols, **args)


def test_matching_series_pass_and_a_different_price_level_is_flagged(tmp_path: Path) -> None:
    store, daily = _stores(
        tmp_path,
        sip_close={"GOOD": 100.0, "WRONG": 50.0, "NEAR": 100.0},
        daily_close={"GOOD": 100.2, "WRONG": 100.0, "NEAR": 103.0},  # 0.2%, 100%, 3%
    )
    out = _check(daily, store, ["GOOD", "WRONG", "NEAR", "ABSENT"])
    assert out["symbols_exceeding_fraction"] == ["WRONG"]
    assert out["symbols_with_any_mismatch"] == {"WRONG": [4, 4]}
    assert out["missing_comparisons"]["symbols_without_any_comparable_day"] == ["ABSENT"]
    assert out["symbol_days_compared"] == 12
    assert out["check"] == "cross_source_price_consistency"
    assert "not proof of issuer identity" in out["what_it_is_not"]
    text = json.dumps(out)
    for needle in ("100.2", "103.0", "50.0"):  # no price value leaves the function
        assert needle not in text


def test_a_symbol_below_the_mismatch_fraction_is_not_refused(tmp_path: Path) -> None:
    store, daily = _stores(tmp_path, {"A": 100.0}, {"A": 100.0})
    daily.execute("UPDATE \"sep\" SET closeunadj = 150.0 WHERE date = DATE '2016-01-04'")
    out = _check(daily, store, ["A"], max_mismatch_fraction=0.5)
    assert out["symbols_with_any_mismatch"] == {"A": [4, 1]}
    assert out["symbols_exceeding_fraction"] == []


def test_missing_comparisons_are_reported_in_both_directions(tmp_path: Path) -> None:
    store, daily = _stores(tmp_path, {"A": 100.0}, {"A": 100.0})
    daily.execute("DELETE FROM \"sep\" WHERE date = DATE '2016-01-04'")  # SIP day, no vendor row
    daily.execute("INSERT INTO \"sep\" VALUES ('A', DATE '2016-01-08', 100.0)")  # vendor, no SIP
    out = _check(daily, store, ["A"])
    miss = out["missing_comparisons"]
    assert miss["sip_days_without_vendor_row_by_symbol"] == {"A": 1}
    assert miss["vendor_days_without_sip_bars_by_symbol"] == {"A": 1}
    assert out["symbol_days_compared"] == 3


def test_mismatches_on_corporate_action_days_are_reported_not_removed(tmp_path: Path) -> None:
    store, daily = _stores(
        tmp_path, {"A": 100.0}, {"A": 100.0}, actions=[("A", date(2016, 1, 5), "split")]
    )
    daily.execute("UPDATE \"sep\" SET closeunadj = 50.0 WHERE date = DATE '2016-01-05'")
    out = _check(daily, store, ["A"], max_mismatch_fraction=0.9)
    assert out["mismatching_days_on_a_corporate_action_day"] == 1
    assert out["symbol_days_mismatching"] == 1  # still counted toward the fraction
    assert out["corporate_action_symbol_days_in_window"] == 1


def test_settings_have_no_defaults_and_are_proposed_not_baseline(tmp_path: Path) -> None:
    store, daily = _stores(tmp_path, {"A": 100.0}, {"A": 100.0})
    with pytest.raises(TypeError):
        rds.price_consistency_check(  # type: ignore[call-arg]
            daily, store, ["A"], date_from=FROM, date_to=TO
        )
    out = _check(daily, store, ["A"])
    assert "PROPOSED" in out["proposed_settings_status"]
    assert not hasattr(rds, "IDENTITY_PRICE_TOLERANCE")
    assert not hasattr(rds, "IDENTITY_MAX_BAD_FRACTION")
