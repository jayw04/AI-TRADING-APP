"""Tests for the daily factor-refresh universe and staleness gate.

Each test names the production failure it prevents. The three defects, all found
2026-08-03 after 301 of 500 ranking names had sat frozen at 2026-07-06 while every
readiness gate reported green:

1. the refresh universe was the registered list, not the store-wide pool books
   actually rank over;
2. ``status='PAPER'`` excluded IDLE strategies, so a book pending activation could
   never reach a green readiness gate;
3. freshness was read as ``max(date)``, which one current ticker keeps green.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_MODULE = _REPO_ROOT / "apps" / "backend" / "scripts" / "factor_refresh.py"

pytestmark = pytest.mark.skipif(not _MODULE.exists(), reason="factor_refresh.py absent")


def _load():
    spec = importlib.util.spec_from_file_location("factor_refresh", _MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def M():
    return _load()


AS_OF = date(2026, 8, 3)


def _app_db(tmp_path: Path, strategies, positions=()) -> Path:
    """Minimal app DB: only the columns the refresh reads."""
    p = tmp_path / "workbench.sqlite"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE strategies (id INTEGER PRIMARY KEY, status TEXT, symbols_json TEXT)")
    con.execute("CREATE TABLE symbols (id INTEGER PRIMARY KEY, symbol TEXT)")
    con.execute("CREATE TABLE positions (id INTEGER PRIMARY KEY, symbol_id INTEGER, qty REAL)")
    for sid, status, syms in strategies:
        con.execute("INSERT INTO strategies VALUES (?,?,?)", (sid, status, json.dumps(syms)))
    for i, (sym, qty) in enumerate(positions, start=1):
        con.execute("INSERT INTO symbols VALUES (?,?)", (i, sym))
        con.execute("INSERT INTO positions VALUES (?,?,?)", (i, i, qty))
    con.commit()
    con.close()
    return p


def _store(tmp_path: Path, rows, tickers=None, name="factor.duckdb") -> Path:
    """rows: (ticker, date, close, volume). tickers: (ticker, lastpricedate)."""
    import duckdb

    p = tmp_path / name
    con = duckdb.connect(str(p))
    con.execute("CREATE TABLE sep (ticker VARCHAR, date DATE, close DOUBLE, volume DOUBLE)")
    if rows:
        con.executemany("INSERT INTO sep VALUES (?,?,?,?)", rows)
    con.execute("CREATE TABLE tickers (ticker VARCHAR, firstpricedate DATE, lastpricedate DATE)")
    if tickers is None:
        seen = sorted({r[0] for r in rows})
        last = max((r[1] for r in rows), default=AS_OF)
        tickers = [(t, last) for t in seen]
    if tickers:
        con.executemany(
            "INSERT INTO tickers VALUES (?,?,?)",
            [(t, date(2000, 1, 1), lpd) for t, lpd in tickers],
        )
    con.close()
    return p


def _bars(ticker, dv, *, days=5, end=AS_OF, close=100.0):
    return [(ticker, end - timedelta(days=i), close, dv / close) for i in range(days)]


# ------------------------------------------------------------ defect 2: IDLE


def test_idle_strategies_contribute_symbols(M, tmp_path):
    """Defect 2. `status='PAPER'` starved a book pending activation of the very
    data its readiness gate required — it could never go green."""
    db = _app_db(tmp_path, [(9, "IDLE", ["AAA", "BBB"]), (7, "PAPER", ["CCC"])])
    reg = M.registered_symbols(db)
    assert reg["9:IDLE"] == ["AAA", "BBB"]
    assert reg["7:PAPER"] == ["CCC"]


@pytest.mark.parametrize(
    "status", ["IDLE", "PAPER", "LIVE", "PENDING_LIVE", "HALTED", "PAPER_VARIANT", "ERROR"]
)
def test_no_status_is_silently_dropped(M, tmp_path, status):
    db = _app_db(tmp_path, [(1, status, ["ZZZ"])])
    assert M.registered_symbols(db) == {f"1:{status}": ["ZZZ"]}


# ------------------------------------------- defect 1: the pool books rank over


def test_ranking_pool_is_store_wide_not_the_registered_list(M, tmp_path):
    """Defect 1. A book ranks over the top-n store-wide by dollar volume and then
    filters by its registered list, so unregistered names decide which registered
    names survive. Refreshing only registered names cannot keep that correct."""
    rows = _bars("BIG", 1e9) + _bars("MID", 1e6) + _bars("SMALL", 1e3)
    store = _store(tmp_path, rows)
    assert M.ranking_pool(store, AS_OF, n=2) == ["BIG", "MID"]


def test_ranking_pool_does_not_filter_on_lastpricedate(M, tmp_path):
    """The production query drops names whose lastpricedate lags, which is exactly
    how stale names vanish from the pool. The refresh must still pull them —
    filtering here would make the defect self-perpetuating."""
    rows = _bars("FRESH", 1e9) + _bars("STALE", 1e8)
    store = _store(
        tmp_path,
        rows,
        tickers=[("FRESH", AS_OF), ("STALE", date(2026, 7, 6))],
    )
    assert set(M.ranking_pool(store, AS_OF, n=10)) == {"FRESH", "STALE"}


def test_pool_size_floors_at_the_app_default_and_applies_headroom(M):
    assert M.required_pool_size({}, headroom=1.5) == M.DEFAULT_UNIVERSE_SIZE
    assert M.required_pool_size({"a": ["X"] * 100}, headroom=1.5) == M.DEFAULT_UNIVERSE_SIZE
    assert M.required_pool_size({"a": ["X"] * 800}, headroom=1.5) == 1200
    with pytest.raises(ValueError):
        M.required_pool_size({}, headroom=0.9)


def test_universe_unions_pool_registered_and_held(M, tmp_path):
    rows = _bars("BIG", 1e9) + _bars("MID", 1e6) + _bars("TINY", 1.0)
    store = _store(tmp_path, rows)
    db = _app_db(
        tmp_path,
        [(9, "IDLE", ["REGONLY"])],
        positions=[("HELDONLY", 5.0), ("CLOSED", 0.0)],
    )
    res = M.build_refresh_universe(db, store, AS_OF, extra=["SPY"])
    uni = res["universe"]
    assert {"BIG", "MID", "TINY", "REGONLY", "HELDONLY", "SPY"} <= set(uni)
    assert "CLOSED" not in uni, "a zero-qty position is not held"
    assert res["counts"]["registered_not_in_pool"] == 1
    assert res["counts"]["held_not_in_pool"] == 1


def test_held_names_survive_rotation_out_of_the_pool(M, tmp_path):
    """The v1.3 parity run-1 failure in miniature: a holding outside the PIT
    universe was invisible, so its exit was never generated. It must stay
    priceable regardless of liquidity rank."""
    store = _store(tmp_path, _bars("BIG", 1e9))
    db = _app_db(tmp_path, [(9, "IDLE", [])], positions=[("ROTATEDOUT", 3.0)])
    assert "ROTATEDOUT" in M.build_refresh_universe(db, store, AS_OF)["universe"]


def test_empty_universe_is_refused(M, tmp_path):
    store = _store(tmp_path, [], tickers=[])
    db = _app_db(tmp_path, [])
    with pytest.raises(M.RefreshError, match="EMPTY"):
        M.build_refresh_universe(db, store, AS_OF)


# ------------------------------------------- defect 3: max(date) hides staleness


def test_max_date_reads_green_while_most_names_are_frozen(M, tmp_path):
    """Defect 3, the exact 2026-07-06 shape: one current ticker keeps
    `max(date)` at today while the rest of the pool is a month stale."""
    frozen = date(2026, 7, 6)
    rows = _bars("CURRENT", 1e9)
    for i in range(9):
        rows += _bars(f"FROZEN{i}", 1e8, end=frozen)
    store = _store(
        tmp_path, rows, tickers=[("CURRENT", AS_OF)] + [(f"FROZEN{i}", frozen) for i in range(9)]
    )

    import duckdb

    con = duckdb.connect(str(store), read_only=True)
    assert con.execute("SELECT max(date) FROM sep").fetchone()[0] == AS_OF, (
        "precondition: the old global check sees today and passes"
    )
    con.close()

    st = M.per_name_staleness(store, ["CURRENT"] + [f"FROZEN{i}" for i in range(9)])
    assert st["coverage"] == pytest.approx(0.1)
    assert len(st["stale"]) == 9
    assert len(st["lastpricedate_stale"]) == 9


def test_per_name_staleness_flags_missing_names(M, tmp_path):
    store = _store(tmp_path, _bars("PRESENT", 1e9))
    st = M.per_name_staleness(store, ["PRESENT", "ABSENT"])
    assert st["missing"] == ["ABSENT"]
    assert st["coverage"] == pytest.approx(0.5)


def test_a_long_weekend_is_not_staleness(M, tmp_path):
    rows = _bars("A", 1e9) + _bars("B", 1e9, end=AS_OF - timedelta(days=3))
    store = _store(tmp_path, rows, tickers=[("A", AS_OF), ("B", AS_OF - timedelta(days=3))])
    st = M.per_name_staleness(store, ["A", "B"], max_lag_days=4)
    assert st["stale"] == []
    assert st["coverage"] == pytest.approx(1.0)


# ------------------------------------------------------------ the swap gate


def _live_and_stage(tmp_path, stage_rows, stage_tickers=None, live_rows=None):
    live = _store(tmp_path, live_rows or stage_rows, name="live.duckdb")
    stage = _store(tmp_path, stage_rows, tickers=stage_tickers, name="stage.duckdb")
    return live, stage


def test_gate_passes_on_a_fresh_store(M, tmp_path):
    rows = _bars("A", 1e9) + _bars("B", 1e8)
    live, stage = _live_and_stage(tmp_path, rows)
    failures, report = M.verify_staging(live, stage, ["A", "B"])
    assert failures == []
    assert report["per_name"]["coverage"] == pytest.approx(1.0)


def test_gate_fails_on_low_per_name_coverage(M, tmp_path):
    """The regression that matters: the old global checks all pass here."""
    frozen = date(2026, 7, 6)
    rows = _bars("CURRENT", 1e9) + [r for i in range(9) for r in _bars(f"F{i}", 1e8, end=frozen)]
    tickers = [("CURRENT", AS_OF)] + [(f"F{i}", frozen) for i in range(9)]
    live, stage = _live_and_stage(tmp_path, rows, stage_tickers=tickers)
    universe = ["CURRENT"] + [f"F{i}" for i in range(9)]
    failures, _ = M.verify_staging(live, stage, universe)
    assert any("per-name coverage" in f for f in failures)
    assert any("EXCLUDED from the ranking pool" in f for f in failures)


def test_gate_still_catches_sep_regression(M, tmp_path):
    live = _store(tmp_path, _bars("A", 1e9), name="live.duckdb")
    stage = _store(tmp_path, _bars("A", 1e9, end=AS_OF - timedelta(days=10)), name="stage.duckdb")
    failures, _ = M.verify_staging(live, stage, ["A"])
    assert any("REGRESSED" in f for f in failures)


def test_gate_still_catches_lastpricedate_behind_sep(M, tmp_path):
    """The 2026-07-06 incident's original signature: SEP advances past
    tickers.lastpricedate and the PIT universe empties, so every book HOLDS."""
    rows = _bars("A", 1e9)
    live, stage = _live_and_stage(tmp_path, rows, stage_tickers=[("A", AS_OF - timedelta(days=30))])
    failures, _ = M.verify_staging(live, stage, ["A"])
    assert any("PIT universe would EMPTY" in f for f in failures)


def test_gate_fails_on_empty_staging(M, tmp_path):
    live = _store(tmp_path, _bars("A", 1e9), name="live.duckdb")
    stage = _store(tmp_path, [], tickers=[], name="stage.duckdb")
    failures, _ = M.verify_staging(live, stage, ["A"])
    assert any("EMPTY" in f for f in failures)


# ---------------------------------------------------------------- drift pin


def test_constants_match_the_app_universe_module(M):
    """This module cannot import the app package, so the duplication is pinned
    here instead. If the app's universe size changes, the refresh must follow or
    it will under-pull the pool books rank over."""
    src = (_REPO_ROOT / "apps" / "backend" / "app" / "factor_data" / "universe.py").read_text(
        encoding="utf-8"
    )
    assert f"DEFAULT_UNIVERSE_SIZE = {M.DEFAULT_UNIVERSE_SIZE}" in src
    assert f"DEFAULT_LOOKBACK_DAYS = {M.DEFAULT_LOOKBACK_DAYS}" in src
