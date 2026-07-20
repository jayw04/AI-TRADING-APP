"""SPQ-1 Phase 2B development-run orchestrator (2B-1 limited-shard; reused by 2B-2).

Runs the accepted producer over (permanent_security_id x decision_session) units. Each unit yields
exactly one terminal disposition. Deterministic, shardable, restartable; canonical ordering. No signal
value is retained beyond record identities (performance quarantine). Binds the registered sic_mapping
via phase2b.sic_sector without modifying any closed module.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import numpy as np

from .. import (
    PHASE0_CENSUS_SHA256,
    PHASE0_OWNER_RULINGS_SHA256,
    PHASE0_SCHEMA_SHA256,
    PRODUCER_CODE_VERSION,
)
from ..adapters import DEV_END, DEV_START, REGISTERED_PROVENANCE_DB, REGISTERED_RESEARCH_DB
from ..adapters import dev_snapshot as DS
from ..adapters.benchmark_adapter import load_spy_adjclose
from ..adapters.calendar_adapter import load_calendar
from ..adapters.eligibility_adapter import load_earnings_checks
from ..adapters.identity_adapter import load_identity_registry
from ..adapters.partition_guard import OpenedObjectLedger, PartitionGuard
from ..adapters.price_adapter import load_price_series
from ..calendar import RegisteredCalendar
from ..identities import InputIdentityRegistry, canonical_sha256
from ..producer import MarketData, ProductionRequest, SecurityData, produce_decision
from ..refusals import SignalRefusal
from ..returns import CellStatus, arithmetic_total_returns
from ..security_identity import PitIdentityRegistry
from . import DISPOSITION_BY_CLASS, EMITTED
from .sic_sector import SicMapRow, load_sic_map, resolve_sector, sector_etf

REGISTERED = frozenset([REGISTERED_RESEARCH_DB, REGISTERED_PROVENANCE_DB])
ETF_TICKERS = ["SPY", "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
_OBS_IDS: dict[str, str] = {
    "registered_exchange_calendar": "", "spy_total_return_series": "dev-spy",
    "sector_etf_source_series": "dev-sec", "sector_etf_proxy_mapping_table": "dev-map",
    "price_return_adjustment_policy": "v3", "pit_sector_source": "dev-sic",
    "pit_identity_registry": "dev-cross", "eligibility_evidence_sources": "dev-earn",
}


@dataclass(frozen=True)
class UnitResult:
    permanent_security_id: str
    symbol: str
    decision_session: int
    disposition: str
    code: str | None
    decision_eligibility_status: str | None
    record_identity: str | None

    def key(self) -> tuple:
        return (self.decision_session, self.permanent_security_id)

    def as_row(self) -> dict:
        return {"permanent_security_id": self.permanent_security_id, "symbol": self.symbol,
                "decision_session": self.decision_session, "disposition": self.disposition,
                "code": self.code, "decision_eligibility_status": self.decision_eligibility_status,
                "record_identity": self.record_identity}


@dataclass(frozen=True)
class RunContext:
    con: object
    calendar: RegisteredCalendar
    spy_ret: np.ndarray
    sector_ret: dict[str, np.ndarray]        # research_sector -> returns
    registry: InputIdentityRegistry
    lineage: PitIdentityRegistry
    sic_map: list[SicMapRow]
    securities: dict[str, dict]              # permanent_security_id -> {symbol, cik, stock_ret, status, raw_close, raw_volume, sic_obs}
    ledger: OpenedObjectLedger


def _guarded_load_sic_map(con, guard: PartitionGuard) -> list[SicMapRow]:  # noqa: ANN001
    from ..adapters import abs_path
    from ..adapters.manifests import sha256_file
    tok = guard.authorize_read(REGISTERED_RESEARCH_DB, DEV_START, DEV_END, "sic_map", "orchestrator")
    rows = con.execute("select sic_start, sic_end, effective_from, research_sector, sector_etf "
                       "from sic_mapping").fetchall()
    norm = [[None if v is None else str(v) for v in r] for r in rows]
    norm.sort(key=lambda r: json.dumps(r))
    guard.record_completed_read(tok, sha256_file(abs_path(REGISTERED_RESEARCH_DB)),
                                "sic_mapping", None, None, len(norm), canonical_sha256(norm), "",
                                allow_pre_window=True)
    return load_sic_map([(r[0], r[1], r[2], r[3], r[4]) for r in rows])


def _guarded_sic_obs(src, guard, ciks):  # noqa: ANN001
    """PIT SIC observations from research.sic_observations (broad coverage), dev-bounded + guarded."""
    from ..adapters import abs_path
    from ..adapters.manifests import sha256_file
    tok = guard.authorize_read(REGISTERED_RESEARCH_DB, "0001-01-01", DEV_END, "sic_observations",
                               "orchestrator", allow_pre_window=True)
    rows = src.execute(
        "select cik, accepted_utc, sic from sic_observations where cik = ANY($c) "
        "and cast(accepted_utc as date) <= $b", {"c": ciks, "b": DEV_END}).fetchall()
    by: dict[int, list] = {}
    for cik, a, s in rows:
        by.setdefault(int(cik), []).append((a, s))
    norm = sorted([[str(cik), str(a)[:10], str(s)] for cik, a, s in rows])
    guard.record_completed_read(tok, sha256_file(abs_path(REGISTERED_RESEARCH_DB)),
                                "sic_observations", None,
                                max((r[1] for r in norm), default=None), len(rows),
                                canonical_sha256(norm), "", allow_pre_window=True)
    return by


def build_context(snapshot_con, guard, tickers, ciks, sic_map_con):  # noqa: ANN001
    cal = load_calendar(snapshot_con)
    spy = arithmetic_total_returns(load_spy_adjclose(snapshot_con, cal))
    sic_map = _guarded_load_sic_map(sic_map_con, guard)
    sic_obs_by_cik = _guarded_sic_obs(sic_map_con, guard, ciks)
    # sector returns keyed by research_sector via its ETF
    etf_by_sector: dict[str, str] = {r.research_sector: r.sector_etf for r in sic_map}
    sector_ret: dict[str, np.ndarray] = {}
    for sector, etf in etf_by_sector.items():
        rows = snapshot_con.execute(
            'select "date", adjclose from etf_prices where ticker = ? order by "date"', [etf]).fetchall()
        by = {str(d): float(v) for d, v in rows}
        arr = np.array([by.get(s, np.nan) for s in cal.sessions], dtype=np.float64)
        sector_ret[sector] = arithmetic_total_returns(_levels_to_series(arr))
    lineage = load_identity_registry(snapshot_con, cal)
    securities: dict[str, dict] = {}
    for tk in tickers:
        try:
            series = load_price_series(snapshot_con, tk, cal)
        except SignalRefusal:
            continue
        permsec = lineage.resolve_permanent_id(tk, len(cal) - 1)
        close = series["closeadj"]
        present = np.isfinite(close)
        if not present.any():
            continue
        first = int(np.argmax(present))
        status = [CellStatus.PRESENT if present[i] else
                  (CellStatus.YOUNG if i < first else CellStatus.UNEXPLAINED_HOLE)
                  for i in range(len(cal))]
        cik = _ticker_cik(snapshot_con, tk)
        sic_obs = sic_obs_by_cik.get(cik, []) if cik else []
        securities[permsec] = {"symbol": tk, "cik": cik,
                               "stock_ret": arithmetic_total_returns(close),
                               "status": status, "raw_close": series["closeunadj"],
                               "raw_volume": series["volume"], "sic_obs": sic_obs}
    return RunContext(snapshot_con, cal, spy, sector_ret, _registry(cal), lineage, sic_map,
                      securities, guard.ledger)


def _levels_to_series(arr: np.ndarray) -> np.ndarray:
    return arr


def _ticker_cik(con, ticker):  # noqa: ANN001
    r = con.execute("select cik from crosswalk where ticker = ? limit 1", [ticker]).fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _registry(cal):  # noqa: ANN001
    from ..identities import InputIdentityRegistry
    ids = dict(_OBS_IDS)
    ids["registered_exchange_calendar"] = cal.identity
    ids.update({"producer_code_version": PRODUCER_CODE_VERSION,
                "rule_census_identity": PHASE0_CENSUS_SHA256,
                "owner_rulings_identity": PHASE0_OWNER_RULINGS_SHA256,
                "schema_identity": PHASE0_SCHEMA_SHA256})
    return InputIdentityRegistry(ids)


def run_unit(ctx: RunContext, permsec: str, t: int) -> UnitResult:
    sec = ctx.securities[permsec]
    close_t_iso = ctx.calendar.sessions[t] + "T21:00:00Z"
    try:
        sector = resolve_sector(ctx.sic_map, sec["sic_obs"], close_t_iso)
        if sector.sector_id not in ctx.sector_ret:
            sector_etf(ctx.sic_map, sector.sector_id)  # raises if unmapped
        obs: dict[str, str] = {
            k: (ctx.calendar.identity if k == "registered_exchange_calendar" else v)
            for k, v in _OBS_IDS.items()}
        market = MarketData(ctx.calendar, ctx.spy_ret, ctx.sector_ret, obs)
        checks = load_earnings_checks(ctx.con, sec["cik"], ctx.calendar.sessions[t]) if sec["cik"] else []
        secdata = SecurityData(sec["symbol"], sec["stock_ret"], sec["status"],
                               sec["raw_close"], sec["raw_volume"], [sector], checks)
        req = ProductionRequest("MR-002", "B", "LONG", t, close_t_iso)
        rec = produce_decision(market, secdata, ctx.registry, ctx.lineage, req)
        return UnitResult(permsec, sec["symbol"], t, EMITTED, None,
                          rec.decision_eligibility_status, rec.record_identity)
    except SignalRefusal as e:
        return UnitResult(permsec, sec["symbol"], t, DISPOSITION_BY_CLASS[e.code_class], e.code, None, None)


def run_shard(ctx: RunContext, units: list[tuple[str, int]]) -> tuple[list[UnitResult], str]:
    results = [run_unit(ctx, permsec, t) for permsec, t in units]
    results.sort(key=lambda r: r.key())
    content = canonical_sha256([r.as_row() for r in results])
    return results, content


def publish_shard(results: list[UnitResult], content_sha: str, path: str) -> str:
    if os.path.exists(path):
        raise FileExistsError(f"completed shard exists (non-overwriting): {path}")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    payload = json.dumps({"rows": [r.as_row() for r in results], "content_sha256": content_sha,
                          "count": len(results)}, sort_keys=True, indent=1).encode("utf-8")
    tmp = path + ".partial"
    with open(tmp, "wb") as fh:
        fh.write(payload)
    os.replace(tmp, path)
    return content_sha


def merge(shard_results: list[list[UnitResult]]) -> list[UnitResult]:
    flat = [r for shard in shard_results for r in shard]
    seen = set()
    for r in flat:
        if r.key() in seen:
            raise ValueError(f"duplicate unit in merge: {r.key()}")
        seen.add(r.key())
    flat.sort(key=lambda r: r.key())
    return flat


def materialize_run_input(out_path: str, tickers: list[str], ciks: list[int],
                          ledger: OpenedObjectLedger) -> tuple[object, PartitionGuard]:  # noqa: ANN001
    import duckdb
    guard = PartitionGuard(REGISTERED, ledger)
    DS.materialize(duckdb, out_path, tickers, ETF_TICKERS, ciks, guard, "orchestrator")
    con = duckdb.connect(out_path, read_only=True)
    src = duckdb.connect(_abs(REGISTERED_RESEARCH_DB), read_only=True)  # sic_mapping source
    return con, guard, src  # type: ignore[return-value]


def _abs(rel: str) -> str:
    from ..adapters import abs_path
    return abs_path(rel)
