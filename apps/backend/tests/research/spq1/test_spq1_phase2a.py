"""SPQ-1 Phase-2A development-data adapter qualification (real-data, dev-partition only).

Skips if the registered development DBs are absent (they are large, local, not in git). No performance
metric is computed or interpreted; the Phase-1 conversion is a schema-compat check only.
"""
from __future__ import annotations

import os

import duckdb
import numpy as np
import pytest

from app.research.mr002.spq1 import (
    PHASE0_CENSUS_SHA256,
    PHASE0_OWNER_RULINGS_SHA256,
    PHASE0_SCHEMA_SHA256,
    PRODUCER_CODE_VERSION,
)
from app.research.mr002.spq1.adapters import (
    REGISTERED_PROVENANCE_DB,
    REGISTERED_RESEARCH_DB,
    abs_path,
    normalize_utc_iso,
)
from app.research.mr002.spq1.adapters import dev_snapshot as DS
from app.research.mr002.spq1.adapters.benchmark_adapter import load_spy_adjclose
from app.research.mr002.spq1.adapters.calendar_adapter import load_calendar
from app.research.mr002.spq1.adapters.eligibility_adapter import load_earnings_checks
from app.research.mr002.spq1.adapters.identity_adapter import load_identity_registry
from app.research.mr002.spq1.adapters.liquidity_adapter import trailing_adv_from_series
from app.research.mr002.spq1.adapters.partition_guard import OpenedObjectLedger, PartitionGuard
from app.research.mr002.spq1.adapters.pit_sector_adapter import load_sector_records
from app.research.mr002.spq1.adapters.price_adapter import (
    cross_series_substitution_guard,
    load_price_series,
)
from app.research.mr002.spq1.adapters.sector_proxy_adapter import load_sector_returns
from app.research.mr002.spq1.eligibility import evaluate_eligibility
from app.research.mr002.spq1.identities import InputIdentityRegistry, canonical_sha256
from app.research.mr002.spq1.producer import (
    MarketData,
    ProductionRequest,
    SecurityData,
    produce_decision,
)
from app.research.mr002.spq1.refusals import SignalRefusal
from app.research.mr002.spq1.returns import CellStatus, arithmetic_total_returns

pytestmark = pytest.mark.skipif(
    not (os.path.exists(abs_path(REGISTERED_RESEARCH_DB))
         and os.path.exists(abs_path(REGISTERED_PROVENANCE_DB))),
    reason="registered development DBs not present (local-only, not in git)",
)

SAMPLE_TICKERS = ["AAPL"]
SAMPLE_ETFS = ["SPY", "XLK"]
SAMPLE_CIKS = [320193]
REGISTERED = frozenset([REGISTERED_RESEARCH_DB, REGISTERED_PROVENANCE_DB])


def _refuse(fn, code):
    with pytest.raises(SignalRefusal) as e:
        fn()
    assert e.value.code == code, f"expected {code} got {e.value.code}"


@pytest.fixture(scope="module")
def snap(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("devsnap") / "dev.duckdb")
    led = OpenedObjectLedger()
    guard = PartitionGuard(REGISTERED, led)
    s = DS.materialize(duckdb, out, SAMPLE_TICKERS, SAMPLE_ETFS, SAMPLE_CIKS, guard, "test")
    con = duckdb.connect(out, read_only=True)
    yield {"con": con, "snapshot": s, "ledger": led}
    con.close()


# ---- partition guard (technical prevention) ----
def test_guard_accepts_dev_and_rejects_validation_oos_range():
    g = PartitionGuard(REGISTERED, OpenedObjectLedger())
    g.guard_range("2013-01-02", "2019-10-02")                     # dev: ok
    _refuse(lambda: g.guard_range("2013-01-02", "2020-06-01"),    # crosses into validation
            "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS")
    _refuse(lambda: g.guard_range("2024-01-01", "2024-06-01"),    # OOS
            "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS")


def test_guard_rejects_unregistered_and_traversal():
    g = PartitionGuard(REGISTERED, OpenedObjectLedger())
    g.guard_object(REGISTERED_RESEARCH_DB)                        # registered: ok
    _refuse(lambda: g.guard_object("apps/backend/data/validation_secret.duckdb"),
            "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS")
    _refuse(lambda: g.guard_object("apps/backend/data/../../etc/passwd"),
            "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS")


