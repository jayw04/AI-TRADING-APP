"""EAD Phase 0A — corporate_events schema migration + backfill invariance + eligible PIT read.

Covers ADR 0037 Decision 8: the hybrid schema converges on open, the compat view works, the
Form-4 backfill is inert for the legacy insider read (``events_asof`` unchanged), and the new
``events_asof_eligible`` anchors on ``available_time`` with the ``research_eligible`` gate.
All offline (temp DuckDB); no box / live stack.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from app.altdata.events.store import EAD_COLUMN_DDL, CorporateEvent, EventStore

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_event_store_ead.py"
_spec = importlib.util.spec_from_file_location("migrate_event_store_ead", _SCRIPT)
_mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mig)
migrate_event_store = _mig.migrate_event_store


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def _make_legacy_db(path: Path, rows: list[tuple[str, str, str]]) -> None:
    """Create a pre-EAD (10-column) corporate_events table with insider rows, inserted the way
    the old positional code did — the starting point a real migration meets."""
    con = duckdb.connect(str(path))
    con.execute(
        """
        CREATE TABLE corporate_events (
            event_id VARCHAR PRIMARY KEY, cik BIGINT, ticker VARCHAR, event_type VARCHAR,
            source VARCHAR, accession VARCHAR, filed_at TIMESTAMP, event_date DATE,
            payload JSON, ingested_at TIMESTAMP
        )
        """
    )
    for acc, ticker, filed in rows:
        f = _dt(filed).replace(tzinfo=None)
        con.execute(
            "INSERT INTO corporate_events VALUES (?,?,?,?,?,?,?,?,?,?)",
            [f"{acc}:insider_buy", 320193, ticker, "insider_buy", "sec_edgar_form4", acc,
             f, f.date(), json.dumps({"buy_value": 150500.0, "is_officer": True}), f],
        )
    con.close()


_ROWS = [("acc-1", "AAPL", "2026-06-10T18:30:00"),
         ("acc-2", "MSFT", "2026-06-11T18:30:00"),
         ("acc-3", "AAPL", "2026-06-15T18:30:00")]


# --- fresh DB already carries the EAD schema -------------------------------------------------

def test_fresh_store_has_ead_columns_and_view(tmp_path):
    store = EventStore(str(tmp_path / "ev.duckdb"))
    cols = {r[0] for r in store._con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'corporate_events'").fetchall()}
    for name, _ in EAD_COLUMN_DDL:
        assert name in cols
    # compat view exists and computes pit_time = filed_at when available_time is NULL
    store.upsert_events([CorporateEvent(
        cik=1, ticker="AAPL", event_type="insider_buy", source="sec_edgar_form4",
        accession="a", filed_at=_dt("2026-06-10T12:00:00"), event_date=date(2026, 6, 10))])
    row = store._con.execute(
        "SELECT CAST(pit_time AS DATE) FROM corporate_events_pit").fetchone()
    assert str(row[0]) == "2026-06-10"
    store.close()


# --- migration converges a legacy DB (idempotently) ------------------------------------------

def test_migration_adds_columns_and_is_idempotent(tmp_path):
    path = tmp_path / "legacy.duckdb"
    _make_legacy_db(path, _ROWS)

    rep = migrate_event_store(path, backup=False)
    assert set(rep["columns_added"]) == {n for n, _ in EAD_COLUMN_DDL}
    assert rep["backfill"]["available_time_populated"] == 3
    assert rep["backfill"]["eligible_before"] == 0
    assert rep["backfill"]["eligible_after"] == 3          # all three have a ticker

    # second run is a no-op on columns (idempotent) and the backfill is stable
    rep2 = migrate_event_store(path, backup=False)
    assert rep2["columns_added"] == []
    assert rep2["backfill"]["eligible_after"] == 3


def test_migration_backup_is_written(tmp_path):
    path = tmp_path / "legacy.duckdb"
    _make_legacy_db(path, _ROWS)
    rep = migrate_event_store(path, backup=True)
    assert rep["backup_path"] is not None
    assert Path(rep["backup_path"]).exists()


# --- the core invariance guarantee: INSIDER-001's read is unchanged --------------------------

def test_backfill_is_inert_for_legacy_events_asof(tmp_path):
    path = tmp_path / "legacy.duckdb"
    _make_legacy_db(path, _ROWS)

    # snapshot the legacy read BEFORE migration
    with EventStore(str(path), read_only=True) as ro:
        before = ro.events_asof(date(2026, 6, 30), event_type="insider_buy")

    migrate_event_store(path, backup=False)

    # …and AFTER. events_asof projects only the legacy 8 columns, so the objects are identical.
    with EventStore(str(path), read_only=True) as ro:
        after = ro.events_asof(date(2026, 6, 30), event_type="insider_buy")

    assert before == after                                  # frozen dataclass equality
    assert [e.accession for e in after] == ["acc-1", "acc-2", "acc-3"]
    assert all(e.available_time is None for e in after)     # legacy read never surfaces it


# --- events_asof_eligible: available_time anchor + research_eligible gate ---------------------

def _eligible_ev(acc, ticker, filed, avail, *, eligible=True) -> CorporateEvent:
    return CorporateEvent(
        cik=1, ticker=ticker, event_type="gov_contract_award", source="quiver",
        accession=acc, filed_at=_dt(filed), event_date=_dt(filed).date(),
        payload={"amount": 1_000_000.0}, available_time=_dt(avail),
        resolved_security_id="CIK0000000001", provider_dataset="government_contracts",
        source_event_id=f"q-{acc}", research_eligible=eligible)


def test_events_asof_eligible_anchors_on_available_time(tmp_path):
    store = EventStore(str(tmp_path / "ev.duckdb"))
    store.upsert_events([
        # filed early but available late -> excluded as-of a date between the two
        _eligible_ev("c1", "LMT", "2026-06-10T12:00:00", "2026-06-20T12:00:00"),
        # available early -> included
        _eligible_ev("c2", "RTX", "2026-06-05T12:00:00", "2026-06-08T12:00:00"),
        # available early but NOT research_eligible -> excluded
        _eligible_ev("c3", "GD", "2026-06-01T12:00:00", "2026-06-02T12:00:00", eligible=False),
    ])

    got = store.events_asof_eligible(date(2026, 6, 15), event_type="gov_contract_award")
    accs = [e.accession for e in got]
    assert accs == ["c2"]                                   # only the eligible, available-by-15th one
    assert got[0].resolved_security_id == "CIK0000000001"   # EAD columns round-trip
    assert got[0].provider_dataset == "government_contracts"
    assert got[0].research_eligible is True

    # the legacy read is anchored on filed_at and ignores eligibility -> sees c1 and c2 (not the
    # future one is c1 filed 6-10 <= 6-15; c3 filed 6-1) — proving the two reads differ by design
    legacy = store.events_asof(date(2026, 6, 15), event_type="gov_contract_award")
    assert {e.accession for e in legacy} == {"c1", "c2", "c3"}
    store.close()


def test_eligible_read_excludes_forward_dated_and_hidden_rows(tmp_path):
    store = EventStore(str(tmp_path / "ev.duckdb"))
    store.upsert_events([_eligible_ev("c1", "LMT", "2026-06-10T12:00:00", "2026-06-20T12:00:00")])
    # nothing is eligible-and-available on the 15th
    assert store.events_asof_eligible(date(2026, 6, 15)) == []
    # on/after the availability date it appears
    assert [e.accession for e in store.events_asof_eligible(date(2026, 6, 20))] == ["c1"]
    store.close()
