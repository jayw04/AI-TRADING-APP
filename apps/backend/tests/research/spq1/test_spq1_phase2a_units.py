"""SPQ-1 Phase-2A DB-independent unit tests (no registered DB required; always run)."""
from __future__ import annotations

import duckdb
import numpy as np
import pytest

from app.research.mr002.spq1.adapters import DEV_END, DEV_START, normalize_utc_iso
from app.research.mr002.spq1.adapters.calendar_adapter import (
    PRE_WINDOW,
    dev_calendar_sha256,
    load_calendar,
    map_effective_session,
)
from app.research.mr002.spq1.adapters.identity_adapter import load_identity_registry
from app.research.mr002.spq1.adapters.liquidity_adapter import trailing_adv_from_series
from app.research.mr002.spq1.adapters.manifests import (
    build_development_manifest,
    build_input_manifest,
)
from app.research.mr002.spq1.adapters.partition_guard import OpenedObjectLedger, PartitionGuard
from app.research.mr002.spq1.adapters.price_adapter import load_price_series
from app.research.mr002.spq1.calendar import RegisteredCalendar
from app.research.mr002.spq1.refusals import SignalRefusal

CAL10 = RegisteredCalendar(tuple(f"2013-01-{d:02d}" for d in range(2, 12)))  # 10 sessions


def _refuse(fn, code):
    with pytest.raises(SignalRefusal) as e:
        fn()
    assert e.value.code == code, f"expected {code} got {e.value.code}"


def _crosswalk_db(tmp_path, rows, name="cw"):
    p = str(tmp_path / f"{name}.duckdb")
    con = duckdb.connect(p)
    con.execute("create table crosswalk (permaticker bigint, ticker varchar, effective_from varchar, "
                "relationship_type varchar, source_record_id varchar)")
    for r in rows:
        con.execute("insert into crosswalk values (?,?,?,?,?)", list(r))
    con.close()
    return duckdb.connect(p, read_only=True)


# ---- normalize / manifests ----
def test_normalize_utc_iso_variants():
    assert normalize_utc_iso("2012-01-25 15:42:11-06:00") == "2012-01-25T21:42:11Z"
    assert normalize_utc_iso("2015-06-15T00:00:00Z") == "2015-06-15T00:00:00Z"
    assert normalize_utc_iso("2015-06-15") == "2015-06-15T00:00:00Z"
    assert normalize_utc_iso("2015-06-15 09:30:00") == "2015-06-15T09:30:00Z"


def test_manifests_build_and_determinism():
    m1 = build_input_manifest("T", [{"b": 2}, {"a": 1}])
    m2 = build_input_manifest("T", [{"a": 1}, {"b": 2}])
    assert m1["manifest_sha256"] == m2["manifest_sha256"]
    dev = build_development_manifest(["a", "b"], "guard-id", "snap-id")
    assert dev.development_start == DEV_START and dev.development_end == DEV_END
    assert len(dev.identity) == 64


# ---- Finding 2: calendar hash ----
def test_dev_calendar_hash_serialization_stable():
    d = ("2013-01-02", "2013-01-03")
    assert dev_calendar_sha256(d) == dev_calendar_sha256(d) and len(dev_calendar_sha256(d)) == 64


def test_load_calendar_wrong_count_refused(tmp_path):
    p = str(tmp_path / "px.duckdb")
    con = duckdb.connect(p)
    con.execute("create table prices (ticker varchar, date varchar)")
    con.execute("insert into prices values ('AAPL','2013-01-02'),('AAPL','2013-01-03')")
    con.close()
    ro = duckdb.connect(p, read_only=True)
    _refuse(lambda: load_calendar(ro), "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH")  # count != 1700
    ro.close()


# ---- Finding 1: identity effective-date mapping ----
def test_map_effective_session_rules():
    assert map_effective_session(CAL10, "2010-01-01") == (0, PRE_WINDOW)      # pre-window
    assert map_effective_session(CAL10, "2013-01-05")[0] == 3                 # on session
    assert map_effective_session(CAL10, "2013-01-06T12:00")[0] == 4           # on-or-after (not before)
    _refuse(lambda: map_effective_session(CAL10, ""), "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS")
    _refuse(lambda: map_effective_session(CAL10, "None"),
            "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS")
    _refuse(lambda: map_effective_session(CAL10, "2099-01-01"),               # after window
            "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS")


def test_identity_unknown_relationship_fails_closed(tmp_path):
    con = _crosswalk_db(tmp_path, [(1, "AAA", "2013-01-05", "mystery_action", "s1")])
    _refuse(lambda: load_identity_registry(con, CAL10),
            "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS")
    con.close()


def test_identity_pre_window_and_missing_effective(tmp_path):
    con = _crosswalk_db(tmp_path, [(9, "PRE", "2000-01-01", "direct", "s")])
    reg = load_identity_registry(con, CAL10)
    assert reg.lineage["PRE"][0].source_evidence_identity.startswith("crosswalk:PRE_WINDOW")
    con.close()
    con2 = _crosswalk_db(tmp_path, [(9, "PRE", None, "direct", "s")], name="cw2")
    _refuse(lambda: load_identity_registry(con2, CAL10),
            "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS")
    con2.close()


# ---- Finding 3: opened-object ledger actual reads ----
def test_guard_authorize_then_completed_and_out_of_range(tmp_path):
    led = OpenedObjectLedger()
    g = PartitionGuard(frozenset({"apps/backend/data/x.duckdb"}), led)
    tok = g.authorize_read("apps/backend/data/x.duckdb", DEV_START, DEV_END, "u", "reader")
    assert led.entries == []            # pre-read authorization alone is NOT an opened-object proof
    # a returned row outside the authorized bounds fails closed
    _refuse(lambda: g.record_completed_read(tok, "objsha", "q", DEV_START, "2020-06-01", 5, "rh"),
            "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS")
    assert led.entries == []
    g.record_completed_read(tok, "objsha", "q", DEV_START, DEV_END, 7, "rh")
    e = led.entries[0]
    assert e["status"] == "COMPLETED" and e["result_row_count"] == 7 and e["object_sha256"] == "objsha"


def test_guard_pre_window_lower_relaxed_but_upper_enforced():
    g = PartitionGuard(frozenset({"x"}), OpenedObjectLedger())
    g.guard_range("0001-01-01", DEV_END, allow_pre_window=True)          # ok
    _refuse(lambda: g.guard_range("0001-01-01", "2024-01-01", allow_pre_window=True),
            "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS")                 # upper still enforced


# ---- liquidity / price guards ----
def test_liquidity_raw_pair_guard_rejects_adjusted():
    n = 60
    series = {"closeunadj": np.full(n, 10.0), "close": np.full(n, 10.0),
              "volume": np.full(n, 1000.0), "closeadj": np.full(n, 9.0)}
    _refuse(lambda: trailing_adv_from_series(series, 40),
            "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH")


def test_price_adapter_duplicate_row_guard(tmp_path):
    p = str(tmp_path / "tiny.duckdb")
    con = duckdb.connect(p)
    con.execute("create table prices (ticker varchar, date varchar, closeadj double, "
                "closeunadj double, close double, open double, volume double)")
    con.execute("insert into prices values ('Z','2013-01-02',1,1,1,1,1),('Z','2013-01-02',1,1,1,1,1)")
    con.close()
    ro = duckdb.connect(p, read_only=True)
    _refuse(lambda: load_price_series(ro, "Z", RegisteredCalendar(("2013-01-02", "2013-01-03"))),
            "INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE")
    ro.close()
