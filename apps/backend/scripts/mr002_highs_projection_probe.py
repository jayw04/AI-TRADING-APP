"""Can HiGHS solve the R2 tightened EUCLIDEAN PROJECTION? (DIAGNOSTIC ONLY — nothing changed.)

The owner excluded HiGHS from the proposal role because its LP feasibility result "is not the
registered Euclidean projection". That is correct about the LP. But HiGHS also has a QP solver, and
that IS the projection — so the exclusion rests on a premise worth testing, now that BOTH
authorized proposal solvers have failed:

    quadprog  false `constraints are inconsistent` at eta = 1e-12          (LP: feasible)
    Clarabel  converges at eta <= 1e-11 but its own inequality residual
              EXCEEDS eta, so the tightening buys nothing;
              false `PrimalInfeasible` at eta >= 1e-10                     (LP: feasible)

This probe measures, for HiGHS QP on the same tightened projections:
    status, the residuals WE measure (not what the solver reports), and — decisively — whether the
    UNMODIFIED exact constructor then certifies membership in the ORIGINAL untightened set.

Nothing here is used as a proposal or enters any certificate. It is evidence for a ruling.
"""

from __future__ import annotations

import json
import sys
from datetime import date

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.repair import canonical_order  # noqa: E402
from scripts.mr002_coverage_signed_gap import (  # noqa: E402
    CORPUS,
    FALLBACK,
    PRIMARY,
    capture,
    try_solve,
)
from scripts.mr002_eta_sweep_diagnosis import exact_repair_exists  # noqa: E402

N = 20
ETAS = [1e-12, 1e-11, 1e-10, 1e-9, 1e-8]


def highs_projection(eta, z_s, A_ub, b_ub, A_eq, b_eq, upper):
    """min 1/2||w - z_s||^2 over the tightened set, via HiGHS QP."""
    import highspy
    import scipy.sparse as sp

    z_s = np.asarray(z_s, float)
    n = len(z_s)
    p, rows = canonical_order(z_s, A_ub, b_ub, A_eq, b_eq, upper)
    A_nz = A_ub[np.ix_(rows, p)] if rows else np.zeros((0, n))
    b_nz = b_ub[rows] if rows else np.zeros(0)
    u = np.asarray(upper, float)[p]

    rows_all = np.vstack([A_eq[:, p], A_nz]) if rows else A_eq[:, p]
    lo = np.concatenate([np.asarray(b_eq, float), np.full(len(rows), -highspy.kHighsInf)])
    hi = np.concatenate([np.asarray(b_eq, float), b_nz - eta])

    h = highspy.Highs()
    # Options taken from the VALIDATED HiGHS path, not re-derived. `qp_regularization_value = 0`
    # matters: the 1e-7 default would silently ALTER the QP being solved.
    for k, v in (("output_flag", False), ("log_to_console", False), ("solver", "qpasm"),
                 ("presolve", "off"), ("parallel", "off"), ("threads", 1), ("random_seed", 0),
                 ("time_limit", 60.0), ("qp_allow_hot_start", False),
                 ("qp_regularization_value", 0.0), ("small_matrix_value", 1e-12),
                 ("kkt_tolerance", 1e-10)):
        if "kOk" not in str(h.setOptionValue(k, v)):
            return f"option_rejected:{k}", None, None, None

    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = n, rows_all.shape[0]
    lp.col_cost_ = (-z_s[p]).tolist()                     # 1/2 w'Iw - z_s'w
    lp.col_lower_ = np.full(n, eta).tolist()
    lp.col_upper_ = (u - eta).tolist()
    lp.row_lower_, lp.row_upper_ = lo.tolist(), hi.tolist()
    S = sp.csr_matrix(rows_all)
    lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
    lp.a_matrix_.start_ = S.indptr.tolist()
    lp.a_matrix_.index_ = S.indices.tolist()
    lp.a_matrix_.value_ = S.data.tolist()

    hess = highspy.HighsHessian()
    hess.dim_ = n
    hess.format_ = highspy.HessianFormat.kTriangular
    hess.start_ = list(range(n + 1))
    hess.index_ = list(range(n))
    hess.value_ = [1.0] * n                               # P = I
    model = highspy.HighsModel()
    model.lp_ = lp
    model.hessian_ = hess
    if "kOk" not in str(h.passModel(model)):
        return "passModel_failed", None, None, None
    if "kOk" not in str(h.run()):
        return "run_not_ok", None, None, None
    ms = str(h.getModelStatus())
    x = np.asarray(h.getSolution().col_value, float)
    if x.shape != (n,) or not np.all(np.isfinite(x)):
        return ms, None, None, None

    meq = A_eq.shape[0]
    A_full = np.vstack([A_eq[:, p], A_nz, -np.eye(n), np.eye(n)])
    b_full = np.concatenate([np.asarray(b_eq, float), b_nz - eta,
                             np.full(n, -eta), u - eta])
    r_eq = float(np.max(np.abs(A_full[:meq] @ x - b_full[:meq])))
    r_ineq = float(np.max(np.maximum(A_full[meq:] @ x - b_full[meq:], 0.0)))
    w = np.empty(n)
    w[np.asarray(p)] = x
    return ms, r_eq, r_ineq, w


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

    print(f"=== HiGHS QP on the R2 tightened projection, {seen} qualifying overlaps ===")
    print("=== REPAIRED = the UNMODIFIED exact constructor certifies the ORIGINAL set.\n")
    print(f"{'eta':>8} {'Optimal':>8} {'REPAIRED':>9}  {'med r_eq':>10} {'med r_ineq':>11}")
    print("-" * 54)
    out = []
    for eta in ETAS:
        n_ok = n_rep = 0
        eqs, ins, stats = [], [], {}
        for z1, rec in picked:
            st, r_eq, r_ineq, w = highs_projection(eta, z1, *rec[1:])
            stats[st] = stats.get(st, 0) + 1
            if w is None or "ptimal" not in st:
                continue
            n_ok += 1
            eqs.append(r_eq)
            ins.append(r_ineq)
            if exact_repair_exists(w, rec[1], rec[2], rec[3], rec[4], rec[5]):
                n_rep += 1
        me = float(np.median(eqs)) if eqs else float("nan")
        mi = float(np.median(ins)) if ins else float("nan")
        print(f"{eta:>8.0e} {n_ok:>8} {n_rep:>9}  {me:>10.2e} {mi:>11.2e}")
        print(f"         statuses: {stats}")
        out.append({"eta": eta, "optimal": n_ok, "repaired": n_rep,
                    "median_r_eq": me, "median_r_ineq": mi, "statuses": stats})

    with open("/out/MR002_HiGHS_Projection_Probe.json", "w", encoding="utf-8") as fh:
        json.dump({"overlaps": seen, "grid": out,
                   "note": "DIAGNOSTIC ONLY. Not used as a proposal; enters no certificate."},
                  fh, indent=2)
    print("\nwrote /out/MR002_HiGHS_Projection_Probe.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
