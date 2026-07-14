"""How THICK is the Stage-3 feasible set's interior? (DIAGNOSTIC ONLY — nothing is changed.)

The eta sweep showed Clarabel solving 0/20 tightened projections at eta >= 1e-10, which is
backwards: a LARGER tightening leaves a LARGER interior and should be EASIER. Unless the tightened
set is going INFEASIBLE — i.e. the feasible set has an interior thinner than 1e-10.

That distinction decides the remedy, so it is measured, not inferred:

  * if the tightened set stays feasible and only Clarabel fails, the proposal solver is the problem;
  * if the tightened set is genuinely EMPTY at eta >= 1e-10, then eta is squeezed between the
    solver's residual floor (~3e-12) and the interior width, and NO eta works robustly. The
    one-coordinate-repair-from-a-numerical-interior-proposal approach would be dead as specified.

The LP is a feasibility ORACLE here, never a proposal.
"""

from __future__ import annotations

import json
import sys
from datetime import date

import numpy as np
from scipy.optimize import linprog

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from scripts.mr002_coverage_signed_gap import (  # noqa: E402
    CORPUS,
    FALLBACK,
    PRIMARY,
    capture,
    try_solve,
)

N = 20
ETAS = [1e-12, 1e-11, 1e-10, 1e-9, 1e-8, 1e-7, 1e-6]


def feasible(eta, A_ub, b_ub, A_eq, b_eq, upper):
    n = A_eq.shape[1]
    keep = [r for r in range(A_ub.shape[0]) if np.any(A_ub[r] != 0.0)]
    u = np.asarray(upper, float)
    if np.any(u <= 2 * eta):
        return False
    r = linprog(c=np.zeros(n),
                A_ub=A_ub[keep] if keep else None,
                b_ub=(b_ub[keep] - eta) if keep else None,
                A_eq=A_eq, b_eq=b_eq,
                bounds=[(eta, float(x) - eta) for x in u], method="highs")
    return bool(r.success)


def max_interior(A_ub, b_ub, A_eq, b_eq, upper):
    """The largest eta for which the tightened set is nonempty — the interior 'thickness'.

    max e  s.t.  A_ub w <= b_ub - e,  e <= w <= u - e,  A_eq w = b_eq,  e >= 0
    A linear program in (w, e).
    """
    n = A_eq.shape[1]
    keep = [r for r in range(A_ub.shape[0]) if np.any(A_ub[r] != 0.0)]
    c = np.zeros(n + 1)
    c[-1] = -1.0                                   # maximise e
    rows, rhs = [], []
    for r in keep:
        rows.append(np.concatenate([A_ub[r], [1.0]]))       # A_ub w + e <= b_ub
        rhs.append(float(b_ub[r]))
    for i in range(n):
        row = np.zeros(n + 1)
        row[i], row[-1] = -1.0, 1.0                          # -w_i + e <= 0
        rows.append(row)
        rhs.append(0.0)
        row2 = np.zeros(n + 1)
        row2[i], row2[-1] = 1.0, 1.0                         # w_i + e <= u_i
        rows.append(row2)
        rhs.append(float(upper[i]))
    A_eq2 = np.hstack([A_eq, np.zeros((A_eq.shape[0], 1))])
    res = linprog(c=c, A_ub=np.array(rows), b_ub=np.array(rhs), A_eq=A_eq2, b_eq=b_eq,
                  bounds=[(None, None)] * n + [(0.0, None)], method="highs")
    return float(res.x[-1]) if res.success else 0.0


def main() -> int:
    jp._solve_qp = capture
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    for cfg in ("A", "B", "C"):
        run_config(days, CONFIGS[cfg])

    picked, seen = [], 0
    for _i, inst in enumerate(CORPUS):
        rec = (inst["t"], inst["A_ub"], inst["b_ub"],
               inst["A_eq"], inst["b_eq"], inst["upper"])
        ok1, _, _z1, _, _ = try_solve(PRIMARY, rec)
        ok2, _, _z2, _, _ = try_solve(FALLBACK, rec)
        if not (ok1 and ok2):
            continue
        picked.append(rec)
        seen += 1
        if seen >= N:
            break

    widths = [max_interior(r[1], r[2], r[3], r[4], r[5]) for r in picked]
    w = np.array(widths)
    print(f"=== {seen} qualifying overlaps ===\n")
    print("MAXIMUM TIGHTENING the feasible set can absorb (its interior 'thickness'):")
    print(f"    min {w.min():.3e}   median {np.median(w):.3e}   max {w.max():.3e}")
    print(f"    below 1e-10: {int((w < 1e-10).sum())}/{seen}    "
          f"below 1e-8: {int((w < 1e-8).sum())}/{seen}")
    print()
    print(f"{'eta':>8}  {'tightened set FEASIBLE (LP)':>28}")
    print("-" * 40)
    table = {}
    for eta in ETAS:
        k = sum(feasible(eta, r[1], r[2], r[3], r[4], r[5]) for r in picked)
        table[eta] = k
        print(f"{eta:>8.0e}  {k:>10} / {seen}")

    print("\nThe usable eta must satisfy BOTH:")
    print("    eta > the proposal solver's inequality-residual floor  (~3e-12, measured)")
    print("    eta < the feasible set's interior thickness            (measured above)")
    print("If those two bounds cross, no eta works and the approach is dead AS SPECIFIED —")
    print("which is an adjudication question, not something to tune around.")

    with open("/out/MR002_InteriorWidth_Diagnosis.json", "w", encoding="utf-8") as fh:
        json.dump({"overlaps": seen, "interior_widths": widths,
                   "feasible_by_eta": {f"{k:.0e}": v for k, v in table.items()},
                   "note": "DIAGNOSTIC ONLY. LP used as a feasibility oracle, never as a proposal."},
                  fh, indent=2)
    print("\nwrote /out/MR002_InteriorWidth_Diagnosis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
