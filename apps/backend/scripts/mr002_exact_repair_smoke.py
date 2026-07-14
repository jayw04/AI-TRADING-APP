"""Smoke + sizing probe for the exact minimum-L-infinity repair.

Runs the real constructor on real corpus overlaps BEFORE the fixture suite is written against it —
a design that cannot repair the actual geometry is not worth 20 fixtures.

Reports what the ruling requires recorded: basis dimension, singleton eliminations, reduced-core
dimension, integer bit growth, and exact-solve duration.
"""

from __future__ import annotations

import sys
from datetime import date

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.exact_repair import (  # noqa: E402
    RepairUnavailable,
    agreement,
    certify_repair,
    objective_agreement,
)
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

    ok = fail = 0
    for i, inst in enumerate(CORPUS):
        rec = (inst["t"], inst["A_ub"], inst["b_ub"],
               inst["A_eq"], inst["b_eq"], inst["upper"])
        p_ok, _, z1, lam1, c1 = try_solve(PRIMARY, rec)
        f_ok, _, z2, lam2, c2 = try_solve(FALLBACK, rec)
        if not (p_ok and f_ok):
            continue
        n = len(inst["t"])
        try:
            r1 = certify_repair(z1, c1, *rec)
            r2 = certify_repair(z2, c2, *rec)
        except (RepairUnavailable, Exception) as e:  # noqa: BLE001
            print(f"  i={i:<4} n={n:<3} FAILED  {type(e).__name__}: {str(e)[:70]}")
            fail += 1
            if ok + fail >= N:
                break
            continue

        a_ok, dz, bound = agreement(r1, r2, z1, z2)
        o_ok, df, obound = objective_agreement(r1, r2, c1, c2)
        print(f"  i={i:<4} n={n:<3} rho*={float(r1.rho_star):.2e} changed={r1.n_coords_changed}/{n}"
              f"  delta={r1.delta_upper:.2e} Ghat={r1.ghat_upper:.2e} R={r1.radius_upper:.2e}"
              f"  |z1-z2|={dz:.1e} agree={a_ok}/{o_ok}")
        print(f"         basis={r1.basis_dim} singles={r1.singletons_eliminated} "
              f"core={r1.core_dim} bits(num/den)={r1.max_num_bits}/{r1.max_den_bits} "
              f"{r1.solve_seconds*1000:.0f}ms")
        ok += 1
        if ok + fail >= N:
            break

    print(f"\n{ok} repaired, {fail} failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
