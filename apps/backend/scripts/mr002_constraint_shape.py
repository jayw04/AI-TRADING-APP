"""What shape are the Stage-3 constraints? The feasible-repair design depends on it.

Specifically: how many equality rows, are they all-ones (a budget), and is there interior slack?
An exact-rational repair is trivial for one budget row and needs a small exact linear solve for
several. Checked, not assumed.
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from scripts.mr002_coverage_signed_gap import CORPUS, capture  # noqa: E402


def main() -> int:
    jp._solve_qp = capture
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    for cfg in ("A", "B", "C"):
        run_config(days, CONFIGS[cfg])

    meq = Counter()
    mub = Counter()
    eq_all_ones = 0
    n_vals = Counter()
    ub_row_nnz = Counter()
    budget_vs_capsum = []
    for inst in CORPUS:
        A_eq, A_ub, b_eq, b_ub, u = (inst["A_eq"], inst["A_ub"], inst["b_eq"],
                                     inst["b_ub"], inst["upper"])
        meq[A_eq.shape[0]] += 1
        mub[A_ub.shape[0]] += 1
        n_vals[len(inst["t"])] += 1
        if A_eq.shape[0] == 1 and np.array_equal(A_eq[0], np.ones(A_eq.shape[1])):
            eq_all_ones += 1
        for r in range(A_ub.shape[0]):
            ub_row_nnz[int(np.count_nonzero(A_ub[r]))] += 1
        if A_eq.shape[0] == 1:
            # how much room is there between the budget and the sum of the upper bounds?
            budget_vs_capsum.append(float(u.sum() - b_eq[0]))

    print("instances                :", len(CORPUS))
    print("equality rows (count)    :", dict(meq))
    print("equality row is all-ones :", eq_all_ones, "/", len(CORPUS))
    print("inequality rows (count)  :", dict(sorted(mub.items())))
    ns = sorted(n_vals)
    print("n (variables)            : min", ns[0], " max", ns[-1],
          " p95", ns[int(0.95 * (len(ns) - 1))])
    mub_max = max(mub)
    print("standard-form size (4n + m_ub + 1 vars, 1 + m_ub + 3n rows) at max n:",
          f"vars ~{4 * ns[-1] + mub_max + 1}, rows ~{1 + mub_max + 3 * ns[-1]}")
    print("A_ub row nonzeros        :", dict(sorted(ub_row_nnz.items())[:8]), "...")
    if budget_vs_capsum:
        a = np.array(budget_vs_capsum)
        print(f"sum(upper) - b_eq        : min {a.min():.6g}  median {np.median(a):.6g}  "
              f"max {a.max():.6g}")
        print(f"  instances with NO box slack (<=0): {int((a <= 0).sum())}")
        print("  (If this is comfortably positive, an exact-rational absorber coordinate always")
        print("   exists and the repair needs no inward tightening.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
