"""Which eta makes R2 work? (ruling §13 — DIAGNOSTIC ONLY, adjudicate; do not adjust)

Nothing is changed. eta, the tolerances, the profile and the certificate are all untouched, and
NOTHING produced here is used as a proposal or enters any certificate.

WHAT SAMPLE A SHOWED. Clarabel refused 40/50 tightened projections at tol 1e-14. Loosening the
tolerance to 1e-10 makes it converge 20/20 — but the point it returns violates the TIGHTENED set by
a median of 2.9e-12, i.e. by MORE than eta = 1e-12. The tightening is swamped by the proposal
solver's own attainable accuracy, and buys no original-set slack at all.

So the failure is not that eta is too large. It is that eta is TOO SMALL to survive the numerics of
the proposal solver.

THE CORRECTED REQUIREMENT. Two residuals matter, and they act differently:

  r_eq   |A_eq w - b_eq|          the absorber CORRECTS this exactly, by moving one coordinate by
                                  Delta ~ r_eq / |a_k|. That correction then perturbs every
                                  inequality row containing k by ~Delta. So r_eq must be small
                                  compared to eta, or the absorber itself eats the slack.

  r_ineq max(A_ub w - (b_ub-eta), 0)  and the bound violations. Original-set slack = eta - r_ineq,
                                  so r_ineq must be BELOW eta or the point is already outside the
                                  original set.

  => a usable proposal needs  eta  >  (r_ineq + C * r_eq)  with room to spare.

An eta far below the solver's residual floor cannot satisfy that at any tolerance. This sweep
measures the floor and reports, for each (eta, tol), how many overlaps actually obtain an EXACT
REPAIR from the unmodified constructor — which is the only column that decides anything.

COST OF A LARGER ETA is bounded and small: delta ~ eta*sqrt(n) enters the radius additively, and
Ghat ~ |grad f| * delta. Sample A already ran with worst delta 6.2e-08 and worst repaired gap
2.9e-08 while the radius-agreement ratio sat at 7.7e-06 — five orders of margin. The agreement
gates can absorb a much larger eta without difficulty.
"""

from __future__ import annotations

import json
import sys
import warnings
from datetime import date
from fractions import Fraction

import numpy as np
import scipy.sparse as sp

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.certificate import to_fraction  # noqa: E402
from app.research.mr002.repair import (  # noqa: E402
    CLARABEL_DYNAMIC_DELTA,
    CLARABEL_DYNAMIC_EPS,
    CLARABEL_PROPORTIONAL,
    CLARABEL_STATIC_REG,
    canonical_order,
)
from scripts.mr002_coverage_signed_gap import (  # noqa: E402
    CORPUS,
    FALLBACK,
    PRIMARY,
    capture,
    try_solve,
)

N = 20
ETAS = [1e-12, 1e-11, 1e-10, 1e-9, 1e-8, 1e-7]
TOLS = [1e-10]


def tightened(eta, z_s, A_ub, b_ub, A_eq, b_eq, upper):
    """The R2 construction, with eta as a parameter (diagnostic only)."""
    n = len(z_s)
    p, rows = canonical_order(z_s, A_ub, b_ub, A_eq, b_eq, upper)
    A_nz = A_ub[np.ix_(rows, p)] if rows else np.zeros((0, n))
    b_nz = b_ub[rows] if rows else np.zeros(0)
    u = np.asarray(upper, float)[p]
    A = np.vstack([A_eq[:, p], A_nz, -np.eye(n), np.eye(n)])
    b = np.concatenate([np.asarray(b_eq, float), b_nz - eta, np.full(n, -eta), u - eta])
    return p, rows, A, b


def solve(tol, eta, z_s, A_ub, b_ub, A_eq, b_eq, upper):
    import clarabel

    z_s = np.asarray(z_s, float)
    n = len(z_s)
    meq = A_eq.shape[0]
    p, rows, A, b = tightened(eta, z_s, A_ub, b_ub, A_eq, b_eq, upper)

    s = clarabel.DefaultSettings()
    s.max_threads, s.max_iter, s.time_limit, s.verbose = 1, 500, 60.0, False
    for f in ("tol_gap_abs", "tol_gap_rel", "tol_feas", "tol_infeas_abs", "tol_infeas_rel"):
        setattr(s, f, tol)
    s.equilibrate_enable = True
    s.presolve_enable = False
    s.direct_kkt_solver = True
    s.direct_solve_method = "qdldl"
    s.static_regularization_enable = True
    s.static_regularization_constant = CLARABEL_STATIC_REG
    s.static_regularization_proportional = CLARABEL_PROPORTIONAL
    s.dynamic_regularization_enable = True
    s.dynamic_regularization_eps = CLARABEL_DYNAMIC_EPS
    s.dynamic_regularization_delta = CLARABEL_DYNAMIC_DELTA
    s.iterative_refinement_enable = True

    cones = [clarabel.ZeroConeT(meq), clarabel.NonnegativeConeT(len(rows) + 2 * n)]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            sol = clarabel.DefaultSolver(sp.csc_matrix(np.eye(n)), -z_s[p],
                                         sp.csc_matrix(A), b, cones, s).solve()
    except Exception as e:  # noqa: BLE001
        return f"EXC:{type(e).__name__}", None, None, None

    status = str(sol.status)
    x = np.asarray(sol.x, float)
    if x.shape != (n,) or not np.all(np.isfinite(x)):
        return status, None, None, None
    r_eq = float(np.max(np.abs(A[:meq] @ x - b[:meq])))
    r_ineq = float(np.max(np.maximum(A[meq:] @ x - b[meq:], 0.0)))
    w = np.empty(n)
    w[np.asarray(p)] = x
    return status, r_eq, r_ineq, w


