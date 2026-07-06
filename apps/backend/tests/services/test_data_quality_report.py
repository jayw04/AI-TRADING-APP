"""EAD Data-Quality Report (ADR 0037 §4.0) — counters + license gating, built over the store."""

from __future__ import annotations

from app.altdata.events.store import EventStore
from app.altdata.quiver.ingest import ingest_govcontracts
from app.altdata.sec.cik_map import CikMap
from app.altdata.security_master import SecurityMaster
from app.services.data_quality import build_govcontract_data_quality, render_report

_ROW = {
    "Ticker": "LMT", "Date": "2026-07-05", "Description": "C2CI SUPPORT",
    "Agency": "DHS", "Amount": 248831.0, "action_date": "2026-07-02",
}


def _sm() -> SecurityMaster:
    return SecurityMaster(CikMap(by_ticker={"LMT": 936468}, titles={936468: "Lockheed Martin Corp"}))


class _FakeClient:
    def __init__(self, data):
        self._data = data

    def govcontracts_history(self, ticker):
        return list(self._data.get(ticker.strip().upper(), []))


def test_report_counts_and_license_gate(tmp_path):
    store = EventStore(str(tmp_path / "ev.duckdb"))
    client = _FakeClient({
        "LMT": [_ROW, {**_ROW, "Amount": 10.0, "Description": "OTHER"}],   # 2 resolved
        "ZZZZ": [{**_ROW, "Ticker": "ZZZZ"}],                             # 1 unresolved
    })
    rep = ingest_govcontracts(client, store, ["LMT", "ZZZZ"], security_master=_sm())

    dq = build_govcontract_data_quality(store, ingest_report=rep)

    assert dq.source_id == "DCAP-007"
    assert dq.events_total == 3 and dq.events_eligible == 2 and dq.events_ineligible == 1
    assert dq.unresolved_reasons.get("no_public_security") == 1
    assert dq.missing_available_time == 0            # eligible rows all have available_time
    assert dq.raw_hash_coverage == 1.0               # every event carries a raw_payload_hash
    assert abs(dq.mapping_failure_rate - (1 / 3)) < 1e-9
    assert dq.pit_violations == 0                    # available_time = action + lag >= event_date

    # license gate: Hobbyist -> customer-facing BLOCKED
    assert dq.customer_facing_allowed is False
    assert "BLOCKED" in dq.license_status

    # ingest counters threaded through
    assert dq.ingest_events_ingested == 3 and dq.ingest_api_failures == 0

    text = render_report(dq)
    assert "DCAP-007" in text and "no_public_security" in text
    store.close()


def test_report_on_empty_store_is_safe(tmp_path):
    store = EventStore(str(tmp_path / "ev.duckdb"))
    dq = build_govcontract_data_quality(store)
    assert dq.events_total == 0 and dq.raw_hash_coverage == 0.0 and dq.mapping_failure_rate == 0.0
    assert dq.customer_facing_allowed is False
    store.close()