# ---- calendar (hash enforced, not just count) ----
def test_calendar_is_1700_dev_sessions(snap):
    cal = load_calendar(snap["con"])
    assert len(cal) == 1700
    assert cal.sessions[0] == "2013-01-02" and cal.sessions[-1] == "2019-10-02"


def test_calendar_hash_rejects_same_count_perturbation(snap, tmp_path):
    from app.research.mr002.spq1.adapters import DEV_CALENDAR_SHA256
    from app.research.mr002.spq1.adapters.calendar_adapter import dev_calendar_sha256
    dates = list(load_calendar(snap["con"]).sessions)
    assert dev_calendar_sha256(tuple(dates)) == DEV_CALENDAR_SHA256      # governed hash matches
    dates[800] = "2099-12-31"                                           # replace one; count stays 1700
    p = str(tmp_path / "bad.duckdb")
    con = duckdb.connect(p)
    con.execute("create table prices (ticker varchar, date varchar)")
    con.executemany("insert into prices values ('AAPL', ?)", [[d] for d in sorted(dates)])
    con.close()
    ro = duckdb.connect(p, read_only=True)
    _refuse(lambda: load_calendar(ro), "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH")
    ro.close()


def test_identity_pre_window_disposition(snap):
    reg = load_identity_registry(snap["con"], load_calendar(snap["con"]))
    assert reg.lineage["AAPL"][0].source_evidence_identity.startswith("crosswalk:PRE_WINDOW")


def test_opened_object_ledger_records_actual_reads(snap):
    entries = snap["ledger"].entries
    assert entries and all(e["status"] == "COMPLETED" for e in entries)
    assert all(e["result_row_count"] > 0 for e in entries)
    # no read returned a row beyond the development window (future/validation/OOS)
    assert all(e["actual_max_date"] is None or e["actual_max_date"] <= "2019-10-02" for e in entries)
    # crosswalk PIT-bound: max effective_from <= DEV_END (no future identity row)
    cw = [e for e in entries if e["query_identity"].startswith("crosswalk")][0]
    assert cw["actual_max_date"] <= "2019-10-02"


# ---- identity ----
def test_identity_permanent_id(snap):
    ident = load_identity_registry(snap["con"], load_calendar(snap["con"]))
    assert ident.resolve_permanent_id("AAPL", 1000) == "PSEC-199059"


# ---- price series V3 ----
def test_price_series_v3_distinct_and_substitution_guard(snap):
    cal = load_calendar(snap["con"])
    s = load_price_series(snap["con"], "AAPL", cal)
    fin = np.isfinite(s["closeadj"]) & np.isfinite(s["closeunadj"])
    assert fin.any() and not np.array_equal(s["closeadj"][fin], s["closeunadj"][fin])
    cross_series_substitution_guard("raw_close", "closeunadj")    # correct binding: ok
    _refuse(lambda: cross_series_substitution_guard("raw_close", "closeadj"),
            "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH")


# ---- benchmark + sector proxy ----
def test_benchmark_spy_only_and_sector_unknown_refused(snap):
    cal = load_calendar(snap["con"])
    assert int(np.isfinite(load_spy_adjclose(snap["con"], cal)).sum()) == 1700
    _refuse(lambda: load_spy_adjclose(snap["con"], cal, ticker="QQQ"),
            "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH")
    assert "TECH" in load_sector_returns(snap["con"], cal, ["TECH"])
    _refuse(lambda: load_sector_returns(snap["con"], cal, ["NOPE"]),
            "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH")


