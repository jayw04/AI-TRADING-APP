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
from ..adapters.identity_adapter import load_identity_registry
from ..adapters.partition_guard import OpenedObjectLedger, PartitionGuard
from ..adapters.price_adapter import load_price_series
from ..calendar import RegisteredCalendar
from ..identities import InputIdentityRegistry, canonical_sha256
from ..producer import MarketData, ProductionRequest, SecurityData, produce_decision
from ..refusals import SignalRefusal, refuse
from ..returns import CellStatus, arithmetic_total_returns
from ..security_identity import PitIdentityRegistry
from . import DISPOSITION_BY_CLASS, EMITTED
from .cutoff import et_close_cutoff_iso
from .sic_sector import SicMapRow, load_sic_map, resolve_sector, sector_etf

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_CODE_MODULES = ("__init__.py", "cutoff.py", "sic_sector.py", "orchestrator.py")


def code_identity() -> dict[str, str]:
    """SHA-256 of every Phase-2B execution module (bound in the run manifest; run refuses on drift)."""
    import hashlib
    return {m: hashlib.sha256(open(os.path.join(_THIS_DIR, m), "rb").read()).hexdigest()
            for m in _CODE_MODULES}


def verify_code_identity(expected: dict[str, str]) -> None:
    actual = code_identity()
    if actual != expected:
        raise RuntimeError(f"phase2b orchestration code identity mismatch: {actual} != {expected}")

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
        # Enumeration key is (session, symbol) — PIT-safe; permanent_security_id is resolved AT t.
        return (self.decision_session, self.symbol)

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
    securities: dict[str, dict]              # SYMBOL -> {stock_ret, status, raw_close, raw_volume, cik_timeline}
    sic_obs_by_cik: dict[int, list]          # cik -> [(accepted_utc_full_iso, sic, accession)]
    earnings_by_cik: dict[int, list]         # cik -> earnings_anchors rows (bulk, ledgered)
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
    """PIT SIC observations from research.sic_observations, dev-bounded + guarded. Preserves the full
    registered field set (cik, accepted_utc, sic, accession) and the COMPLETE UTC timestamp; the ledger
    result hash binds all four fields + the full timestamp (per the amended source contract)."""
    from ..adapters import abs_path, normalize_utc_iso
    from ..adapters.manifests import sha256_file
    tok = guard.authorize_read(REGISTERED_RESEARCH_DB, "0001-01-01", DEV_END, "sic_observations",
                               "orchestrator", allow_pre_window=True)
    rows = src.execute(
        "select cik, accepted_utc, sic, accession from sic_observations where cik = ANY($c) "
        "and cast(accepted_utc as date) <= $b", {"c": ciks, "b": DEV_END}).fetchall()
    by: dict[int, list] = {}
    norm = []
    for cik, a, s, acc in rows:
        ts = normalize_utc_iso(a)
        by.setdefault(int(cik), []).append((ts, str(s), str(acc)))
        norm.append([str(cik), ts, str(s), str(acc)])   # full timestamp + accession
    norm.sort()
    guard.record_completed_read(tok, sha256_file(abs_path(REGISTERED_RESEARCH_DB)),
                                "sic_observations[cik,accepted_utc,sic,accession]", None,
                                max((r[1] for r in norm), default=None), len(rows),
                                canonical_sha256(norm), "", allow_pre_window=True)
    return by


def _snap_ledger(guard, snap_path, snap_sha, purpose, rows_for_hash, row_count, max_key):  # noqa: ANN001
    """Record a bounded bulk read of the (registered) development snapshot object."""
    tok = guard.authorize_read(snap_path, "0001-01-01", DEV_END, purpose, "orchestrator",
                               allow_pre_window=True)
    guard.record_completed_read(tok, snap_sha, f"snapshot:{purpose}", None, max_key, row_count,
                                canonical_sha256(rows_for_hash), "", allow_pre_window=True)


def _date_ord(cal, date_str, default):  # noqa: ANN001
    d = str(date_str)[:10]
    if d < cal.sessions[0]:
        return 0 if default == "lo" else -1
    if d > cal.sessions[-1]:
        return len(cal) if default == "hi" else len(cal) - 1
    lo, hi = 0, len(cal) - 1
    while lo < hi:                       # first session on/after d
        mid = (lo + hi) // 2
        if cal.sessions[mid] < d:
            lo = mid + 1
        else:
            hi = mid
    return lo


