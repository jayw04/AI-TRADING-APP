"""Diagnose the Stage-3 quadprog 'constraints are inconsistent' INVALID_RUN.

Per the frozen contract this MUST NOT occur: stages 1 and 2 already proved the region
non-empty. So it is an implementation defect and must be understood exactly, not patched
by loosening anything.
"""
from __future__ import annotations

import sys
from datetime import date

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.joint_portfolio import InvalidRun  # noqa: E402

CAPTURE: dict = {}
_orig_solve_qp = jp._solve_qp


def spy(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
    try:
        return _orig_solve_qp(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper)
    except InvalidRun:
        CAPTURE.update(dict(H_diag=H_diag, targets=targets, A_ub=A_ub, b_ub=b_ub,
                            A_eq=A_eq, b_eq=b_eq, upper=upper))
        raise


jp._solve_qp = spy

from scripts.mr002_development_run import run_config  # noqa: E402
from app.research.mr002.dataset import FrozenDataset  # noqa: E402
from app.research.mr002.runner import CONFIGS  # noqa: E402

ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))

try:
    run_config(days, CONFIGS["A"])
    print("no failure")
    raise SystemExit(0)
except InvalidRun as exc:
    print("FAILED:", exc)

A_eq = CAPTURE["A_eq"]
A_ub = CAPTURE["A_ub"]
b_ub = CAPTURE["b_ub"]
upper = CAPTURE["upper"]
n = len(upper)

print(f"\nn vars = {n}   (targets min={CAPTURE['targets'].min():.3e} "
      f"max={CAPTURE['targets'].max():.3e})")
print(f"A_ub rows = {A_ub.shape[0]}")

# --- hypothesis 1: a constraint row with a ZERO normal vector -----------------------
eq_norm = np.linalg.norm(A_eq, axis=1)
print(f"\nA_eq row norms: {eq_norm}")
print("  -> ZERO-NORM EQUALITY ROW" if np.any(eq_norm < 1e-15) else "  -> equality rows OK")

ub_norm = np.linalg.norm(A_ub, axis=1)
zero_ub = np.where(ub_norm < 1e-15)[0]
print(f"zero-norm inequality rows: {len(zero_ub)}")

# --- hypothesis 2: duplicate / linearly dependent rows -------------------------------
C_rows = [A_eq, -A_ub, np.eye(n), -np.eye(n)]
C = np.vstack([r for r in C_rows if r.size]).T
print(f"\nC shape {C.shape}, rank {np.linalg.matrix_rank(C)}")

# --- hypothesis 3: is the region actually non-empty? Ask HiGHS (independent) ---------
from scipy.optimize import linprog  # noqa: E402

feas = linprog(
    c=np.zeros(n), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=CAPTURE["b_eq"],
    bounds=[(0.0, float(u)) for u in upper], method="highs-ds",
    options=jp.LP_OPTIONS,
)
print(f"\nHiGHS feasibility of the SAME Stage-3 region: success={feas.success} "
      f"status={feas.status} ({feas.message})")
if feas.success:
    z = feas.x
    print(f"  -> a feasible point EXISTS. max A_ub violation = "
          f"{float(np.max(A_ub @ z - b_ub)):.3e}")
    print("  => quadprog is WRONG to call the constraints inconsistent.")

# --- hypothesis 4: how thin is the band? ---------------------------------------------
print(f"\nlast two A_ub rows (the R and Q bands):")
for i in (-2, -1):
    print(f"  row {i}: |a|={ub_norm[i]:.3f}  b={b_ub[i]:.6e}")

# --- hypothesis 5: bounds with upper == 0 (degenerate variables) ----------------------
print(f"\nvars with upper bound == 0: {(upper == 0).sum()}")
print(f"vars with upper < 1e-9    : {(upper < 1e-9).sum()}")
