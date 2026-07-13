"""Capture the Stage-3 RAW stationarity failure (5.03 >> 1e-8) and identify its cause.

The registered cascade triggers ONLY on the exact false-inconsistency ValueError, so a
residual failure is INVALID_RUN by contract. Understand it before escalating.

DIAGNOSTIC ONLY.
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

CAP: dict = {}
_orig = jp._solve_qp


def spy(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
    try:
        return _orig(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper)
    except InvalidRun as exc:
        if "stationarity" in str(exc) and not CAP:
            CAP.update(dict(H_diag=H_diag, targets=targets, A_ub=A_ub, b_ub=b_ub,
                            A_eq=A_eq, b_eq=b_eq, upper=upper, err=str(exc)))
        raise


jp._solve_qp = spy

from app.research.mr002.dataset import FrozenDataset  # noqa: E402
from app.research.mr002.runner import CONFIGS  # noqa: E402
from scripts.mr002_development_run import run_config  # noqa: E402

ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
try:
    run_config(days, CONFIGS["A"])
    print("no failure")
    raise SystemExit(0)
except InvalidRun as exc:
    print("FAILED:", exc)

t = np.asarray(CAP["targets"], float)
A_ub, b_ub = CAP["A_ub"], CAP["b_ub"]
A_eq, b_eq = CAP["A_eq"], CAP["b_eq"]
upper = CAP["upper"]
n = len(t)
meq = A_eq.shape[0]

print(f"\nn={n}  rows={A_ub.shape[0]}  meq={meq}")
print(f"targets: min={t.min():.4e} max={t.max():.4e} ratio={t.max()/t.min():.3e}")
print(f"A_eq row norm: {np.linalg.norm(A_eq, axis=1)}   <-- ZERO means a degenerate "
      f"equality row (n_x == 0: no new candidates)")
print(f"t == upper bitwise: {t.tobytes() == np.asarray(upper, float).tobytes()}")

H = np.diag(2.0 / t)
a = 2.0 * np.ones(n)
C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)

with warnings.catch_warnings():
    warnings.simplefilter("error")
    out = quadprog.solve_qp(H, a, C, b, meq)
z = np.asarray(out[0], float)
lam = np.asarray(out[4], float)

grad = H @ z - a
print(f"\n|grad|_inf              = {np.max(np.abs(grad)):.4e}   (theory: <= 2)")
print(f"|C @ lam|_inf           = {np.max(np.abs(C @ lam)):.4e}")
print(f"stationarity |g - C.l|  = {np.max(np.abs(grad - C @ lam)):.4e}")
print(f"lam: min={lam.min():.4e} max={lam.max():.4e}  nonzero={int((np.abs(lam)>1e-12).sum())}")
print(f"lam[:meq] (equality)    = {lam[:meq]}")

# is the PRIMAL point actually optimal? compare against an independent solve.
from scipy.optimize import minimize  # noqa: E402

r = minimize(lambda x: float(np.sum((x - t) ** 2 / t)),
             x0=np.clip(t, 0, upper), jac=lambda x: 2 * (x - t) / t,
             bounds=[(0.0, float(u)) for u in upper],
             constraints=[{"type": "ineq", "fun": lambda x: b_ub - A_ub @ x},
                          {"type": "eq", "fun": lambda x: (A_eq @ x - b_eq).ravel()}],
             method="SLSQP", options={"maxiter": 800, "ftol": 1e-16})
obj_qp = float(np.sum((z - t) ** 2 / t))
print(f"\nquadprog objective      = {obj_qp:.9e}")
if r.success:
    print(f"independent SLSQP obj   = {r.fun:.9e}")
    print(f"max |z_qp - z_slsqp|    = {np.max(np.abs(z - r.x)):.4e}")
    print(f"  => quadprog PRIMAL is {'OPTIMAL' if abs(obj_qp - r.fun) < 1e-9 else 'SUBOPTIMAL'}")

print(f"\nprimal residual = {jp._primal_residual(z, A_ub, b_ub, A_eq, b_eq, upper):.3e}")

# does the SCALED formulation give clean multipliers?
T = np.diag(t)
C_s, b_s = jp._qp_matrices(A_ub @ T, b_ub, A_eq @ T, b_eq, upper / t, n)
out_s = quadprog.solve_qp(np.diag(2.0 * t), 2.0 * t, C_s, b_s, meq)
u, lam_u = np.asarray(out_s[0], float), np.asarray(out_s[4], float)
z_s = T @ u
n_rows = meq + A_ub.shape[0]
lam_z = lam_u.copy()
lam_z[n_rows:n_rows + n] /= t
lam_z[n_rows + n:] /= t
print(f"\nSCALED: stationarity in original coords = "
      f"{np.max(np.abs(H @ z_s - a - C @ lam_z)):.4e}")
print(f"SCALED: max |z_scaled - z_raw|          = {np.max(np.abs(z_s - z)):.4e}")
