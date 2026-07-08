"""LOBBY-001 spend-spike normalizer + ingest — PIT aggregation, median baseline, spike gate,
new-entrant exclusion, provenance. Synthetic Security Master + fake client; no network."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.altdata.events.store import EventStore
from app.altdata.quiver.lobbying import (
    activity_quarter,
    aggregate_firm_quarters,
    build_lobby_events,
    deadline,
)
from app.altdata.quiver.lobbying_ingest import ingest_lobbying
from app.altdata.sec.cik_map import CikMap
from app.altdata.security_master import SecurityMaster


def _sm() -> SecurityMaster:
    return SecurityMaster(CikMap(by_ticker={"NVDA": 1045810}, titles={1045810: "NVIDIA Corp"}))


def _f(ticker: str, filed: str, amount: float) -> dict:
    return {"Ticker": ticker, "Amount": str(amount), "Date": filed,
            "Client": ticker, "Registrant": "R", "Issue": "Defense", "Specific_Issue": "x"}


def _baseline_then(spike_amt: float, base_amt: float = 50_000, *, ticker: str = "NVDA"):
    """4 nonzero baseline quarters (Q1–Q4 2024) at ``base_amt`` then a Q1-2025 quarter at ``spike_amt``."""
    return [_f(ticker, "2024-04-15", base_amt),  # Q1 2024
            _f(ticker, "2024-07-15", base_amt),  # Q2 2024
            _f(ticker, "2024-10-15", base_amt),  # Q3 2024
            _f(ticker, "2025-01-15", base_amt),  # Q4 2024 (filed by Jan 20 2025)
            _f(ticker, "2025-04-15", spike_amt)]  # Q1 2025


# --- calendar ---------------------------------------------------------------------------------

def test_activity_quarter_and_deadline():
    assert activity_quarter(date(2026, 7, 7)) == (2026, 2)     # Jul filing -> Q2 activity
    assert activity_quarter(date(2026, 1, 10)) == (2025, 4)    # Jan filing -> prior-year Q4
    assert activity_quarter(date(2026, 4, 15)) == (2026, 1)
    assert deadline((2026, 2)) == date(2026, 7, 20)
    assert deadline((2025, 4)) == date(2026, 1, 20)            # Q4 due next January


# --- PIT aggregation --------------------------------------------------------------------------

def test_late_filing_excluded_from_as_of_deadline_total():
    # one on-time Q1-2025 filing ($100k, Apr 15) + one LATE Q1-2025 filing ($1M, filed May 5 > Apr 20)
    rows = [_f("NVDA", "2025-04-15", 100_000), _f("NVDA", "2025-05-05", 1_000_000)]
    quarters, dq = aggregate_firm_quarters(rows)
    fq = quarters[(2025, 1)]
    assert fq.spend_total == 100_000            # the $1M late row is NOT in the total
    assert fq.filing_row_count == 1 and fq.late_rows_excluded == 1
    assert dq.filings_on_time == 1 and dq.late_excluded == 1


# --- spike detection --------------------------------------------------------------------------

def test_spike_fires_at_2x_median_over_floor():
    evs, dq = build_lobby_events("NVDA", _baseline_then(200_000), security_master=_sm())
    assert len(evs) == 1 and dq.spike_events == 1
    ev = evs[0]
    assert ev.event_type == "lobby_spike" and ev.research_eligible is True
    assert ev.payload["quarter"] == "2025Q1"
    assert ev.payload["spend_total"] == 200_000 and ev.payload["baseline_value"] == 50_000
    assert ev.payload["spike_ratio"] == 4.0
    assert ev.available_time == datetime(2025, 4, 20, tzinfo=UTC)   # the observable Q1 deadline


def test_no_spike_below_2x_or_below_floor():
    # baseline 80k -> 2x = 160k, above the 100k floor, so the two gates are separable:
    assert build_lobby_events("NVDA", _baseline_then(90_000, 80_000), security_master=_sm())[0] == []   # <100k floor
    assert build_lobby_events("NVDA", _baseline_then(120_000, 80_000), security_master=_sm())[0] == []  # >=100k but <2x median


def test_median_baseline_resists_a_prior_spike():
    # baseline quarters {50k,50k,50k,500k}: median=50k, mean=162.5k. A 150k quarter is a spike vs the
    # median (>=100k) but NOT vs the mean (<325k) — confirms we use MEDIAN (owner review item 2).
    rows = [_f("NVDA", "2024-04-15", 50_000), _f("NVDA", "2024-07-15", 50_000),
            _f("NVDA", "2024-10-15", 50_000), _f("NVDA", "2025-01-15", 500_000),
            _f("NVDA", "2025-04-15", 150_000)]
    evs, _ = build_lobby_events("NVDA", rows, security_master=_sm())
    assert [e.payload["quarter"] for e in evs] == ["2025Q1"]
    assert evs[0].payload["baseline_value"] == 50_000


def test_new_entrant_excluded_under_four_prior_nonzero():
    # only 3 prior nonzero quarters before the material quarter -> excluded (reserved for LOBBY-002)
    rows = [_f("NVDA", "2024-07-15", 50_000), _f("NVDA", "2024-10-15", 50_000),
            _f("NVDA", "2025-01-15", 50_000), _f("NVDA", "2025-04-15", 300_000)]
    evs, dq = build_lobby_events("NVDA", rows, security_master=_sm())
    assert evs == [] and dq.excluded_new_entrant_quarters == 1


def test_no_filing_quarter_is_a_gap_not_a_zero():
    # skip Q3 2024 entirely -> only 3 prior nonzero quarters exist -> the Q1-2025 material quarter is
    # a new entrant (a missing quarter does NOT count as a zero baseline point).
    rows = [_f("NVDA", "2024-04-15", 50_000), _f("NVDA", "2024-07-15", 50_000),
            _f("NVDA", "2025-01-15", 50_000), _f("NVDA", "2025-04-15", 300_000)]  # no Q3 2024
    evs, dq = build_lobby_events("NVDA", rows, security_master=_sm())
    assert evs == [] and dq.excluded_new_entrant_quarters == 1


def test_provenance_payload_complete():
    ev = build_lobby_events("NVDA", _baseline_then(200_000), security_master=_sm())[0][0]
    for k in ("quarter", "spend_total", "baseline_value", "baseline_method", "spike_ratio",
              "filing_row_count", "rows_included_hash", "late_rows_excluded_count",
              "available_time_basis"):
        assert k in ev.payload
    assert ev.payload["baseline_method"] == "median_nonzero_4q"
    assert ev.payload["available_time_basis"] == "quarter_deadline"
    assert ev.source_event_id.startswith("qlob_")


# --- ingest -----------------------------------------------------------------------------------

class _FakeClient:
    def __init__(self, data, fail=()):
        self._data = data
        self._fail = set(fail)

    def lobbying_history(self, ticker):
        if ticker in self._fail:
            raise RuntimeError("boom")
        return list(self._data.get(ticker.strip().upper(), []))


def test_ingest_idempotent_with_data_quality(tmp_path):
    store = EventStore(str(tmp_path / "ev.duckdb"))
    client = _FakeClient(data={"NVDA": _baseline_then(200_000)}, fail={"BAD"})
    rep = ingest_lobbying(client, store, ["NVDA", "BAD"], security_master=_sm())
    assert rep.fetch_failures == 1
    assert rep.events_built == 1 and rep.eligible == 1 and rep.events_ingested == 1
    assert rep.data_quality.tickers == 1 and rep.data_quality.spike_events == 1
    # re-run: idempotent (deterministic source_event_id)
    assert ingest_lobbying(client, store, ["NVDA"], security_master=_sm()).events_ingested == 0
    got = store.events_asof_eligible(date(2025, 5, 1), event_type="lobby_spike")
    assert {e.ticker for e in got} == {"NVDA"} and len(got) == 1
    store.close()
