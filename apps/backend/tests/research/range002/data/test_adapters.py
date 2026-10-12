"""Snapshot manifest, store-backed PIT adapter and minute-bar loader on SYNTHETIC fixtures.

DuckDB / Parquet files are built in tmp_path. Nothing here is vendor data and no number
describes any real store; these tests prove structural behaviour (fail-closed provenance,
identity attribution by interval, collapsed-grain disclosure, capability and range gating,
conservative minute classification).
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

import duckdb
import pytest

from app.research.range002.data.bar_loader import load_session, load_sessions, volume_reconciles
from app.research.range002.data.manifest import (
    MANIFEST_SCHEMA,
    ManifestError,
    parse_snapshot_manifest,
    verify_snapshot_files,
)
from app.research.range002.data.pit_universe import (
    BASIS_SPLIT_ADJUSTED,
    NO_DECISION_DAY_PRINT,
    NOT_COMMON_STOCK,
    UniverseParams,
)
from app.research.range002.data.store_adapter import (
    SnapshotError,
    build_month_from_store,
    load_identity_records,
    open_snapshot,
)
from app.research.range002.governance.errors import InvalidCapabilityError
from app.research.range002.screen.errors import DataDefectError
from app.research.range002.screen.params import extract_params
from app.research.range002.spec.hashing import file_sha256
from app.research.range002.spec.loader import parse_draft
from tests.research.range002.governance.conftest import (
    synthetic_manifest,  # noqa: F401  (autouse manifest seam)
)
from tests.research.range002.screen.conftest import make_capability, synth_payload

COMMON = "Domestic Common Stock"
PARAMS = UniverseParams(
    n=3, adv_window=5, min_price=10.0, basis=BASIS_SPLIT_ADJUSTED,
    category_map=(COMMON,), intraday_basis="raw",
)  # fmt: skip
SESSIONS = [date(2026, 2, 23) + timedelta(days=i) for i in range(5)]  # Mon..Fri
MONTH = date(2026, 3, 2)


def _write_parquet_snapshot(root: Path) -> None:
    con = duckdb.connect(":memory:")
    con.execute(
        'CREATE TABLE tickers("table" VARCHAR, permaticker VARCHAR, ticker VARCHAR, category VARCHAR,'
        " isdelisted VARCHAR, firstpricedate DATE, lastpricedate DATE)"
    )
    con.execute(
        f"""INSERT INTO tickers VALUES
        ('SEP','P1','BIG','{COMMON}','N','2010-01-04','2026-02-27'),
        ('SF1','P1','BIG','{COMMON}','N','2012-01-04','2026-02-27'),
        ('SEP','P2','MID','{COMMON}','N','2010-01-04','2026-02-27'),
        ('SEP','P3','DEAD','{COMMON}','Y','2012-01-03','2026-06-01'),
        ('SEP','P4','XYZ','{COMMON}','Y','2010-01-04','2026-01-10'),
        ('SEP','P5','XYZ','{COMMON}','N','2026-02-01','2026-02-27'),
        ('SEP','P6','ETF1','ETF','N','2010-01-04','2026-02-27')"""
    )
    con.execute(
        "CREATE TABLE sep(ticker VARCHAR, date DATE, close DOUBLE, closeunadj DOUBLE, volume DOUBLE)"
    )
    for tick, px, vol in [
        ("BIG", 100.0, 1_000_000),
        ("MID", 50.0, 400_000),
        ("DEAD", 20.0, 900_000),
        ("XYZ", 30.0, 700_000),
        ("ETF1", 200.0, 5_000_000),
        ("GHOST", 40.0, 600_000),  # no identity record at all
    ]:
        for d in SESSIONS:
            con.execute("INSERT INTO sep VALUES (?, ?, ?, ?, ?)", [tick, d, px, px, vol])
    con.execute(
        "CREATE TABLE actions(date DATE, action VARCHAR, ticker VARCHAR, contraticker VARCHAR)"
    )
    for t in ("tickers", "sep", "actions"):
        con.execute(f"COPY {t} TO '{(root / (t + '.parquet')).as_posix()}' (FORMAT PARQUET)")
    con.close()


@pytest.fixture
def cap(tmp_path: Path) -> object:
    return make_capability(tmp_path, synth_payload())[0]


@pytest.fixture
def snap(tmp_path: Path) -> Path:
    root = tmp_path / "snap"
    root.mkdir()
    _write_parquet_snapshot(root)
    return root


def _manifest(root: Path, *, consistent: bool = True, drop_col: str | None = None) -> str:
    def cols(name: str) -> list[str]:
        c = duckdb.connect(":memory:")
        names = [
            r[0]
            for r in c.execute(
                f"SELECT column_name FROM (DESCRIBE SELECT * FROM read_parquet('{(root / (name + '.parquet')).as_posix()}'))"
            ).fetchall()
        ]
        return [x for x in names if x != drop_col]

    tables = {}
    for name in ("tickers", "sep", "actions"):
        f = root / f"{name}.parquet"
        tables[name] = {
            "rows": 1,
            "min_date": None,
            "max_date": None,
            "columns": cols(name),
            "files": [{"path": f.name, "sha256": file_sha256(f)}],
        }
    return json.dumps(
        {
            "schema": MANIFEST_SCHEMA,
            "source": "synthetic",
            "extracted_at_utc": "2026-10-12T00:00:00Z",
            "method": "EXPORT DATABASE (PARQUET)",
            "cross_table_consistent": consistent,
            "consistency_basis": "single read transaction",
            "tables": tables,
        }
    )


# --- manifest -------------------------------------------------------------------------------


def test_manifest_verifies_and_fails_closed(snap: Path) -> None:
    good = parse_snapshot_manifest(_manifest(snap))
    assert verify_snapshot_files(good, snap).ok

    assert not verify_snapshot_files(
        parse_snapshot_manifest(_manifest(snap, consistent=False)), snap
    ).ok
    missing = verify_snapshot_files(
        parse_snapshot_manifest(_manifest(snap, drop_col="closeunadj")), snap
    )
    assert any("closeunadj" in d for d in missing.defects)

    (snap / "sep.parquet").write_bytes(b"tampered")
    tampered = verify_snapshot_files(good, snap)
    assert any("checksum mismatch" in d for d in tampered.defects)

    for bad in ("not json", json.dumps({"schema": "other"})):
        with pytest.raises(ManifestError):
            parse_snapshot_manifest(bad)


# --- store-backed PIT -----------------------------------------------------------------------


def test_month_from_parquet_attributes_reused_ticker_by_interval(snap: Path, cap: object) -> None:
    con = open_snapshot(snap)
    build = build_month_from_store(
        cap,
        con,
        MONTH,
        PARAMS,
        table_filter="SEP",
        lookback_calendar_days=14,
        raw_vendor_rows_attested=False,
        exploratory_scope_amendment_id=None,
    )
    u = build.universe
    assert build.universe.decision_day == date(2026, 2, 27)
    # XYZ's prices in the window belong to the NEW issuer P5 (old issuer P4 ended 2026-01-10)
    assert [m.permaticker for m in u.members] == ["P1", "P5", "P2"]
    assert next(m for m in u.members if m.permaticker == "P5").vendor_ticker == "XYZ"
    assert {e.permaticker: e.reason for e in u.excluded} == {
        "P4": NO_DECISION_DAY_PRINT,  # the OLD issuer of XYZ: in the population, no print that day
        "P6": NOT_COMMON_STOCK,
    }
    assert u.below_cut == 1  # DEAD (delisted later) ranks 4th: cut, not dropped for delisting
    assert build.observations.unattributed_rows == len(SESSIONS)  # GHOST: reported, not kept
    assert build.identity.one_row_per_ticker is False  # XYZ appears twice: reuse is observable
    assert u.population == len(u.members) + u.below_cut + len(u.excluded)


def test_table_filter_is_required_when_the_vendor_table_column_exists(snap: Path) -> None:
    con = open_snapshot(snap)
    with pytest.raises(SnapshotError):
        load_identity_records(con, table_filter=None)


def test_collapsed_grain_is_disclosed_not_read_as_no_reuse(tmp_path: Path) -> None:
    path = tmp_path / "collapsed.duckdb"
    c = duckdb.connect(str(path))
    c.execute(
        "CREATE TABLE tickers(permaticker VARCHAR, ticker VARCHAR, category VARCHAR, isdelisted BOOLEAN, firstpricedate DATE, lastpricedate DATE)"
    )
    c.execute(
        "INSERT INTO tickers VALUES ('P1','AAA','Domestic Common Stock',false,'2010-01-04','2026-02-27')"
    )
    c.execute(
        "CREATE TABLE sep(ticker VARCHAR, date DATE, close DOUBLE, closeunadj DOUBLE, volume DOUBLE)"
    )
    c.execute(
        "CREATE TABLE actions(date DATE, action VARCHAR, ticker VARCHAR, contraticker VARCHAR)"
    )
    c.close()
    load = load_identity_records(open_snapshot(path), table_filter=None)
    assert load.one_row_per_ticker is True


def test_snapshot_missing_a_required_column_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "bad.duckdb"
    c = duckdb.connect(str(path))
    c.execute("CREATE TABLE tickers(ticker VARCHAR)")
    c.execute("CREATE TABLE sep(ticker VARCHAR, date DATE)")
    c.execute("CREATE TABLE actions(date DATE)")
    c.close()
    with pytest.raises(SnapshotError):
        open_snapshot(path)


def test_value_reading_entry_points_need_a_capability_and_stay_in_range(
    snap: Path, cap: object
) -> None:
    con = open_snapshot(snap)
    with pytest.raises(InvalidCapabilityError):
        build_month_from_store(
            None,
            con,
            MONTH,
            PARAMS,
            table_filter="SEP",
            lookback_calendar_days=14,
            raw_vendor_rows_attested=False,
            exploratory_scope_amendment_id=None,
        )
    with pytest.raises(DataDefectError):  # 2025 is outside the authorised range
        build_month_from_store(
            cap,
            con,
            date(2025, 12, 1),
            PARAMS,
            table_filter="SEP",
            lookback_calendar_days=14,
            raw_vendor_rows_attested=False,
            exploratory_scope_amendment_id=None,
        )


# --- minute-bar loader ----------------------------------------------------------------------

DAY = date(2026, 3, 2)  # EST: 09:30 ET == 14:30 UTC


def _minute_store(tmp_path: Path, *, skip: time | None = time(10, 15), dup: bool = False) -> object:
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE minute_bars(symbol VARCHAR, ts TIMESTAMP, open DOUBLE, high DOUBLE,"
        " low DOUBLE, close DOUBLE, volume BIGINT, basis VARCHAR)"
    )
    t = datetime(2026, 3, 2, 14, 30)
    while t < datetime(2026, 3, 2, 21, 0):  # 16:00 ET exclusive
        et = (t - timedelta(hours=5)).time()
        if et != skip:
            con.execute(
                "INSERT INTO minute_bars VALUES ('AAA', ?, 10, 10.1, 9.9, 10, 100, 'raw')", [t]
            )
        t += timedelta(minutes=1)
    if dup:
        con.execute(
            "INSERT INTO minute_bars VALUES ('AAA', ?, 10, 10, 10, 10, 1, 'raw')",
            [datetime(2026, 3, 2, 14, 30)],
        )
    return con


@pytest.fixture
def params(tmp_path: Path, cap: object):  # type: ignore[no-untyped-def]
    return extract_params(cap, parse_draft(synth_payload()))


def _kw(params, **over):  # type: ignore[no-untyped-def]
    base = {
        "permaticker": "P-AAA",
        "source_feed": params.feed,
        "source_ts_convention": params.bar_timestamp_convention,
        "no_trade_evidence": frozenset(),
        "halt_minutes": frozenset(),
    }
    base.update(over)
    return base


def test_missing_minute_is_a_gap_unless_interval_evidence_names_it(
    tmp_path: Path, cap: object, params
) -> None:  # type: ignore[no-untyped-def]
    con = _minute_store(tmp_path)
    s = load_session(cap, con, params, "AAA", DAY, time(16, 0), **_kw(params))
    assert s is not None and s.bars[0].start == time(9, 30) and s.bars[-1].start == time(15, 59)
    assert s.gap_minutes == frozenset({time(10, 15)})  # no evidence -> unresolved DATA_GAP
    # a daily total that reconciles exactly must NOT clear the gap: it cannot place the minute
    assert volume_reconciles(cap, s, float(sum(b.volume for b in s.bars)), 0.0) is True
    assert s.gap_minutes == frozenset({time(10, 15)})
    # only interval-level evidence for that exact minute makes it a no-trade minute
    ok = load_session(
        cap, con, params, "AAA", DAY, time(16, 0),
        **_kw(params, no_trade_evidence=frozenset({time(10, 15)})),
    )  # fmt: skip
    assert ok is not None and ok.gap_minutes == frozenset()
    # evidence for a minute that HAS a bar is contradictory, never silently accepted
    with pytest.raises(DataDefectError):
        load_session(
            cap, con, params, "AAA", DAY, time(16, 0),
            **_kw(params, no_trade_evidence=frozenset({time(9, 30)})),
        )  # fmt: skip
    assert not any(b.start == time(10, 15) for b in s.bars)  # nothing fabricated


def test_loader_refuses_wrong_feed_convention_duplicates_and_range(
    tmp_path: Path, cap: object, params
) -> None:  # type: ignore[no-untyped-def]
    con = _minute_store(tmp_path)
    with pytest.raises(DataDefectError):
        load_session(
            cap, con, params, "AAA", DAY, time(16, 0), **_kw(params, source_feed="iex-other")
        )
    with pytest.raises(DataDefectError):
        load_session(
            cap, con, params, "AAA", DAY, time(16, 0), **_kw(params, source_ts_convention="end")
        )
    with pytest.raises(DataDefectError):
        load_session(cap, con, params, "AAA", date(2025, 3, 3), time(16, 0), **_kw(params))
    with pytest.raises(DataDefectError):
        load_session(
            cap, _minute_store(tmp_path, dup=True), params, "AAA", DAY, time(16, 0), **_kw(params)
        )
    with pytest.raises(InvalidCapabilityError):
        load_session(None, con, params, "AAA", DAY, time(16, 0), **_kw(params))


def test_load_sessions_lists_every_missing_symbol_day(tmp_path: Path, cap: object, params) -> None:  # type: ignore[no-untyped-def]
    con = _minute_store(tmp_path)
    sessions, missing = load_sessions(
        cap,
        con,
        params,
        [("AAA", DAY), ("BBB", DAY)],
        {DAY: time(16, 0)},
        source_feed=params.feed,
        source_ts_convention=params.bar_timestamp_convention,
        no_trade_evidence={},
        permaticker_of={("AAA", DAY): "P-AAA", ("BBB", DAY): "P-BBB"},
    )
    assert [s.symbol for s in sessions] == ["AAA"] and missing == (("BBB", DAY),)
    with pytest.raises(DataDefectError):  # a day absent from the calendar is not silently skipped
        load_sessions(
            cap,
            con,
            params,
            [("AAA", date(2026, 3, 3))],
            {DAY: time(16, 0)},
            source_feed=params.feed,
            source_ts_convention=params.bar_timestamp_convention,
            no_trade_evidence={},
            permaticker_of={("AAA", date(2026, 3, 3)): "P-AAA"},
        )


def _collapsed_store(tmp_path: Path) -> Path:
    """The shape of the live store: one row per ticker, no vendor `table` column."""
    path = tmp_path / "live_shape.duckdb"
    c = duckdb.connect(str(path))
    c.execute(
        "CREATE TABLE tickers(permaticker VARCHAR, ticker VARCHAR, category VARCHAR, isdelisted BOOLEAN,"
        " firstpricedate DATE, lastpricedate DATE)"
    )
    c.execute(
        f"INSERT INTO tickers VALUES ('P1','BIG','{COMMON}',false,'2010-01-04','2026-02-27'),"
        f"('P2','MID','{COMMON}',false,'2010-01-04','2026-02-27')"
    )
    c.execute(
        "CREATE TABLE sep(ticker VARCHAR, date DATE, close DOUBLE, closeunadj DOUBLE, volume DOUBLE)"
    )
    for t, px, v in (("BIG", 100.0, 1_000_000), ("MID", 50.0, 400_000)):
        for d in SESSIONS:
            c.execute("INSERT INTO sep VALUES (?, ?, ?, ?, ?)", [t, d, px, px, v])
    c.execute(
        "CREATE TABLE actions(date DATE, action VARCHAR, ticker VARCHAR, contraticker VARCHAR)"
    )
    c.close()
    return path


def _build(con, cap, **kw):  # type: ignore[no-untyped-def]
    return build_month_from_store(
        cap, con, MONTH, PARAMS, table_filter=None,
        lookback_calendar_days=14, **kw,
    )  # fmt: skip


def test_collapsed_ticker_history_blocks_a_pit_build(tmp_path: Path, cap: object) -> None:
    con = open_snapshot(_collapsed_store(tmp_path))
    with pytest.raises(SnapshotError, match="DATA-INTEGRITY BLOCKER"):
        _build(con, cap, raw_vendor_rows_attested=False, exploratory_scope_amendment_id=None)


def test_restricted_build_is_labelled_exploratory_not_the_pit_test(
    tmp_path: Path, cap: object
) -> None:
    con = open_snapshot(_collapsed_store(tmp_path))
    built = _build(
        con, cap, raw_vendor_rows_attested=False, exploratory_scope_amendment_id="AMEND-7"
    )
    assert built.scope == "EXPLORATORY_RESTRICTED:AMEND-7" and built.scope != "PIT_FULL"
    attested = _build(con, cap, raw_vendor_rows_attested=True, exploratory_scope_amendment_id=None)
    assert attested.scope == "PIT_FULL"  # only on an explicit attestation of raw vendor rows
