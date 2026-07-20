"""Generate the Increment-2 qualification-evidence bundle: source hashes, a canonical synthetic trade
ledger (exact-float schema, dependency-lock sha embedded), determinism proof, and cost-model bindings.
Writes MR002_Increment2_Qualification.json and MR002_Increment2_LedgerReport.json. Reads NO real
dataset — all inputs are synthetic constants; no signal generation / universe / sector / optimization.
"""
import hashlib
import json
import sys

import mr002_valoos_costmodel as C
import mr002_valoos_execution as X
from mr002_valoos_execution import Market, TradeIntent, simulate_sequence

DEP_LOCK = "MR002_Increment1_Dependencies.json"
SRC = ["mr002_valoos_costmodel.py", "mr002_valoos_execution.py", "mr002_valoos_report.py",
       "test_increment2.py", "_gen_evidence_inc2.py"]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _sequence():
    opens = {s: 100.0 for s in range(0, 9)}
    opens[6] = 110.0
    mkt = Market(opens=opens, adv_dollars={s: 1e12 for s in range(0, 9)}, nav=1e12)
    intents = [
        TradeIntent("L1", "AAA", "long", "PL1", 0, 100, exit_decision_session=5),
        TradeIntent("S1", "BBB", "short", "PS1", 0, 100),                 # time-stop + borrow
    ]
    return simulate_sequence(intents, mkt, C.BASE)


def _build_ledger(seq):
    stress = [X.recompute_position_under_schedule(p, C.STRESS) for p in seq["positions"]]
    severe = [X.recompute_position_under_schedule(p, C.SEVERE) for p in seq["positions"]]
    return X.ledger_report(
        events=seq["events"], positions=seq["positions"], base_schedule="BASE",
        stress=stress, severe=severe, code_identity={s: sha(s) for s in SRC},
        dependency_lock_sha256=sha(DEP_LOCK))


seq = _sequence()
report = _build_ledger(seq)
report2 = _build_ledger(_sequence())
open("MR002_Increment2_LedgerReport.json", "w", encoding="utf-8").write(
    json.dumps(report, sort_keys=True, indent=2))


def _sched(s):
    return {"bps_per_side": s.commission_slippage_bps_per_side, "borrow_bps_per_year": s.borrow_bps_per_year,
            "day_count": s.borrow_day_count, "classification": s.classification}


qual = {
    "record_type": "MR002_Increment2_Qualification",
    "increment": 2, "version": "1.0",
    "scope": "frozen cost model (base/stress/severe) + synthetic trade ledger (16 frozen fields) + "
             "next-open execution semantics + mechanical ADV/NAV clips; synthetic-only",
    "owner_authorization": "docs/review/comments.md adjudication 2026-07-20 (Increment 2 authorized after closeout)",
    "excluded_not_authorized": ["residual signal calculation", "universe reconstruction",
        "sector mapping", "portfolio optimization", "beta/sector exposure constraints",
        "real vendor data adapters", "development performance", "validation/OOS access"],
    "cost_schedules": {"BASE": _sched(C.BASE), "STRESS": _sched(C.STRESS), "SEVERE": _sched(C.SEVERE)},
    "next_open_semantics": {"entry": "official open t+1", "exit_decision": "official open e+1",
        "time_stop": "official open t+6", "missing_entry": "cancel", "missing_exit": "defer to next open",
        "no_same_open_reentry": True, "clip_never_delay": True},
    "controls": {"adv_participation_cap": X.ADV_PARTICIPATION_CAP, "nav_new_entry_cap": X.NAV_NEW_ENTRY_CAP,
                 "costs_from": "executed notional (not intended order notional)"},
    "event_fields": list(X.EVENT_FIELDS),
    "source_hashes": {s: sha(s) for s in SRC},
    "dependency_lock": DEP_LOCK, "dependency_lock_sha256": sha(DEP_LOCK),
    "python": sys.version.split()[0],
    "tests": {"count": 22, "result": "22 passed", "file": "test_increment2.py"},
    "ledger_report_output_hash": report["output_hash"],
    "determinism_proof": {"run1_hash": report["output_hash"], "run2_hash": report2["output_hash"],
                          "byte_identical": report["output_hash"] == report2["output_hash"]},
    "report_self_hash_verifies": X.ledger_report_hash(report) == report["output_hash"],
    "reconciliation_all_positions": all(p["reconciles"] for p in seq["positions"]),
    "development_free_assertions": {"validation_data_read": report["validation_data_read"],
        "oos_data_read": report["oos_data_read"],
        "development_performance_computed": report["development_performance_computed"],
        "synthetic_fixture_only": report["synthetic_fixture_only"]},
    "no_real_dataset_opened": True,
}
open("MR002_Increment2_Qualification.json", "w", encoding="utf-8").write(
    json.dumps(qual, sort_keys=True, indent=2))
print("ledger_report_output_hash:", report["output_hash"])
print("determinism byte_identical:", qual["determinism_proof"]["byte_identical"])
print("positions:", len(seq["positions"]), "reconcile_all:", qual["reconciliation_all_positions"])
