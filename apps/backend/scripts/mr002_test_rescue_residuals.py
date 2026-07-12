"""CRITICAL PRE-CHECK for the registered Stage-3 cascade.

The owner's step 7 requires EVERY acceptance check to be recomputed in ORIGINAL z
coordinates, with bound multipliers transformed by division by t_i.

With t_i ~ 1e-8 that division AMPLIFIES the bound multiplier by ~1e8. If the amplified
floating-point error exceeds the registered stationarity threshold (1e-8), then a
correctly-rescued solve would FAIL its own acceptance check and become a FALSE
INVALID_RUN -- i.e. the remedy would not actually work.

This script measures the ORIGINAL-COORDINATE residuals of every rescued solve.
DIAGNOSTIC ONLY. No performance computed, printed or persisted.
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
from scipy.optimize import linprog  # noqa: E402

FALSE_INCONSISTENCY = "constraints are inconsistent, no solution"

OUT = {"solves": 0, "rescues": 0, "rescue_detail": [],
       "raw_max_kkt": 0.0, "raw_max_stationarity": 0.0}


def _qp(H, a, C, b, meq):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        return quadprog.solve_qp(H, a, C, b, meq)


def _residuals(z, lam, meq, H, a, C_orig, b_orig, A_ub, b_ub, A_eq, b_eq, upper):
    """All checks in ORIGINAL coordinates."""
    primal = jp._primal_residual(z, A_ub, b_ub, A_eq, b_eq, upper)
    ineq = lam[meq:]
    dual = float(np.max(np.maximum(-ineq, 0.0))) if ineq.size else 0.0
    stat = float(np.max(np.abs(H @ z - a - C_orig @ lam)))
    slack = C_orig.T @ z - b_orig
    comp = float(np.max(np.abs(ineq * slack[meq:]))) if ineq.size else 0.0
    return primal, dual, stat, comp, max(primal, dual, stat, comp)


def cascade(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(targets)
    t = np.asarray(targets, float)
    OUT["solves"] += 1

    if np.any(t <= 0):
        raise InvalidRun("non-positive target: T would be singular")
    if not np.allclose(t, upper, rtol=0, atol=0):
        raise InvalidRun("t_i must equal the registered upper bound of variable i")

    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C = np.vstack([A_eq, -A_ub, np.eye(n), -np.eye(n)]).T
    b = np.concatenate([b_eq, -b_ub, np.zeros(n), -upper])
    meq = A_eq.shape[0]

    # ---------- STEP 1: registered RAW attempt -----------------------------------------
    try:
        out = _qp(H, a, C, b, meq)
        z = np.asarray(out[0], float)
        lam = np.asarray(out[4], float)
        pr, du, st, cp, kkt = _residuals(z, lam, meq, H, a, C, b,
                                         A_ub, b_ub, A_eq, b_eq, upper)
        OUT["raw_max_kkt"] = max(OUT["raw_max_kkt"], kkt)
        OUT["raw_max_stationarity"] = max(OUT["raw_max_stationarity"], st)
        return z, {"stage3_formulation": "RAW", "kkt_residual": kkt,
                   "primal_residual": pr, "dual_residual": du,
                   "stationarity_residual": st, "complementarity_residual": cp,
                   "hessian_condition_number": float(np.max(H) / np.min(H)),
                   "qp_iterations": [0, 0]}
    except ValueError as exc:
        if str(exc) != FALSE_INCONSISTENCY:      # e.g. "matrix G is not positive definite"
            raise InvalidRun(f"stage3: fatal raw exception: {exc}") from exc
        raw_msg = str(exc)

    # ---------- STEP 3-4: HiGHS zero-objective feasibility probe (original region) ------
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        probe = linprog(c=np.zeros(n), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                        bounds=[(0.0, float(u)) for u in upper],
                        method="highs-ds", options=jp.LP_OPTIONS)
    if not (probe.success and probe.status == 0):
        raise InvalidRun("stage3: feasibility probe not optimal -> INVALID_RUN")
    probe_pr = jp._primal_residual(np.asarray(probe.x, float), A_ub, b_ub,
                                   A_eq, b_eq, upper)
    if probe_pr > 1e-9:
        raise InvalidRun(f"stage3: probe primal feasibility {probe_pr:.3e} > 1e-9")

    # ---------- STEP 5: the single scaled retry ----------------------------------------
    T = np.diag(t)
    H_s = np.diag(2.0 * t)                       # = T H T
    a_s = 2.0 * t                                # = T a
    A_s = A_ub @ T
    Aeq_s = A_eq @ T
    up_s = upper / t                             # == 1.0 exactly
    C_s = np.vstack([Aeq_s, -A_s, np.eye(n), -np.eye(n)]).T
    b_s = np.concatenate([b_eq, -b_ub, np.zeros(n), -up_s])
    out = _qp(H_s, a_s, C_s, b_s, meq)           # any raise -> propagates -> fatal
    u = np.asarray(out[0], float)
    lam_s = np.asarray(out[4], float)

    # ---------- STEP 6: map back --------------------------------------------------------
    z = T @ u

    # ---------- multiplier transform: rows unchanged, BOUNDS divided by t_i -------------
    n_rows = meq + A_ub.shape[0]
    lam_z = lam_s.copy()
    lam_z[n_rows:n_rows + n] /= t                # lower-bound multipliers
    lam_z[n_rows + n:] /= t                      # upper-bound multipliers

    # ---------- STEP 7: EVERY check, in ORIGINAL coordinates ---------------------------
    pr, du, st, cp, kkt = _residuals(z, lam_z, meq, H, a, C, b,
                                     A_ub, b_ub, A_eq, b_eq, upper)
    # scaled-coordinate comparison (numerically stable reference)
    pr_s, du_s, st_s, cp_s, kkt_s = _residuals(u, lam_s, meq, H_s, a_s, C_s, b_s,
                                               A_s, b_ub, Aeq_s, b_eq, up_s)
    obj = float(np.sum((z - t) ** 2 / t))

    OUT["rescues"] += 1
    OUT["rescue_detail"].append({
        "n_vars": int(n), "t_min": float(t.min()),
        "amplification_1_over_t_min": float(1.0 / t.min()),
        "raw_exception_message": raw_msg,
        "feasibility_probe_status": int(probe.status),
        "raw_coordinate_objective": obj,
        "ORIGINAL_coords": {"primal": pr, "dual": du, "stationarity": st,
                            "complementarity": cp, "kkt": kkt},
        "SCALED_coords": {"primal": pr_s, "dual": du_s, "stationarity": st_s,
                          "complementarity": cp_s, "kkt": kkt_s},
        "ORIGINAL_passes_registered_limits": {
            "primal<=1e-9": pr <= 1e-9, "dual<=1e-9": du <= 1e-9,
            "stationarity<=1e-8": st <= 1e-8, "complementarity<=1e-8": cp <= 1e-8,
            "kkt<=1e-8": kkt <= 1e-8,
        },
    })
    return z, {"stage3_formulation": "SCALED_RESCUE", "kkt_residual": kkt,
               "primal_residual": pr, "dual_residual": du,
               "stationarity_residual": st, "complementarity_residual": cp,
               "hessian_condition_number": float(np.max(H) / np.min(H)),
               "qp_iterations": [0, 0]}


jp._solve_qp = cascade

from app.research.mr002.dataset import FrozenDataset  # noqa: E402
from app.research.mr002.runner import CONFIGS  # noqa: E402
from scripts.mr002_development_run import run_config  # noqa: E402

ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
for name in ("A", "B", "C"):
    print(f"config {name} ...", flush=True)
    run_config(days, CONFIGS[name])

print(json.dumps(OUT, indent=2))