# ---- PIT sector availability ----
def test_pit_sector_latest_governs_and_post_cutoff_excluded(snap):
    recs = load_sector_records(snap["con"], 320193)
    assert recs and all(r.availability_timestamp.endswith("Z") for r in recs)
    from app.research.mr002.spq1.sector_pit import resolve_sector
    # a cutoff before the first accepted record -> no PIT sector available
    _refuse(lambda: resolve_sector(recs, "2011-01-01T00:00:00Z"),
            "INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING")
    # a mid-window cutoff -> the latest record available by then governs (not a future one)
    late = max(r.availability_timestamp for r in recs)
    mid = sorted(r.availability_timestamp for r in recs)[len(recs) // 2]
    chosen = resolve_sector(recs, mid)
    assert chosen.availability_timestamp <= mid < late


# ---- eligibility availability (Correction-1 path on real data) ----
def test_eligibility_post_cutoff_evidence_missing(snap):
    checks = load_earnings_checks(snap["con"], 320193, "2015-06-15")
    latest = max(c.availability_timestamp for c in checks)
    # cutoff before the latest earnings acceptance -> that record is post-cutoff.
    early_cutoff = sorted(c.availability_timestamp for c in checks)[0]
    just_before = "2012-01-01T00:00:00Z"
    _refuse(lambda: evaluate_eligibility([c for c in checks
                                          if c.availability_timestamp == latest], just_before),
            "INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING")
    assert early_cutoff.endswith("Z")


# ---- liquidity ----
def test_liquidity_raw_pair(snap):
    cal = load_calendar(snap["con"])
    s = load_price_series(snap["con"], "AAPL", cal)
    adv = trailing_adv_from_series(s, 1699)
    assert adv > 0


# ---- determinism ----
def test_adapter_determinism(snap, tmp_path):
    con = snap["con"]
    a = [canonical_sha256({"s": r.sector_id, "a": r.availability_timestamp})
         for r in load_sector_records(con, 320193)]
    b = [canonical_sha256({"s": r.sector_id, "a": r.availability_timestamp})
         for r in load_sector_records(con, 320193)]
    assert a == b
    # re-materialize -> identical snapshot content hash
    out2 = str(tmp_path / "dev2.duckdb")
    s2 = DS.materialize(duckdb, out2, SAMPLE_TICKERS, SAMPLE_ETFS, SAMPLE_CIKS,
                        PartitionGuard(REGISTERED, OpenedObjectLedger()), "det")
    assert s2.content_sha256 == snap["snapshot"].content_sha256


# ---- source identity ----
def test_source_identity_mismatch_refused(snap):
    ids = {k: "x" for k in [
        "registered_exchange_calendar", "spy_total_return_series", "sector_etf_source_series",
        "sector_etf_proxy_mapping_table", "price_return_adjustment_policy", "pit_sector_source",
        "pit_identity_registry", "eligibility_evidence_sources"]}
    ids.update({"producer_code_version": PRODUCER_CODE_VERSION,
                "rule_census_identity": PHASE0_CENSUS_SHA256,
                "owner_rulings_identity": PHASE0_OWNER_RULINGS_SHA256,
                "schema_identity": "WRONG"})
    _refuse(lambda: InputIdentityRegistry(ids),
            "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH")


# ---- Phase-1 conversion (schema compatibility only; z is an unexamined artifact) ----
def test_real_data_converts_to_phase1_record(snap):
    con = snap["con"]
    cal = load_calendar(con)
    s = load_price_series(con, "AAPL", cal)
    spy = arithmetic_total_returns(load_spy_adjclose(con, cal))
    tech = arithmetic_total_returns(load_sector_returns(con, cal, ["TECH"])["TECH"])
    obs = {k: v for k, v in {
        "registered_exchange_calendar": cal.identity, "spy_total_return_series": "dev-spy",
        "sector_etf_source_series": "dev-sec", "sector_etf_proxy_mapping_table": "dev-map",
        "price_return_adjustment_policy": "v3", "pit_sector_source": "dev-sic",
        "pit_identity_registry": "dev-cross", "eligibility_evidence_sources": "dev-earn"}.items()}
    ids = dict(obs)
    ids.update({"producer_code_version": PRODUCER_CODE_VERSION,
                "rule_census_identity": PHASE0_CENSUS_SHA256,
                "owner_rulings_identity": PHASE0_OWNER_RULINGS_SHA256,
                "schema_identity": PHASE0_SCHEMA_SHA256})
    reg = InputIdentityRegistry(ids)
    market = MarketData(cal, spy, {"TECH": tech}, obs)
    sec = SecurityData("AAPL", arithmetic_total_returns(s["closeadj"]),
                       [CellStatus.PRESENT] * len(cal), s["closeunadj"], s["volume"],
                       load_sector_records(con, 320193),
                       load_earnings_checks(con, 320193, "2019-10-02"))
    lin = load_identity_registry(con, cal)
    rec = produce_decision(market, sec, reg, lin,
                           ProductionRequest("MR-002", "B", "LONG", 1699, "2019-10-02T21:00:00Z"))
    # schema compatibility only — do NOT examine/interpret the signal value.
    assert rec.sector_id == "TECH" and len(rec.canonical()) == 19
    assert normalize_utc_iso("2019-10-02 15:00:00-06:00") == "2019-10-02T21:00:00Z"
