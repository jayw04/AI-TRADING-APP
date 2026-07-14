"""Why did the one-coordinate exact repair fail on 46 of 50 overlaps? (ruling §9 — adjudicate)

Nothing is altered. The repair constructor, the proposal generator, the gates and the solvers are
untouched. This only records WHICH exact check rejects each absorber candidate, and by how much.

Hypothesis under test: the proposal is only TOLERANCE-feasible on the ACTIVE inequality rows. A
row that is tight at the optimum is satisfied to ~1e-16, which in EXACT rational arithmetic means
it is violated by ~1e-17 about half the time. The one-coordinate absorber can only move w_k, so it
cannot repair a violated row r with A_ub[r, k] == 0 — and every candidate fails.

If so, the defect is in the PROPOSAL (which the ruling says is not evidence of anything), not in
the exact certificate — and the remedy is a proposal that is strictly interior on the inequality
rows. That is a change to a frozen component and is NOT made here.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from fractions import Fraction

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.certificate import to_fraction  # noqa: E402
from app.research.mr002.repair import _propose  # noqa: E402
from scripts.mr002_coverage_signed_gap import (  # noqa: E402
    CORPUS,
    FALLBACK,
    PRIMARY,
    capture,
    try_solve,
)

N_OVERLAPS = 40


def diagnose(z_s, t, A_ub, b_ub, A_eq, b_eq, upper):
    n = len(t)
    A_ub = np.asarray(A_ub, float)
    A_eq = np.asarray(A_eq, float)
    w_tilde, source = _propose(z_s, A_ub, b_ub, A_eq, b_eq, upper)

    U = [to_fraction(v) for v in np.asarray(upper, float).ravel()]
    x = [min(max(to_fraction(w_tilde[i]), Fraction(0)), U[i]) for i in range(n)]
    a = [to_fraction(v) for v in A_eq[0]]
    beta = to_fraction(np.asarray(b_eq, float).ravel()[0])
    Aub = [[to_fraction(A_ub[r, i]) for i in range(n)] for r in range(A_ub.shape[0])]
    Bub = [to_fraction(v) for v in np.asarray(b_ub, float).ravel()]

    # Is the CLIPPED proposal already exactly infeasible on the inequality rows, before any
    # absorber touches it?
    pre_violated = []
    for r in range(len(Bub)):
        lhs = sum(Aub[r][i] * x[i] for i in range(n))
        if lhs > Bub[r]:
            pre_violated.append((r, float(lhs - Bub[r]), int(np.count_nonzero(A_ub[r]))))

    reasons = {"bound": 0, "inequality": 0, "ok": 0}
    ineq_rows_blocking = set()
    for k in range(n):
        if a[k] == 0:
            continue
        w = list(x)
        w[k] = (beta - sum(a[i] * x[i] for i in range(n) if i != k)) / a[k]
        if not (Fraction(0) <= w[k] <= U[k]):
            reasons["bound"] += 1
            continue
        bad_row = None
        for r in range(len(Bub)):
            if sum(Aub[r][i] * w[i] for i in range(n)) > Bub[r]:
                bad_row = r
                break
        if bad_row is None:
            reasons["ok"] += 1
        else:
            reasons["inequality"] += 1
            ineq_rows_blocking.add(bad_row)

    return {
        "n": n,
        "proposal_source": source,
        "clipped_proposal_already_violates_rows": pre_violated[:6],
        "n_rows_violated_pre_absorber": len(pre_violated),
        "candidate_outcomes": reasons,
        "blocking_rows": sorted(ineq_rows_blocking)[:6],
    }


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
    agg = {"bound": 0, "inequality": 0, "ok": 0}
    n_with_pre_violation = 0
    worst_pre = 0.0
    for i, inst in enumerate(CORPUS):
        rec = (inst["t"], inst["A_ub"], inst["b_ub"],
               inst["A_eq"], inst["b_eq"], inst["upper"])
        ok1, _, z1, _, _ = try_solve(PRIMARY, rec)
        ok2, _, _z2, _, _ = try_solve(FALLBACK, rec)
        if not (ok1 and ok2):
            continue
        d = diagnose(z1, *rec)
        d["instance"] = i
        rows.append(d)
        for k in agg:
            agg[k] += d["candidate_outcomes"][k]
        if d["n_rows_violated_pre_absorber"]:
            n_with_pre_violation += 1
            worst_pre = max(worst_pre, max(v[1] for v in
                                           d["clipped_proposal_already_violates_rows"]))
        seen += 1
        if seen >= N_OVERLAPS:
            break

    print(f"=== {seen} qualifying overlaps, PRIMARY point ===\n")
    print("Absorber candidate outcomes, pooled:")
    for k, v in agg.items():
        print(f"   {k:12} {v}")
    print(f"\nOverlaps whose CLIPPED PROPOSAL already violates an inequality row exactly, "
          f"before any absorber runs: {n_with_pre_violation} / {seen}")
    print(f"Worst such exact violation: {worst_pre:.3e}")
    print("\n(If that violation is ~1e-17, the proposal is merely TOLERANCE-feasible on rows that")
    print(" are ACTIVE at the optimum. A one-coordinate absorber cannot fix a violated row r when")
    print(" A_ub[r, k] == 0, so every candidate fails — the exact certificate is behaving")
    print(" correctly and the PROPOSAL is the defect.)\n")
    for d in rows[:8]:
        print(f"  i={d['instance']:>4} n={d['n']:>3} src={d['proposal_source']:<20} "
              f"pre-violated rows={d['n_rows_violated_pre_absorber']:>2} "
              f"outcomes={d['candidate_outcomes']}")

    with open("/out/MR002_RepairFailure_Diagnosis.json", "w", encoding="utf-8") as fh:
        json.dump({"overlaps_examined": seen, "pooled_candidate_outcomes": agg,
                   "overlaps_with_pre_absorber_violation": n_with_pre_violation,
                   "worst_exact_pre_violation": worst_pre, "records": rows}, fh, indent=2)
    print("\nwrote /out/MR002_RepairFailure_Diagnosis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
