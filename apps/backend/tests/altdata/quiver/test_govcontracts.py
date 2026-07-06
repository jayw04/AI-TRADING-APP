"""Quiver government-contract normalizer + ingest (EAD Phase 1). Offline; fixture Security
Master + fake client; no network."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.altdata.events.store import EventStore
from app.altdata.quiver.govcontracts import (
    DISCLOSURE_LAG_DAYS,
    govcontract_to_event,
)
from app.altdata.quiver.ingest import ingest_govcontracts
from app.altdata.sec.cik_map import CikMap
from app.altdata.security_master import SecurityMaster

_ROW = {
    "Ticker": "LMT", "Date": "2026-07-05", "Description": "C2CI SYSTEMS SUPPORT",
    "Agency": "Department of Homeland Security", "Amount": 248831.0, "action_date": "2026-07-02",
}


def _sm() -> SecurityMaster:
    return SecurityMaster(CikMap(
        by_ticker={"LMT": 936468, "RTX": 101829},
        titles={936468: "Lockheed Martin Corp", 101829: "Raytheon Technologies"},
    ))


# --- normalizer --------------------------------------------------------------------------------

def test_normalizes_a_resolved_award():
    ev = govcontract_to_event(_ROW, security_master=_sm())
    assert ev is not None
    assert ev.event_type == "gov_contract_award" and ev.source == "quiver"
    assert ev.provider_dataset == "government_contracts" and ev.data_source_id == "DCAP-007"
    assert ev.event_date == date(2026, 7, 2)                       # action_date = the event
    # available_time = action_date + conservative lag (NOT Quiver's snapshot Date)
    assert ev.available_time == datetime(2026, 7, 2, tzinfo=UTC) + timedelta(days=DISCLOSURE_LAG_DAYS)
    assert ev.filed_at == ev.available_time
    assert ev.research_eligible is True
    assert ev.resolved_security_id == "CIK0000936468" and ev.ticker == "LMT"
    assert ev.raw_payload_hash and ev.source_event_id.startswith("qgc_")
    assert ev.event_id == f"{ev.source_event_id}:gov_contract_award"


def test_quiver_date_is_provenance_only_not_availability():
    ev = govcontract_to_event(_ROW, security_master=_sm())
    assert ev.payload["quiver_snapshot_date"] == "2026-07-05"      # kept for provenance
    # availability is derived from action_date, so it must NOT equal the snapshot Date
    assert ev.available_time.date() != date(2026, 7, 5)


def test_deterministic_idempotency_key():
    a = govcontract_to_event(_ROW, security_master=_sm())
    b = govcontract_to_event(dict(_ROW), security_master=_sm())
    assert a.source_event_id == b.source_event_id and a.event_id == b.event_id


def test_unresolved_ticker_is_ineligible_with_reason():
    row = {**_ROW, "Ticker": "ZZZZ"}
    ev = govcontract_to_event(row, security_master=_sm())
    assert ev is not None
    assert ev.research_eligible is False
    assert ev.unresolved_reason == "no_public_security"
    assert ev.resolved_security_id is None and ev.cik == 0


def test_rows_missing_pit_fields_are_dropped():
    assert govcontract_to_event({**_ROW, "action_date": None}, security_master=_sm()) is None
    assert govcontract_to_event({**_ROW, "Ticker": ""}, security_master=_sm()) is None


# --- ingest ------------------------------------------------------------------------------------

class _FakeClient:
    def __init__(self, data, fail=()):
        self._data = data
        self._fail = set(fail)

    def govcontracts_history(self, ticker):
        if ticker in self._fail:
            raise RuntimeError("boom")
        return list(self._data.get(ticker.strip().upper(), []))


def test_ingest_upserts_and_is_idempotent(tmp_path):
    store = EventStore(str(tmp_path / "ev.duckdb"))
    client = _FakeClient(
        data={"LMT": [_ROW, {**_ROW, "Amount": 5000.0, "Description": "OTHER"}],
              "ZZZZ": [{**_ROW, "Ticker": "ZZZZ"}]},
        fail={"BAD"},
    )
    rep = ingest_govcontracts(client, store, ["LMT", "ZZZZ", "BAD"], security_master=_sm())

    assert rep.fetch_failures == 1                    # BAD raised
    assert rep.events_built == 3                      # 2 LMT + 1 ZZZZ
    assert rep.unresolved == 1                        # ZZZZ not resolved
    assert rep.unresolved_reasons.get("no_public_security") == 1
    assert rep.events_ingested == 3
    # re-run: idempotent (same deterministic ids)
    assert ingest_govcontracts(client, store, ["LMT", "ZZZZ"], security_master=_sm()).events_ingested == 0

    # only the resolved+available LMT awards are EAD-eligible, anchored on available_time
    got = store.events_asof_eligible(date(2026, 7, 30), event_type="gov_contract_award")
    assert {e.ticker for e in got} == {"LMT"} and len(got) == 2
    assert all(e.resolved_security_id == "CIK0000936468" for e in got)
    store.close()


class _FakeBulkClient:
    def __init__(self, rows):
        self._rows = rows

    def govcontracts_live(self):
        return list(self._rows)


def test_bulk_ingest_upserts_and_tallies(tmp_path):
    from app.altdata.quiver.ingest import ingest_govcontracts_bulk

    store = EventStore(str(tmp_path / "ev.duckdb"))
    client = _FakeBulkClient([_ROW, {**_ROW, "Ticker": "ZZZZ"}])
    rep = ingest_govcontracts_bulk(client, store, security_master=_sm())
    assert rep.rows_seen == 2 and rep.events_built == 2
    assert rep.events_ingested == 2 and rep.unresolved == 1
    # idempotent re-run
    assert ingest_govcontracts_bulk(client, store, security_master=_sm()).events_ingested == 0
    store.close()
