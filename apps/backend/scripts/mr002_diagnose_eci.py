"""Diagnose the 81% EXECUTION_CONSTRAINED_INFEASIBLE rate.

Two candidate defects:

  D-A  open_next is populated ONLY for the day's PIT UNIVERSE members (dataset.py:239).
       A HELD position whose symbol leaves the ranking universe (or has a non-finite z,
       or an unresolved sector) gets NO execution price -> is marked non-tradable ->
       becomes a FIXED exposure. Entry eligibility is being conflated with the ability to
       TRADE AN EXISTING POSITION.

  D-B  The ECI probe tests feasibility at z = 0 only. But z = 0 infeasible does NOT imply
       the LP is infeasible: new orders x DILUTE a fixed exposure and can restore
       compliance. A single fixed position always breaches at z = 0
       (sector_gross/G = 1.0 > 0.20), so ECI fires whenever ANY position is fixed --
       even when a perfectly good feasible portfolio exists.

DIAGNOSTIC ONLY.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date

import numpy as np

sys.path.insert(0, "/work/apps/backend")

from scipy.optimize import linprog  # noqa: E402

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.dataset import FrozenDataset  # noqa: E402
from app.research.mr002.joint_portfolio import (  # noqa: E402
    EXECUTION_CONSTRAINED_INFEASIBLE,
    NO_EXECUTABLE_OPEN,
    Holding,
    NewCandidate,
    build_joint,
)

R = {
    "sessions": 0,
    "sessions_with_positions": 0,
    "eci_sessions": 0,
    "eci_with_any_fixed_position": 0,
    "held_positions_seen": 0,
    "held_without_open_next": 0,
    "held_without_open_next_but_price_row_EXISTS": 0,
    "eci_sessions_where_LP_IS_ACTUALLY_FEASIBLE": 0,
    "eci_sessions_where_LP_genuinely_infeasible": 0,
    "fixed_reason_counts": Counter(),
}

_orig_build = build_joint


def probe_lp_feasible(fixed, tradable, cands):
    """Is the Stage-1 LP region ACTUALLY non-empty? (the correct infeasibility test)"""
    A_ub, b_ub, A_eq, b_eq, upper, _lab = jp._build(fixed, tradable, cands)
    n = len(upper)
    if n == 0:
        return bool(A_ub.size == 0 or np.max(-b_ub) <= 1e-9)
    f = linprog(c=np.zeros(n), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                bounds=[(0.0, float(u)) for u in upper],
                method="highs-ds", options=jp.LP_OPTIONS)
    return bool(f.success and f.status == 0)


def spy_build(holdings, candidates):
    R["sessions"] += 1
    if holdings:
        R["sessions_with_positions"] += 1
    R["held_positions_seen"] += len(holdings)

    res = _orig_build(holdings, candidates)

    if res.outcome == EXECUTION_CONSTRAINED_INFEASIBLE:
        R["eci_sessions"] += 1
        reasons = res.diagnostics.get("fixed_reasons", {})
        R["fixed_reason_counts"].update(reasons.values())
        if any(r == NO_EXECUTABLE_OPEN for r in reasons.values()):
            R["eci_with_any_fixed_position"] += 1

        # rebuild the classification exactly as build_joint does, then ask HiGHS whether
        # the LP region is REALLY empty
        fixed, tradable = [], []
        for h in sorted(holdings, key=lambda x: x.permaticker):
            if not h.tradable:
                fixed.append(jp.Fixed(h.permaticker, h.d, h.c, h.sector, h.beta,
                                      NO_EXECUTABLE_OPEN))
            elif h.c <= jp.EPS_INCLUDE:
                fixed.append(jp.Fixed(h.permaticker, h.d, h.c, h.sector, h.beta,
                                      jp.BELOW_NUMERICAL_INCLUSION_FLOOR))
            else:
                tradable.append(h)
        cands = [c for c in sorted(candidates, key=lambda x: x.permaticker)
                 if c.w > jp.EPS_INCLUDE]
        if probe_lp_feasible(fixed, tradable, cands):
            R["eci_sessions_where_LP_IS_ACTUALLY_FEASIBLE"] += 1
        else:
            R["eci_sessions_where_LP_genuinely_infeasible"] += 1
    return res


import scripts.mr002_development_run as devrun  # noqa: E402

devrun.build_joint = spy_build

from app.research.mr002.runner import CONFIGS  # noqa: E402

ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))

# ---- D-A: is open_next missing for held symbols whose PRICE ROW actually exists? -------
# Rebuild the price index directly from the store to see whether the bar is really absent
# or merely filtered out by universe membership.
con = ds.con if hasattr(ds, "con") else None
print("running config A with the ECI spy ...", flush=True)
devrun.run_config(days, CONFIGS["A"])

R["fixed_reason_counts"] = dict(R["fixed_reason_counts"])
print(json.dumps(R, indent=2))
