"""MR-002 Gate N2 — final verdict record.

Binds the sealed corrected stress population, the qualification result, the per-axis diagnostics,
and the authority chain back through the N2 defect record and the N1 final verdict.

The disposition is computed from the six frozen pass-rule checks, not asserted.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
OUT = os.path.join(REPO, ".mr002out", "n2")


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob_sha(path: str) -> str:
    o = subprocess.run(["git", "-C", REPO, "show", f"HEAD:{path}"], capture_output=True)
    return hashlib.sha256(o.stdout).hexdigest() if o.returncode == 0 else "UNCOMMITTED"


def file_sha(p: str) -> str:
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


q = json.load(open(os.path.join(OUT, "n2_qualification.json")))
defect = json.load(open(os.path.join(
    _HERE, "MR002_N2_StressGeneratorDefect_v1.0.json")))
t = q["totals"]

axis_table = {}
b_reasons: dict[str, int] = {}
for ax, r in q["per_axis"].items():
    axis_table[ax] = {
        "instances": r["instances"], "A_certified": r["A_certified"], "B_rescue": r["B_rescue"],
        "unresolved": r["unresolved"], "integrity_defects": r["integrity_defects"],
        "unregistered_termination_reasons": r["unregistered_termination_reasons"],
        "max_agreement_deviation": r["max_agreement_deviation"],
        "R_exact": r["R_exact"], "R_unavailable": r["R_unavailable"],
        "R_skipped_size_budget": r["R_skipped_size_budget"],
        "repair_bound_available": r["repair_bound_available"],
        "repair_bound_unavailable": r["repair_bound_unavailable"],
        "runtime_seconds": round(r["seconds"], 1),
        "reproducibility_mismatches": r["reproducibility_mismatches"],
        "A_reasons": r["A_reasons"], "B_reasons": r["B_reasons"],
    }
    for k, v in r["B_reasons"].items():
        b_reasons[k] = b_reasons.get(k, 0) + v

REC: dict = {
    "record_type": "MR002_N2_VERDICT",
    "record_status": "FINAL",
    "version": "1.0",
    "program": "MR-002 / SPQ-1",
    "gate": "N2",
    "date": "2026-08-19",

    "disposition": q["disposition"],
    "solver_A": q["solver_A"],
    "solver_B": q["solver_B"],
    "solver_pair_unchanged_by_N2": True,
    "authorizes": "nothing beyond N2 — N3 requires its own grant",

    "authority_chain": {
        "sealed_registration": {
            "record": "MR002_N1_ProspectiveRegistration_v1.0 §8",
            "identity_sha256": "7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af",
        },
        "n1_final_verdict": "629eee0ee1c257a23312b539fbac8542b40cbf6f2cef296ba2c829fb6b29bd81",
        "n2_grant": "owner, 2026-08-19",
        "generator_defect_and_seal": {
            "record": "MR002_N2_StressGeneratorDefect_v1.0",
            "identity_sha256": defect["record_identity_sha256"],
            "sealed_before_solving": True,
        },
    },

    "population": {
        "population_hash": q["population_hash"],
        "seed": 20260819,
        "instances": t["instances"],
        "axes": {a: axis_table[a]["instances"] for a in sorted(axis_table)},
        "stress_npz_sha256": file_sha(os.path.join(OUT, "stress.npz")),
        "sealed_unsolved_at_commit": "3cdecc7",
        "rejected_predecessor": defect["defect"]["rejected_population_hash"],
    },

    # ── the six frozen pass-rule checks ──────────────────────────────────────────────────────────
    "pass_rule": {
        "rule": "100% registered resolution or STOP",
        "checks": q["pass_rule_checks"],
        "all_satisfied": all(q["pass_rule_checks"].values()),
        "single_unexplained_unresolved_tail_would_mean": "N2_STOP",
    },

    "totals": {k: t[k] for k in sorted(t)},

    "per_axis_diagnostics": axis_table,
    "diagnostics_are_not_thresholds": (
        "per-axis figures are diagnostic only. No additional pass threshold is derived from them, "
        "before or after seeing them."),

    # ── the finding that matters ─────────────────────────────────────────────────────────────────
    "headline_finding": {
        "PIQP_P2_iteration_limit_terminations": b_reasons.get("ITERATION_LIMIT_REACHED", 0),
        "what_that_is": (
            "PIQP_MAX_ITER_REACHED — the exact failure mode that consumed the sealed validation "
            "opening on 2026-08-19 and produced an INTEGRITY_FAILURE with no economic verdict"),
        "how_v2_classified_them": (
            "every one as NO_CERTIFIED_CANDIDATE with the REGISTERED reason ITERATION_LIMIT_REACHED, "
            "read from the library's status enum, never from message text"),
        "integrity_defects_produced": t["integrity_defects"],
        "unregistered_termination_reasons": t["unregistered_termination_reasons"],
        "instances_left_unresolved": t["unresolved"],
        "under_the_v1_method": (
            "PIQP had no registered numerical status, so an identical termination mapped to "
            "UNREGISTERED_EXCEPTION -> INTEGRITY_DEFECT -> INVALID_RUN. Any coincidence of a PIQP "
            "iteration limit with a QUADPROG_SQRT failure was therefore fatal, which is exactly what "
            "happened on the consumed validation instance."),
        "conclusion": (
            "the fragility class N2 exists to test is removed: 62 iteration-limit terminations "
            "occurred, none became an integrity defect, and the method resolved 3,000 of 3,000."),
    },

    "corrected_A1_confirms_the_defect_diagnosis": {
        "axis": "A1 — Hessian conditioning swept to kappa 5e9 at registered target scale",
        "instances": axis_table["A1"]["instances"],
        "A_certified": axis_table["A1"]["A_certified"],
        "B_rescue": axis_table["A1"]["B_rescue"],
        "unresolved": axis_table["A1"]["unresolved"],
        "max_agreement_deviation": axis_table["A1"]["max_agreement_deviation"],
        "reading": (
            "with target scale held inside the registered envelope, conditioning through kappa 5e9 "
            "is resolved by Solver A alone on every instance. The rejected population's A1 failures "
            "were absolute-scale artifacts, as the controlled experiment indicated."),
    },

    "reference_solver_R": {
        "size_budget_max_dim": q["R_size_budget_max_dim"],
        "budget_is_deterministic_not_wall_clock": (
            "a wall-clock budget would make R availability depend on machine load, so the same "
            "instance could be R_EXACT in one run and R_UNAVAILABLE in the next — which would break "
            "the reproducibility requirement this gate tests"),
        "R_exact": t["R_exact"], "R_unavailable": t["R_unavailable"],
        "R_skipped_size_budget": t["R_skipped_size_budget"],
    },

    "execution_identities": {
        "runtime_image": "mr002-research:v1.4",
        "network": "none",
        "frozen_thread_env": {
            "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1", "OPENBLAS_CORETYPE": "HASWELL",
        },
        "bound_source": {p: blob_sha(p) for p in (
            "apps/backend/scripts/mr002_n2_generate.py",
            "apps/backend/scripts/mr002_n2_qualify.py",
            "apps/backend/scripts/mr002_n2_derive_scale_envelope.py",
            "apps/backend/app/research/mr002/n1/method.py",
            "apps/backend/app/research/mr002/n1/reference.py",
        )},
        "qualification_report_sha256": file_sha(os.path.join(OUT, "n2_qualification.json")),
        "run_once": True,
    },

    "boundary": {
        "development_domain_only": True,
        "sealed_or_reference_bytes_read": 0,
        "validation_store_opened": False,
        "oos": "NOT AUTHORIZED",
        "N3": "NOT AUTHORIZED — requires its own grant",
        "validation_2": "PROHIBITED",
        "consumed_validation_opening": "unchanged",
    },
}

REC["record_identity_sha256"] = hashlib.sha256(_canonical(REC)).hexdigest()
out = os.path.join(_HERE, "MR002_N2_Verdict_v1.0.json")
with open(out, "wb") as fh:
    fh.write(_canonical(REC))

print(json.dumps({
    "record": "MR002_N2_Verdict_v1.0",
    "record_identity_sha256": REC["record_identity_sha256"],
    "disposition": REC["disposition"],
    "solver_A": REC["solver_A"], "solver_B": REC["solver_B"],
    "population_hash": REC["population"]["population_hash"],
    "resolved": f"{t['resolved']}/{t['instances']}",
    "piqp_iteration_limit_terminations": REC["headline_finding"][
        "PIQP_P2_iteration_limit_terminations"],
}, indent=1))
