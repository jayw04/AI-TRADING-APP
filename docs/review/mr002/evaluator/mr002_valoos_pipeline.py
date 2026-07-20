"""MR-002 Increment 3 — synthetic portfolio-to-metrics pipeline (synthetic only).

Orchestrates the per-session replay -> official-open daily NAV/return series -> Increment-1 metric
primitives, and emits a canonical exact-float report. The PORTFOLIO return series (not a helper
series) is what is passed to the Increment-1 interfaces. Reads no real data; computes no
residual/z/sigma; records synthetic_fixture_only=true.
"""

from __future__ import annotations

import hashlib

import mr002_valoos_metrics as M
import mr002_valoos_report as R
from mr002_valoos_nav import daily_nav_record, return_series
from mr002_valoos_portfolio_state import PortfolioState
from mr002_valoos_replay import process_session

SCHEMA_VERSION = "increment3-v1.0-synthetic"


def run_replay(sessions: list, *, initial_cash: float, config_id: str, warmup_nav=None) -> dict:
    """sessions: ordered [{session, date, opens, adv, candidate_records, exit_signals}]. Returns the
    per-session results, daily NAV records, portfolio return series, and final state. A REFUSED session
    leaves the committed state unchanged (atomicity) and does not advance the NAV series."""
    first = sessions[0]["session"]
    state = PortfolioState(session=first - 1, cash=initial_cash)
    nav_prev = initial_cash if warmup_nav is None else warmup_nav
    results, nav_records = [], []
    for sess in sessions:
        res = process_session(state, candidate_records=sess["candidate_records"],
                              exit_signals=sess.get("exit_signals", []),
                              market={"session": sess["session"], "date": sess["date"],
                                      "opens": sess["opens"], "adv": sess["adv"]},
                              config_id=config_id)
        results.append(res)
        if res["disposition"] == "COMMITTED":
            state = res["committed_state"]
            rec = daily_nav_record(session=sess["session"], cash=state.cash, held=state.held,
                                   opens_s=sess["opens"], nav_prev=nav_prev)
            nav_records.append(rec)
            nav_prev = rec["nav"]
    return {"results": results, "nav_records": nav_records,
            "return_series": return_series(nav_records), "final_state": state}


def metric_handoff(returns: list) -> dict:
    """Feed the PORTFOLIO daily return series into the Increment-1 metric primitives. Returns the
    metrics plus the exact input-series identity so the qualification can prove the same series was
    passed (not a separately constructed helper)."""
    out = {"input_series_len": len(returns),
           "input_series_exact_hex": [float(r).hex() for r in returns],
           "label": "SYNTHETIC_INTERFACE_QUALIFICATION_ONLY",
           "note": "Metric values (incl. any gate_pass / confirmatory_gate_pass flags) are interface "
                   "wiring proof on a synthetic fixture, NOT an MR-002 research-gate outcome."}
    if len(returns) >= 1:
        try:
            out["geometric_annualized_return"] = M.geometric_annualized_return(returns)
            out["compounded_max_drawdown"] = M.compounded_max_drawdown(returns)
            out["calmar"] = M.calmar(returns)
        except M.IntegrityStop as e:
            out["metric_stop"] = str(e)
    if len(returns) >= 2:
        out["stationary_bootstrap_confirmatory"] = M.stationary_bootstrap_confirmatory(returns)
    return out


def build_pipeline_report(*, replay: dict, metrics: dict, identity: dict, config_id: str,
                          code_identity: dict, dependency_lock_sha256: str) -> dict:
    """Canonical, exact-float, deterministic Increment-3 report (reuses the Increment-1 canonicalizer:
    signed-zero preserved, non-finite refuses)."""
    record = {
        "record_type": "MR002_ValOOS_PortfolioReplay",
        "schema_version": SCHEMA_VERSION,
        "config_id": config_id,
        "research_gate_verdict": "NOT_EVALUATED_SYNTHETIC",
        "performance_interpretation_authorized": False,
        "governing_registry_identity": identity.get("registry_sha256"),
        "governing_resolution_identity": identity.get("resolution_sha256"),
        "governing_source_identities": identity.get("source_shas"),
        "sessions": [{"session": r["session"], "disposition": r["disposition"], "stop_code": r["stop_code"],
                      "events": r["events"], "intended": r["intended"], "removal_events": r["removal_events"],
                      "drift_repair": r.get("drift_repair"), "exposure": r["exposure"],
                      "atomicity_committed": r["atomicity_committed"]} for r in replay["results"]],
        "nav_records": replay["nav_records"],
        "return_series": replay["return_series"],
        "metrics": metrics,
        "code_identity": code_identity,
        "dependency_lock_sha256": dependency_lock_sha256,
        "validation_data_read": False,
        "oos_data_read": False,
        "development_performance_computed": False,
        "synthetic_fixture_only": True,
    }
    canonical = R._canonicalize(record)
    canonical["output_hash"] = hashlib.sha256(R._serialize(canonical)).hexdigest()
    return canonical


def report_hash(record: dict) -> str:
    return hashlib.sha256(R._serialize({k: v for k, v in record.items() if k != "output_hash"})).hexdigest()
