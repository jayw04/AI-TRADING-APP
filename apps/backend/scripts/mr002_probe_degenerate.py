"""Which degenerate tightened projections does Clarabel actually solve at 1e-14?

The §9 fixture must exhibit a highly degenerate projection that IS solved and reaches the exact
constructor. An exactly duplicated row (rank-deficient) returns AlmostSolved, which is the correct
refusal but tests the stop path, not the mechanism. Probe, don't guess.
"""

from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "/work/apps/backend")

from app.research.mr002.repair import RepairUnavailable, repair  # noqa: E402

CASES = {
    "duplicate row (rank-deficient)": (
        np.array([[1.0, 1.0, 0, 0, 0, 0], [1.0, 1.0, 0, 0, 0, 0], [0, 0, 1.0, 1.0, 0, 0]]),
        np.array([0.30, 0.30, 0.30]), np.array([0.90]),
    ),
    "nested cap (row2 = row0+row1)": (
        np.array([[1.0, 1.0, 0, 0, 0, 0], [0, 0, 1.0, 1.0, 0, 0],
                  [1.0, 1.0, 1.0, 1.0, 0, 0]]),
        np.array([0.30, 0.30, 0.60]), np.array([0.90]),
    ),
    "overlapping caps, independent": (
        np.array([[1.0, 1.0, 0, 0, 0, 0], [0, 0, 1.0, 1.0, 0, 0], [0, 1.0, 1.0, 0, 0, 0]]),
        np.array([0.30, 0.30, 0.30]), np.array([0.90]),
    ),
    "overlapping caps + empty row": (
        np.array([[1.0, 1.0, 0, 0, 0, 0], [0, 0, 1.0, 1.0, 0, 0], [0, 1.0, 1.0, 0, 0, 0],
                  [0, 0, 0, 0, 0, 0]]),
        np.array([0.30, 0.30, 0.30, 0.0]), np.array([0.90]),
    ),
    "three tight, one slack, + empty": (
        np.array([[1.0, 1.0, 0, 0, 0, 0], [0, 0, 1.0, 1.0, 0, 0], [0, 1.0, 1.0, 0, 0, 0],
                  [0, 0, 0, 0, 1.0, 1.0], [0, 0, 0, 0, 0, 0]]),
        np.array([0.30, 0.30, 0.30, 0.50, 0.0]), np.array([0.90]),
    ),
}

n = 6
t = np.full(n, 0.2)
upper = np.full(n, 0.5)
z = np.full(n, 0.15)

for name, (A_ub, b_ub, b_eq) in CASES.items():
    tight = int(np.sum(np.abs(A_ub @ z - b_ub) < 1e-12))
    try:
        zhat, k, n_cand, n_feas, empties = repair(z, t, A_ub, b_ub, np.ones((1, n)), b_eq, upper)
        print(f"  SOLVED   {name:34} tight_rows={tight}  absorbers_feasible={n_feas}/{n_cand} "
              f"empties={len(empties)}")
    except RepairUnavailable as e:
        print(f"  REFUSED  {name:34} tight_rows={tight}  {str(e)[:58]}")
