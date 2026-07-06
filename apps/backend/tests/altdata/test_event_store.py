"""PIT corporate-event store — idempotent upsert + the as-of (no-look-ahead) read (offline)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.altdata.events.store import CorporateEvent, EventStore


def _ev(accession: str, ticker: str, filed: str) -> CorporateEvent:
    f = datetime.fromisoformat(filed).replace(tzinfo=UTC)
    return CorporateEvent(
        cik=320193, ticker=ticker, event_type="insider_buy", source="sec_edgar_form4",
        accession=accession, filed_at=f, event_date=f.date(),
        payload={"buy_value": 150500.0, "is_officer": True},
    )


def test_upsert_is_idempotent(tmp_path):
    store = EventStore(str(tmp_path / "ev.duckdb"))
    events = [_ev("acc-1", "AAPL", "2026-06-10T18:30:00"),
              _ev("acc-2", "MSFT", "2026-06-11T18:30:00")]
    assert store.upsert_events(events) == 2
    assert store.upsert_events(events) == 0          # re-ingest = no-op
    assert store.upsert_events(events + [_ev("acc-3", "NVDA", "2026-06-12T18:30:00")]) == 1
    assert store.count() == 3
    store.close()


def test_events_asof_is_point_in_time(tmp_path):
    store = EventStore(str(tmp_path / "ev.duckdb"))
    store.upsert_events([
        _ev("acc-1", "AAPL", "2026-06-10T18:30:00"),
        _ev("acc-2", "AAPL", "2026-06-15T18:30:00"),
    ])
    # Before any filing: nothing is knowable.
    assert store.events_asof(date(2026, 6, 9)) == []
    # On the first filing date: exactly one (no look-ahead to the 6-15 filing).
    asof_10 = store.events_asof(date(2026, 6, 10))
    assert [e.accession for e in asof_10] == ["acc-1"]
    # After both: both, with payload round-tripped.
    asof_16 = store.events_asof(date(2026, 6, 16))
    assert [e.accession for e in asof_16] == ["acc-1", "acc-2"]
    assert asof_16[0].payload["buy_value"] == 150500.0
    store.close()


def test_pit_date_is_utc_not_server_timezone(tmp_path):
    """Regression: a tz-aware MIDNIGHT-UTC filing must land on its UTC date regardless of the
    server timezone — not roll back a day (which it did before filed_at was normalized to
    naive-UTC, because DuckDB's CAST(timestamp AS DATE) converts tz-aware values to local)."""
    store = EventStore(str(tmp_path / "ev.duckdb"))
    store.upsert_events([
        CorporateEvent(cik=1, ticker="AAPL", event_type="insider_buy", source="sec_edgar_form4",
                       accession="acc-mid", filed_at=datetime(2026, 6, 10, 0, 0, tzinfo=UTC),
                       event_date=date(2026, 6, 10), payload={}),
    ])
    assert store.coverage()["first_filed"] == "2026-06-10"      # not 2026-06-09
    assert store.events_asof(date(2026, 6, 9)) == []            # not yet knowable
    assert len(store.events_asof(date(2026, 6, 10))) == 1       # knowable on the UTC filing date
    store.close()


def test_filters_and_coverage(tmp_path):
    store = EventStore(str(tmp_path / "ev.duckdb"))
    store.upsert_events([
        _ev("acc-1", "AAPL", "2026-06-10T18:30:00"),
        _ev("acc-2", "MSFT", "2026-06-11T18:30:00"),
    ])
    assert [e.accession for e in store.events_asof(date(2026, 6, 30), ticker="aapl")] == ["acc-1"]
    cov = store.coverage()
    assert cov["n_events"] == 2 and cov["by_type"] == {"insider_buy": 2}
    assert cov["first_filed"] == "2026-06-10" and cov["last_filed"] == "2026-06-11"
    assert cov["distinct_tickers"] == 2
    store.close()
