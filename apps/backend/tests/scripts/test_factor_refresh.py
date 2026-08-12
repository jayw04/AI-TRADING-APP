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

#: Mirrors the REAL production schema (app/db/models/symbol.py). The column is
#: ``ticker``. A fixture that invented ``symbol`` is what let a broken query ship:
#: the test agreed with the code and both disagreed with the database.
_SYMBOLS_DDL = (
    "CREATE TABLE symbols ("
    " id INTEGER PRIMARY KEY, ticker VARCHAR(20), exchange VARCHAR(20),"
    " asset_class VARCHAR(20), name VARCHAR(255), active BOOLEAN)"
)


def _app_db(tmp_path: Path, strategies, positions=()) -> Path:
    """Minimal app DB: only the columns the refresh reads."""
    p = tmp_path / "workbench.sqlite"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE strategies (id INTEGER PRIMARY KEY, status TEXT, symbols_json TEXT)")
    con.execute(_SYMBOLS_DDL)
    con.execute("CREATE TABLE positions (id INTEGER PRIMARY KEY, symbol_id INTEGER, qty REAL)")
    for sid, status, syms in strategies:
        con.execute("INSERT INTO strategies VALUES (?,?,?)", (sid, status, json.dumps(syms)))
    for i, (sym, qty) in enumerate(positions, start=1):
        con.execute("INSERT INTO symbols (id, ticker) VALUES (?,?)", (i, sym))
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
    # A registered list must be non-empty (see the symbols_json contract below);
    # the point of this test is the HELD name, which is registered nowhere.
    db = _app_db(tmp_path, [(9, "IDLE", ["UNRELATED"])], positions=[("ROTATEDOUT", 3.0)])
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


# ------------------------------------ symbols_json must fail closed, with attribution


def _raw_db(tmp_path: Path, rows) -> Path:
    """An app DB whose symbols_json is written verbatim, bypassing json.dumps."""
    p = tmp_path / "raw.sqlite"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE strategies (id INTEGER PRIMARY KEY, status TEXT, symbols_json TEXT)")
    con.execute(_SYMBOLS_DDL)
    con.execute("CREATE TABLE positions (id INTEGER PRIMARY KEY, symbol_id INTEGER, qty REAL)")
    con.executemany("INSERT INTO strategies VALUES (?,?,?)", rows)
    con.commit()
    con.close()
    return p


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (None, "NULL"),
        ("", "empty or non-text"),
        ("   ", "empty or non-text"),
        ("{oops", "invalid JSON"),
        ('{"AAPL": 1}', "must be a JSON array"),
        ("5", "must be a JSON array"),
        ('"AAPL"', "must be a JSON array"),
        ("[]", "empty array"),
        ('["AAA", 7]', "must be a string"),
        ('["AAA", "  "]', "is blank"),
    ],
)
def test_bad_symbols_json_fails_closed(M, tmp_path, raw, reason):
    """A silently omitted strategy drops out of the safety union and its names go
    stale — the exact failure this module exists to prevent. Every malformed shape
    must raise, and the error must name the offending strategy."""
    db = _raw_db(tmp_path, [(9, "IDLE", raw)])
    with pytest.raises(M.RefreshError, match=reason):
        M.registered_symbols(db)


def test_bad_symbols_json_error_names_the_strategy_but_not_the_value(M, tmp_path):
    """The raw value may be large or hold data that does not belong in a log."""
    secret = "SENSITIVE-DO-NOT-LOG-" + "X" * 200
    db = _raw_db(tmp_path, [(9, "IDLE", json.dumps({secret: 1}))])
    with pytest.raises(M.RefreshError) as exc:
        M.registered_symbols(db)
    assert "9:IDLE" in str(exc.value)
    assert secret not in str(exc.value)


def test_non_array_json_does_not_silently_yield_dict_keys(M, tmp_path):
    """A JSON object iterates its KEYS and would produce plausible-but-wrong
    symbols with no error at all — worse than omission, because nothing signals
    it. This is the regression that matters most."""
    db = _raw_db(tmp_path, [(9, "IDLE", '{"AAA": 1, "BBB": 2}')])
    with pytest.raises(M.RefreshError):
        M.registered_symbols(db)


def test_valid_symbols_are_stripped_uppercased_deduped_and_sorted(M, tmp_path):
    db = _raw_db(tmp_path, [(9, "IDLE", '[" bbb ", "aaa", "AAA", "Ccc"]')])
    assert M.registered_symbols(db) == {"9:IDLE": ["AAA", "BBB", "CCC"]}


