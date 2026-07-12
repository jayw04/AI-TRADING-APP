"""Isolate the cause of quadprog's false 'constraints are inconsistent' and test
candidate remedies on the ACTUAL captured failing instance."""
from __future__ import annotations

import sys
from datetime import date

import numpy as np
import quadprog

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.joint_portfolio import InvalidRun  # noqa: E402

CAPTURE: dict = {}
_orig = jp._solve_qp


def spy(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
    try:
        return _orig(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper)
    except InvalidRun:
        CAPTURE.update(dict(H_diag=H_diag, targets=targets, A_ub=A_ub, b_ub=b_ub,
                            A_eq=A_eq, b_eq=b_eq, upper=upper))
        raise


jp._solve_qp = spy

from app.research.mr002.dataset import FrozenDataset  # noqa: E402
from app.research.mr002.runner import CONFIGS  # noqa: E402
from scripts.mr002_development_run import run_config  # noqa: E402

ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
try:
    run_config(ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2)), CONFIGS["A"])
except InvalidRun:
    pass

t = CAPTURE["targets"]
A_ub, b_ub = CAPTURE["A_ub"], CAPTURE["b_ub"]
A_eq, b_eq = CAPTURE["A_eq"], CAPTURE["b_eq"]
upper = CAPTURE["upper"]
n = len(t)

print(f"n={n}  target min={t.min():.4e}  max={t.max():.4e}  ratio={t.max()/t.min():.3e}")
print(f"tiny targets (<1e-6): {(t < 1e-6).sum()}   -> Hessian entries up to {2/t.min():.3e}")


def try_qp(H, a, C, b, meq, label):
    try:
        out = quadprog.solve_qp(H, a, C, b, meq)
        return out[0], f"{label}: OK"
    except ValueError as e:
        return None, f"{label}: FAIL ({e})"


def build(A_ub, b_ub, A_eq, b_eq, upper, n):
    C = np.vstack([A_eq, -A_ub, np.eye(n), -np.eye(n)]).T
    b = np.concatenate([b_eq, -b_ub, np.zeros(n), -upper])
    return C, b


print()
# ---- baseline (what the harness does today) ------------------------------------------
H = np.diag(2.0 / t)
a = 2.0 * np.ones(n)
C, b = build(A_ub, b_ub, A_eq, b_eq, upper, n)
_, msg = try_qp(H, a, C, b, 1, "R0 baseline diag(2/t)")
print(msg)

# ---- R1: drop ONLY the band rows (last two) ------------------------------------------
_, msg = try_qp(H, a, *build(A_ub[:-2], b_ub[:-2], A_eq, b_eq, upper, n), 1,
                "R1 baseline WITHOUT the two lexicographic band rows")
print(msg)

# ---- R2: exclude the sub-1e-6 target variables ----------------------------------------
keep = t >= 1e-6
m = int(keep.sum())
if m < n:
    Hk = np.diag(2.0 / t[keep])
    ak = 2.0 * np.ones(m)
    Ck, bk = build(A_ub[:, keep], b_ub, A_eq[:, keep], b_eq, upper[keep], m)
    _, msg = try_qp(Hk, ak, Ck, bk, 1, f"R2 drop {n-m} sub-1e-6 targets")
    print(msg + "   [NOTE: this DROPS exposure -> not acceptable as-is]")

# ---- R3: VARIABLE SCALING  u = z / t  (exact reformulation, no regularization) --------
# D = sum (z-t)^2/t  ->  z = T u  ->  D = sum t (u-1)^2
# quadprog: 1/2 u' H u - a' u  with  H = diag(2t), a = 2t
T = np.diag(t)
Hs = np.diag(2.0 * t)
as_ = 2.0 * t
A_ub_s = A_ub @ T
A_eq_s = A_eq @ T
upper_s = upper / t                       # == 1 for every variable, by construction
Cs, bs = build(A_ub_s, b_ub, A_eq_s, b_eq, upper_s, n)
us, msg = try_qp(Hs, as_, Cs, bs, 1, "R3 VARIABLE SCALING u = z/t (exact)")
print(msg)
if us is not None:
    zs = T @ us
    print(f"    max A_ub violation: {float(np.max(A_ub @ zs - b_ub)):.3e}")
    print(f"    bounds ok: {bool(np.all(zs >= -1e-12) and np.all(zs <= upper + 1e-12))}")
    print(f"    equality residual: {float(np.max(np.abs(A_eq @ zs - b_eq))):.3e}")
    print(f"    objective D = {float(np.sum((zs - t) ** 2 / t)):.9e}")

# ---- cross-check R3 against an independent solver on the SAME problem -----------------
from scipy.optimize import minimize  # noqa: E402

cons = [
    {"type": "ineq", "fun": lambda z: b_ub - A_ub @ z},
    {"type": "eq", "fun": lambda z: (A_eq @ z - b_eq).ravel()},
]
r = minimize(lambda z: np.sum((z - t) ** 2 / t), x0=np.clip(t, 0, upper),
             bounds=[(0.0, float(u)) for u in upper], constraints=cons,
             method="SLSQP", options={"maxiter": 500, "ftol": 1e-14})
if us is not None and r.success:
    print(f"\n    independent SLSQP objective   = {r.fun:.9e}")
    print(f"    max |z_scaled - z_slsqp|      = {float(np.max(np.abs(zs - r.x))):.3e}")
