"""Why does Clarabel refuse 40/50 tightened projections? (ruling §13 — adjudicate, do not adjust)

Nothing is changed. The frozen C1 profile is untouched, and NOTHING produced here is used as a
proposal or enters any certificate. This is evidence for the owner's ruling.

TWO HYPOTHESES, and they call for different remedies:

  H1  The 1e-14 tolerance is unreachable for these problems at any settings.
      -> the eps = eta/100 derivation, or eta itself, has to be revisited.

  H2  The imported REGULARIZATION VALUES are the blocker.
      The validated Clarabel profile was frozen against the STAGE-3 QP, whose Hessian is
      diag(2/t) — badly conditioned. `static_regularization_constant = 1e-8` is appropriate there.
      The PROJECTION QP has P = I, which is perfectly conditioned. A 1e-8 static regularization on
      an identity Hessian is enormous relative to the 1e-14 accuracy being demanded, and would
      floor the achievable residual far above it.
      -> the field NAMES were rightly imported; the VALUES should not have been.

The discriminating measurement is not the status string, it is the ACHIEVED FEASIBILITY RESIDUAL
on the tightened constraints, measured independently of what Clarabel reports about itself.

THE BINDING REQUIREMENT that any remedy must satisfy: the proposal's violation of the tightened
constraints must be strictly below eta, because the original-set slack it buys is (eta - residual).
A residual of 1e-10 buys NOTHING — it leaves the proposal outside the original set by more than the
tightening moved it in. So the column that decides this is `max_tightened_violation < 1e-12`.
"""

from __future__ import annotations

import json
import sys
import warnings
from datetime import date

import numpy as np
import scipy.sparse as sp

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.repair import (  # noqa: E402
    CLARABEL_DYNAMIC_DELTA,
    CLARABEL_DYNAMIC_EPS,
    CLARABEL_PROPORTIONAL,
    ETA_FLOAT,
    build_tightened_problem,
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

# (label, tolerance, static_regularization_constant)
GRID = [
    ("C1 as frozen        (tol 1e-14, static 1e-8)", 1e-14, 1e-8),
    ("H2: identity-scale  (tol 1e-14, static 1e-12)", 1e-14, 1e-12),
    ("H2: identity-scale  (tol 1e-14, static 1e-14)", 1e-14, 1e-14),
    ("H2: no static reg   (tol 1e-14, static OFF)", 1e-14, None),
    ("H1: looser tol      (tol 1e-12, static 1e-8)", 1e-12, 1e-8),
    ("H1: looser tol      (tol 1e-10, static 1e-8)", 1e-10, 1e-8),
]


def run(tol, static_reg, z_s, A_ub, b_ub, A_eq, b_eq, upper):
    import clarabel

    z_s = np.asarray(z_s, float)
    n = len(z_s)
    p, rows = canonical_order(z_s, A_ub, b_ub, A_eq, b_eq, upper)
    A, b, _k = build_tightened_problem(
        A_ub[np.ix_(rows, p)] if rows else np.zeros((0, n)),
        b_ub[rows] if rows else np.zeros(0),
        A_eq[:, p], b_eq, np.asarray(upper, float)[p])
    meq = A_eq.shape[0]

    s = clarabel.DefaultSettings()
    s.max_threads = 1
    s.max_iter = 500
    s.time_limit = 60.0
    s.verbose = False
    for f in ("tol_gap_abs", "tol_gap_rel", "tol_feas", "tol_infeas_abs", "tol_infeas_rel"):
        setattr(s, f, tol)
    s.equilibrate_enable = True
    s.presolve_enable = False
    s.direct_kkt_solver = True
    s.direct_solve_method = "qdldl"
    s.static_regularization_enable = static_reg is not None
    if static_reg is not None:
        s.static_regularization_constant = static_reg
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
        return f"EXC:{type(e).__name__}", None

    status = str(sol.status)
    x = np.asarray(sol.x, float)
    if x.shape != (n,) or not np.all(np.isfinite(x)):
        return status, None
    # The residual MEASURED BY US, not reported by the solver: max violation of the TIGHTENED set.
    viol = float(np.max(np.concatenate([
        np.abs(A[:meq] @ x - b[:meq]),
        np.maximum(A[meq:] @ x - b[meq:], 0.0),
    ])))
    return status, viol


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
    for i, inst in enumerate(CORPUS):
        rec = (inst["t"], inst["A_ub"], inst["b_ub"],
               inst["A_eq"], inst["b_eq"], inst["upper"])
        ok1, _, z1, _, _ = try_solve(PRIMARY, rec)
        ok2, _, _z2, _, _ = try_solve(FALLBACK, rec)
        if not (ok1 and ok2):
            continue
        picked.append((i, z1, rec))
        seen += 1
        if seen >= N:
            break

    print(f"=== {seen} qualifying overlaps (primary point), tightened projection ===")
    print(f"=== eta = {ETA_FLOAT:.0e}. A proposal is only USEFUL if its tightened-set violation")
    print("=== is BELOW eta — otherwise the tightening bought no original-set slack at all.\n")

    out = {}
    for label, tol, sreg in GRID:
        statuses: dict[str, int] = {}
        viols = []
        usable = 0
        for _i, z1, rec in picked:
            st, v = run(tol, sreg, z1, *rec[1:])
            statuses[st] = statuses.get(st, 0) + 1
            if v is not None:
                viols.append(v)
                if st == "Solved" and v < ETA_FLOAT:
                    usable += 1
        med = float(np.median(viols)) if viols else float("nan")
        worst = float(np.max(viols)) if viols else float("nan")
        n_solved = statuses.get("Solved", 0)
        print(f"{label}")
        print(f"    Solved {n_solved:>2}/{seen}   usable (Solved AND violation < eta): {usable:>2}"
              f"   median violation {med:.2e}   worst {worst:.2e}")
        print(f"    statuses: {statuses}")
        out[label] = {"tol": tol, "static_reg": sreg, "solved": n_solved, "usable": usable,
                      "median_violation": med, "worst_violation": worst, "statuses": statuses}

    print("\nREAD THE `usable` COLUMN, not `Solved`. A converged proposal whose tightened-set")
    print("violation exceeds eta is worthless: it sits outside the original set by more than the")
    print("tightening moved it in, and the exact constructor will reject every absorber.")

    with open("/out/MR002_C1_Convergence_Diagnosis.json", "w", encoding="utf-8") as fh:
        json.dump({"overlaps": seen, "eta": ETA_FLOAT, "grid": out,
                   "note": "DIAGNOSTIC ONLY. No output used as a proposal or in any certificate."},
                  fh, indent=2)
    print("\nwrote /out/MR002_C1_Convergence_Diagnosis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
