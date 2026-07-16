"""ROOT-CAUSE TEST: is the registered inclusion floor eps_include = 1e-8 the cause?

Every one of the 4 registered-path Stage-3 failures has a decision variable at
target ~1.0e-8 -- i.e. a variable that only just cleared the floor -- giving a Hessian
entry of ~2/1e-8 = 2e8 next to entries of ~1e2.

Sweep the floor and count RAW (registered, unscaled) quadprog failures. If a higher floor
drives failures to zero, the defect is the floor, not the solver -- and the fix is a root
fix inside the registered single-solver contract, not a fallback.

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
from app.research.mr002.dataset import FrozenDataset  # noqa: E402
from app.research.mr002.runner import CONFIGS  # noqa: E402

COUNT = {"solves": 0, "raw_fail": 0, "min_target": 1.0, "excluded_mass": 0.0}
_orig_solve = jp._solve_qp


def counting_solve(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(targets)
    t = np.asarray(targets, float)
    COUNT["solves"] += 1
    COUNT["min_target"] = min(COUNT["min_target"], float(t.min()))
    C = np.vstack([A_eq, -A_ub, np.eye(n), -np.eye(n)]).T
    b = np.concatenate([b_eq, -b_ub, np.zeros(n), -upper])
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            out = quadprog.solve_qp(np.diag(2.0 / t), 2.0 * np.ones(n), C, b, 1)
        z = np.asarray(out[0], float)
    except Exception:
        COUNT["raw_fail"] += 1
        from scipy.optimize import linprog
        f = linprog(c=np.zeros(n), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                    bounds=[(0.0, float(u)) for u in upper], method="highs-ds",
                    options=jp.LP_OPTIONS)
        z = np.asarray(f.x, float)          # diagnostic continuation only
    return z, {"kkt_residual": 0.0, "hessian_condition_number": 1.0,
               "primal_residual": jp._primal_residual(z, A_ub, b_ub, A_eq, b_eq, upper),
               "dual_residual": 0.0, "stationarity_residual": 0.0,
               "complementarity_residual": 0.0, "qp_iterations": [0, 0]}


jp._solve_qp = counting_solve

from scripts.mr002_development_run import run_config  # noqa: E402

ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))

results = []
for floor in (1e-8, 1e-7, 1e-6, 1e-5, 1e-4):
    jp.EPS_INCLUDE = floor
    COUNT.update({"solves": 0, "raw_fail": 0, "min_target": 1.0})
    for name in ("A", "B", "C"):
        run_config(days, CONFIGS[name])
    row = {
        "eps_include": floor,
        "usd_on_10m_nav": floor * 10_000_000,
        "stage3_solves": COUNT["solves"],
        "REGISTERED_raw_quadprog_failures": COUNT["raw_fail"],
        "smallest_target_admitted": COUNT["min_target"],
        "largest_hessian_entry": 2.0 / COUNT["min_target"],
    }
    results.append(row)
    print(json.dumps(row), flush=True)

print()
print(json.dumps({"inclusion_floor_sweep": results}, indent=2))
