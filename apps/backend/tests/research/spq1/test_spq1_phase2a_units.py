"""SPQ-1 Phase-2A DB-independent unit tests (no registered DB required; always run)."""
from __future__ import annotations

import duckdb
import numpy as np
import pytest

from app.research.mr002.spq1.adapters import DEV_END, DEV_START, normalize_utc_iso
from app.research.mr002.spq1.adapters.calendar_adapter import date_to_ordinal
from app.research.mr002.spq1.adapters.liquidity_adapter import trailing_adv_from_series
from app.research.mr002.spq1.adapters.manifests import (
    build_development_manifest,
    build_input_manifest,
)
from app.research.mr002.spq1.adapters.partition_guard import OpenedObjectLedger, PartitionGuard
from app.research.mr002.spq1.adapters.price_adapter import load_price_series
from app.research.mr002.spq1.calendar import RegisteredCalendar
from app.research.mr002.spq1.refusals import SignalRefusal


def _refuse(fn, code):
    with pytest.raises(SignalRefusal) as e:
        fn()
    assert e.value.code == code


def test_normalize_utc_iso_variants():
    assert normalize_utc_iso("2012-01-25 15:42:11-06:00") == "2012-01-25T21:42:11Z"
    assert normalize_utc_iso("2015-06-15T00:00:00Z") == "2015-06-15T00:00:00Z"
    assert normalize_utc_iso("2015-06-15") == "2015-06-15T00:00:00Z"     # date-only
    assert normalize_utc_iso("2015-06-15 09:30:00") == "2015-06-15T09:30:00Z"  # naive -> UTC


def test_date_to_ordinal():
    cal = RegisteredCalendar(tuple(f"2013-01-{d:02d}" for d in range(1, 11)))
    assert date_to_ordinal(cal, "2013-01-01") == 0
    assert date_to_ordinal(cal, "2010-01-01") == 0            # pre-window clamps to 0
    assert date_to_ordinal(cal, "2013-01-05") == 4
    assert date_to_ordinal(cal, "2013-01-04T12:00") == 3      # between sessions -> at/before
    assert date_to_ordinal(cal, "2099-01-01") == 9            # post-window clamps to last


def test_manifests_build_and_determinism():
    recs = [{"b": 2}, {"a": 1}]
    m1 = build_input_manifest("T", recs)
    m2 = build_input_manifest("T", list(reversed(recs)))
    assert m1["manifest_sha256"] == m2["manifest_sha256"]     # order-independent
    dev = build_development_manifest(["a", "b"], "guard-id", "snap-id")
    assert dev.development_start == DEV_START and dev.development_end == DEV_END
    assert len(dev.identity) == 64


def test_guard_inverted_range_and_ledger():
    led = OpenedObjectLedger()
    g = PartitionGuard(frozenset({"apps/backend/data/x.duckdb"}), led)
    _refuse(lambda: g.guard_range("2019-01-01", "2013-01-01"),
            "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS")
    g.guarded_read("apps/backend/data/x.duckdb", DEV_START, DEV_END, "unit", "reader", 3)
    assert led.entries[0]["partition"] == "DEVELOPMENT" and led.entries[0]["result_row_count"] == 3


def test_liquidity_raw_pair_guard_rejects_adjusted():
    n = 60
    series = {
        "closeunadj": np.full(n, 10.0), "close": np.full(n, 10.0),   # identical -> not raw
        "volume": np.full(n, 1000.0), "closeadj": np.full(n, 9.0),
    }
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
    cal = RegisteredCalendar(("2013-01-02", "2013-01-03"))
    _refuse(lambda: load_price_series(ro, "Z", cal), "INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE")
    ro.close()
