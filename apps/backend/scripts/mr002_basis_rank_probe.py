"""Is HiGHS's basis EXACTLY consistent, at any tolerance? (capability characterization, not evidence)

The decisive question is not the size of the residual. It is whether

    M[:, S] x_S = h

has ANY exact rational solution — i.e. whether  rank(M[:,S]) == rank([M[:,S] | h]).

If the ranks differ, the basis does not correspond to ANY exactly feasible point, and no tolerance
can rescue it: the residual would merely shrink while remaining nonzero. That is precisely the case
the owner names — "if it merely reduces the residual while exact reconstruction still fails, the
basis-oracle approach itself stops for adjudication."

Swept over candidate oracle profiles. Nothing here is evidence; no profile is frozen.
"""

from __future__ import annotations

import sys
from datetime import date
from fractions import Fraction

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.exact_repair import build_standard_form  # noqa: E402
from scripts.mr002_coverage_signed_gap import (  # noqa: E402
    CORPUS,
    FALLBACK,
    PRIMARY,
    capture,
    try_solve,
)

N = 8

PROFILES = [
    ("default tol, scaling on", {"primal_feasibility_tolerance": 1e-7,
                                 "dual_feasibility_tolerance": 1e-7}),
    ("tol 1e-10, scaling on", {"primal_feasibility_tolerance": 1e-10,
                               "dual_feasibility_tolerance": 1e-10}),
    ("tol 1e-10, scaling OFF", {"primal_feasibility_tolerance": 1e-10,
                                "dual_feasibility_tolerance": 1e-10,
                                "simplex_scale_strategy": 0}),
    ("tol 1e-12, scaling OFF", {"primal_feasibility_tolerance": 1e-12,
                                "dual_feasibility_tolerance": 1e-12,
                                "simplex_scale_strategy": 0}),
]


def exact_rank(rows):
    """Exact rational rank by Gaussian elimination."""
    A = [list(r) for r in rows]
    nr = len(A)
    nc = len(A[0]) if nr else 0
    rank = 0
    for col in range(nc):
        piv = next((i for i in range(rank, nr) if A[i][col] != 0), None)
        if piv is None:
            continue
        A[rank], A[piv] = A[piv], A[rank]
        pv = A[rank][col]
        for i in range(rank + 1, nr):
            if A[i][col] != 0:
                f = A[i][col] / pv
                for j in range(col, nc):
                    A[i][j] -= f * A[rank][j]
        rank += 1
    return rank


def run(profile, M, h, c):
    import highspy
    import scipy.sparse as sp

    nrows, ncols = len(M), len(c)
    Mf = np.array([[float(v) for v in r] for r in M])
    hf = np.array([float(v) for v in h])
    hs = highspy.Highs()
    base = {"output_flag": False, "log_to_console": False, "solver": "simplex",
            "simplex_strategy": 1, "presolve": "off", "parallel": "off",
            "threads": 1, "random_seed": 0}
    for k, v in {**base, **profile}.items():
        hs.setOptionValue(k, v)
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = ncols, nrows
    lp.col_cost_ = [float(v) for v in c]
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
    if "kOptimal" not in str(hs.getModelStatus()):
        return None, str(hs.getModelStatus())
    b = hs.getBasis()
    bc = [j for j in range(ncols) if "kBasic" in str(b.col_status[j])]
    obj = hs.getInfo().objective_function_value
    rho_basic = "kBasic" in str(b.col_status[ncols - 1])   # the rho column is last
    return bc, f"kOptimal|rho={obj:.3e}|rho_basic={rho_basic}"


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
        p_ok, _, z1, _, _ = try_solve(PRIMARY, rec)
        f_ok, _, _z2, _, _ = try_solve(FALLBACK, rec)
        if not (p_ok and f_ok):
            continue
        picked.append((z1, rec))
        seen += 1
        if seen >= N:
            break

    print(f"=== {seen} overlaps.  CONSISTENT = rank(M[:,S]) == rank([M[:,S] | h])  (exact) ===\n")
    for label, prof in PROFILES:
        consistent = full_rank = 0
        notes = []
        for z1, rec in picked:
            M, h, c, _n, _m, _p, _r = build_standard_form(z1, *rec[1:])
            bc, st = run(prof, M, h, c)
            if bc is None:
                continue
            sub = [[M[r][j] for j in bc] for r in range(len(M))]
            aug = [[M[r][j] for j in bc] + [h[r]] for r in range(len(M))]
            r1, r2 = exact_rank(sub), exact_rank(aug)
            if r1 == r2:
                consistent += 1
            if r1 == len(bc):
                full_rank += 1
            notes.append(st)
        print(f"  {label:26}  exactly consistent: {consistent}/{seen}   "
              f"full column rank: {full_rank}/{seen}")
        print(f"       {notes[0]}")
        print(f"       {notes[1]}")

    print("\nIf CONSISTENT stays below the sample size at every tolerance, the basis oracle cannot")
    print("supply an exactly feasible basis on this geometry, and no tolerance fixes it.")
    _ = Fraction
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
