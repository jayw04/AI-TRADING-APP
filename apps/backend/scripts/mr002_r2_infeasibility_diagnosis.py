"""Is the R2 tightened set EMPTY, or is quadprog reporting a FALSE infeasibility?

Sample A returned TIGHTENED_PROPOSAL_NOT_OBTAINED on 50/50 overlaps, every one of them
`ValueError: constraints are inconsistent, no solution` from quadprog. Two very different worlds:

  (a) the tightened set is genuinely empty  -> eta is too large for this model family, and R2 as
      specified cannot work;
  (b) quadprog is wrong                     -> the SAME false-infeasibility mode that defeats
      QUADPROG_SQRT on its five instances, now hitting the proposal solver.

Nothing is changed here. This is DIAGNOSIS ONLY: an independent LP feasibility test on the
tightened constraints, plus the slack profile of the original accepted solution. The LP is not a
proposal and is not used as one — it only answers "is the set empty".
"""

from __future__ import annotations

import json
import sys
from datetime import date

import numpy as np
from scipy.optimize import linprog

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.repair import ETA_FLOAT, build_tightened_problem  # noqa: E402
from scripts.mr002_coverage_signed_gap import (  # noqa: E402
    CORPUS,
    FALLBACK,
    PRIMARY,
    capture,
    try_solve,
)

N = 12


def main() -> int:
    jp._solve_qp = capture
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    for cfg in ("A", "B", "C"):
        run_config(days, CONFIGS[cfg])

    rows, seen = [], 0
    for i, inst in enumerate(CORPUS):
        rec = (inst["t"], inst["A_ub"], inst["b_ub"],
               inst["A_eq"], inst["b_eq"], inst["upper"])
        ok1, _, z1, _, _ = try_solve(PRIMARY, rec)
        ok2, _, _z2, _, _ = try_solve(FALLBACK, rec)
        if not (ok1 and ok2):
            continue
        t, A_ub, b_ub, A_eq, b_eq, upper = rec
        n = len(t)

        # --- Is the TIGHTENED set empty? Independent LP feasibility test. -------------------
        keep = [r for r in range(A_ub.shape[0]) if np.any(A_ub[r] != 0.0)]
        lp = linprog(
            c=np.zeros(n),
            A_ub=A_ub[keep] if keep else None,
            b_ub=(b_ub[keep] - ETA_FLOAT) if keep else None,
            A_eq=A_eq, b_eq=b_eq,
            bounds=[(ETA_FLOAT, float(u) - ETA_FLOAT) for u in upper],
            method="highs",
        )
        # --- and is the ORIGINAL set's interior reachable at all? ---------------------------
        lp0 = linprog(c=np.zeros(n), A_ub=A_ub if A_ub.shape[0] else None,
                      b_ub=b_ub if A_ub.shape[0] else None, A_eq=A_eq, b_eq=b_eq,
                      bounds=[(0.0, float(u)) for u in upper], method="highs")

        # --- how much room does the ORIGINAL solution actually have? ------------------------
        at_zero = int(np.sum(z1 <= 0.0))
        at_upper = int(np.sum(z1 >= upper - 0.0))
        tiny_upper = int(np.sum(np.asarray(upper, float) <= 2 * ETA_FLOAT))
        row_slack = (b_ub - A_ub @ z1) if A_ub.shape[0] else np.zeros(0)
        nz_slack = row_slack[keep] if keep else np.zeros(0)

        # how big is the equality's reachable range once the box is tightened?
        a = A_eq[0]
        lo = float(np.sum(np.where(a >= 0, a * ETA_FLOAT, a * (upper - ETA_FLOAT))))
        hi = float(np.sum(np.where(a >= 0, a * (upper - ETA_FLOAT), a * ETA_FLOAT)))

        rows.append({
            "instance": i, "n": n,
            "tightened_feasible": bool(lp.success),
            "tightened_status": str(lp.message)[:60],
            "original_feasible": bool(lp0.success),
            "coords_at_zero": at_zero, "coords_at_upper": at_upper,
            "coords_with_upper_le_2eta": tiny_upper,
            "min_nonzero_row_slack": float(nz_slack.min()) if nz_slack.size else None,
            "n_rows_with_slack_below_eta": int(np.sum(nz_slack < ETA_FLOAT))
            if nz_slack.size else 0,
            "n_nonzero_rows": len(keep),
            "b_eq": float(b_eq[0]),
            "tightened_eq_range": [lo, hi],
            "b_eq_inside_tightened_range": bool(lo <= float(b_eq[0]) <= hi),
        })
        seen += 1
        if seen >= N:
            break

    n_tight_feas = sum(r["tightened_feasible"] for r in rows)
    print(f"=== {seen} qualifying overlaps ===\n")
    print(f"tightened set feasible per INDEPENDENT LP : {n_tight_feas} / {seen}")
    print(f"original set feasible per LP             : "
          f"{sum(r['original_feasible'] for r in rows)} / {seen}")
    print()
    print("If the LP says FEASIBLE while quadprog said 'constraints are inconsistent', the")
    print("proposal solver is producing a FALSE INFEASIBILITY — the same Goldfarb-Idnani mode")
    print("that defeats QUADPROG_SQRT on its five instances. If the LP agrees the set is EMPTY,")
    print("eta is too large for this model family and R2 cannot work as specified.\n")
    for r in rows:
        print(f"  i={r['instance']:>4} n={r['n']:>3} tight_LP={str(r['tightened_feasible']):<5} "
              f"@0={r['coords_at_zero']:>3} @u={r['coords_at_upper']:>3} "
              f"rows<eta_slack={r['n_rows_with_slack_below_eta']:>2}/{r['n_nonzero_rows']:<2} "
              f"min_slack={r['min_nonzero_row_slack']} "
              f"b_eq_in_range={r['b_eq_inside_tightened_range']}")

    with open("/out/MR002_R2_Infeasibility_Diagnosis.json", "w", encoding="utf-8") as fh:
        json.dump({"examined": seen, "tightened_feasible_count": n_tight_feas,
                   "eta": ETA_FLOAT, "records": rows}, fh, indent=2)
    print("\nwrote /out/MR002_R2_Infeasibility_Diagnosis.json")

    # And what does the FROZEN proposal path itself report on the same instances?
    print("\n--- what quadprog says on the same tightened problems ---")
    import quadprog
    for r in rows[:6]:
        inst = CORPUS[r["instance"]]
        C, b, _k = build_tightened_problem(inst["A_ub"], inst["b_ub"], inst["A_eq"],
                                           inst["b_eq"], inst["upper"])
        try:
            quadprog.solve_qp(np.eye(r["n"]), np.zeros(r["n"]), C, b, 1)
            msg = "solved"
        except Exception as e:  # noqa: BLE001
            msg = f"{type(e).__name__}: {e}"
        print(f"  i={r['instance']:>4} LP={str(r['tightened_feasible']):<5} quadprog={msg[:56]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