# ----------------------------------------------------------------- digests


def test_universe_report_carries_four_digests_each_with_a_count(M, tmp_path):
    store = _store(tmp_path, _bars("BIG", 1e9) + _bars("MID", 1e8))
    db = _app_db(tmp_path, [(9, "IDLE", ["AAA"])], positions=[("HELDNAME", 2.0)])
    res = M.build_refresh_universe(db, store, AS_OF, extra=["SPY"])
    for name in ("ranking_pool", "registered_union", "held_symbols", "final_refresh_universe"):
        entry = res["digests"][name]
        assert len(entry["sha256"]) == 64
        assert isinstance(entry["count"], int)


def test_digest_is_canonical_and_order_insensitive(M):
    assert M.digest(["bbb", "AAA"]) == M.digest([" aaa ", "BBB"])
    assert M.digest(["AAA", "AAA"]) == M.digest(["AAA"])
    assert M.digest(["AAA"]) != M.digest(["AAB"])


def test_digest_counts_distinguish_sets_a_digest_alone_cannot(M, tmp_path):
    """Count travels with every digest so a malformed serialisation that drops or
    duplicates entries cannot present as the same set."""
    store = _store(tmp_path, _bars("BIG", 1e9))
    db = _app_db(tmp_path, [(9, "IDLE", ["AAA", "BBB"])])
    res = M.build_refresh_universe(db, store, AS_OF)
    assert res["digests"]["registered_union"]["count"] == 2


# ------------------------------------------------ attribution and growth control


def test_universe_is_exactly_the_union_of_its_components(M, tmp_path):
    store = _store(tmp_path, _bars("BIG", 1e9))
    db = _app_db(tmp_path, [(9, "IDLE", ["AAA"])])
    res = M.build_refresh_universe(db, store, AS_OF, extra=["SPY"])
    attributed = M.attribute(res)
    assert set(attributed) == set(res["universe"])
    assert attributed["SPY"] == ["extra"]


def test_a_universe_member_from_no_component_fails_closed(M, tmp_path):
    """The integrity check behind "unexplained growth": the union is trivially
    explained by its own definition, so what must be caught is an artifact that is
    NOT the union of its recorded components."""
    store = _store(tmp_path, _bars("BIG", 1e9))
    db = _app_db(tmp_path, [(9, "IDLE", ["AAA"])])
    res = M.build_refresh_universe(db, store, AS_OF)
    res["universe"] = sorted(set(res["universe"]) | {"SMUGGLED"})
    with pytest.raises(M.RefreshError, match="no recorded component"):
        M.attribute(res)


def test_component_member_missing_from_the_universe_fails_closed(M, tmp_path):
    store = _store(tmp_path, _bars("BIG", 1e9))
    db = _app_db(tmp_path, [(9, "IDLE", ["AAA"])])
    res = M.build_refresh_universe(db, store, AS_OF)
    res["universe"] = [s for s in res["universe"] if s != "AAA"]
    with pytest.raises(M.RefreshError, match="absent from the universe"):
        M.attribute(res)


def _doc(symbols, components=None):
    comps = components or {
        "ranking_pool": list(symbols),
        "registered_union": [],
        "held": [],
        "extra": [],
    }
    return {"universe": sorted(symbols), "counts": {"total": len(symbols)}, "components": comps}


def test_first_run_records_a_baseline_and_computes_no_relative_growth(M):
    """Relative growth against an absent or zero prior is undefined; dividing by
    it would fail the bootstrap for no reason."""
    res = M.growth_control(_doc(["AAA", "BBB"]), None)
    assert res["state"] == "BOOTSTRAP_BASELINE_RECORDED"
    assert res["prior_count"] is None
    assert res["relative_delta"] is None
    assert res["requires_review"] is False


def test_subsequent_runs_compare_against_the_prior_sealed_run(M):
    prior = _doc(["AAA", "BBB"])
    res = M.growth_control(_doc(["AAA", "BBB", "CCC"]), prior)
    assert res["state"] == "COMPARATIVE_GROWTH_CONTROL_ACTIVE"
    assert res["prior_count"] == 2
    assert res["absolute_delta"] == 1
    assert res["added_symbols"]["count"] == 1
    assert res["removed_symbols"]["count"] == 0
    assert res["component_attribution"] == {"ranking_pool": 1}