def exact_repair_exists(w_tilde, A_ub, b_ub, A_eq, b_eq, upper):
    """The UNMODIFIED constructor's verdict: does any absorber verify against the ORIGINAL set?"""
    n = len(upper)
    U = [to_fraction(v) for v in np.asarray(upper, float).ravel()]
    x = [min(max(to_fraction(w_tilde[i]), Fraction(0)), U[i]) for i in range(n)]
    a = [to_fraction(v) for v in np.asarray(A_eq, float)[0]]
    beta = to_fraction(np.asarray(b_eq, float).ravel()[0])
    Aub = np.asarray(A_ub, float)
    Bub = [to_fraction(v) for v in np.asarray(b_ub, float).ravel()]
    for k in range(n):
        if a[k] == 0:
            continue
        w = list(x)
        w[k] = (beta - sum(a[i] * x[i] for i in range(n) if i != k)) / a[k]
        if not (Fraction(0) <= w[k] <= U[k]):
            continue
        if all(sum(to_fraction(Aub[r, i]) * w[i] for i in range(n)) <= Bub[r]
               for r in range(len(Bub))):
            return True
    return False


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
        ok1, _, z1, _, _ = try_solve(PRIMARY, rec)
        ok2, _, _z2, _, _ = try_solve(FALLBACK, rec)
        if not (ok1 and ok2):
            continue
        picked.append((z1, rec))
        seen += 1
        if seen >= N:
            break

    print(f"=== {seen} qualifying overlaps, PRIMARY point, R2 tightened projection ===")
    print("=== The only column that decides anything is REPAIRED: the unmodified exact")
    print("=== constructor certifying membership in the ORIGINAL untightened set.\n")
    print(f"{'eta':>8} {'tol':>8} {'Solved':>7} {'REPAIRED':>9}  {'med r_eq':>10} "
          f"{'med r_ineq':>11}")
    print("-" * 60)

    out = []
    for eta in ETAS:
        for tol in TOLS:
            n_solved = n_rep = 0
            eqs, ins = [], []
            stats: dict[str, int] = {}
            for z1, rec in picked:
                st, r_eq, r_ineq, w = solve(tol, eta, z1, *rec[1:])
                stats[st] = stats.get(st, 0) + 1
                if st != "Solved" or w is None:
                    continue
                n_solved += 1
                eqs.append(r_eq)
                ins.append(r_ineq)
                if exact_repair_exists(w, rec[1], rec[2], rec[3], rec[4], rec[5]):
                    n_rep += 1
            me = float(np.median(eqs)) if eqs else float("nan")
            mi = float(np.median(ins)) if ins else float("nan")
            print(f"{eta:>8.0e} {tol:>8.0e} {n_solved:>7} {n_rep:>9}  {me:>10.2e} {mi:>11.2e}")
            print(f"         statuses: {stats}")
            out.append({"eta": eta, "tol": tol, "solved": n_solved, "repaired": n_rep,
                        "median_r_eq": me, "median_r_ineq": mi})

    print("\nThe proposal solver's residual FLOOR is what sets the usable eta. An eta below that")
    print("floor cannot buy original-set slack at any tolerance — which is why eta = 1e-12 fails")
    print("and why the remedy is a LARGER eta, not a tighter tolerance.")

    with open("/out/MR002_EtaSweep_Diagnosis.json", "w", encoding="utf-8") as fh:
        json.dump({"overlaps": seen, "grid": out,
                   "note": "DIAGNOSTIC ONLY. No output used as a proposal or in any certificate. "
                           "eta and the frozen profile are UNCHANGED."}, fh, indent=2)
    print("\nwrote /out/MR002_EtaSweep_Diagnosis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
