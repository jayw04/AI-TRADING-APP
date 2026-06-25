"""§2 data-validation gate + the store's filing-latency / PIT audit (offline)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.altdata.events.store import CorporateEvent, EventStore
from app.altdata.sec.ingest import IngestReport
from app.altdata.validate import validate


def _ev(accession: str, *, event_date: date, filed: date) -> CorporateEvent:
    return CorporateEvent(
        cik=1, ticker="AAPL", event_type="insider_buy", source="sec_edgar_form4",
        accession=accession,
        filed_at=datetime(filed.year, filed.month, filed.day, 18, 30, tzinfo=UTC),
        event_date=event_date, payload={"buy_value": 1000.0},
    )


def test_latency_audit_and_pit_violation(tmp_path):
    store = EventStore(str(tmp_path / "ev.duckdb"))
    store.upsert_events([
        _ev("a1", event_date=date(2026, 6, 10), filed=date(2026, 6, 12)),  # latency 2d
        _ev("a2", event_date=date(2026, 6, 1), filed=date(2026, 6, 9)),    # latency 8d (>5)
        _ev("a3", event_date=date(2026, 6, 15), filed=date(2026, 6, 10)),  # filed BEFORE txn -> -5d (PIT violation)
    ])
    lat = store.latency_audit(event_type="insider_buy")
    assert lat["min_latency_days"] == -5 and lat["max_latency_days"] == 8
    assert lat["n_pit_violations"] == 1     # the filed-before-transaction one
    assert lat["n_latency_over_5d"] == 1
    store.close()


def _good_store(tmp_path) -> EventStore:
    store = EventStore(str(tmp_path / "ev.duckdb"))
    store.upsert_events([
        _ev("a1", event_date=date(2026, 6, 10), filed=date(2026, 6, 12)),
        _ev("a2", event_date=date(2026, 6, 11), filed=date(2026, 6, 12)),
    ])
    return store


def test_validate_go_when_clean(tmp_path):
    store = _good_store(tmp_path)
    ingest = IngestReport(tickers_requested=10, ciks_resolved=10, form4_filings_seen=2,
                          events_ingested=2)
    rep = validate(store, ingest=ingest)
    assert rep.passed is True and rep.blockers == []
    assert rep.checks["cik_resolution"]["rate"] == 1.0
    store.close()


def test_validate_blocks_low_cik_resolution(tmp_path):
    store = _good_store(tmp_path)
    ingest = IngestReport(tickers_requested=100, ciks_resolved=50,  # 50% < 85%
                          unresolved_tickers=["ZZZ"], events_ingested=2)
    rep = validate(store, ingest=ingest)
    assert rep.passed is False
    assert any("CIK resolution" in b for b in rep.blockers)
    store.close()


def test_validate_blocks_pit_violation(tmp_path):
    store = EventStore(str(tmp_path / "ev.duckdb"))
    store.upsert_events([_ev("a3", event_date=date(2026, 6, 15), filed=date(2026, 6, 10))])
    rep = validate(store)
    assert rep.passed is False
    assert any("PIT violation" in b for b in rep.blockers)
    store.close()


def test_validate_blocks_empty_store(tmp_path):
    store = EventStore(str(tmp_path / "ev.duckdb"))
    rep = validate(store)
    assert rep.passed is False
    assert any("no events" in b for b in rep.blockers)
    store.close()