def resolve_cik_at(cik_timeline, t):  # noqa: ANN001
    """PIT CIK for session ordinal t from the registered crosswalk intervals (no unordered LIMIT 1).
    Overlapping intervals with conflicting CIK fail closed SECURITY_IDENTITY_AMBIGUOUS."""
    active = [c for (lo, hi, c) in cik_timeline if lo <= t and (hi is None or t < hi)]
    if not active:
        raise refuse("INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS", f"no CIK effective at session {t}")
    if len(set(active)) != 1:
        raise refuse("INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS",
                     f"conflicting CIKs {sorted(set(active))} at session {t}")
    return active[0]


def build_context(snapshot_con, guard, tickers, ciks, sic_map_con, snap_path="", snap_sha=""):  # noqa: ANN001
    cal = load_calendar(snapshot_con)
    _snap_ledger(guard, snap_path, snap_sha, "calendar", list(cal.sessions), len(cal), cal.sessions[-1])
    spy_levels = load_spy_adjclose(snapshot_con, cal)
    _snap_ledger(guard, snap_path, snap_sha, "spy", [f"{v}" for v in spy_levels],
                 int(np.isfinite(spy_levels).sum()), cal.sessions[-1])
    spy = arithmetic_total_returns(spy_levels)
    sic_map = _guarded_load_sic_map(sic_map_con, guard)
    sic_obs_by_cik = _guarded_sic_obs(sic_map_con, guard, ciks)
    # sector returns keyed by research_sector via its ETF (one bulk etf_prices read, ledgered)
    etf_rows = snapshot_con.execute('select ticker, "date", adjclose from etf_prices').fetchall()
    _snap_ledger(guard, snap_path, snap_sha, "sector_etfs",
                 sorted([str(r) for r in etf_rows]), len(etf_rows),
                 max((str(r[1]) for r in etf_rows), default=None))
    etf_by_sector: dict[str, str] = {r.research_sector: r.sector_etf for r in sic_map}
    etf_series: dict[str, dict[str, float]] = {}
    for tk, d, v in etf_rows:
        etf_series.setdefault(str(tk), {})[str(d)] = float(v)
    sector_ret: dict[str, np.ndarray] = {}
    for sector, etf in etf_by_sector.items():
        by = etf_series.get(etf, {})
        arr = np.array([by.get(s, np.nan) for s in cal.sessions], dtype=np.float64)
        sector_ret[sector] = arithmetic_total_returns(arr)
    # crosswalk (bulk, ledgered) -> per-symbol CIK timeline + the PIT lineage registry
    cw = snapshot_con.execute("select ticker, cik, effective_from, effective_to from crosswalk").fetchall()
    _snap_ledger(guard, snap_path, snap_sha, "crosswalk", sorted([str(r) for r in cw]), len(cw), None)
    cik_timeline: dict[str, list] = {}
    for tk, cik, eff_from, eff_to in cw:
        cik_timeline.setdefault(str(tk), []).append(
            (_date_ord(cal, eff_from, "lo"), None if eff_to is None else _date_ord(cal, eff_to, "hi"),
             int(cik)))
    lineage = load_identity_registry(snapshot_con, cal)
    securities: dict[str, dict] = {}
    for tk in tickers:
        try:
            series = load_price_series(snapshot_con, tk, cal)
        except SignalRefusal:
            continue
        close = series["closeadj"]
        present = np.isfinite(close)
        if not present.any():
            continue
        _snap_ledger(guard, snap_path, snap_sha, f"prices:{tk}", [f"{v}" for v in close],
                     int(present.sum()), cal.sessions[-1])
        first = int(np.argmax(present))
        status = [CellStatus.PRESENT if present[i] else
                  (CellStatus.YOUNG if i < first else CellStatus.UNEXPLAINED_HOLE)
                  for i in range(len(cal))]
        securities[tk] = {"symbol": tk, "stock_ret": arithmetic_total_returns(close),
                          "status": status, "raw_close": series["closeunadj"],
                          "raw_volume": series["volume"], "cik_timeline": cik_timeline.get(tk, [])}
    # earnings evidence (bulk, ledgered) for the authorized CIK set
    ea = snapshot_con.execute(
        "select cik, accession, acceptance_utc, event_time_basis, cooling_start_session, "
        "cooling_end_session from earnings_anchors where cast(cik as bigint) = ANY($c)",
        {"c": ciks}).fetchall()
    _snap_ledger(guard, snap_path, snap_sha, "earnings", sorted([str(r) for r in ea]), len(ea), None)
    earnings_by_cik: dict[int, list] = {}
    for row in ea:
        earnings_by_cik.setdefault(int(row[0]), []).append(row[1:])
    return RunContext(snapshot_con, cal, spy, sector_ret, _registry(cal), lineage, sic_map,
                      securities, sic_obs_by_cik, earnings_by_cik, guard.ledger)


