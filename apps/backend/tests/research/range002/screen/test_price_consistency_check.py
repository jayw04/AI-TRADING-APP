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
    assert out["per_symbol_not_passing"]["WRONG"] == {
        "numerator_not_passing": 4,
        "denominator_sip_days": 4,
        "mismatching": 4,
        "missing_comparisons": 0,
        "fraction": 1.0,
    }
    assert out["totals"] == {
        "sip_symbol_days": 12,
        "compared": 12,
        "mismatching": 4,
        "missing_comparisons": 0,
    }
    assert out["missing_comparisons"]["symbols_without_any_comparable_day"] == ["ABSENT"]
    assert out["check"] == "cross_source_price_consistency"
    assert "not proof of issuer identity" in out["what_it_is_not"]
    text = json.dumps(out)
    for needle in ("100.2", "103.0", "50.0"):  # no price value leaves the function
        assert needle not in text


def test_every_mismatch_is_listed_with_its_corporate_action_flag(tmp_path: Path) -> None:
    store, daily = _stores(
        tmp_path, {"A": 100.0}, {"A": 100.0}, actions=[("A", date(2016, 1, 5), "split")]
    )
    daily.execute(
        "UPDATE \"sep\" SET closeunadj = 50.0 WHERE date IN (DATE '2016-01-05', DATE '2016-01-07')"
    )
    out = _check(daily, store, ["A"], max_mismatch_fraction=0.9)
    assert out["mismatches"] == [
        {"symbol": "A", "day": "2016-01-05", "corporate_action_that_day": "split"},
        {"symbol": "A", "day": "2016-01-07", "corporate_action_that_day": None},
    ]
    assert out["mismatching_days_on_a_corporate_action_day"] == 1
    assert out["corporate_action_symbol_days_in_window"] == 1


def test_a_missing_comparison_counts_as_not_passing_never_as_passing(tmp_path: Path) -> None:
    store, daily = _stores(tmp_path, {"A": 100.0}, {"A": 100.0})
    # two of four SIP days have no vendor row: 2/4 = 50% not passing, over the 10% limit
    daily.execute("DELETE FROM \"sep\" WHERE date IN (DATE '2016-01-04', DATE '2016-01-05')")
    out = _check(daily, store, ["A"])
    assert out["symbols_exceeding_fraction"] == ["A"]
    row = out["per_symbol_not_passing"]["A"]
    assert (row["numerator_not_passing"], row["denominator_sip_days"]) == (2, 4)
    assert row["mismatching"] == 0 and row["missing_comparisons"] == 2
    assert out["totals"]["compared"] == 2 and out["totals"]["missing_comparisons"] == 2
    miss = out["missing_comparisons"]
    assert miss["sip_days_without_usable_vendor_close_by_symbol"] == {"A": 2}


def test_vendor_days_without_sip_bars_are_reported(tmp_path: Path) -> None:
    store, daily = _stores(tmp_path, {"A": 100.0}, {"A": 100.0})
    daily.execute("INSERT INTO \"sep\" VALUES ('A', DATE '2016-01-08', 100.0)")
    out = _check(daily, store, ["A"])
    assert out["missing_comparisons"]["vendor_days_without_sip_bars_by_symbol"] == {"A": 1}
    assert out["totals"]["sip_symbol_days"] == 4


def test_a_symbol_below_the_fraction_is_not_refused(tmp_path: Path) -> None:
    store, daily = _stores(tmp_path, {"A": 100.0}, {"A": 100.0})
    daily.execute("UPDATE \"sep\" SET closeunadj = 150.0 WHERE date = DATE '2016-01-04'")
    out = _check(daily, store, ["A"], max_mismatch_fraction=0.5)
    assert out["per_symbol_not_passing"]["A"]["numerator_not_passing"] == 1
    assert out["symbols_exceeding_fraction"] == []


def test_settings_have_no_defaults_and_are_owner_approved_for_this_attempt(tmp_path: Path) -> None:
    store, daily = _stores(tmp_path, {"A": 100.0}, {"A": 100.0})
    with pytest.raises(TypeError):
        rds.price_consistency_check(  # type: ignore[call-arg]
            daily, store, ["A"], date_from=FROM, date_to=TO
        )
    out = _check(daily, store, ["A"])
    assert "this attempt only" in out["proposed_settings_status"]
    assert not hasattr(rds, "IDENTITY_PRICE_TOLERANCE")
    assert not hasattr(rds, "IDENTITY_MAX_BAD_FRACTION")
