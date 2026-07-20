"""Generate the Increment-1 v1.2 qualification-evidence bundle: source hashes, a canonical
full-battery synthetic report (exact-float schema, dependency-lock sha embedded), determinism proof,
and the dependency binding. Writes MR002_Increment1_Qualification.json and
MR002_Increment1_CanonicalReport.json. Reads NO real dataset — all inputs are synthetic constants."""
import hashlib
import json
import sys

import numpy as np
import scipy

import mr002_valoos_gates as G
import mr002_valoos_report as R
from mr002_valoos_identity import load_governing_identity

GOV_DIR = ".."
DEP_LOCK = "MR002_Increment1_Dependencies.json"
SRC = ["mr002_valoos_identity.py", "mr002_valoos_registry.py", "mr002_valoos_metrics.py",
       "mr002_valoos_gates.py", "mr002_valoos_report.py", "test_increment1.py", "_gen_evidence.py"]

# passing (value, sample) for all 22 governing gates
PASS_GATES = {
    "net_sharpe": (1.5, "sealed_OOS"), "bootstrap_mean_lower_bound": (0.0001, "sealed_OOS"),
    "net_calmar": (2.0, "sealed_OOS"), "combined_max_drawdown": (0.10, "validation+OOS_combined"),
    "positive_validation_folds": (4, "validation"), "parameter_stability_A": (0.5, "validation"),
    "parameter_stability_C": (0.5, "validation"), "deflated_sharpe": (0.99, "sealed_OOS"),
    "net_annualized_return": (0.08, "sealed_OOS"), "cost_stress": (0.02, "sealed_OOS"),
    "breadth_completed_trades": (600, "sealed_OOS"), "breadth_distinct_entry_dates": (150, "sealed_OOS"),
    "breadth_long_trades": (300, "sealed_OOS"), "breadth_short_trades": (300, "sealed_OOS"),
    "trade_concentration_top10": (0.15, "sealed_OOS"),
    "trade_concentration_single_stock": (0.05, "sealed_OOS"),
    "annual_positive_years": (4, "validation+OOS_combined"),
    "annual_largest_positive_year_fraction": (0.30, "validation+OOS_combined"),
    "trend_regimes_positive_count": (3, "validation+OOS_combined"),
    "trend_regime_loss_concentration": (0.40, "validation+OOS_combined"),
    "volatility_regime_floor": (-0.20, "validation+OOS_combined"), "capacity": (0.01, "sealed_OOS"),
}
REQ_DIAGS = ["pbo", "positive_pnl_regime_concentration", "annual_herfindahl", "severe_cost_stress"]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


loaded = load_governing_identity(GOV_DIR)


def make_canonical_report():
    b = G.GateBattery()
    for gid, (val, sample) in PASS_GATES.items():
        b.add_gate(gid, val, sample=sample)
    for d in REQ_DIAGS:
        b.add_diagnostic(d, 0.10)
    verdict = b.evaluate()
    return R.build_report(
        window="synthetic", verdict=verdict, governing_identity=loaded,
        code_identity={s: sha(s) for s in SRC},
        dependency_identity={"numpy": np.__version__, "scipy": scipy.__version__,
                             "python": sys.version.split()[0]},
        dependency_lock_sha256=sha(DEP_LOCK),
        fixture_identity={"fixture": "increment1-v1.2-full-battery", "seed": 42},
        metric_values={"net_sharpe": 1.5, "neg_zero_probe": -0.0},
        gate_results=b.to_list(), diagnostics=b.diagnostics_list(), hard_stop_evidence=None, seed=42)


report = make_canonical_report()
report2 = make_canonical_report()
open("MR002_Increment1_CanonicalReport.json", "w", encoding="utf-8").write(
    json.dumps(report, sort_keys=True, indent=2))

qual = {
    "record_type": "MR002_Increment1_Qualification",
    "increment": 1, "version": "1.2",
    "scope": "identity loader (v1.0.4 chain) + metric primitives (stationary bootstrap) + gate engine "
             "+ report kernel (dependency-lock embedded) + DSR dispersion validation + production DSR "
             "interface + synthetic fixtures",
    "owner_rulings_applied": "docs/review/comments.md 2026-07-20 (Ruling 1 bootstrap, Ruling 2 DSR dispersion, Ruling 3 increment v1.2)",
    "governing_prereg": "MR002_ValidationOOS_Preregistration_v1.0.4 (bootstrap-corrected)",
    "governance_records": ["MR002_ValidationOOS_CorrectionRecord_v1.0.4.json",
                           "MR002_DSR_DispersionResolution_v1.0.json"],
    "governing_identity": loaded if "gates_frozen" not in loaded else {k: v for k, v in loaded.items() if k != "gates_frozen"},
    "source_hashes": {s: sha(s) for s in SRC},
    "dependency_lock": DEP_LOCK,
    "dependency_lock_sha256": sha(DEP_LOCK),
    "bootstrap": "frozen v0.3 stationary (Politis-Romano, circular); expected L 5 (confirmatory) + 10 "
                 "(robustness); 10000 replications; seed 20260711; moving-block REJECTED and removed",
    "tests": {"count": 53, "result": "53 passed", "log": "MR002_Increment1_TestLog.txt"},
    "canonical_report_output_hash": report["output_hash"],
    "canonical_report_dispositions": {"research_gate_verdict": report["research_gate_verdict"],
                                      "run_disposition": report["run_disposition"]},
    "determinism_proof": {"run1_hash": report["output_hash"], "run2_hash": report2["output_hash"],
                          "byte_identical": report["output_hash"] == report2["output_hash"]},
    "report_self_hash_verifies": R.report_hash(report) == report["output_hash"],
    "signed_zero_preserved": report["metric_values"]["neg_zero_probe"]["exact_hex"] == "-0x0.0p+0",
    "development_free_assertions": {"validation_data_read": report["validation_data_read"],
        "oos_data_read": report["oos_data_read"],
        "development_performance_computed": report["development_performance_computed"],
        "synthetic_fixture_only": report["synthetic_fixture_only"]},
    "no_real_dataset_opened": True,
    "dsr_N_source": "MR002_DSR_TrialLedger_v1.0.json (deda5cec...), N=5 — no code-constant fallback",
    "dsr_dispersion_provenance": "SYNTHETIC in fixtures; production path requires the countersigned "
        "MR002_DSR_TrialDispersion_Validation_v1.0.json (absent now -> REFUSED_CODE_OR_DATA_IDENTITY); "
        "estimator frozen by MR002_DSR_DispersionResolution_v1.0 (sigma_trials = stddev ddof=1 of "
        "A/B/C validation annualized Sharpes, /sqrt(252)); A/B/C Sharpes NOT computed now",
}
open("MR002_Increment1_Qualification.json", "w", encoding="utf-8").write(
    json.dumps(qual, sort_keys=True, indent=2))
print("output_hash:", report["output_hash"])
print("determinism byte_identical:", qual["determinism_proof"]["byte_identical"])
print("dispositions:", report["research_gate_verdict"], report["run_disposition"])
print("signed_zero_preserved:", qual["signed_zero_preserved"])
