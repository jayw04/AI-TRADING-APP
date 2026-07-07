"""Quiver congressional-trading normalizer + ingest (CONGRESS-001). Offline; fixture Security
Master + fake client; no network."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.altdata.events.store import EventStore
from app.altdata.quiver.congress_ingest import ingest_congress, ingest_congress_bulk
from app.altdata.quiver.congresstrading import congress_to_event
from app.altdata.sec.cik_map import CikMap
from app.altdata.security_master import SecurityMaster

_ROW = {
    "Representative": "Nancy Pelosi", "BioGuideID": "P000197", "ReportDate": "2026-07-05",
    "TransactionDate": "2026-06-20", "Ticker": "NVDA", "Transaction": "Purchase",
    "Range": "$1,000,001 - $5,000,000", "House": "Representatives",
}


def _sm() -> SecurityMaster:
    return SecurityMaster(CikMap(
        by_ticker={"NVDA": 1045810, "AAPL": 320193},
        titles={1045810: "NVIDIA Corp", 320193: "Apple Inc"},
    ))


# --- normalizer --------------------------------------------------------------------------------

def test_normalizes_a_resolved_purchase():
    ev = congress_to_event(_ROW, security_master=_sm())
    assert ev is not None
    assert ev.event_type == "congress_trade" and ev.source == "quiver"
    assert ev.provider_dataset == "congress_trading" and ev.data_source_id == "DCAP-007"
    assert ev.event_date == date(2026, 6, 20)                      # TransactionDate = the trade
    assert ev.payload["direction"] == "buy" and ev.payload["range_low"] == 1000001
    assert ev.research_eligible is True
    assert ev.resolved_security_id == "CIK0001045810" and ev.ticker == "NVDA"
    assert ev.source_event_id.startswith("qct_")
    assert ev.event_id == f"{ev.source_event_id}:congress_trade"


def test_available_time_is_observable_reportdate_not_transactiondate():
    """The CONGRESS-001 advantage: PIT anchor = the OBSERVABLE ReportDate, no lag calibration,
    and NEVER the (private) TransactionDate."""
    ev = congress_to_event(_ROW, security_master=_sm())
    assert ev.available_time == datetime(2026, 7, 5, tzinfo=UTC)   # ReportDate
    assert ev.filed_at == ev.available_time
    assert ev.available_time.date() != ev.event_date              # not the trade date (look-ahead)


def test_direction_parsing():
    def d(t):
        return congress_to_event({**_ROW, "Transaction": t}, security_master=_sm()).payload["direction"]
    assert d("Purchase") == "buy"
    assert d("Sale") == "sell"
    assert d("Sale (Partial)") == "sell"
    assert d("Exchange") is None


def test_range_low_parsing():
    def r(rng):
        return congress_to_event({**_ROW, "Range": rng}, security_master=_sm()).payload["range_low"]
    assert r("$1,001 - $15,000") == 1001
    assert r("$50,001 - $100,000") == 50001
    assert r("$50,000,000 +") == 50000000
    assert r(None) is None


def test_deterministic_idempotency_key():
    a = congress_to_event(_ROW, security_master=_sm())
    b = congress_to_event(dict(_ROW), security_master=_sm())
    assert a.source_event_id == b.source_event_id and a.event_id == b.event_id


def test_unresolved_ticker_is_ineligible_with_reason():
    ev = congress_to_event({**_ROW, "Ticker": "ZZZZ"}, security_master=_sm())
    assert ev is not None and ev.research_eligible is False
    assert ev.unresolved_reason == "no_public_security"
    assert ev.resolved_security_id is None and ev.cik == 0


def test_rows_missing_pit_fields_are_dropped():
    assert congress_to_event({**_ROW, "ReportDate": None}, security_master=_sm()) is None
    assert congress_to_event({**_ROW, "Ticker": ""}, security_master=_sm()) is None


# --- ingest ------------------------------------------------------------------------------------

class _FakeClient:
    def __init__(self, data, fail=()):
        self._data = data
        self._fail = set(fail)

    def congresstrading_history(self, ticker):
        if ticker in self._fail:
            raise RuntimeError("boom")
        return list(self._data.get(ticker.strip().upper(), []))


def test_ingest_upserts_idempotent_and_tallies_direction(tmp_path):
    store = EventStore(str(tmp_path / "ev.duckdb"))
    sale = {**_ROW, "Transaction": "Sale", "Range": "$15,001 - $50,000"}
    client = _FakeClient(
        data={"NVDA": [_ROW, sale], "ZZZZ": [{**_ROW, "Ticker": "ZZZZ"}]}, fail={"BAD"},
    )
    rep = ingest_congress(client, store, ["NVDA", "ZZZZ", "BAD"], security_master=_sm())
    assert rep.fetch_failures == 1                    # BAD raised
    assert rep.events_built == 3                      # 2 NVDA + 1 ZZZZ
    assert rep.buys == 2 and rep.sells == 1           # NVDA buy + ZZZZ buy; NVDA sale
    assert rep.unresolved == 1                        # ZZZZ not resolved
    assert rep.events_ingested == 3
    # re-run: idempotent (same deterministic ids)
    assert ingest_congress(client, store, ["NVDA", "ZZZZ"], security_master=_sm()).events_ingested == 0
    # only resolved NVDA trades are EAD-eligible, anchored on the observable ReportDate
    got = store.events_asof_eligible(date(2026, 7, 30), event_type="congress_trade")
    assert {e.ticker for e in got} == {"NVDA"} and len(got) == 2
    store.close()


class _FakeBulkClient:
    def __init__(self, rows):
        self._rows = rows

    def congresstrading_live(self):
        return list(self._rows)


def test_bulk_ingest_upserts_and_tallies(tmp_path):
    store = EventStore(str(tmp_path / "ev.duckdb"))
    client = _FakeBulkClient([_ROW, {**_ROW, "Ticker": "ZZZZ"}])
    rep = ingest_congress_bulk(client, store, security_master=_sm())
    assert rep.rows_seen == 2 and rep.events_built == 2
    assert rep.events_ingested == 2 and rep.unresolved == 1
    assert ingest_congress_bulk(client, store, security_master=_sm()).events_ingested == 0
    store.close()