def test_large_growth_is_flagged_for_review_not_failed(M):
    """A newly registered strategy or a new holding can legitimately expand the
    set, so expansion is reported rather than refused."""
    res = M.growth_control(_doc([f"S{i}" for i in range(20)]), _doc(["S0", "S1"]))
    assert res["requires_review"] is True
    assert res["state"] == "COMPARATIVE_GROWTH_CONTROL_ACTIVE"


def test_absolute_ceiling_is_a_stop(M):
    big = _doc([f"S{i}" for i in range(30)])
    with pytest.raises(M.RefreshError, match="exceeds the absolute ceiling"):
        M.growth_control(big, None, max_universe=10)


def test_a_failed_attempt_never_becomes_the_comparison_anchor(M):
    """The anchor is the last SEALED SUCCESSFUL run. If a failed attempt could
    re-baseline it, one bad run silently moves the reference."""
    sealed = _doc(["AAA", "BBB"])
    first = M.growth_control(_doc(["AAA", "BBB", "CCC"]), sealed)
    second = M.growth_control(_doc(["AAA", "BBB", "CCC"]), sealed)
    assert first["absolute_delta"] == second["absolute_delta"] == 1


# --------------------------------------------- decision-path isolation boundary


def test_another_strategys_symbol_may_move_the_cutoff_but_not_enter_wss(M, tmp_path):
    """Isolation belongs at decision time, not data time. A name registered only
    to another strategy legitimately competes for the store-wide top-n cutoff, but
    it must not reach WSS's eligible set unless WSS registers it independently."""
    store = _store(tmp_path, _bars("OTHERONLY", 9e9) + _bars("WSSNAME", 1e8))
    db = _app_db(tmp_path, [(9, "IDLE", ["WSSNAME"]), (7, "PAPER", ["OTHERONLY"])])
    res = M.build_refresh_universe(db, store, AS_OF)

    # Data layer: the shared store carries both — that is the design.
    assert "OTHERONLY" in res["universe"]
    assert "OTHERONLY" in res["components"]["ranking_pool"]

    # Decision layer: WSS's eligible set is its own registered list, and the other
    # strategy's exclusive name is not in it.
    wss_registered = set(M.registered_symbols(db)["9:IDLE"])
    wss_eligible = {s for s in res["universe"] if s in wss_registered}
    assert "WSSNAME" in wss_eligible
    assert "OTHERONLY" not in wss_eligible


# ------------------------------------------------------- no authority coupling


def test_refresh_construction_never_mutates_strategy_or_trading_state(M, tmp_path):
    """The actual security boundary: refresh membership confers no authority.
    Construction must not touch status, schedulers, trading flags or the broker."""
    store = _store(tmp_path, _bars("BIG", 1e9))
    db = _app_db(tmp_path, [(9, "IDLE", ["AAA"]), (7, "PAPER", ["BBB"])])

    query = "SELECT id, status, symbols_json FROM strategies ORDER BY id"
    before = sqlite3.connect(db).execute(query).fetchall()
    M.build_refresh_universe(db, store, AS_OF)
    after = sqlite3.connect(db).execute(query).fetchall()

    assert before == after


def test_the_app_db_is_opened_read_only(M):
    """Even a bug cannot write: the connection is a read-only URI."""
    src = Path(M.__file__).read_text(encoding="utf-8")
    assert src.count("mode=ro") >= 2


def test_module_reaches_no_broker_scheduler_or_manifest(M):
    """Static boundary: nothing in this module may dispatch a broker request,
    enable a scheduler, or create an activation manifest."""
    src = Path(M.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "alpaca",
        "OrderRouter",
        "scheduler_enabled",
        "activation_manifest",
        "requests.post",
        "httpx.post",
    ):
        assert forbidden not in src, f"factor_refresh must not reference {forbidden}"


# --------------------------------------------- schema contract vs the real DB


def test_held_symbols_query_uses_the_real_column_name():
    """Regression: 2026-08-04 production recovery aborted with
    "no such column: sym.symbol". The query said `sym.symbol`; the database has
    `symbols.ticker`. The unit test passed anyway because its fixture had invented
    a `symbol` column — the test agreed with the code and both disagreed with
    production. Pin the query against the ORM, which is the source of truth."""
    src = _MODULE.read_text(encoding="utf-8")
    assert "SELECT DISTINCT sym.ticker" in src, "held_symbols must select symbols.ticker"
    assert "SELECT DISTINCT sym.symbol" not in src, "symbols has no `symbol` column"


