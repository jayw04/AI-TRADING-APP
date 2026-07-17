"""SCAN-001 premarket-data gate — increment (B) live-scan tests.

Covers the historical store join (``store_features_for`` against an in-memory DuckDB) and the
fail-soft scan orchestration (``run_premarket_scan`` with a monkeypatched gappers reader): the
gappers→store→panel→candidate funnel, PIT (only prior bars), and graceful empty behaviour.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import duckdb
import pytest

from app.services import premarket_scan as ps


class _FakeStore:
    """Minimal stand-in exposing ``.con`` like FactorDataStore."""

    def __init__(self, con: Any) -> None:
        self.con = con


def _con_with_bars(symbol: str = "AAA", n: int = 30) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE sep (ticker VARCHAR, date DATE, open DOUBLE, high DOUBLE, "
        "low DOUBLE, close DOUBLE, volume DOUBLE)"
    )
    # n daily bars ending 2024-01-30; clean $4 range on a $100 close → ATR 4%
    for i in range(n):
        d = date(2024, 1, 1).toordinal() + i
        con.execute(
            "INSERT INTO sep VALUES (?, ?, ?, ?, ?, ?, ?)",
            [symbol, date.fromordinal(d), 100.0, 102.0, 98.0, 100.0, 1_000_000.0],
        )
    return con


def test_store_features_for_computes_from_prior_bars() -> None:
    con = _con_with_bars("AAA", n=30)
    feats = ps.store_features_for(con, ["AAA"], date(2024, 3, 1))
    assert "AAA" in feats
    assert feats["AAA"]["atr_pct"] == 4.0
    assert feats["AAA"]["prev_dollar_vol"] == 100_000_000.0


def test_store_features_for_is_point_in_time() -> None:
    con = _con_with_bars("AAA", n=30)
    # asof before any bar exists → no prior history → symbol omitted
    assert ps.store_features_for(con, ["AAA"], date(2023, 12, 1)) == {}


def test_store_features_for_drops_uncovered_and_short_history() -> None:
    con = _con_with_bars("AAA", n=30)
    feats = ps.store_features_for(con, ["AAA", "ZZZ"], date(2024, 3, 1))
    assert set(feats) == {"AAA"}          # ZZZ has no rows → omitted


def test_store_features_for_empty_symbols() -> None:
    con = _con_with_bars()
    assert ps.store_features_for(con, [], date(2024, 3, 1)) == {}


def test_run_premarket_scan_funnel(monkeypatch: pytest.MonkeyPatch) -> None:
    con = _con_with_bars("AAA", n=30)
    # AAA is a real gapper with store coverage; ZZZ has no store coverage → dropped
    payload = {
        "date": "2024-03-01", "scanned_at": "2024-03-01T13:00:00Z", "stale": False,
        "gappers": [
            {"symbol": "AAA", "price": 50.0, "gap_pct": 8.0, "premarket_volume": 4_000_000},
            {"symbol": "ZZZ", "price": 30.0, "gap_pct": 9.0, "premarket_volume": 5_000_000},
        ],
    }
    monkeypatch.setattr(ps, "read_gappers_for", lambda _asof: payload)
    report = ps.run_premarket_scan(_FakeStore(con), asof=date(2024, 3, 1), top_n=15)
    assert report["stale"] is False
    assert report["gappers_in"] == 2
    assert report["store_covered"] == 1            # only AAA is in the store
    assert report["eligible_panel"] == 1
    assert [c["symbol"] for c in report["candidates"]] == ["AAA"]
    assert report["candidates"][0]["reason"] == "Gap + RVOL + ATR"


def test_run_premarket_scan_passes_gappers_source_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0041: the payload's source lands in the report as gappers_source."""
    payload = {
        "date": "2024-03-01", "scanned_at": "2024-03-01T13:05:00Z", "stale": False,
        "source": "box_native_alpaca_v1", "gappers": [],
    }
    monkeypatch.setattr(ps, "read_gappers_for", lambda _asof: payload)
    report = ps.run_premarket_scan(_FakeStore(_con_with_bars()), asof=date(2024, 3, 1))
    assert report["gappers_source"] == "box_native_alpaca_v1"


def test_run_premarket_scan_fail_soft_when_no_gappers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ps, "read_gappers_for",
        lambda _asof: {"date": None, "scanned_at": None, "count": 0, "gappers": [],
                       "stale": True, "source": None},
    )
    report = ps.run_premarket_scan(_FakeStore(_con_with_bars()), asof=date(2024, 3, 1))
    assert report["gappers_in"] == 0
    assert report["candidate_count"] == 0
    assert report["candidates"] == []
    assert report["stale"] is True


def test_run_premarket_scan_asks_for_asofs_own_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """The scan must resolve ``asof``'s gappers, not "the latest" — the PIT contract."""
    asked: list[date] = []

    def _fake(asof: date) -> dict:
        asked.append(asof)
        return {"date": None, "scanned_at": None, "count": 0, "gappers": [], "stale": True,
                "source": None}

    monkeypatch.setattr(ps, "read_gappers_for", _fake)
    ps.run_premarket_scan(_FakeStore(_con_with_bars()), asof=date(2024, 3, 1))
    assert asked == [date(2024, 3, 1)]


def test_run_premarket_scan_never_substitutes_a_neighbouring_day(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression, end-to-end through the real reader: a missed scanner day yields an EMPTY
    report, not the prior day's scan.

    The old reader ignored ``asof`` and returned the newest file, so a day the scanner missed
    silently recorded the previous day's candidates under today's ``asof`` — a duplicate in the
    gate's forward series that back-filled to ``filled`` and counted toward the verdict.
    """
    import json as _json

    from app.services import premarket_gappers as pg

    external = tmp_path / "external"
    native = tmp_path / "native"
    external.mkdir()
    native.mkdir()
    monkeypatch.setattr(pg, "_directory", lambda: str(external))
    monkeypatch.setattr(pg, "_native_directory", lambda: str(native))
    # Only 03-01 was scanned; 03-04 was missed.
    (external / "premarket_gappers_2024-03-01.json").write_text(
        _json.dumps({
            "scanned_at": "2024-03-01T13:00:00Z",
            "gappers": [
                {"symbol": "AAA", "price": 50.0, "gap_pct": 8.0, "premarket_volume": 4_000_000}
            ],
        }),
        encoding="utf-8",
    )

    missed = ps.run_premarket_scan(_FakeStore(_con_with_bars("AAA", n=30)), asof=date(2024, 3, 4))
    assert missed["gappers_in"] == 0, "must not inherit 2024-03-01's gappers"
    assert missed["candidates"] == []
    assert missed["date"] is None
    assert missed["scanned_at"] is None
    assert missed["gappers_source"] is None
    assert missed["stale"] is True

    # ...while the day that WAS scanned still reports normally.
    scanned = ps.run_premarket_scan(
        _FakeStore(_con_with_bars("AAA", n=30)), asof=date(2024, 3, 1)
    )
    assert scanned["gappers_in"] == 1
    assert scanned["stale"] is False
    assert scanned["gappers_source"] == pg.SOURCE_EXTERNAL
