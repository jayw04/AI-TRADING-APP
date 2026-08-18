"""Synthetic fail-closed qualification for the governed Parquet -> DuckDB materializer.

Hermetic and AWS-free: every read goes through the governed FixtureReader, so no credential, no
network and no sealed byte is involved. All fixtures are invented.

The suite proves the materializer REFUSES rather than repairs: a bad checksum, a missing or
unregistered table, an absent required column, an unpinned read, and -- most importantly -- any
true interval overlap in the three first-match-wins registries, because zero-overlap is exactly
what makes the existing first-match implementation determinate.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import os

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.research.mr002.phase3b.readers import FixtureReader, PinnedObject, PinnedReadRefused
from app.research.mr002.phase3c.materialize import (
    REQUIRED_COLUMNS,
    MaterializationRefused,
    TableSource,
    materialize,
)

D = dt.date

# key prefix per table -- the 6 sealed validation objects and the 4 identity-bound reference objects
PARTITION_OF = {
    "actions": "validation", "anchors": "validation", "etf_prices": "validation",
    "prices": "validation", "sic_observations": "validation", "universe": "validation",
    "crosswalk": "reference", "sic_mapping": "reference",
    "predecessor_overrides": "reference", "security_sector_overrides": "reference",
}
SEALED = {t for t, p in PARTITION_OF.items() if p == "validation"}
REFERENCE = {t for t, p in PARTITION_OF.items() if p == "reference"}


def _rows(table: str) -> dict:
    """Minimal well-formed content for each registered table."""
    if table == "crosswalk":
        return {"permaticker": [1, 1, 2], "cik": [10, 11, 20],
                "effective_from": [None, D(2015, 1, 5), None],
                "effective_to": [D(2015, 1, 2), None, None]}
    if table == "predecessor_overrides":
        return {"permaticker": [1], "predecessor_cik": [10], "successor_cik": [11],
                "event_date": [D(2015, 1, 3)], "review_status": ["approved"]}
    if table == "security_sector_overrides":
        return {"permaticker": [1, 1], "effective_from": [None, D(2018, 10, 1)],
                "effective_to": [D(2018, 9, 28), None],
                "review_status": ["approved", "approved"], "sector_etf": ["XLY", "XLC"]}
    if table == "sic_mapping":
        return {"sic_start": [1000, 2000], "sic_end": [1999, 2999],
                "effective_from": [None, None], "effective_to": [None, None],
                "sector_etf": ["XLK", "XLF"], "mapping_confidence": ["HIGH", "HIGH"]}
    if table == "sic_observations":
        return {"cik": [10], "accepted_utc": [D(2015, 1, 1)], "sic": [1500.0]}
    if table == "anchors":
        return {"cik": [10], "session_date": [D(2015, 2, 2)],
                "availability_class": ["A"], "event_time_basis": ["B"]}
    if table == "universe":
        return {"universe_month": ["2015-01"], "ticker": ["AAA"], "permaticker": [1],
                "in_long_universe": [True], "in_short_universe": [False]}
    if table == "prices":
        return {"ticker": ["AAA"], "date": [D(2015, 1, 2)], "open": [10.0], "close": [10.5],
                "closeadj": [10.5], "volume": [1000.0]}
    if table == "etf_prices":
        return {"ticker": ["SPY"], "date": [D(2015, 1, 2)], "adjclose": [200.0]}
    if table == "actions":
        return {"ticker": ["AAA"], "date": [D(2015, 1, 2)], "action": ["split"]}
    raise AssertionError(table)


def _write(root: str, table: str, data: dict) -> PinnedObject:
    key = f"{PARTITION_OF[table]}/{table}.parquet"
    path = os.path.join(root, key.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    pq.write_table(pa.table(data), buf)
    payload = buf.getvalue()
    with open(path, "wb") as fh:
        fh.write(payload)
    return PinnedObject(bucket="synthetic", key=key, version_id=f"v-{table}",
                        sha256=hashlib.sha256(payload).hexdigest())


def _sources(root: str, overrides: dict | None = None,
             drop: str | None = None, extra: bool = False) -> list[TableSource]:
    overrides = overrides or {}
    out = []
    for table in REQUIRED_COLUMNS:
        if table == drop:
            continue
        out.append(TableSource(table, _write(root, table, overrides.get(table, _rows(table)))))
    if extra:
        PARTITION_OF["not_registered"] = "reference"
        out.append(TableSource("not_registered", _write(root, "not_registered", {"a": [1]})))
    return out


# ----------------------------------------------------------------------------- happy path

def test_materializes_ten_tables_and_reports_the_read_split(tmp_path):
    root = str(tmp_path / "fx")
    out = str(tmp_path / "m.duckdb")
    ev = materialize(_sources(root), FixtureReader(root), out)

    assert ev["objects_opened_count"] == 10
    assert ev["representation_only"] is True
    assert os.path.exists(out)

    sealed = {o["table"] for o in ev["objects_opened"] if o["partition"] == "VALIDATION"}
    reference = {o["table"] for o in ev["objects_opened"] if o["partition"] == "REFERENCE"}
    assert sealed == SEALED and len(sealed) == 6
    assert reference == REFERENCE and len(reference) == 4
    assert {"predecessor_overrides", "security_sector_overrides"} <= reference

    for o in ev["objects_opened"]:
        assert o["version_id"] and o["sha256"] and o["rows"] >= 1


def test_logical_content_identity_is_stable_and_content_sensitive(tmp_path):
    a = materialize(_sources(str(tmp_path / "a")), FixtureReader(str(tmp_path / "a")),
                    str(tmp_path / "a.duckdb"))
    b = materialize(_sources(str(tmp_path / "b")), FixtureReader(str(tmp_path / "b")),
                    str(tmp_path / "b.duckdb"))
    assert a["logical_content_identity"] == b["logical_content_identity"]

    changed = dict(_rows("prices"))
    changed["close"] = [99.0]
    c = materialize(_sources(str(tmp_path / "c"), overrides={"prices": changed}),
                    FixtureReader(str(tmp_path / "c")), str(tmp_path / "c.duckdb"))
    assert c["logical_content_identity"] != a["logical_content_identity"]


def test_disjoint_open_ended_intervals_are_not_treated_as_overlapping(tmp_path):
    """Regression: (None, 2018-09-28) and (2018-10-01, None) are DISJOINT successive intervals.

    An earlier cruder overlap test short-circuited on a None bound and reported a false positive.
    The fixture's crosswalk and overrides both use this shape, so a happy-path materialization
    passing IS the assertion.
    """
    root = str(tmp_path / "fx")
    ev = materialize(_sources(root), FixtureReader(root), str(tmp_path / "m.duckdb"))
    for t in ("crosswalk", "security_sector_overrides"):
        assert ev["determinism_preconditions"][t]["true_overlaps"] == 0


# ----------------------------------------------------------------------------- fail closed

def test_checksum_mismatch_refuses(tmp_path):
    root = str(tmp_path / "fx")
    srcs = _sources(root)
    bad = srcs[0]
    srcs[0] = TableSource(bad.table, PinnedObject(bad.obj.bucket, bad.obj.key,
                                                  bad.obj.version_id, "0" * 64))
    with pytest.raises(PinnedReadRefused):
        materialize(srcs, FixtureReader(root), str(tmp_path / "m.duckdb"))


def test_unpinned_read_refuses(tmp_path):
    root = str(tmp_path / "fx")
    srcs = _sources(root)
    o = srcs[0].obj
    srcs[0] = TableSource(srcs[0].table, PinnedObject(o.bucket, o.key, "", o.sha256))
    with pytest.raises(PinnedReadRefused):
        materialize(srcs, FixtureReader(root), str(tmp_path / "m.duckdb"))


def test_missing_table_refuses(tmp_path):
    root = str(tmp_path / "fx")
    with pytest.raises(MaterializationRefused, match="no pinned object supplied"):
        materialize(_sources(root, drop="anchors"), FixtureReader(root),
                    str(tmp_path / "m.duckdb"))


def test_unregistered_table_refuses(tmp_path):
    root = str(tmp_path / "fx")
    with pytest.raises(MaterializationRefused, match="unregistered table"):
        materialize(_sources(root, extra=True), FixtureReader(root), str(tmp_path / "m.duckdb"))


def test_missing_required_column_refuses(tmp_path):
    root = str(tmp_path / "fx")
    short = {k: v for k, v in _rows("prices").items() if k != "closeadj"}
    with pytest.raises(MaterializationRefused, match="required columns absent"):
        materialize(_sources(root, overrides={"prices": short}), FixtureReader(root),
                    str(tmp_path / "m.duckdb"))


@pytest.mark.parametrize("table,data", [
    ("crosswalk", {"permaticker": [1, 1], "cik": [10, 11],
                   "effective_from": [D(2015, 1, 1), D(2015, 1, 5)],
                   "effective_to": [D(2015, 2, 1), D(2015, 1, 20)]}),
    ("security_sector_overrides", {"permaticker": [1, 1],
                                   "effective_from": [D(2018, 1, 1), D(2018, 6, 1)],
                                   "effective_to": [D(2018, 12, 1), None],
                                   "review_status": ["approved", "approved"],
                                   "sector_etf": ["XLY", "XLC"]}),
])
def test_true_interval_overlap_refuses(tmp_path, table, data):
    """Two rows matching the same key on the same date would make first-match order-dependent."""
    root = str(tmp_path / "fx")
    with pytest.raises(MaterializationRefused, match="overlapping intervals"):
        materialize(_sources(root, overrides={table: data}), FixtureReader(root),
                    str(tmp_path / "m.duckdb"))


def test_sic_mapping_range_overlap_refuses(tmp_path):
    """sic_mapping matches on a SIC RANGE crossed with a date range; both must be disjoint."""
    root = str(tmp_path / "fx")
    data = {"sic_start": [1000, 1500], "sic_end": [1999, 2500],
            "effective_from": [None, None], "effective_to": [None, None],
            "sector_etf": ["XLK", "XLF"], "mapping_confidence": ["HIGH", "HIGH"]}
    with pytest.raises(MaterializationRefused, match="sic-range"):
        materialize(_sources(root, overrides={"sic_mapping": data}), FixtureReader(root),
                    str(tmp_path / "m.duckdb"))


def test_sic_mapping_overlapping_ranges_on_disjoint_dates_are_allowed(tmp_path):
    """Overlapping SIC ranges are fine when their DATE ranges are disjoint -- only the crossed
    product can produce two matches for one lookup."""
    root = str(tmp_path / "fx")
    data = {"sic_start": [1000, 1500], "sic_end": [1999, 2500],
            "effective_from": [None, D(2020, 1, 1)], "effective_to": [D(2019, 12, 31), None],
            "sector_etf": ["XLK", "XLF"], "mapping_confidence": ["HIGH", "HIGH"]}
    ev = materialize(_sources(root, overrides={"sic_mapping": data}), FixtureReader(root),
                     str(tmp_path / "m.duckdb"))
    assert ev["determinism_preconditions"]["sic_mapping"]["true_overlaps"] == 0
