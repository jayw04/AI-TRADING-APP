"""MR-002 Gate N2 — qualify the N1-frozen A/B pair on the preregistered stress population.

Sealed authority: MR002_N1_ProspectiveRegistration_v1.0 §8; N2 granted by the owner 2026-08-19
after N1 closed (final verdict 629eee0ee1c257a23312b539fbac8542b40cbf6f2cef296ba2c829fb6b29bd81).

FROZEN PAIR — NOT UNDER SELECTION HERE:
    Solver A = QUADPROG_SQRT      Solver B = PIQP_P2
N2 may PASS or STOP. It may NOT substitute a solver; any substitution restarts N1.

PASS RULE (100% registered resolution or STOP). For each of the 3,000 stress instances:
    no SYSTEM_INTEGRITY_DEFECT · no UNREGISTERED_TERMINATION_REASON · the method resolves to a
    certified allocation · no certified-solution disagreement · applicable agreement/equivalence
    evidence clean · deterministic regeneration and rerun reproduce identical dispositions.
A single unexplained unresolved numerical tail means N2_STOP.

⛔ If N2 exposes a failure the answer is NOT to patch the instance and rerun. The preregistered rule
governs, and this script neither retries nor repairs.

REFERENCE SOLVER R IS BOUNDED BY A **SIZE** BUDGET, NOT A WALL-CLOCK ONE. A wall-clock budget would
make R availability depend on machine load, so the same instance could be R_EXACT in one run and
R_UNAVAILABLE in the next — which would break the reproducibility requirement this gate is partly
testing. A dimension threshold is deterministic. Instances above it are recorded
R_SKIPPED_SIZE_BUDGET and reported per axis; they are never silently counted as available.

Per-axis diagnostics are DIAGNOSTIC ONLY. No additional pass threshold is invented from them.

Development domain only. No sealed reader, no validation store, no OOS.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from fractions import Fraction

import numpy as np

sys.path.insert(0, "/work/apps/backend")

from app.research.mr002.n1 import method as M  # noqa: E402
from app.research.mr002.n1 import reference as R  # noqa: E402

STRESS_NPZ = "/work/.mr002out/n2/stress.npz"
OUT_DIR = "/work/.mr002out/n2"
POPULATION_HASH = "4334649c46439868adb2ccad3f20daa9aacb97be3af431b41788775dfd045ace"

A_PROFILE = "QUADPROG_SQRT"
B_PROFILE = "PIQP_P2"
SLACK = Fraction(1, 10**10)
SLACK_SQ = SLACK * SLACK
#: deterministic size budget for R (see module docstring). Declared, not tuned after results.
R_MAX_DIM = int(os.environ.get("N2_R_MAX_DIM", "80"))
R_SKIPPED = "R_SKIPPED_SIZE_BUDGET"

AXES = ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8")


def isqrt_up(sq: Fraction) -> Fraction:
    if sq <= 0:
        return Fraction(0)
    p, q = sq.numerator, sq.denominator
    return Fraction(math.isqrt(p * q) + 1, q)


def exact_sep_sq(z1, z2) -> Fraction:
    a = [R.to_fraction(v) for v in np.asarray(z1, dtype=float).ravel()]
    b = [R.to_fraction(v) for v in np.asarray(z2, dtype=float).ravel()]
    return sum(((a[i] - b[i]) ** 2 for i in range(len(a))), Fraction(0))


def blank(axis: str) -> dict:
    return {"axis": axis, "instances": 0, "A_certified": 0, "B_rescue": 0, "unresolved": 0,
            "integrity_defects": 0, "unregistered_termination_reasons": 0,
            "certified_disagreements": 0, "agreement_checked": 0,
            "agreement_by_slack_floor": 0, "agreement_by_bound": 0, "agreement_unavailable": 0,
            "max_agreement_deviation": 0.0,
            "R_exact": 0, "R_unavailable": 0, "R_skipped_size_budget": 0,
            "repair_bound_available": 0, "repair_bound_unavailable": 0,
            "seconds": 0.0, "reproducibility_mismatches": 0,
            "B_reasons": {}, "A_reasons": {}}


def main() -> int:
    t0 = time.time()
    limit = int(os.environ.get("N2_LIMIT", "0"))
    from app.research.mr002 import repair as RP
    from scripts.mr002_coverage_signed_gap import SOLVERS, canonical_qualify

    d = np.load(STRESS_NPZ, allow_pickle=False)
    got = str(d["population_hash"])
    if got != POPULATION_HASH:
        raise SystemExit(f"ABORT: population hash {got} != registered {POPULATION_HASH}")
    n_inst = int(d["n_instances"])
    with open(os.path.join(OUT_DIR, "n2_population.json")) as fh:
        params = json.load(fh)["parameters"]
    if limit:
        n_inst = min(n_inst, limit)
    print(f"[{time.time()-t0:7.1f}s] population verified, {n_inst} instances, "
          f"A={A_PROFILE} B={B_PROFILE}, R size budget n<={R_MAX_DIM}", flush=True)

    per = {a: blank(a) for a in AXES}
    failures: list[dict] = []
    dispositions: list[tuple] = []

    def radius(z, cert, rec):
        try:
            return R.to_fraction(RP.certify_repair(z, cert, *rec).radius_upper)
        except Exception:  # noqa: BLE001 — unavailability is a recorded state
            return None

    for i in range(n_inst):
        ti = time.time()
        axis = params[i]["axis"]
        s = per[axis]
        s["instances"] += 1
        rec = tuple(d[f"{i}_{k}"] for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper"))

        a = M.normalize(A_PROFILE, SOLVERS[A_PROFILE], canonical_qualify, rec)
        b = M.normalize(B_PROFILE, SOLVERS[B_PROFILE], canonical_qualify, rec)

        for who, o in (("A", a), ("B", b)):
            if o.reason:
                key = f"{who}_reasons"
                s[key][o.reason] = s[key].get(o.reason, 0) + 1
            if o.outcome == M.SYSTEM_INTEGRITY_DEFECT:
                s["integrity_defects"] += 1
            if o.reason == M.UNREGISTERED_TERMINATION_REASON:
                s["unregistered_termination_reasons"] += 1

        if a.outcome == M.SYSTEM_INTEGRITY_DEFECT or b.outcome == M.SYSTEM_INTEGRITY_DEFECT:
            disp, z = M.INVALID_RUN, None
        elif a.is_certified:
            disp, z = M.PRIMARY_CERTIFIED, a.z
            s["A_certified"] += 1
        elif b.is_certified:
            disp, z = M.SECONDARY_CERTIFIED, b.z
            s["B_rescue"] += 1
        else:
            disp, z = M.UNRESOLVED_INSTANCE, None
            s["unresolved"] += 1

        # ── SA-2: both certified must agree within the §4 bound ────────────────────────────────
        ra = None
        if a.is_certified and b.is_certified:
            s["agreement_checked"] += 1
            sep = exact_sep_sq(a.z, b.z)
            dev = float(isqrt_up(sep))
            s["max_agreement_deviation"] = max(s["max_agreement_deviation"], dev)
            if sep <= SLACK_SQ:
                s["agreement_by_slack_floor"] += 1
            else:
                ra = radius(a.z, a.cert, rec)
                rb = radius(b.z, b.cert, rec)
                if (ra is None or rb is None) and len(rec[0]) <= R_MAX_DIM:
                    rr0 = R.solve_reference(rec, hint_z=a.z)
                    if rr0.is_exact:
                        ra = ra if ra is not None else isqrt_up(R.exact_distance(a.z, rr0.z))
                        rb = rb if rb is not None else isqrt_up(R.exact_distance(b.z, rr0.z))
                if ra is None or rb is None:
                    s["agreement_unavailable"] += 1
                elif sep <= (ra + rb + SLACK) ** 2:
                    s["agreement_by_bound"] += 1
                else:
                    s["certified_disagreements"] += 1
                    disp = M.CERTIFIED_SOLUTION_DISAGREEMENT
                    failures.append({"i": i, "axis": axis, "why": "CERTIFIED_SOLUTION_DISAGREEMENT",
                                     "deviation": dev, "bound": float(ra + rb + SLACK)})

        # ── diagnostics: repair-bound availability and R availability ──────────────────────────
        if z is not None:
            cert = a.cert if a.is_certified else b.cert
            rr = ra if ra is not None else radius(z, cert, rec)
            s["repair_bound_available" if rr is not None else "repair_bound_unavailable"] += 1

        if len(rec[0]) > R_MAX_DIM:
            s["R_skipped_size_budget"] += 1
        else:
            hint = z if z is not None else None
            res = R.solve_reference(rec, hint_z=hint) if hint is not None else R.ReferenceResult(
                R.R_UNAVAILABLE)
            s["R_exact" if res.is_exact else "R_unavailable"] += 1

        if disp not in (M.PRIMARY_CERTIFIED, M.SECONDARY_CERTIFIED):
            failures.append({"i": i, "axis": axis, "disposition": disp,
                             "A": [a.outcome, a.reason, a.detail[:100]],
                             "B": [b.outcome, b.reason, b.detail[:100]]})

        dispositions.append((disp, None if z is None else np.asarray(z, float).tobytes()))
        s["seconds"] += time.time() - ti
        if (i + 1) % 250 == 0:
            print(f"[{time.time()-t0:7.1f}s]   {i+1}/{n_inst}", flush=True)

    # ── reproducibility: rerun and compare dispositions + accepted allocations ─────────────────
    print(f"[{time.time()-t0:7.1f}s] reproducibility rerun ...", flush=True)
    mismatches = 0
    for i in range(n_inst):
        rec = tuple(d[f"{i}_{k}"] for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper"))
        a = M.normalize(A_PROFILE, SOLVERS[A_PROFILE], canonical_qualify, rec)
        b = M.normalize(B_PROFILE, SOLVERS[B_PROFILE], canonical_qualify, rec)
        if a.outcome == M.SYSTEM_INTEGRITY_DEFECT or b.outcome == M.SYSTEM_INTEGRITY_DEFECT:
            disp, z = M.INVALID_RUN, None
        elif a.is_certified:
            disp, z = M.PRIMARY_CERTIFIED, a.z
        elif b.is_certified:
            disp, z = M.SECONDARY_CERTIFIED, b.z
        else:
            disp, z = M.UNRESOLVED_INSTANCE, None
        want = dispositions[i]
        got_pair = (disp, None if z is None else np.asarray(z, float).tobytes())
        # the SA-2 upgrade is applied post hoc, so compare the pre-SA-2 disposition
        if want[0] == M.CERTIFIED_SOLUTION_DISAGREEMENT:
            if got_pair[1] != want[1]:
                mismatches += 1
                per[params[i]["axis"]]["reproducibility_mismatches"] += 1
        elif got_pair != want:
            mismatches += 1
            per[params[i]["axis"]]["reproducibility_mismatches"] += 1

    # ── roll-up and the frozen pass rule ───────────────────────────────────────────────────────
    tot = {k: sum(per[a][k] for a in AXES) for k in (
        "instances", "A_certified", "B_rescue", "unresolved", "integrity_defects",
        "unregistered_termination_reasons", "certified_disagreements", "agreement_checked",
        "agreement_by_slack_floor", "agreement_by_bound", "agreement_unavailable",
        "R_exact", "R_unavailable", "R_skipped_size_budget",
        "repair_bound_available", "repair_bound_unavailable", "reproducibility_mismatches")}
    tot["resolved"] = tot["A_certified"] + tot["B_rescue"]
    tot["max_agreement_deviation"] = max(per[a]["max_agreement_deviation"] for a in AXES)

    checks = {
        "no_system_integrity_defect": tot["integrity_defects"] == 0,
        "no_unregistered_termination_reason": tot["unregistered_termination_reasons"] == 0,
        "full_registered_resolution": tot["resolved"] == tot["instances"],
        "no_certified_solution_disagreement": tot["certified_disagreements"] == 0,
        "agreement_evidence_clean": tot["agreement_unavailable"] == 0,
        "deterministic_rerun": tot["reproducibility_mismatches"] == 0,
    }
    disposition = "N2_PASS" if all(checks.values()) else "N2_STOP"

    report = {
        "population_hash": POPULATION_HASH, "instances": tot["instances"],
        "solver_A": A_PROFILE, "solver_B": B_PROFILE,
        "R_size_budget_max_dim": R_MAX_DIM,
        "per_axis": per, "totals": tot, "pass_rule_checks": checks,
        "disposition": disposition, "failures": failures[:100],
        "diagnostics_are_not_thresholds": (
            "per-axis figures are diagnostic only; no additional pass threshold is derived from them"),
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    suffix = f"_limit{limit}" if limit else ""
    with open(os.path.join(OUT_DIR, f"n2_qualification{suffix}.json"), "w") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)

    print(f"\n{'axis':5s} {'inst':>5} {'Acert':>6} {'Bresc':>6} {'unres':>6} {'integ':>6} "
          f"{'unreg':>6} {'maxdev':>10} {'Rex':>5} {'Runa':>5} {'Rskip':>6} "
          f"{'repOK':>6} {'repNo':>6} {'repro':>6} {'secs':>7}")
    for ax in AXES:
        r = per[ax]
        print(f"{ax:5s} {r['instances']:5d} {r['A_certified']:6d} {r['B_rescue']:6d} "
              f"{r['unresolved']:6d} {r['integrity_defects']:6d} "
              f"{r['unregistered_termination_reasons']:6d} {r['max_agreement_deviation']:10.2e} "
              f"{r['R_exact']:5d} {r['R_unavailable']:5d} {r['R_skipped_size_budget']:6d} "
              f"{r['repair_bound_available']:6d} {r['repair_bound_unavailable']:6d} "
              f"{r['reproducibility_mismatches']:6d} {r['seconds']:7.1f}")
    print(f"\ntotals: {tot}")
    print("\npass-rule checks:")
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print(f"\nDISPOSITION: {disposition}")
    print(f"[{time.time()-t0:7.1f}s] wrote qualification report", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
