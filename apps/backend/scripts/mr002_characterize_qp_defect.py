"""Characterize the Stage-3 solver defect across the FULL development window.

Does NOT stop at the first failure. For every Stage-3 solve it records which methods
succeed, proves feasibility independently, and measures whether the successful methods
agree on the SAME unique minimizer.

DIAGNOSTIC ONLY. No performance is computed, printed or persisted.
"""
from __future__ import annotations

import json
import sys
import warnings
from datetime import date

import numpy as np
import quadprog

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.joint_portfolio import InvalidRun  # noqa: E402
from scipy.optimize import linprog, minimize  # noqa: E402

R = {
    "solves": 0,
    "quadprog_raw_ok": 0,
    "quadprog_raw_fail": 0,
    "quadprog_scaled_ok": 0,
    "quadprog_scaled_fail": 0,
    "slsqp_ok": 0,
    "slsqp_fail": 0,
    "highs_proves_feasible_on_quadprog_failure": 0,
    "highs_proves_INFEASIBLE_on_quadprog_failure": 0,
    "max_disagreement_raw_vs_scaled": 0.0,
    "max_disagreement_scaled_vs_slsqp": 0.0,
    "max_obj_gap_scaled_vs_slsqp": 0.0,
    "failing_instances": [],
}


def _qp(H, a, C, b, meq):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        return quadprog.solve_qp(H, a, C, b, meq)


def diag_solve_qp(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(targets)
    t = np.asarray(targets, float)
    R["solves"] += 1

    def build(Au, Ae, up):
        C = np.vstack([Ae, -Au, np.eye(n), -np.eye(n)]).T
        bb = np.concatenate([b_eq, -b_ub, np.zeros(n), -up])
        return C, bb

    # --- method 1: REGISTERED (raw) ----------------------------------------------------
    z_raw = None
    C0, b0 = build(A_ub, A_eq, upper)
    try:
        z_raw = np.asarray(_qp(np.diag(2.0 / t), 2.0 * np.ones(n), C0, b0, 1)[0], float)
        R["quadprog_raw_ok"] += 1
    except Exception:
        R["quadprog_raw_fail"] += 1

    # --- method 2: variable-scaled quadprog  u = z/t -----------------------------------
    T = np.diag(t)
    z_sc = None
    Cs, bs = build(A_ub @ T, A_eq @ T, upper / t)
    try:
        u = np.asarray(_qp(np.diag(2.0 * t), 2.0 * t, Cs, bs, 1)[0], float)
        z_sc = T @ u
        R["quadprog_scaled_ok"] += 1
    except Exception:
        R["quadprog_scaled_fail"] += 1

    # --- method 3: independent SLSQP ---------------------------------------------------
    z_sl = None
    res = minimize(
        lambda z: float(np.sum((z - t) ** 2 / t)),
        x0=np.clip(t, 0.0, upper),
        jac=lambda z: 2.0 * (z - t) / t,
        bounds=[(0.0, float(u_)) for u_ in upper],
        constraints=[{"type": "ineq", "fun": lambda z: b_ub - A_ub @ z,
                      "jac": lambda z: -A_ub},
                     {"type": "eq", "fun": lambda z: (A_eq @ z - b_eq).ravel(),
                      "jac": lambda z: A_eq}],
        method="SLSQP", options={"maxiter": 800, "ftol": 1e-16},
    )
    if res.success:
        z_sl = np.asarray(res.x, float)
        R["slsqp_ok"] += 1
    else:
        R["slsqp_fail"] += 1

    # --- on any quadprog failure: is the region ACTUALLY feasible? ----------------------
    if z_raw is None or z_sc is None:
        f = linprog(c=np.zeros(n), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                    bounds=[(0.0, float(u_)) for u_ in upper],
                    method="highs-ds", options=jp.LP_OPTIONS)
        if f.success:
            R["highs_proves_feasible_on_quadprog_failure"] += 1
        else:
            R["highs_proves_INFEASIBLE_on_quadprog_failure"] += 1
        if len(R["failing_instances"]) < 12:
            R["failing_instances"].append({
                "n_vars": int(n),
                "n_rows": int(A_ub.shape[0]),
                "target_min": float(t.min()),
                "target_max": float(t.max()),
                "target_ratio": float(t.max() / t.min()),
                "raw_ok": z_raw is not None,
                "scaled_ok": z_sc is not None,
                "slsqp_ok": z_sl is not None,
                "highs_feasible": bool(f.success),
            })

    # --- do the successful methods agree on the SAME unique minimizer? -----------------
    if z_raw is not None and z_sc is not None:
        R["max_disagreement_raw_vs_scaled"] = max(
            R["max_disagreement_raw_vs_scaled"], float(np.max(np.abs(z_raw - z_sc))))
    if z_sc is not None and z_sl is not None:
        R["max_disagreement_scaled_vs_slsqp"] = max(
            R["max_disagreement_scaled_vs_slsqp"], float(np.max(np.abs(z_sc - z_sl))))
        o1 = float(np.sum((z_sc - t) ** 2 / t))
        o2 = float(np.sum((z_sl - t) ** 2 / t))
        R["max_obj_gap_scaled_vs_slsqp"] = max(
            R["max_obj_gap_scaled_vs_slsqp"], abs(o1 - o2))

    z = z_sc if z_sc is not None else (z_raw if z_raw is not None else z_sl)
    if z is None:
        raise InvalidRun("no Stage-3 method succeeded")
    return z, {"kkt_residual": 0.0, "hessian_condition_number": 1.0,
               "primal_residual": jp._primal_residual(z, A_ub, b_ub, A_eq, b_eq, upper),
               "dual_residual": 0.0, "stationarity_residual": 0.0,
               "complementarity_residual": 0.0, "qp_iterations": [0, 0]}


jp._solve_qp = diag_solve_qp

from app.research.mr002.dataset import FrozenDataset  # noqa: E402
from app.research.mr002.runner import CONFIGS  # noqa: E402
from scripts.mr002_development_run import run_config  # noqa: E402

ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
print(f"development sessions: {len(days)}")
for name in ("A", "B", "C"):
    print(f"  config {name} ...", flush=True)
    run_config(days, CONFIGS[name])

print(json.dumps(R, indent=2))