def test_fixture_schema_matches_the_orm_model():
    """The fixture must mirror app/db/models/symbol.py. If the model gains or
    renames a column this fails here rather than in production."""
    model = (_REPO_ROOT / "apps" / "backend" / "app" / "db" / "models" / "symbol.py").read_text(
        encoding="utf-8"
    )
    assert '__tablename__ = "symbols"' in model
    for col in ("id", "ticker", "exchange", "asset_class", "name", "active"):
        assert f"{col}:" in model, f"ORM lost column {col}"
        assert col in _SYMBOLS_DDL, f"fixture lost column {col}"
    assert "symbol:" not in model, "the ORM has no `symbol` column; do not reintroduce one"


def test_held_symbols_reads_against_the_real_schema(M, tmp_path):
    """End-to-end against a fixture built from the production DDL."""
    db = _app_db(tmp_path, [(9, "IDLE", ["AAA"])], positions=[("HELDNAME", 4.0), ("CLOSED", 0.0)])
    assert M.held_symbols(db) == ["HELDNAME"]


# ------------------------------------------- provider-exhaustion classification

CUT = date(2026, 7, 31)
DEAD = date(2026, 6, 12)


def _ev(**over):
    """Well-formed exhaustion evidence for a genuinely dead symbol."""
    ev = {
        "symbol": "SATS",
        "requested": True,
        "request_status": "ok",
        "provider_rows_after_live_frontier": 0,
        "corroboration": {
            "source": "alpaca",
            "last_date": "2026-06-23",
            "control_symbol": "AAPL",
            "control_last_date": "2026-08-04",
        },
    }
    ev.update(over)
    return ev


def _classify(M, **over):
    kw = {
        "live_last": DEAD,
        "stage_last": DEAD,
        "cutoff": CUT,
        "evidence": _ev(),
        "held_qty": 0,
        "open_orders": 0,
        "registered_in": [],
    }
    kw.update(over)
    return M.classify_stale_symbol("SATS", **kw)


def test_dead_symbol_fully_evidenced_is_provider_exhausted(M):
    """The SATS shape: requested, request OK, no newer rows, frontier unmoved,
    an independent source also stops, its control is current, and the name is not
    operationally required."""
    verdict, reason = _classify(M)
    assert verdict == M.PROVIDER_EXHAUSTED
    assert "ceased trading" in reason


def test_current_symbol_is_fresh_and_never_exhausted(M):
    """AAPL-style control: a name inside tolerance is FRESH regardless of evidence."""
    verdict, _ = _classify(M, stage_last=date(2026, 8, 4), evidence=None)
    assert verdict == M.FRESH


@pytest.mark.parametrize(
    ("over", "because"),
    [
        ({"evidence": None}, "no exhaustion evidence"),
        ({"evidence": _ev(requested=False)}, "was not requested"),
        ({"evidence": _ev(request_status="timeout")}, "request status"),
        ({"evidence": _ev(request_status="error")}, "request status"),
        ({"evidence": _ev(provider_rows_after_live_frontier=None)}, "not reported"),
        ({"evidence": _ev(provider_rows_after_live_frontier=14)}, "ingestion missed them"),
        ({"evidence": _ev(symbol="OTHER")}, "symbol mismatch"),
        ({"evidence": _ev(corroboration={})}, "corroboration missing"),
        (
            {
                "evidence": _ev(
                    corroboration={
                        "source": "alpaca",
                        "last_date": "2026-06-23",
                        "control_symbol": "AAPL",
                        "control_last_date": "2026-06-01",
                    }
                )
            },
            "control is not current",
        ),
        (
            {
                "evidence": _ev(
                    corroboration={
                        "source": "alpaca",
                        "last_date": "2026-08-04",
                        "control_symbol": "AAPL",
                        "control_last_date": "2026-08-04",
                    }
                )
            },
            "coverage regression, not exhaustion",
        ),
        ({"held_qty": 12.0}, "no proven alternate price source"),
        ({"open_orders": 1}, "no proven alternate price source"),
        ({"registered_in": ["9:IDLE"]}, "no alternate source"),
        ({"stage_last": date(2026, 7, 20)}, "!= live"),
        ({"live_last": None}, "!= live"),
    ],
)
def test_anything_unproven_is_failed_not_exhausted(M, over, because):
    """Every path that is not positively proven must fail closed. 'The provider
    returned nothing newer' equally describes an outage, a malformed response, an
    omitted request or an ingestion bug — none of which are a dead instrument."""
    verdict, reason = _classify(M, **over)
    assert verdict == M.FAILED_OR_UNEXPLAINED, f"expected fail-closed, got {verdict}: {reason}"
    assert because in reason


