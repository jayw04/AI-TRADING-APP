"""MR-002 — does PIQP certify the five QUADPROG_SQRT failures? (closes a gap in the evidence)

The intersection run covered quadprog x3, Clarabel and HiGHS. It did NOT include PIQP. So the
claim "instance 2765 is certified by no other characterized solver" is UNPROVEN, and the
erratum would bind it. This closes that.

DIAGNOSTIC ONLY. No performance is computed. Preflight and the development run remain stopped.
Validation and sealed OOS remain sealed and unread.

The PIQP solve path is IMPORTED from the validated characterizer, never re-derived — the same
discipline that my broken hand-rolled Clarabel violated.
"""

from __future__ import annotations

import hashlib
import json
import sys
import warnings
from datetime import date

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from scripts.mr002_piqp import solve_piqp as _piqp_raw  # noqa: E402
from scripts.mr002_solver_intersection import (  # noqa: E402
    LIMITS,
    REGISTERED_CORPUS_HASH,
    _hash_instance,
    failures,
    solve_sqrt,
)

FIXTURES = [800, 1328, 2140, 2296, 2765]
CORPUS: list[dict] = []


def capture(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
    t = np.asarray(targets, float)
    CORPUS.append({
        "t": t.copy(), "A_ub": A_ub.copy(), "b_ub": b_ub.copy(),
        "A_eq": A_eq.copy(), "b_eq": b_eq.copy(),
        "upper": np.asarray(upper, float).copy(),
        "hash": _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper),
    })
    from scripts.mr002_solver_intersection import solve_raw, solve_tscaled
    for fn in (solve_raw, solve_sqrt, solve_tscaled):
        try:
            z, ck = fn(t, A_ub, b_ub, A_eq, b_eq, upper)
            if not failures(ck):
                return z, dict(ck, stage3_formulation="CAPTURE",
                               hessian_condition_number=1.0, qp_iterations=[0, 0])
        except ValueError:
            continue
    from scipy.optimize import linprog
    n = len(t)
    f = linprog(c=np.zeros(n), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                bounds=[(0.0, float(u)) for u in upper], method="highs-ds",
                options=jp.LP_OPTIONS)
    if not f.success:
        raise jp.InvalidRun("capture: infeasible")
    z = np.asarray(f.x, float)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    ck = jp._acceptance(z, np.zeros(C.shape[1]), A_eq.shape[0], H, a, C, b,
                        A_ub, b_ub, A_eq, b_eq, upper)
    return z, dict(ck, stage3_formulation="DIAGNOSTIC_FALLBACK",
                   hessian_condition_number=1.0, qp_iterations=[0, 0])


def piqp(profile_scale_cost, t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    H = np.diag(2.0 / t)
    a = 2.0 * np.ones(n)
    C, b = jp._qp_matrices(A_ub, b_ub, A_eq, b_eq, upper, n)
    meq = A_eq.shape[0]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        z, lam = _piqp_raw(profile_scale_cost, t, A_ub, b_ub, A_eq, b_eq, upper)
    if not (np.all(np.isfinite(z)) and np.all(np.isfinite(lam))):
        raise RuntimeError("non-finite primal or dual")
    return z, jp._acceptance(z, lam, meq, H, a, C, b, A_ub, b_ub, A_eq, b_eq, upper)


def main() -> int:
    jp._solve_qp = capture
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    for name in ("A", "B", "C"):
        run_config(days, CONFIGS[name])

    ch = hashlib.sha256("|".join(i["hash"] for i in CORPUS).encode()).hexdigest()
    print(f"corpus {len(CORPUS)}  hash {ch}")
    if ch != REGISTERED_CORPUS_HASH:
        print("ABORT: corpus hash mismatch", file=sys.stderr)
        return 1
    print("✓ corpus reproduced exactly\n")

    out = {}
    print("Does PIQP certify the five QUADPROG_SQRT failures?")
    for i in FIXTURES:
        inst = CORPUS[i]
        rec = (inst["t"], inst["A_ub"], inst["b_ub"],
               inst["A_eq"], inst["b_eq"], inst["upper"])
        row = {"instance_hash": inst["hash"]}
        for prof, sc in (("P1", False), ("P2", True)):
            try:
                _z, ck = piqp(sc, *(x.copy() for x in rec))
                bad = failures(ck)
                row[prof] = "QUALIFIES" if not bad else "+".join(bad)
            except Exception as e:  # noqa: BLE001
                row[prof] = f"{type(e).__name__}: {str(e)[:60]}"
        out[str(i)] = row
        print(f"  {i:>5}  P1={row['P1']:<45} P2={row['P2']}")

    p2765 = out["2765"]
    only_highs = not any(str(p2765[p]).startswith("QUALIFIES") for p in ("P1", "P2"))
    print("\n" + "=" * 74)
    if only_highs:
        print("CONFIRMED: PIQP does NOT certify 2765. HiGHS remains the ONLY solver that can.")
    else:
        print("⚠ CONTRADICTION: PIQP DOES certify 2765. The claim 'HiGHS-only' is FALSE and")
        print("  the erratum must not bind it. The cascade choice must be re-adjudicated.")
    print("=" * 74)

    with open("/out/MR002_PIQP_on_SqrtFailures.json", "w", encoding="utf-8") as fh:
        json.dump({"corpus_hash": ch, "fixtures": out,
                   "highs_is_sole_certifier_of_2765": only_highs,
                   "no_performance_computed": True}, fh, indent=2)
    print("wrote /out/MR002_PIQP_on_SqrtFailures.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
