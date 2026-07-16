"""Is HiGHS's optimal basis EXACTLY primal-feasible in the all-equality standard form?

The exact reconstruction fails with `Mx = h` inconsistent. Two possibilities:

  (a) my reconstruction is wrong;
  (b) the basis is EXACTLY primal-infeasible — HiGHS accepted it because the violation is below its
      float tolerance.

Structure of the suspicion: in the canonical nonnegative standard form EVERY row is an equality, so
every ROW LOGICAL is a FIXED variable (lb = ub = h_r). A basic fixed variable is degenerate, and its
exactly-reconstructed value need not sit on its bound. The basic solution is then exactly
infeasible even though the float simplex sees the violation as ~1e-16 and calls it optimal.

Test: solve the square system on the NONBASIC rows only (those are the ones that genuinely
constrain the basic structural columns), then measure, exactly, how far the BASIC rows are from
their equality bound. If that gap is ~1e-16 rather than 0, hypothesis (b) is confirmed and the
all-equality submission form is the defect — not the repair method.
"""

from __future__ import annotations

import sys
from datetime import date
from fractions import Fraction

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.exact_repair import (  # noqa: E402
    basis_from_highs,
    build_standard_form,
    exact_solve,
)
from scripts.mr002_coverage_signed_gap import (  # noqa: E402
    CORPUS,
    FALLBACK,
    PRIMARY,
    capture,
    try_solve,
)

N = 8


def main() -> int:
    jp._solve_qp = capture
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    for cfg in ("A", "B", "C"):
        run_config(days, CONFIGS[cfg])

    seen = 0
    for i, inst in enumerate(CORPUS):
        rec = (inst["t"], inst["A_ub"], inst["b_ub"],
               inst["A_eq"], inst["b_eq"], inst["upper"])
        p_ok, _, z1, _, _ = try_solve(PRIMARY, rec)
        f_ok, _, _z2, _, _ = try_solve(FALLBACK, rec)
        if not (p_ok and f_ok):
            continue

        # Does the model contain coefficients that HiGHS's `small_matrix_value` would DROP?
        import numpy as _np
        nzs = _np.abs(_np.concatenate([rec[3].ravel(), rec[1].ravel()]))
        nzs = nzs[nzs > 0]
        print(f"     min |nonzero A_eq/A_ub coeff| = {nzs.min():.3e}  "
              f"(small_matrix_value would drop anything below it)")
        M, h, c, n, m, _perm, _rows = build_standard_form(z1, *rec[1:])
        nrows, ncols = len(M), len(c)
        bc, br = basis_from_highs(M, h, c)
        nonbasic_rows = [r for r in range(nrows) if r not in set(br)]

        print(f"i={i:<4} n={n:<3} rows={nrows} cols={ncols} "
              f"basic_struct={len(bc)} basic_rows={len(br)} nonbasic_rows={len(nonbasic_rows)}")

        # The rows that actually constrain the basic structural columns are the NONBASIC ones:
        # a nonbasic row's logical sits at its bound h_r, so sum_j M[r,j] x_j = h_r.
        # A BASIC row's logical is an unknown -- the row does not constrain x at all.
        if len(bc) != len(nonbasic_rows):
            print("     (basic structural count != nonbasic row count — cannot square the system)")
            seen += 1
            if seen >= N:
                break
            continue

        cols = [[M[r][j] for r in nonbasic_rows] for j in bc]
        rhs = [h[r] for r in nonbasic_rows]
        try:
            xB, n_single, core = exact_solve(cols, rhs)
        except Exception as e:  # noqa: BLE001
            print(f"     square solve failed: {type(e).__name__}: {str(e)[:60]}")
            seen += 1
            if seen >= N:
                break
            continue

        x = [Fraction(0)] * ncols
        for idx, j in enumerate(bc):
            x[j] = xB[idx]

        worst = Fraction(0)
        for r in br:                                  # a BASIC fixed logical must equal its bound
            acc = Fraction(0)
            for j in range(ncols):
                if M[r][j] != 0:
                    acc += M[r][j] * x[j]
            worst = max(worst, abs(acc - h[r]))
        neg = sum(1 for v in x if v < 0)
        print(f"     square solve OK (singles={n_single}, core={core}). "
              f"worst |basic-row activity - h| = {float(worst):.3e}   negative vars: {neg}")

        seen += 1
        if seen >= N:
            break

    print("\nIf `worst` is ~1e-16 rather than exactly 0, HiGHS's basis is EXACTLY primal-infeasible")
    print("in the all-equality standard form: the degenerate basic FIXED logicals sit off their")
    print("bounds. The repair METHOD is fine; the all-equality submission form is the defect.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