def test_held_exhausted_symbol_is_fatal_even_with_perfect_evidence(M):
    """A provider-exhausted HELD name still needs a valuation and exit path. The
    instrument is dead everywhere, so no alternate source can price it."""
    verdict, reason = _classify(M, held_qty=100.0)
    assert verdict == M.FAILED_OR_UNEXPLAINED
    assert "no proven alternate price source" in reason


def _etf_ev(**over):
    """An ETF outside the provider's subscription: alive, priced elsewhere."""
    ev = _ev(symbol="GLD")
    ev["corroboration"] = {
        "source": "alpaca",
        "last_date": "2026-08-04",
        "control_symbol": "AAPL",
        "control_last_date": "2026-08-04",
    }
    ev.update(over)
    return ev


def test_uncovered_etf_with_no_provider_history_is_not_covered(M):
    """The nine cross-asset ETFs: never in SEP, but trading normally and priced by
    Alpaca. Not exhausted — the instrument is alive; the provider simply does not
    carry it."""
    verdict, reason = M.classify_stale_symbol(
        "GLD",
        live_last=None,
        stage_last=None,
        cutoff=CUT,
        evidence=_etf_ev(),
        held_qty=0,
        open_orders=0,
        registered_in=[],
    )
    assert verdict == M.PROVIDER_NOT_COVERED
    assert "outside provider coverage" in reason


def test_held_uncovered_etf_is_allowed_because_alternate_source_prices_it(M):
    """Condition 8: a held name is acceptable when a separate price source is
    proven. Several of the nine ETFs are held and priced via Alpaca daily bars."""
    verdict, _ = M.classify_stale_symbol(
        "GLD",
        live_last=None,
        stage_last=None,
        cutoff=CUT,
        evidence=_etf_ev(),
        held_qty=250.0,
        open_orders=0,
        registered_in=["9:IDLE"],
    )
    assert verdict == M.PROVIDER_NOT_COVERED


def test_provider_stopped_while_instrument_still_trades_is_a_coverage_regression(M):
    """Had provider history, provider stopped, instrument still trades elsewhere.
    That is a coverage change worth looking at, never a silent pass."""
    verdict, reason = M.classify_stale_symbol(
        "XYZ",
        live_last=DEAD,
        stage_last=DEAD,
        cutoff=CUT,
        evidence=_etf_ev(symbol="XYZ"),
        held_qty=0,
        open_orders=0,
        registered_in=[],
    )
    assert verdict == M.FAILED_OR_UNEXPLAINED
    assert "coverage regression" in reason


def test_effective_last_uses_the_earlier_of_sep_and_lastpricedate(M, tmp_path):
    """A name with FRESH sep but a lagging lastpricedate is still excluded from the
    ranking pool, so it must not read as fresh. This is the SATS-class gate."""
    store = _store(
        tmp_path,
        _bars("FRESHSEP", 1e9),
        tickers=[("FRESHSEP", date(2026, 6, 12))],
    )
    st = M.per_name_staleness(store, ["FRESHSEP"])
    assert st["sep_max_by_symbol"]["FRESHSEP"] == str(AS_OF)
    assert st["effective_last_by_symbol"]["FRESHSEP"] == "2026-06-12"
    assert st["lastpricedate_stale"] == ["FRESHSEP"]


def test_classification_is_pure(M):
    """No store, provider or credential reachable from the classifier."""
    import inspect

    src = inspect.getsource(M.classify_stale_symbol)
    for banned in ("duckdb", "sqlite3", "connect(", "requests", "httpx", "os.environ"):
        assert banned not in src, f"classifier must stay pure; found {banned}"


def test_sats_is_not_hard_coded_anywhere(M):
    """The mechanism must generalise to future mergers, delistings and ticker
    changes — SATS is a fixture, not an exception list."""
    src = _MODULE.read_text(encoding="utf-8")
    assert "SATS" not in src
