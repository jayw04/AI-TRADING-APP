"""Do the REGISTERED-path (raw quadprog) failures succeed under the scaled formulation?

That single question decides whether a deterministic two-method cascade reaches ZERO
Stage-3 failures across the full development window.

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
from scipy.optimize import linprog  # noqa: E402

RES = {
    "solves": 0,
    "raw_ok": 0,
    "raw_fail": 0,
    "raw_fail_scaled_ok": 0,
    "raw_fail_scaled_ALSO_fail": 0,
    "cascade_failures": 0,
    "max_cascade_vs_highs_disagreement": 0.0,
    "raw_fail_detail": [],
}


def qp(H, a, C, b, meq):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        return quadprog.solve_qp(H, a, C, b, meq)


def solve(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(targets)
    t = np.asarray(targets, float)
    RES["solves"] += 1

    def build(Au, Ae, up):
        return (np.vstack([Ae, -Au, np.eye(n), -np.eye(n)]).T,
                np.concatenate([b_eq, -b_ub, np.zeros(n), -up]))

    def ok(z):
        pr = jp._primal_residual(z, A_ub, b_ub, A_eq, b_eq, upper)
        return z, {"kkt_residual": 0.0, "hessian_condition_number": 1.0,
                   "primal_residual": pr, "dual_residual": 0.0,
                   "stationarity_residual": 0.0, "complementarity_residual": 0.0,
                   "qp_iterations": [0, 0]}

    # --- METHOD 1: the REGISTERED raw formulation --------------------------------------
    C0, b0 = build(A_ub, A_eq, upper)
    try:
        z = np.asarray(qp(np.diag(2.0 / t), 2.0 * np.ones(n), C0, b0, 1)[0], float)
        RES["raw_ok"] += 1
        return ok(z)
    except Exception as exc:
        RES["raw_fail"] += 1
        raw_err = str(exc)

    # --- METHOD 2: the scaled formulation, ONLY on a raw failure ------------------------
    T = np.diag(t)
    Cs, bs = build(A_ub @ T, A_eq @ T, upper / t)
    z = None
    scaled_ok = False
    try:
        u = np.asarray(qp(np.diag(2.0 * t), 2.0 * t, Cs, bs, 1)[0], float)
        z = T @ u
        scaled_ok = True
        RES["raw_fail_scaled_ok"] += 1
    except Exception:
        RES["raw_fail_scaled_ALSO_fail"] += 1
        RES["cascade_failures"] += 1

    f = linprog(c=np.zeros(n), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                bounds=[(0.0, float(u_)) for u_ in upper],
                method="highs-ds", options=jp.LP_OPTIONS)

    RES["raw_fail_detail"].append({
        "n_vars": int(n), "n_rows": int(A_ub.shape[0]),
        "target_min": float(t.min()), "target_max": float(t.max()),
        "target_ratio": float(t.max() / t.min()),
        "raw_error": raw_err, "scaled_ok": scaled_ok,
        "highs_proves_feasible": bool(f.success),
    })

    if z is None:
        if not f.success:
            raise InvalidRun("genuinely infeasible")
        z = np.asarray(f.x, float)          # diagnostic continuation only
    return ok(z)


jp._solve_qp = solve

from app.research.mr002.dataset import FrozenDataset  # noqa: E402
from app.research.mr002.runner import CONFIGS  # noqa: E402
from scripts.mr002_development_run import run_config  # noqa: E402

ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
for name in ("A", "B", "C"):
    print(f"config {name} ...", flush=True)
    run_config(days, CONFIGS[name])

print(json.dumps(RES, indent=2))
