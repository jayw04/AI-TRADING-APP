"""Smoke: drive every solver through the CERTIFIED canonical predicate on one rich instance.

Cheap pre-check before the full 3,895-instance replay — a crash 20 minutes into the corpus is a
wasted hour, and the interval path is new code.
"""

from __future__ import annotations

import sys
import time

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import scripts.mr002_complementary_coverage as cov  # noqa: E402

t = np.array([0.237, 0.059, 0.138, 0.598])
upper = np.array([0.195, 0.283, 0.041, 0.033])
A_ub = np.array([[1.0, 0.0, 0.0, 1.0]])
b_ub = np.array([0.076])
A_eq = np.ones((1, 4))
b_eq = np.array([0.227])
rec = (t, A_ub, b_ub, A_eq, b_eq, upper)

for name in cov.SOLVERS:
    t0 = time.perf_counter()
    ok, why, _z, _lam, cert = cov.try_solve(name, rec)
    dt = (time.perf_counter() - t0) * 1e3
    g = f"{cert.certified_gap:.3e}" if cert else "—"
    r = f"{cert.radius:.3e}" if cert else "—"
    w = f"{max(cert.primal_interval_width, cert.dual_interval_width):.1e}" if cert else "—"
    clip = cert.n_multipliers_clipped if cert else "—"
    print(f"{name:18} ok={str(ok):5} G={g:>11}  r={r:>11}  width={w:>8}  clipped={clip}  "
          f"{dt:6.1f}ms  {why[:40]}")

# A larger instance, to size the corpus replay honestly.
rng = np.random.default_rng(0)
n = 180
t = rng.uniform(0.001, 0.02, n)
upper = np.full(n, 0.05)
A_ub = np.zeros((6, n))
for r_ in range(6):
    A_ub[r_, rng.choice(n, 30, replace=False)] = 1.0
b_ub = np.full(6, 0.30)
A_eq = np.ones((1, n))
b_eq = np.array([float(t.sum())])

t0 = time.perf_counter()
ok, why, _z, _lam, cert = cov.try_solve("QUADPROG_SQRT", (t, A_ub, b_ub, A_eq, b_eq, upper))
dt = (time.perf_counter() - t0) * 1e3
print(f"\nn={n} timing: {dt:.1f} ms/certification  ok={ok}  {why[:40]}")
print(f"  -> full replay estimate: {dt * 3895 * 7 / 1000 / 60:.1f} min")
