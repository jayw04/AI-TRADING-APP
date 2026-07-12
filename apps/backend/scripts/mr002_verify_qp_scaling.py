"""Verify the PROPOSED Stage-3 variable scaling across the full development window.

DIAGNOSTIC ONLY. Reports solver/structural statistics. NO performance is computed,
printed or persisted -- the remedy is not yet registered, so nothing performance-related
may be derived from a run that uses it.
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

STATS = {"solves": 0, "max_kkt": 0.0, "max_kappa": 0.0, "max_scaled_kappa": 0.0,
         "min_target": 1.0, "max_target_ratio": 0.0}


def scaled_solve_qp(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
    """PROPOSED: solve Stage 3 in u = z / t.

    EXACT reformulation, not regularization:
        D = sum (z_i - t_i)^2 / t_i ,  z = T u  (T = diag(t), t_i > 0)
          = sum t_i (u_i - 1)^2
    quadprog form: H = diag(2 t), a = 2 t. Constraints A(T u) <= b. Bounds 0 <= u <= 1,
    since upper_i == t_i for BOTH blocks (y bounded by c, x bounded by w).

    T is a positive diagonal bijection, so the feasible set and the unique minimizer are
    identical. No jitter, no ridge, no fallback solver, no change to objective, constraints,
    bounds or economics -- only the floating-point path the solver walks.
    """
    n = len(targets)
    t = np.asarray(targets, dtype=float)
    T = np.diag(t)

    H = np.diag(2.0 * t)
    a = 2.0 * t
    A_ub_s = A_ub @ T
    A_eq_s = A_eq @ T
    upper_s = upper / t                       # == 1.0 by construction

    kappa = float(np.linalg.cond(H)) if n else 1.0
    if kappa > jp.HESSIAN_CONDITION_MAX:
        raise InvalidRun(f"scaled hessian_condition_number {kappa:.3e} too large")

    C = np.vstack([A_eq_s, -A_ub_s, np.eye(n), -np.eye(n)]).T
    b = np.concatenate([b_eq, -b_ub, np.zeros(n), -upper_s])
    meq = A_eq_s.shape[0]

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            out = quadprog.solve_qp(H, a, C, b, meq)
    except ValueError as exc:
        raise InvalidRun(f"stage3(scaled): quadprog failed: {exc}") from exc

    u = np.asarray(out[0], dtype=float)
    z = T @ u                                  # back to registered units
    lam = np.asarray(out[4], dtype=float)

    primal = jp._primal_residual(z, A_ub, b_ub, A_eq, b_eq, upper)
    ineq = lam[meq:]
    dual = float(np.max(np.maximum(-ineq, 0.0))) if ineq.size else 0.0
    stat = float(np.max(np.abs(H @ u - a - C @ lam))) if n else 0.0
    slack = C.T @ u - b
    comp = float(np.max(np.abs(ineq * slack[meq:]))) if ineq.size else 0.0
    kkt = max(primal, dual, stat, comp)

    for nm, v, lim in (("primal", primal, jp.PRIMAL_RESIDUAL_MAX),
                       ("dual", dual, jp.DUAL_RESIDUAL_MAX),
                       ("stationarity", stat, jp.STATIONARITY_RESIDUAL_MAX),
                       ("complementarity", comp, jp.COMPLEMENTARITY_RESIDUAL_MAX)):
        if v > lim:
            raise InvalidRun(f"stage3(scaled): {nm} residual {v:.3e} > {lim:.0e}")

    STATS["solves"] += 1
    STATS["max_kkt"] = max(STATS["max_kkt"], kkt)
    STATS["max_kappa"] = max(STATS["max_kappa"], float(np.max(H_diag) / np.min(H_diag)))
    STATS["max_scaled_kappa"] = max(STATS["max_scaled_kappa"], kappa)
    STATS["min_target"] = min(STATS["min_target"], float(t.min()))
    STATS["max_target_ratio"] = max(STATS["max_target_ratio"], float(t.max() / t.min()))

    info = {"primal_residual": primal, "dual_residual": dual,
            "stationarity_residual": stat, "complementarity_residual": comp,
            "kkt_residual": kkt, "hessian_condition_number": kappa,
            "qp_iterations": [int(i) for i in np.asarray(out[3]).ravel()],
            "scaled": True}
    return z, info


jp._solve_qp = scaled_solve_qp

from app.research.mr002.dataset import FrozenDataset  # noqa: E402
from app.research.mr002.runner import CONFIGS  # noqa: E402
from scripts.mr002_development_run import metrics, run_config  # noqa: E402

ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
print(f"development sessions: {len(days)}")

out: dict = {}
for name in ("A", "B", "C"):
    print(f"  config {name} ...", flush=True)
    acc = run_config(days, CONFIGS[name])
    m = metrics(acc, name, len(days))          # raises InvalidRun on any reconciliation fail
    out[name] = {
        "session_funnel": m["session_funnel"],
        "determinism": m["determinism"],
        "solver": m["solver"],
        "STRUCTURAL_ONLY": "performance intentionally NOT reported: the remedy is unregistered",
    }

print(json.dumps({"qp_scaling_stats": STATS, "configs": out}, indent=2))
print("\nALL THREE CONFIGURATIONS COMPLETED WITH ZERO INVALID_RUN under the proposed scaling.")
