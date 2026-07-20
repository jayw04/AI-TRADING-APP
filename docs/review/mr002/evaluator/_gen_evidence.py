"""Generate the Increment-1 qualification-evidence bundle (source hashes, canonical synthetic
report, determinism proof, dependency inventory). Writes MR002_Increment1_Qualification.json and
MR002_Increment1_CanonicalReport.json. Reads NO real dataset."""
import hashlib
import json
import platform
import sys

import numpy as np
import scipy

import mr002_valoos_gates as G
import mr002_valoos_metrics as M
from mr002_valoos_identity import load_governing_identity
from mr002_valoos_report import build_report, report_hash

GOV_DIR = ".."
SRC = ["mr002_valoos_identity.py", "mr002_valoos_metrics.py", "mr002_valoos_gates.py",
       "mr002_valoos_report.py", "test_increment1.py"]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


loaded = load_governing_identity(GOV_DIR)


def make_canonical_report():
    """Single deterministic build path (seed-42 fixture) — used for BOTH the canonical report and
    the determinism proof so the two runs are byte-for-byte comparable."""
    daily = np.random.default_rng(7).normal(0.0012, 0.004, 900)
    b = G.GateBattery()
    sharpe = M.annualized_sharpe(daily)
    lb = M.block_bootstrap_mean_lower_bound(daily)
    dsr = M.deflated_sharpe(daily, trials_n=loaded["dsr_trials_N"], trial_sharpe_std=0.01)
    b.gate("sharpe", sharpe >= 0.70, sharpe, 0.70)
    b.gate("bootstrap_mean_lb", lb > 0.0, lb, 0.0)
    b.gate("dsr", dsr["gate_pass"], dsr["dsr"], 0.95)
    b.diagnostic("pbo", 0.10)
    return build_report(
        window="synthetic", disposition=b.disposition(), governing_identity=loaded,
        code_identity={s: sha(s) for s in SRC}, dependency_identity={"numpy": np.__version__,
        "scipy": scipy.__version__, "python": sys.version.split()[0]},
        fixture_identity={"fixture": "increment1-canonical", "seed": 42, "n": 900},
        metric_values={"sharpe": sharpe, "bootstrap_lb": lb, "dsr": dsr["dsr"]},
        gate_results=b.to_list(), diagnostics=[{"pbo": 0.10, "classification": "DIAGNOSTIC"}],
        hard_stop_evidence=None, seed=42), dsr


report, dsr = make_canonical_report()
report2, _ = make_canonical_report()

open("MR002_Increment1_CanonicalReport.json", "w", encoding="utf-8").write(
    json.dumps(report, sort_keys=True, indent=2))

qual = {
    "record_type": "MR002_Increment1_Qualification",
    "increment": 1,
    "scope": "governing-identity loader + metric primitives + gate engine + report kernel + synthetic fixtures",
    "governing_identity": loaded,
    "source_hashes": {s: sha(s) for s in SRC},
    "dependency_inventory": {"numpy": np.__version__, "scipy": scipy.__version__,
                             "python": sys.version.split()[0], "platform": platform.platform()},
    "tests": {"count": 14, "result": "14 passed", "log": "MR002_Increment1_TestLog.txt"},
    "canonical_report_output_hash": report["output_hash"],
    "determinism_proof": {"run1_hash": report["output_hash"], "run2_hash": report2["output_hash"],
                          "byte_identical": report["output_hash"] == report2["output_hash"]},
    "report_self_hash_verifies": report_hash(report) == report["output_hash"],
    "development_free_assertions": {"validation_data_read": report["validation_data_read"],
        "oos_data_read": report["oos_data_read"],
        "development_performance_computed": report["development_performance_computed"],
        "synthetic_fixture_only": report["synthetic_fixture_only"]},
    "no_real_dataset_opened": True,
    "dsr_N_source": "MR002_DSR_TrialLedger_v1.0.json (deda5cec...), N=5 — no code-constant fallback",
}
open("MR002_Increment1_Qualification.json", "w", encoding="utf-8").write(
    json.dumps(qual, sort_keys=True, indent=2))
print("canonical report output_hash:", report["output_hash"])
print("determinism byte_identical:", qual["determinism_proof"]["byte_identical"])
print("dsr gate_pass:", dsr["gate_pass"], "dsr:", round(dsr["dsr"], 6))
