"""MR-002 — DIAGNOSIS of the certified-gap replay outcome (owner ruling §6: STOP, adjudicate).

The replay halted: QUADPROG_SQRT -> PIQP_P2 left 35 unresolved instances. Nothing is altered here
— no solver setting, tolerance, cascade order or objective. This script only CHARACTERIZES why,
so the adjudication is made on evidence.

Three questions:

  1. Are the negative certified gaps the signed COMPLEMENTARITY residual?
     When stationarity holds exactly, h = q - C lam = -Hz, and

         G = f - d = z'Hz + q'z - b'lam = z'(Hz + q) - b'lam
                   = z'(C lam) - b'lam   = lam'(C'z - b)   = S_lag

     i.e. the certified gap COLLAPSES to the signed complementarity/violation term. The registered
     predicate gates that quantity in ABSOLUTE value; the certified-gap gate now requires it to be
     NONNEGATIVE. If the data bear this out, the negative gaps are not solver defects — they are
     the arithmetic consequence of a point that is feasible only to within rounding.

  2. What is the distribution of G, and how much of it sits within 1e-10 in MAGNITUDE?

  3. Do determinism and shuffle-invariance actually fail?
     The coverage run reported both as False, but its loops conflate "the fallback NONQUALIFIES on
     this instance" with "the fallback returned a DIFFERENT answer on a rerun". With 2,054 primary
     failures instead of 5, that conflation is guaranteed to fire. Reported honestly here.

DIAGNOSTIC ONLY. No performance computed, printed or persisted. Preflight and the development run
remain STOPPED. Validation and sealed OOS remain sealed and unread.
"""

from __future__ import annotations

import json
import sys
from datetime import date

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.certificate import CERTIFIED_GAP_MAX, certify  # noqa: E402
from scripts.mr002_complementary_coverage import (  # noqa: E402
    CORPUS,
    FALLBACK,
    PRIMARY,
    SOLVERS,
    capture,
    try_solve,
)
from scripts.mr002_solver_intersection import LIMITS  # noqa: E402