def _earnings_checks(rows, session_date):  # noqa: ANN001
    """In-memory earnings-blackout ExclusionChecks (mirrors the Phase-2A adapter; no per-unit DB read)."""
    from ..adapters import normalize_utc_iso
    from ..eligibility import ExclusionCheck
    out = []
    for accession, acceptance_utc, basis, cool_start, cool_end in rows:
        excludes = (cool_start is not None and cool_end is not None
                    and str(cool_start) <= session_date <= str(cool_end))
        out.append(ExclusionCheck(
            rule_id=f"EARN-BLACKOUT:{accession}", precedence_category="event_blackout",
            excludes=excludes, observed_value=f"basis={basis};window={cool_start}..{cool_end}",
            threshold="no earnings within [t+1 open, session-6 open]",
            source_identity=f"earnings_anchor:{accession}",
            availability_timestamp=normalize_utc_iso(acceptance_utc), evidence_present=True))
    return out


def _registry(cal):  # noqa: ANN001
    from ..identities import InputIdentityRegistry
    ids = dict(_OBS_IDS)
    ids["registered_exchange_calendar"] = cal.identity
    ids.update({"producer_code_version": PRODUCER_CODE_VERSION,
                "rule_census_identity": PHASE0_CENSUS_SHA256,
                "owner_rulings_identity": PHASE0_OWNER_RULINGS_SHA256,
                "schema_identity": PHASE0_SCHEMA_SHA256})
    return InputIdentityRegistry(ids)


def run_unit(ctx: RunContext, symbol: str, t: int) -> UnitResult:
    """Resolve identity + CIK AT the decision session t (PIT); no end-of-window resolution."""
    sec = ctx.securities[symbol]
    close_t_iso = et_close_cutoff_iso(ctx.calendar.sessions[t])
    permsec = ""
    try:
        permsec = ctx.lineage.resolve_permanent_id(symbol, t)           # PIT identity @ t
        cik = resolve_cik_at(sec["cik_timeline"], t)                    # PIT CIK @ t
        sector = resolve_sector(ctx.sic_map, ctx.sic_obs_by_cik.get(cik, []), close_t_iso)
        if sector.sector_id not in ctx.sector_ret:
            sector_etf(ctx.sic_map, sector.sector_id)  # raises if unmapped
        obs: dict[str, str] = {
            k: (ctx.calendar.identity if k == "registered_exchange_calendar" else v)
            for k, v in _OBS_IDS.items()}
        market = MarketData(ctx.calendar, ctx.spy_ret, ctx.sector_ret, obs)
        checks = _earnings_checks(ctx.earnings_by_cik.get(cik, []), ctx.calendar.sessions[t])
        secdata = SecurityData(symbol, sec["stock_ret"], sec["status"],
                               sec["raw_close"], sec["raw_volume"], [sector], checks)
        req = ProductionRequest("MR-002", "B", "LONG", t, close_t_iso)
        rec = produce_decision(market, secdata, ctx.registry, ctx.lineage, req)
        return UnitResult(permsec, symbol, t, EMITTED, None,
                          rec.decision_eligibility_status, rec.record_identity)
    except SignalRefusal as e:
        return UnitResult(permsec, symbol, t, DISPOSITION_BY_CLASS[e.code_class], e.code, None, None)


def run_shard(ctx: RunContext, units: list[tuple[str, int]]) -> tuple[list[UnitResult], str]:
    results = [run_unit(ctx, symbol, t) for symbol, t in units]
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
                          ledger: OpenedObjectLedger):  # noqa: ANN001, ANN201
    import duckdb
    # the dev snapshot is a registered dev-only object; its reads are guarded + ledgered too.
    guard = PartitionGuard(REGISTERED | frozenset({out_path}), ledger)
    snap = DS.materialize(duckdb, out_path, tickers, ETF_TICKERS, ciks, guard, "orchestrator")
    con = duckdb.connect(out_path, read_only=True)
    src = duckdb.connect(_abs(REGISTERED_RESEARCH_DB), read_only=True)  # sic_mapping/sic_obs source
    return con, guard, src, out_path, snap.content_sha256


def _abs(rel: str) -> str:
    from ..adapters import abs_path
    return abs_path(rel)
