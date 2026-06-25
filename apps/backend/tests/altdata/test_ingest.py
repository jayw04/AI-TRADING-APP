"""Form 4 ingestion orchestration — submissions -> XML -> Event Store (offline fake client)."""

from __future__ import annotations

from datetime import date

from app.altdata.events.store import EventStore
from app.altdata.sec.cik_map import CikMap
from app.altdata.sec.ingest import (
    form4_xml_url,
    ingest_form4,
    submissions_url,
)
from tests.altdata.test_form4 import OFFICER_BUY

_SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["4", "8-K", "4"],
            "accessionNumber": ["0000320193-26-000061", "0000320193-26-000060", "0000320193-26-000010"],
            "filingDate": ["2026-06-10", "2026-06-09", "2026-01-05"],
            "acceptanceDateTime": ["2026-06-10T18:30:00.000Z", "2026-06-09T16:00:00.000Z",
                                   "2026-01-05T18:30:00.000Z"],
            "primaryDocument": ["form4.xml", "8k.htm", "form4.xml"],
        }
    }
}


class FakeClient:
    """Routes EDGAR URLs to canned submissions JSON + the Form 4 XML; counts calls."""

    def __init__(self) -> None:
        self.calls = 0

    def get_json(self, url: str):
        self.calls += 1
        assert url == submissions_url(320193)
        return _SUBMISSIONS

    def get_text(self, url: str) -> str:
        self.calls += 1
        assert url == form4_xml_url(320193, "0000320193-26-000061", "form4.xml") or "form4.xml" in url
        return OFFICER_BUY


def _store(tmp_path) -> EventStore:
    return EventStore(str(tmp_path / "ev.duckdb"))


def test_ingests_form4_buys_since_window(tmp_path):
    cmap = CikMap(by_ticker={"AAPL": 320193})
    store = _store(tmp_path)
    # since 2026-06-01 keeps the 6-10 Form 4, drops the 8-K and the Jan filing.
    rep = ingest_form4(FakeClient(), store, ["AAPL"], since="2026-06-01", cik_map=cmap)
    assert rep.tickers_requested == 1 and rep.ciks_resolved == 1
    assert rep.form4_filings_seen == 1          # only the 6-10 Form 4 (8-K excluded, Jan out of window)
    assert rep.events_ingested == 1
    assert rep.fetch_failures == 0

    evs = store.events_asof(date(2026, 6, 30), event_type="insider_buy")
    assert len(evs) == 1
    e = evs[0]
    assert e.ticker == "AAPL" and e.accession == "0000320193-26-000061"
    assert e.event_date == date(2026, 6, 10)
    assert e.payload["is_officer"] is True and e.payload["buy_value"] == 150500.0
    store.close()


def test_ingest_is_idempotent(tmp_path):
    cmap = CikMap(by_ticker={"AAPL": 320193})
    store = _store(tmp_path)
    ingest_form4(FakeClient(), store, ["AAPL"], since="2026-06-01", cik_map=cmap)
    rep2 = ingest_form4(FakeClient(), store, ["AAPL"], since="2026-06-01", cik_map=cmap)
    assert rep2.events_ingested == 0  # re-run stores nothing new
    assert store.count() == 1
    store.close()


def test_unresolved_tickers_reported(tmp_path):
    cmap = CikMap(by_ticker={"AAPL": 320193})  # ZZZZ unresolvable
    store = _store(tmp_path)
    rep = ingest_form4(FakeClient(), store, ["AAPL", "ZZZZ"], since="2026-06-01", cik_map=cmap)
    assert rep.unresolved_tickers == ["ZZZZ"]
    assert rep.ciks_resolved == 1
    store.close()