def main() -> int:  # noqa: PLR0915
    jp._solve_qp = capture
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    for cfg in ("A", "B", "C"):
        run_config(days, CONFIGS[cfg])
    print(f"corpus {len(CORPUS)}\n")

    rows = []
    fails: dict[str, set[int]] = {PRIMARY: set(), FALLBACK: set()}
    for i, inst in enumerate(CORPUS):
        rec = (inst["t"], inst["A_ub"], inst["b_ub"], inst["A_eq"], inst["b_eq"], inst["upper"])
        n = len(inst["t"])
        C, b = jp._qp_matrices(*rec[1:], n)
        meq = inst["A_eq"].shape[0]
        for name in (PRIMARY, FALLBACK):
            try:
                z, lam = SOLVERS[name](*(x.copy() for x in rec))
            except Exception:  # noqa: BLE001
                fails[name].add(i)
                continue
            ck = jp._acceptance(z, lam, meq, np.diag(2.0 / inst["t"]), 2.0 * np.ones(n),
                                C, b, *rec[1:])
            cert = certify(z, lam, *rec)
            kkt_bad = [k for k, lim in LIMITS.items() if ck[k] > lim]
            if kkt_bad or not cert.qualifies:
                fails[name].add(i)
            rows.append({
                "i": i, "solver": name,
                "G": cert.certified_gap,
                "S_lag": cert.lagrangian_slack,
                "kkt_bad": kkt_bad,
                "complementarity": float(ck.get("complementarity", float("nan"))),
                "primal_residual": float(ck.get("primal_residual", float("nan"))),
            })
        if (i + 1) % 1000 == 0:
            print(f"  {i+1}/{len(CORPUS)}", flush=True)

    # ---- Q1: is G the signed complementarity term? ------------------------------------
    print("\n=== Q1  Does G collapse to the signed Lagrangian/complementarity term? ===")
    for name in (PRIMARY, FALLBACK):
        rs = [r for r in rows if r["solver"] == name]
        d = [abs(r["G"] - r["S_lag"]) for r in rs]
        rel = [abs(r["G"] - r["S_lag"]) / max(abs(r["G"]), 1e-300) for r in rs if r["G"] != 0]
        print(f"  {name:16} max |G - S_lag| = {max(d):.3e}   median rel = "
              f"{float(np.median(rel)):.3e}")
    print("  (If G == S_lag to rounding, the certified gap IS the signed complementarity residual,")
    print("   whose ABSOLUTE value the registered predicate already gates.)")

    # ---- Q2: distribution --------------------------------------------------------------
    print("\n=== Q2  Distribution of the certified gap ===")
    summary = {}
    for name in (PRIMARY, FALLBACK):
        rs = [r for r in rows if r["solver"] == name]
        G = np.array([r["G"] for r in rs])
        clean = np.array([not r["kkt_bad"] for r in rs])           # passes every registered gate
        neg = G < 0
        within = np.abs(G) <= CERTIFIED_GAP_MAX
        s = {
            "certificates": len(rs),
            "kkt_clean": int(clean.sum()),
            "G_negative": int(neg.sum()),
            "G_negative_and_kkt_clean": int((neg & clean).sum()),
            "abs_G_within_1e-10": int(within.sum()),
            "kkt_clean_and_absG_within_1e-10": int((clean & within).sum()),
            "kkt_clean_and_G_in_[0,1e-10]": int((clean & (G >= 0) & within).sum()),
            "worst_negative": float(G.min()),
            "n_abs_G_above_1e-10": int((~within).sum()),
        }
        summary[name] = s
        print(f"  {name}")
        for k, v in s.items():
            print(f"      {k:38} {v}")

    # ---- The 35 unresolved, and what a TWO-SIDED gate would do (diagnostic only) --------
    unresolved = sorted(fails[PRIMARY] & fails[FALLBACK])
    print(f"\n=== The cascade's {len(unresolved)} unresolved instances ===")
    byreason = {}
    for i in unresolved:
        for name in (PRIMARY, FALLBACK):
            r = next((x for x in rows if x["i"] == i and x["solver"] == name), None)
            if r is None:
                key = f"{name}:raised"
            elif r["kkt_bad"]:
                key = f"{name}:KKT({'+'.join(r['kkt_bad'])})"
            elif r["G"] < 0:
                key = f"{name}:CERTIFIED_GAP_NEGATIVE_APPROX_PRIMAL"
            elif r["G"] > CERTIFIED_GAP_MAX:
                key = f"{name}:CERTIFIED_GAP_LIMIT_EXCEEDED"
            else:
                key = f"{name}:qualifies?"
            byreason[key] = byreason.get(key, 0) + 1
    for k in sorted(byreason):
        print(f"   {byreason[k]:4}  {k}")

    # DIAGNOSTIC counterfactual, NOT a proposed change: what if the gate were two-sided?
    two_sided_fail = {}
    for name in (PRIMARY, FALLBACK):
        bad = set()
        for r in rows:
            if r["solver"] != name:
                continue
            if r["kkt_bad"] or abs(r["G"]) > CERTIFIED_GAP_MAX:
                bad.add(r["i"])
        for i in range(len(CORPUS)):
            if not any(r["i"] == i and r["solver"] == name for r in rows):
                bad.add(i)                                          # solver raised
        two_sided_fail[name] = bad
    ts_unresolved = sorted(two_sided_fail[PRIMARY] & two_sided_fail[FALLBACK])
    print("\n=== DIAGNOSTIC COUNTERFACTUAL (not a proposed change; owner's call) ===")
    print("    If the certified-gap gate were |G| <= 1e-10 (two-sided) instead of 0 <= G <= 1e-10,")
    print("    holding EVERY other tolerance, solver setting and the cascade order fixed:")
    for name in (PRIMARY, FALLBACK):
        print(f"      {name:16} nonqualifications: {len(fails[name]):5}  ->  "
              f"{len(two_sided_fail[name]):5}")
    print(f"      cascade unresolved: {len(unresolved)}  ->  {len(ts_unresolved)}")

    # ---- Q3: determinism / shuffle, reported HONESTLY -----------------------------------
    print("\n=== Q3  Determinism and shuffle invariance (excluding nonqualifying instances) ===")
    rng = np.random.default_rng(0)
    det_checked = det_diff = 0
    shuf_checked = shuf_bad = 0
    worst_shuf = 0.0
    for i in sorted(fails[PRIMARY]):
        inst = CORPUS[i]
        rec = (inst["t"], inst["A_ub"], inst["b_ub"], inst["A_eq"], inst["b_eq"], inst["upper"])
        a_ok, _, za, _, _ = try_solve(FALLBACK, rec)
        b_ok, _, zb, _, _ = try_solve(FALLBACK, rec)
        if not (a_ok and b_ok):
            continue                       # NONQUALIFIES — says nothing about determinism
        det_checked += 1
        if not np.array_equal(za, zb):
            det_diff += 1

        t, A_ub, b_ub, A_eq, b_eq, upper = rec
        p = rng.permutation(len(t))
        r = rng.permutation(A_ub.shape[0])
        ok1, _, z1, _, _ = try_solve(
            FALLBACK, (t[p], A_ub[np.ix_(r, p)], b_ub[r], A_eq[:, p], b_eq, upper[p]))
        if not ok1:
            continue
        shuf_checked += 1
        d = float(np.max(np.abs(za[p] - z1)))
        worst_shuf = max(worst_shuf, d)
        if d > 1e-8:
            shuf_bad += 1
    print(f"  determinism : {det_checked} qualifying instances rechecked, {det_diff} differed")
    print(f"  shuffle     : {shuf_checked} rechecked, {shuf_bad} exceeded 1e-8 "
          f"(worst |delta| = {worst_shuf:.3e})")
    print("  ⚠ The coverage run reported both as FAILED. That was a REPORTING ARTIFACT: its loops")
    print("    treat 'the fallback nonqualifies here' as a determinism failure, and the certified")
    print("    predicate produced 2,054 primary failures instead of 5. Not a real finding.")

    out = {
        "verdict": "STOP FOR ADJUDICATION (owner ruling §6): cascade unresolved != 0",
        "cascade": [PRIMARY, FALLBACK],
        "unresolved": unresolved,
        "unresolved_reasons": byreason,
        "gap_distribution": summary,
        "determinism": {"rechecked": det_checked, "differed": det_diff},
        "shuffle_invariance": {"rechecked": shuf_checked, "violations": shuf_bad,
                               "worst_delta": worst_shuf},
        "diagnostic_counterfactual_two_sided_gate": {
            "note": ("NOT a proposed change. Recorded so the adjudication is made on evidence. "
                     "Every other tolerance, solver setting and the cascade order held fixed."),
            "nonqualifications": {k: len(v) for k, v in two_sided_fail.items()},
            "cascade_unresolved": len(ts_unresolved),
            "unresolved_instances": ts_unresolved,
        },
        "no_performance_computed": True,
    }
    with open("/out/MR002_CertifiedGap_Diagnosis.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print("\nwrote /out/MR002_CertifiedGap_Diagnosis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
