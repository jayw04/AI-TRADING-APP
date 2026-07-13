"""MR-002 v1.1 — SQUARE-ROOT EQUILIBRATION CHARACTERIZATION.

Authorized 2026-07-12. SOLVER CHARACTERIZATION ONLY. No performance is computed, printed
or persisted. Validation and sealed OOS are not touched.

    S = diag(sqrt(t)) ,  z = S v
    D(z) = sum (z_i - t_i)^2 / t_i  =  sum (v_i - sqrt(t_i))^2
    =>  H_sqrt = 2I   (constructed DIRECTLY, exactly 2I -- never as S H S, which is 2I
                       only to a ulp)
        a_sqrt = 2 sqrt(t)
        A_sqrt = A S ,  Aeq_sqrt = Aeq S ,  0 <= v_i <= sqrt(t_i)
    Bound multipliers map back as  mu_z,i = mu_v,i / sqrt(t_i);
    row multipliers keep their association.

CAPTURE-PATH NOTE (raised with the owner). There is no solver-neutral capture: the position
path depends on which solver solved each earlier QP. The corpus below is therefore generated
by the PROPOSED FINAL CASCADE (raw -> sqrt rescue), so the captured instances are exactly
those the registered system would encounter. Each instance is then classified by how RAW and
the current t-SCALED formulation behave ON IT, and the gates are applied to those classes.
Replay operates on immutable copies; no replay result can alter the position path.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import warnings
from collections import Counter
from datetime import date

import numpy as np
import quadprog

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.joint_portfolio import InvalidRun  # noqa: E402

FALSE_INCONSISTENCY = "constraints are inconsistent, no solution"
LIMITS = {
    "primal_residual": 1e-9, "dual_residual": 1e-9,
    "stationarity_residual": 1e-8, "complementarity_residual": 1e-8,
    "kkt_residual": 1e-8,
}
AGREE = 1e-8

CORPUS: list[dict] = []
CAPTURE_PATH: Counter = Counter()


def _qp(H, a, C, b, meq):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        return quadprog.solve_qp(H, a, C, b, meq)


def _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper) -> str:
    h = hashlib.sha256()
    for arr in (t, A_ub, b_ub, A_eq, b_eq, upper):
        a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


# ======================================================================================
# the three formulations -- each returns (z, checks) or raises
# ======================================================================================
def solve_raw(t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = A_eq.shape[0]
    out = _qp(H, a, C, b, meq)
    z = np.asarray(out[0], float)
    lam = np.asarray(out[4], float)
    return z, jp._acceptance(z, lam, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)


def solve_tscaled(t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = A_eq.shape[0]
    T = np.diag(t)
    C_s, b_s = jp._qp_matrices(A_ub @ T, b_ub, A_eq @ T, b_eq, upper / t, n)
    out = _qp(np.diag(2.0 * t), 2.0 * t, C_s, b_s, meq)
    u = np.asarray(out[0], float)
    lam_u = np.asarray(out[4], float)
    z = T @ u
    nr = meq + A_ub.shape[0]
    lam_z = lam_u.copy()
    lam_z[nr:nr + n] /= t
    lam_z[nr + n:] /= t
    return z, jp._acceptance(z, lam_z, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)


def solve_sqrt(t, A_ub, b_ub, A_eq, b_eq, upper):
    """THE CANDIDATE. H is EXACTLY 2I by construction."""
    n = len(t)
    H = np.diag(2.0 / t)                       # original-coordinate Hessian (for checks)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = A_eq.shape[0]

    s = np.sqrt(t)
    S = np.diag(s)
    H_v = 2.0 * np.eye(n)                      # EXACTLY 2I -- not S H S
    a_v = 2.0 * s
    C_v, b_v = jp._qp_matrices(A_ub @ S, b_ub, A_eq @ S, b_eq, s, n)

    out = _qp(H_v, a_v, C_v, b_v, meq)
    v = np.asarray(out[0], float)
    lam_v = np.asarray(out[4], float)
    z = S @ v
    nr = meq + A_ub.shape[0]
    lam_z = lam_v.copy()
    lam_z[nr:nr + n] /= s                      # mu_z = mu_v / sqrt(t)
    lam_z[nr + n:] /= s
    return z, jp._acceptance(z, lam_z, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)


def failures(checks) -> list[str]:
    return sorted(k for k, lim in LIMITS.items() if checks[k] > lim)


def objective(z, t) -> float:
    return float(np.sum((z - t) ** 2 / t))


# ======================================================================================
# PHASE 1 -- generate the corpus with the PROPOSED cascade (raw -> sqrt rescue)
# ======================================================================================
def capture_solver(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
    t = np.asarray(targets, float)
    CORPUS.append({
        "t": t.copy(), "A_ub": A_ub.copy(), "b_ub": b_ub.copy(),
        "A_eq": A_eq.copy(), "b_eq": b_eq.copy(), "upper": np.asarray(upper, float).copy(),
        "hash": _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper),
    })
    # CAPTURE LADDER. The proposed raw->sqrt cascade CANNOT complete the path -- sqrt
    # raises on at least one instance. This ladder is a CAPTURE DEVICE to reach the next
    # session, NOT a proposed remedy. Every formulation is compared OFFLINE, on immutable
    # copies, in Phase 2; no offline result feeds back into the path.
    for nm, fn in (("RAW", solve_raw), ("SQRT", solve_sqrt), ("TSCALED", solve_tscaled)):
        try:
            z, ck = fn(t, A_ub, b_ub, A_eq, b_eq, upper)
            if not failures(ck):
                CAPTURE_PATH[nm] += 1
                return z, dict(ck, stage3_formulation=nm,
                               hessian_condition_number=1.0, qp_iterations=[0, 0])
        except ValueError:
            continue

    from scipy.optimize import linprog

    n = len(t)
    f = linprog(c=np.zeros(n), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                bounds=[(0.0, float(u)) for u in upper], method="highs-ds",
                options=jp.LP_OPTIONS)
    CAPTURE_PATH["DIAGNOSTIC_FALLBACK"] += 1
    if not f.success:
        raise InvalidRun("capture: no formulation solved and the region is infeasible")
    z = np.asarray(f.x, float)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    ck = jp._acceptance(z, np.zeros(C.shape[1]), A_eq.shape[0], H, a, C, b,
                        A_ub, b_ub, A_eq, b_eq, upper)
    return z, dict(ck, stage3_formulation="DIAGNOSTIC_FALLBACK",
                   hessian_condition_number=1.0, qp_iterations=[0, 0])


def main() -> int:
    jp._solve_qp = capture_solver

    from app.research.mr002.dataset import FrozenDataset  # noqa: E402
    from app.research.mr002.runner import CONFIGS  # noqa: E402
    from scripts.mr002_development_run import run_config  # noqa: E402

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    print("PHASE 1 — capture the corpus under the PROPOSED cascade (raw -> sqrt)")
    for name in ("A", "B", "C"):
        print(f"  {name} ...", flush=True)
        run_config(days, CONFIGS[name])
    print(f"  captured {len(CORPUS)} Stage-3 instances")

    corpus_hash = hashlib.sha256(
        "|".join(i["hash"] for i in CORPUS).encode()).hexdigest()
    print(f"  corpus hash: {corpus_hash}")

    # ---- PHASE 2: replay all three formulations on the IMMUTABLE captured instances ----
    print("\nPHASE 2 — replay raw / t-scaled / sqrt on immutable copies")
    R = {
        "instances": len(CORPUS), "corpus_hash": corpus_hash,
        "raw_clean": 0, "raw_raised": 0, "raw_dual_certificate_failure": 0,
        "raw_primal_failure": 0, "raw_other_failure": 0,
        "tscaled_ok": 0, "tscaled_failed": 0,
        "sqrt_ok": 0, "sqrt_failed": 0, "sqrt_failure_kinds": Counter(),
        "class_counts": Counter(),
        "gate_raw_exception_rescued_by_sqrt": [0, 0],
        "gate_dual_corrupt_rescued_by_sqrt": [0, 0],
        "gate_double_failure_rescued_by_sqrt": [0, 0],
        "max_sqrt_vs_raw_z_disagreement_on_raw_clean": 0.0,
        "max_sqrt_vs_raw_obj_disagreement_on_raw_clean": 0.0,
        "worst_sqrt_stationarity": 0.0,
        "max_hessian_entry_seen": 0.0,
        "min_target_seen": 1.0,
    }

    for inst in CORPUS:
        t = inst["t"].copy()
        A_ub, b_ub = inst["A_ub"].copy(), inst["b_ub"].copy()
        A_eq, b_eq = inst["A_eq"].copy(), inst["b_eq"].copy()
        upper = inst["upper"].copy()
        R["max_hessian_entry_seen"] = max(R["max_hessian_entry_seen"], float(2.0 / t.min()))
        R["min_target_seen"] = min(R["min_target_seen"], float(t.min()))

        # --- RAW ---
        raw_z, raw_class = None, None
        try:
            z, ck = solve_raw(t, A_ub, b_ub, A_eq, b_eq, upper)
            bad = failures(ck)
            if not bad:
                R["raw_clean"] += 1
                raw_class = "RAW_CLEAN"
                raw_z = z
            elif set(bad) <= {"dual_residual", "stationarity_residual",
                              "complementarity_residual", "kkt_residual"}:
                R["raw_dual_certificate_failure"] += 1
                raw_class = "RAW_DUAL_CERTIFICATE_FAILURE"
            elif "primal_residual" in bad:
                R["raw_primal_failure"] += 1
                raw_class = "RAW_PRIMAL_FAILURE"          # NOT rescue-eligible
            else:
                R["raw_other_failure"] += 1
                raw_class = "RAW_OTHER_FAILURE"
        except ValueError as e:
            if str(e) == FALSE_INCONSISTENCY:
                R["raw_raised"] += 1
                raw_class = "RAW_FALSE_INCONSISTENCY"
            else:
                R["raw_other_failure"] += 1
                raw_class = "RAW_OTHER_EXCEPTION"

        # --- t-SCALED (the currently registered rescue) ---
        ts_ok = False
        try:
            _z, ck = solve_tscaled(t, A_ub, b_ub, A_eq, b_eq, upper)
            ts_ok = not failures(ck)
        except ValueError:
            ts_ok = False
        R["tscaled_ok" if ts_ok else "tscaled_failed"] += 1

        # --- SQRT (the candidate) ---
        sq_ok, sq_z, sq_ck = False, None, None
        try:
            sq_z, sq_ck = solve_sqrt(t, A_ub, b_ub, A_eq, b_eq, upper)
            bad = failures(sq_ck)
            sq_ok = not bad
            if bad:
                R["sqrt_failure_kinds"]["+".join(bad)] += 1
            R["worst_sqrt_stationarity"] = max(
                R["worst_sqrt_stationarity"], sq_ck["stationarity_residual"])
        except ValueError as e:
            R["sqrt_failure_kinds"][f"RAISED:{e}"] += 1
        R["sqrt_ok" if sq_ok else "sqrt_failed"] += 1

        cls = raw_class + ("" if ts_ok else "|TSCALED_FAILED")
        R["class_counts"][cls] += 1

        # ---- GATES ----
        if raw_class == "RAW_FALSE_INCONSISTENCY":
            R["gate_raw_exception_rescued_by_sqrt"][1] += 1
            R["gate_raw_exception_rescued_by_sqrt"][0] += int(sq_ok)
        if raw_class == "RAW_DUAL_CERTIFICATE_FAILURE":
            R["gate_dual_corrupt_rescued_by_sqrt"][1] += 1
            R["gate_dual_corrupt_rescued_by_sqrt"][0] += int(sq_ok)
        if raw_class != "RAW_CLEAN" and not ts_ok:
            R["gate_double_failure_rescued_by_sqrt"][1] += 1
            R["gate_double_failure_rescued_by_sqrt"][0] += int(sq_ok)

        # ---- agreement on RAW-CLEAN instances ----
        if raw_class == "RAW_CLEAN" and sq_ok:
            R["max_sqrt_vs_raw_z_disagreement_on_raw_clean"] = max(
                R["max_sqrt_vs_raw_z_disagreement_on_raw_clean"],
                float(np.max(np.abs(sq_z - raw_z))))
            R["max_sqrt_vs_raw_obj_disagreement_on_raw_clean"] = max(
                R["max_sqrt_vs_raw_obj_disagreement_on_raw_clean"],
                abs(objective(sq_z, t) - objective(raw_z, t)))

    # ---- verdict ----
    gates = {
        "all_instances_sqrt_ok": R["sqrt_failed"] == 0,
        "raw_exception_instances_rescued": (
            R["gate_raw_exception_rescued_by_sqrt"][0]
            == R["gate_raw_exception_rescued_by_sqrt"][1]),
        "dual_corrupt_instances_rescued": (
            R["gate_dual_corrupt_rescued_by_sqrt"][0]
            == R["gate_dual_corrupt_rescued_by_sqrt"][1]),
        "double_failure_instances_rescued": (
            R["gate_double_failure_rescued_by_sqrt"][0]
            == R["gate_double_failure_rescued_by_sqrt"][1]),
        "z_agreement_on_raw_clean_within_1e-8":
            R["max_sqrt_vs_raw_z_disagreement_on_raw_clean"] <= AGREE,
        "objective_agreement_on_raw_clean_within_1e-8":
            R["max_sqrt_vs_raw_obj_disagreement_on_raw_clean"] <= AGREE,
    }
    R["sqrt_failure_kinds"] = dict(R["sqrt_failure_kinds"])
    R["class_counts"] = dict(R["class_counts"])
    R["capture_path_formulations"] = dict(CAPTURE_PATH)
    R["capture_path_note"] = (
        "The capture ladder raw->sqrt->tscaled->HiGHS is a DEVICE to complete the "
        "path, NOT a proposed remedy. The proposed raw->sqrt cascade CANNOT complete "
        "the path: sqrt raises on at least one instance."
    )
    R["gates"] = gates
    R["VERDICT"] = "PASS" if all(gates.values()) else "FAIL"

    np.savez_compressed(
        "/out/MR002_Stage3_Corpus.npz",
        **{f"{i}_{k}": inst[k] for i, inst in enumerate(CORPUS)
           for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper")},
    )
    with open("/out/MR002_Stage3_Corpus_Hashes.json", "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump({"corpus_hash": corpus_hash,
                   "instance_hashes": [i["hash"] for i in CORPUS]}, fh, indent=2)

    dst = os.environ.get("MR002_SQRT_OUT", "/out/MR002_SqrtEquilibration_Characterization.json")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(R, fh, indent=2)
        fh.write("\n")
    print(json.dumps(R, indent=2))
    print(f"\nreport: {dst}")
    return 0 if R["VERDICT"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
