"""MR-002 v1.1 — FULL-WINDOW EXECUTION-STATE PREFLIGHT (A/B/C).

Registered by the Execution-Availability / ECI-Semantics erratum rev 3 (countersigned
2026-07-12, artifact sha256 b32cf04bcf4c85b64292ec966f675bd2df6397cae5a884abcdfff4fa7569d80a).

PERFORMANCE AGGREGATION IS DISABLED. This script never computes, prints or persists P&L,
returns, Sharpe, hit rate or drawdown. It proves the EXECUTION STATE is correct, and every
required-zero counter must be 0 before any replacement performance may be calculated.

It uses the SAME run_config logic as the development run -- the logic must NOT differ
between the preflight and the performance calculation.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.dataset import FrozenDataset  # noqa: E402
from app.research.mr002.joint_portfolio import (  # noqa: E402
    BELOW_NUMERICAL_INCLUSION_FLOOR,
    EXECUTION_CONSTRAINED_INFEASIBLE,
    NO_EXECUTABLE_OPEN,
)
from app.research.mr002.runner import CONFIGS, exit_reason  # noqa: E402

import scripts.mr002_development_run as devrun  # noqa: E402

DEV_START = date(2013, 1, 2)
DEV_END = date(2019, 10, 2)

ERRATUM = "b32cf04bcf4c85b64292ec966f675bd2df6397cae5a884abcdfff4fa7569d80a"


def preflight(days, cfg_name) -> dict:
    cfg = CONFIGS[cfg_name]
    C = {
        "held_position_days": 0,
        "held_days_with_valid_open": 0,
        "held_days_without_valid_open": 0,
        "NO_EXECUTABLE_OPEN_count": 0,
        "false_missing_open_count": 0,                 # REQUIRED 0
        "hard_exits_due": 0,
        "hard_exits_executed": 0,
        "hard_exits_pending_for_missing_open": 0,
        "stage1_feasible_sessions": 0,
        "stage1_infeasible_sessions": 0,
        "ECI_sessions": 0,
        "ECI_without_status_2": 0,                     # REQUIRED 0
        "status_2_without_fixed_exposure": 0,          # REQUIRED 0
        "NO_EXECUTABLE_OPEN_with_valid_bar": 0,        # REQUIRED 0
        "solver_eligible_without_valid_bar": 0,        # REQUIRED 0
        "below_floor_misclassified_as_no_open": 0,     # REQUIRED 0
        "sessions": 0,
        "sessions_with_decision_hash": 0,
        "eci_fixed_by_reason": {
            "fixed_no_open_count": 0, "fixed_no_open_weight": 0.0,
            "fixed_below_floor_count": 0, "fixed_below_floor_weight": 0.0,
        },
    }

    SESSION = {"inp": None}
    _real_build = jp.build_joint

    def audited_build(holdings, candidates):
        inp = SESSION["inp"]
        avail = inp.exec_open                          # execution_open_available

        for h in holdings:
            C["held_position_days"] += 1
            has_bar = (avail.get(h.permaticker) or 0) > 0
            if has_bar:
                C["held_days_with_valid_open"] += 1
            else:
                C["held_days_without_valid_open"] += 1
            # h.tradable IS execution_open_available -- they must agree exactly
            if h.tradable != has_bar:
                C["false_missing_open_count"] += 1

        res = _real_build(holdings, candidates)
        reasons = res.diagnostics.get("fixed_reasons", {})
        by_pt = {h.permaticker: h for h in holdings}

        for pt, why in reasons.items():
            h = by_pt.get(pt)
            has_bar = (avail.get(pt) or 0) > 0
            if why == NO_EXECUTABLE_OPEN:
                C["NO_EXECUTABLE_OPEN_count"] += 1
                if has_bar:
                    # THE invariant: a valid bar may NEVER be NO_EXECUTABLE_OPEN
                    C["NO_EXECUTABLE_OPEN_with_valid_bar"] += 1
                    if h is not None and h.c <= jp.EPS_INCLUDE:
                        C["below_floor_misclassified_as_no_open"] += 1
            elif why == BELOW_NUMERICAL_INCLUSION_FLOOR:
                # a valid bar MAY exist here -- registered numerical-floor case, NOT a
                # Defect-A failure. Nothing to assert beyond the misclassification check.
                pass

        # solver_reduction_eligible => must have had a valid bar AND exposure > floor
        for pt in res.y:
            h = by_pt.get(pt)
            if (avail.get(pt) or 0) <= 0:
                C["solver_eligible_without_valid_bar"] += 1
            if h is not None and h.c <= jp.EPS_INCLUDE:
                C["solver_eligible_without_valid_bar"] += 1

        st1 = res.diagnostics.get("stage1_status")
        eci = res.outcome == EXECUTION_CONSTRAINED_INFEASIBLE
        n_vars = res.diagnostics.get("n_tradable", 0) + res.diagnostics.get("n_candidates", 0)
        infeasible = eci or (st1 == 2)
        if infeasible:
            C["stage1_infeasible_sessions"] += 1
        else:
            C["stage1_feasible_sessions"] += 1

        if eci:
            C["ECI_sessions"] += 1
            # ECI must be backed by genuine infeasibility: either HiGHS status 2, or the
            # zero-variable case where the fixed book alone is infeasible.
            if not (st1 == 2 or n_vars == 0):
                C["ECI_without_status_2"] += 1
            if not res.diagnostics.get("fixed_reasons"):
                C["status_2_without_fixed_exposure"] += 1
            fbr = res.diagnostics.get("fixed_by_reason", {})
            for k in C["eci_fixed_by_reason"]:
                C["eci_fixed_by_reason"][k] += fbr.get(k, 0)
        if st1 == 0 and eci:
            C["ECI_without_status_2"] += 1              # status 0 can NEVER be ECI

        if res.diagnostics.get("determinism_hash"):
            C["sessions_with_decision_hash"] += 1
        return res

    # tap the loop to publish the current DayInputs, and audit hard exits
    class Tap(list):
        def __iter__(self):
            for x in super().__iter__():
                SESSION["inp"] = x
                C["sessions"] += 1
                yield x

    jp.build_joint = audited_build
    devrun.build_joint = audited_build
    try:
        acc = devrun.run_config(Tap(days), cfg)
    finally:
        jp.build_joint = _real_build
        devrun.build_joint = _real_build

    C["hard_exits_due"] = acc.hard_exits_due
    C["hard_exits_executed"] = acc.hard_exits_executed
    C["hard_exits_pending_for_missing_open"] = acc.hard_exits_pending_missing_open
    # every pending hard exit must be explained by a genuinely absent execution open
    if acc.hard_exits_due != acc.hard_exits_executed + acc.hard_exits_pending_missing_open:
        C["false_missing_open_count"] += 1
    return C


def main() -> int:
    ds = FrozenDataset(os.environ.get(
        "MR002_STORE", "/work/apps/backend/data/mr002_research.duckdb"))
    days = ds.day_inputs(DEV_START, DEV_END)
    print(f"development sessions: {len(days)}  ({days[0].session} .. {days[-1].session})")

    REQUIRED_ZERO = (
        "false_missing_open_count",
        "ECI_without_status_2",
        "status_2_without_fixed_exposure",
        "NO_EXECUTABLE_OPEN_with_valid_bar",
        "solver_eligible_without_valid_bar",
        "below_floor_misclassified_as_no_open",
    )

    out, failed = {}, []
    for name in ("A", "B", "C"):
        print(f"  preflight {name} ...", flush=True)
        C = preflight(days, name)
        for k in REQUIRED_ZERO:
            if C[k] != 0:
                failed.append(f"{name}.{k} = {C[k]} (REQUIRED 0)")
        out[name] = C

    pkg = {
        "record_type": "MR002_EXECUTION_STATE_PREFLIGHT",
        "erratum_sha256": ERRATUM,
        "performance_aggregation": "DISABLED — no P&L, returns, Sharpe, hit rate or drawdown",
        "window": {"start": str(DEV_START), "end": str(DEV_END), "sessions": len(days)},
        "required_zero_counters": list(REQUIRED_ZERO),
        "configs": out,
        "verdict": "PASS" if not failed else "FAIL",
        "failures": failed,
    }
    dst = os.environ.get("MR002_PREFLIGHT_OUT", "/out/MR002_ExecutionStatePreflight.json")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(pkg, fh, indent=2)
        fh.write("\n")

    for name in ("A", "B", "C"):
        C = out[name]
        print(f"\n--- CONFIG {name}")
        for k in ("held_position_days", "held_days_with_valid_open",
                  "held_days_without_valid_open", "NO_EXECUTABLE_OPEN_count",
                  "hard_exits_due", "hard_exits_executed",
                  "hard_exits_pending_for_missing_open",
                  "stage1_feasible_sessions", "stage1_infeasible_sessions",
                  "ECI_sessions", "sessions", "sessions_with_decision_hash"):
            print(f"    {k:38s} {C[k]}")
        print("    REQUIRED-ZERO:")
        for k in REQUIRED_ZERO:
            print(f"      {k:36s} {C[k]}  {'OK' if C[k] == 0 else '<<< FAIL'}")
        print(f"    ECI fixed by reason: {C['eci_fixed_by_reason']}")

    print(f"\nVERDICT: {pkg['verdict']}")
    for f in failed:
        print("  FAIL:", f, file=sys.stderr)
    print(f"report: {dst}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
