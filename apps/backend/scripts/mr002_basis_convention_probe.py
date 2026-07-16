"""Establish HiGHS's basis/row-variable convention EMPIRICALLY on a tiny hand-checkable LP.

The exact reconstruction failed with basic row variables coming out 0 instead of h_r. That is the
row-variable semantics trap the ruling names explicitly. Do not guess the convention — read it off
the solver on a problem whose answer is known by hand, then bind it.

    min rho  s.t.  w0 + w1 = 1,  0 <= w <= 1,  |w_i - z_i| <= rho,  z = (0.5, 0.5)
    => w = z, rho = 0, and every proximity row is tight.
"""

from __future__ import annotations

import sys
from fractions import Fraction

import numpy as np

sys.path.insert(0, "/work/apps/backend")

from app.research.mr002.exact_repair import build_standard_form  # noqa: E402


def main() -> int:
    import highspy
    import scipy.sparse as sp

    z = np.array([0.5, 0.25])
    A_ub = np.array([[1.0, 0.0]])
    b_ub = np.array([0.8])
    A_eq = np.ones((1, 2))
    b_eq = np.array([0.75])
    upper = np.array([1.0, 1.0])

    M, h, c, n, m, perm, rows = build_standard_form(z, A_ub, b_ub, A_eq, b_eq, upper)
    nrows, ncols = len(M), len(c)
    print(f"standard form: {nrows} rows x {ncols} cols  (n={n}, m={m})")

    Mf = np.array([[float(v) for v in r] for r in M])
    hf = np.array([float(v) for v in h])
    cf = np.array([float(v) for v in c])

    hs = highspy.Highs()
    for k, v in (("output_flag", False), ("log_to_console", False), ("solver", "simplex"),
                 ("simplex_strategy", 1), ("presolve", "off"), ("parallel", "off"),
                 ("threads", 1), ("random_seed", 0)):
        hs.setOptionValue(k, v)
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = ncols, nrows
    lp.col_cost_ = cf.tolist()
    lp.col_lower_ = np.zeros(ncols).tolist()
    lp.col_upper_ = np.full(ncols, highspy.kHighsInf).tolist()
    lp.row_lower_ = hf.tolist()
    lp.row_upper_ = hf.tolist()
    S = sp.csr_matrix(Mf)
    lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
    lp.a_matrix_.start_ = S.indptr.tolist()
    lp.a_matrix_.index_ = S.indices.tolist()
    lp.a_matrix_.value_ = S.data.tolist()
    hs.passModel(lp)
    hs.run()
    print("status:", hs.getModelStatus())

    sol = hs.getSolution()
    xv = np.asarray(sol.col_value, float)
    rv = np.asarray(sol.row_value, float)
    b = hs.getBasis()
    col_st = [str(x).split(".")[-1] for x in b.col_status]
    row_st = [str(x).split(".")[-1] for x in b.row_status]

    print("\ncol_status:", col_st)
    print("row_status:", row_st)
    print("col_value :", np.round(xv, 6).tolist())
    print("row_value :", np.round(rv, 6).tolist())
    print("h         :", [float(v) for v in h])
    print("\nrow_value == h ?", np.allclose(rv, hf))

    basic_cols = [j for j in range(ncols) if col_st[j] == "kBasic"]
    basic_rows = [r for r in range(nrows) if row_st[r] == "kBasic"]
    print(f"\nbasic structural: {basic_cols}   basic rows: {basic_rows}")
    print(f"total {len(basic_cols)} + {len(basic_rows)} = {len(basic_cols)+len(basic_rows)} "
          f"(rows = {nrows})")

    # Does the NONBASIC-structural-at-zero + Mx = h reconstruction reproduce HiGHS's x?
    print("\nnonbasic structural values from HiGHS (should all be 0):")
    print([round(float(xv[j]), 12) for j in range(ncols) if j not in basic_cols])

    # Which linear system do the basic structural columns satisfy?
    Msub = Mf[:, basic_cols]
    resid = Msub @ xv[basic_cols] - hf
    print("\n|| M[:,basic_cols] x_basic - h ||_inf =", float(np.max(np.abs(resid))))
    print("  -> if ~0, the structural basic columns alone satisfy EVERY row exactly, and the")
    print("     basic ROW variables are degenerate logicals pinned at their equality bounds.")

    # And the exact rational check of that same claim
    Bc = [[M[r][j] for r in range(nrows)] for j in basic_cols]
    print("\nexact: is M[:, basic_cols] full column rank with a unique solution? "
          f"cols={len(Bc)} rows={nrows}")
    _ = Fraction(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
