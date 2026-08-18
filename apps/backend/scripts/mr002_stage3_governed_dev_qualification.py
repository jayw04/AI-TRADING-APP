"""MR-002 — THE governed Stage-3 development qualification. One run, development corpus only.

Authorized by the owner 2026-08-18 after the Stage-3 executability question was answered:
regenerate the manifest from a clean checkpoint, close the ExecutionPackage/countersignature, then
perform ONE governing development qualification.

This launcher changes nothing numerical. It routes `joint_portfolio` Stage-3 through the
countersigned successor cascade (`QUADPROG_SQRT -> PIQP_P2 once`) via the recorded seam, runs the
accepted development runner and the Phase 3C replay for configs A, B and C over the development
window, and evaluates the governing pass conditions. It adds no third attempt, no jitter, no
tolerance/epsilon/profile change, no per-instance routing and no fallback-by-analogy.

HARD DATA BOUNDARY. The development window is asserted before any replay runs, and a session at or
beyond the validation start aborts the qualification. The validation and sealed OOS partitions are
never opened; `validation_oos_reads` is proved zero structurally, because nothing here constructs a
sealed reader at all.

The counts of today's feasibility probe (3,891 primary / 4 fallback) are NOT an acceptance
threshold. The governing requirement is semantic completion under the frozen decision table.

Usage (inside the pinned image, with the registered thread environment):
    python scripts/mr002_stage3_governed_dev_qualification.py --out <path.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date

sys.path.insert(0, "/work/apps/backend")

from app.research.mr002 import stage3_route as route  # noqa: E402
from app.research.mr002.dataset import FrozenDataset  # noqa: E402
from app.research.mr002.joint_portfolio import (  # noqa: E402
    EXECUTION_CONSTRAINED_INFEASIBLE,
    InvalidRun,
)
from app.research.mr002.phase3c import IntegrityFailure, adopted  # noqa: E402
from app.research.mr002.phase3c.replay import run_config_validation  # noqa: E402
from app.research.mr002.runner import CONFIGS  # noqa: E402
from app.research.mr002.stage3_cascade import (  # noqa: E402
    FALLBACK_QUALIFIED,
    INVALID_RUN,
    PRIMARY_QUALIFIED,
    UNRESOLVED_NUMERICAL_FAILURE,
)

DEV_START, DEV_END = date(2013, 1, 2), date(2019, 10, 2)
VALIDATION_START = date(2019, 10, 3)
OOS_START = date(2023, 5, 30)
STORE = "/work/apps/backend/data/mr002_research.duckdb"
CONFIG_NAMES = ("A", "B", "C")


def _run_hash(session_hashes: list) -> str:
    return hashlib.sha256("|".join(session_hashes).encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/out/MR002_Stage3_GovernedDevQualification_v1.0.json")
    ap.add_argument("--store", default=STORE)
    args = ap.parse_args()

    ds = FrozenDataset(args.store)
    days = ds.day_inputs(DEV_START, DEV_END)

    # ---- hard data boundary, asserted BEFORE any replay --------------------------------------
    if not days:
        raise SystemExit("REFUSED: no development sessions loaded")
    if days[0].session < DEV_START or days[-1].session > DEV_END:
        raise SystemExit(f"REFUSED: loaded {days[0].session}..{days[-1].session}")
    if any(d.session >= VALIDATION_START for d in days):
        raise SystemExit("REFUSED: a session at or beyond the validation start was loaded")
    print(f"development window {days[0].session}..{days[-1].session}, {len(days)} sessions",
          flush=True)

    dev = adopted.load()
    report = {
        "record_type": "MR002_Stage3_GovernedDevQualification",
        "version": "1.0",
        "is_governed_qualification_run": True,
        "boundary": {
            "window": [str(days[0].session), str(days[-1].session)],
            "sessions": len(days),
            "development_only": True,
            "validation_start_excluded": str(VALIDATION_START),
            "oos_start_excluded": str(OOS_START),
            "validation_oos_reads": 0,
            "why_zero_is_structural": (
                "no sealed reader is constructed anywhere in this launcher; the only store opened "
                "is the development research corpus, and the window bound is asserted before any "
                "replay"
            ),
        },
        "adoption_binding": adopted.verify_binding(),
        "cascade": {
            "primary": "QUADPROG_SQRT",
            "fallback": "PIQP_P2",
            "fallback_invocations_per_instance_max": 1,
            "third_attempt": False,
            "jitter": False,
            "tolerance_or_epsilon_or_profile_changed": False,
            "per_instance_routing": False,
            "fallback_by_analogy": False,
        },
        "configs": {},
    }
    failures: list[str] = []

    for name in CONFIG_NAMES:
        print(f"\n=== config {name} ===", flush=True)
        row: dict = {}

        census: list = []
        try:
            with route.routed(census, countersignature=route.EXECUTION_COUNTERSIGNATURE_ID):
                acc = dev.run_config(days, CONFIGS[name])
            row["accepted_runner"] = {
                "result": "COMPLETED",
                "run_hash": _run_hash(acc.session_hashes),
                "reductions": acc.reductions,
                "new_orders": acc.entries_long + acc.entries_short,
                "exits": acc.exits,
                "exit_reasons": dict(acc.exit_reasons),
                "session_outcomes": dict(acc.outcomes),
            }
        except (route.Stage3Stop, InvalidRun) as exc:
            row["accepted_runner"] = {"result": type(exc).__name__, "detail": str(exc)[:300]}
            failures.append(f"{name}: accepted runner did not complete")
            acc = None
        row["stage3_accepted_runner"] = route.census_summary(census)

        census3: list = []
        try:
            with route.routed(census3, countersignature=route.EXECUTION_COUNTERSIGNATURE_ID):
                va = run_config_validation(days, CONFIGS[name], assert_oos_boundary=True)
            p = va.acc
            row["phase3c"] = {
                "result": "COMPLETED",
                "run_hash": _run_hash(p.session_hashes),
                "reductions": p.reductions,
                "new_orders": p.entries_long + p.entries_short,
                "exits": p.exits,
                "exit_reasons": dict(p.exit_reasons),
            }
            obs = va.band_observations
            eci_applicable = sum(1 for o in obs
                                 if o["outcome"] == EXECUTION_CONSTRAINED_INFEASIBLE
                                 and o["r6a_applies"])
            feasible_breached = sum(1 for o in obs
                                    if o["outcome"] != EXECUTION_CONSTRAINED_INFEASIBLE
                                    and o["breached"])
            eci_breached = sum(1 for o in obs
                               if o["outcome"] == EXECUTION_CONSTRAINED_INFEASIBLE
                               and o["breached"])
            row["r6a"] = {
                "band_observations": len(obs),
                "P1_eci_marked_r6a_applicable": eci_applicable,
                "P1_pass": eci_applicable == 0,
                "P1_eci_sessions_breaching_band": eci_breached,
                "P2_feasible_sessions_breaching_band": feasible_breached,
                "P2_pass": feasible_breached == 0,
            }
            if eci_applicable:
                failures.append(f"{name}: P1 — an ECI session was marked R6A-applicable")
            if feasible_breached:
                failures.append(f"{name}: P2 — a feasible construction ended outside the band")
        except (route.Stage3Stop, IntegrityFailure, InvalidRun) as exc:
            row["phase3c"] = {"result": type(exc).__name__, "detail": str(exc)[:300]}
            failures.append(f"{name}: Phase 3C did not complete")
            p = None
        row["stage3_phase3c"] = route.census_summary(census3)

        # ---- Phase 3C must reproduce the accepted semantics exactly --------------------------
        if acc is not None and p is not None:
            row["differential"] = {
                "run_hash_equal": _run_hash(p.session_hashes) == _run_hash(acc.session_hashes),
                "nav_curve_equal": p.nav_curve == acc.nav_curve,
                "daily_ret_equal": p.daily_ret == acc.daily_ret,
                "reductions_equal": p.reductions == acc.reductions,
                "exit_reasons_equal": dict(p.exit_reasons) == dict(acc.exit_reasons),
                "costs_equal": p.costs == acc.costs,
                "borrow_equal": p.borrow == acc.borrow,
            }
            row["differential"]["EXACT"] = all(row["differential"].values())
            if not row["differential"]["EXACT"]:
                failures.append(f"{name}: Phase 3C differs from the accepted semantics")

        # ---- Stage-3 disposition conditions ---------------------------------------------------
        for label, cen in (("accepted_runner", row["stage3_accepted_runner"]),
                           ("phase3c", row["stage3_phase3c"])):
            d = cen["by_disposition"]
            if not cen["all_reconcile_to_a_registered_disposition"]:
                failures.append(f"{name}/{label}: an invocation did not reconcile")
            if cen["unrecognized_outcomes"]:
                failures.append(f"{name}/{label}: unrecognized solver outcome")
            if d.get(UNRESOLVED_NUMERICAL_FAILURE):
                failures.append(f"{name}/{label}: UNRESOLVED_NUMERICAL_FAILURE")
            if d.get(INVALID_RUN):
                failures.append(f"{name}/{label}: INVALID_RUN")
            if cen["fallback_invoked"] > d.get(FALLBACK_QUALIFIED, 0):
                failures.append(f"{name}/{label}: a fallback was invoked more than once")
            unknown = set(d) - {PRIMARY_QUALIFIED, FALLBACK_QUALIFIED,
                                UNRESOLVED_NUMERICAL_FAILURE, INVALID_RUN}
            if unknown:
                failures.append(f"{name}/{label}: dispositions outside the closed set {unknown}")

        report["configs"][name] = row
        print("  ", json.dumps({k: v for k, v in row.items()
                                if k in ("accepted_runner", "phase3c", "differential")})[:260],
              flush=True)

    # ---- determinism: one config replayed a second time must reproduce its run hash ----------
    print("\n=== determinism re-run (config B) ===", flush=True)
    census_d: list = []
    with route.routed(census_d, countersignature=route.EXECUTION_COUNTERSIGNATURE_ID):
        again = dev.run_config(days, CONFIGS["B"])
    first = report["configs"]["B"].get("accepted_runner", {}).get("run_hash")
    report["determinism"] = {
        "config": "B",
        "first_run_hash": first,
        "second_run_hash": _run_hash(again.session_hashes),
        "reproduces": _run_hash(again.session_hashes) == first,
        "stage3_second_run": route.census_summary(census_d),
    }
    if not report["determinism"]["reproduces"]:
        failures.append("determinism: config B did not reproduce its run hash")

    totals = {"invocations": 0, "PRIMARY_QUALIFIED": 0, "FALLBACK_QUALIFIED": 0}
    for r in report["configs"].values():
        c = r["stage3_accepted_runner"]
        totals["invocations"] += c["invocations"]
        for k in ("PRIMARY_QUALIFIED", "FALLBACK_QUALIFIED"):
            totals[k] += c["by_disposition"].get(k, 0)
    report["stage3_totals_accepted_runner"] = totals
    report["counts_are_corroboration_not_threshold"] = (
        "the governing requirement is semantic completion under the frozen decision table; the "
        "feasibility probe's 3,891/4 split is corroboration if reproduced, never an acceptance "
        "threshold"
    )
    report["failures"] = failures
    report["result"] = "PASS" if not failures else "FAIL"

    body = json.dumps(report, indent=1, sort_keys=True, default=str)
    with open(args.out, "w") as fh:
        fh.write(body + "\n")
    print("\n" + "=" * 72)
    print(json.dumps({"result": report["result"], "failures": failures,
                      "totals": totals,
                      "determinism": report["determinism"]["reproduces"]}, indent=1))
    print("=" * 72)
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
