"""MR-002 — NARROW CAPABILITY GATE for the canonical exact rational simplex (ruling §13).

PREDECLARED, before the first run:

  Analytic cases (rational optima known by hand):
    A1  simple repair, single coordinate
    A2  MULTI-COORDINATE repair — the optimum must move at least two coordinates
    A3  DEGENERATE LP requiring a zero-length pivot
    A4  a REDUNDANT equality-form row
    A5  an EXACTLY INFEASIBLE Phase-I case (must report EXACT_PHASE_I_POSITIVE, not a crash)

  Corpus cases:
    eight MR-002 repair instances selected by ascending lowercase SHA-256 content hash, including
    instances that exhibited the prior HiGHS rho = 0 false basis.

REQUIRED (any failure stops the method before the larger fixture investment):
    exact Phase-I completion; Phase-I optimum = 0 on every feasible instance;
    exact Phase-II completion; exact primal certificate; exact reduced-cost certificate;
    exact objective identity; deterministic pivot sequence; canonical shuffle invariance.

DIAGNOSTIC HYPOTHESIS (predeclared, NOT an acceptance gate): rho* > 0 on essentially every corpus
repair — that is exactly the quantity HiGHS could not resolve. A zero exact optimum is PERMISSIBLE:
it simply means the submitted solver point happened to be exactly feasible.

RECORDED per repair: Phase-I/II pivot counts, wall-clock, peak memory, max numerator/denominator
bit lengths, full and reduced basis dimensions, singleton eliminations, core-solve time, and
exact-certificate verification time.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tracemalloc
from datetime import date
from fractions import Fraction

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.certificate import to_fraction  # noqa: E402
from app.research.mr002.exact_repair import (  # noqa: E402
    build_standard_form,
    exact_repair,
    lp_content_hash,
)
from app.research.mr002.exact_simplex import (  # noqa: E402
    SimplexUnavailable,
    ceilings,
    solve_lp,
)
from scripts.mr002_coverage_signed_gap import (  # noqa: E402
    CORPUS,
    FALLBACK,
    PRIMARY,
    capture,
    fixture_hash,
    try_solve,
)

N_CORPUS = 8


# ---------------------------------------------------------------- analytic predeclared cases
def A1():
    """SINGLE-COORDINATE repair. The equality is short by an exact amount and coordinate 1 is pinned
    at upper = 0, so ALL of the correction must land on coordinate 0."""
    return dict(
        name="A1 single-coordinate",
        z=np.array([0.5, 0.0]), A_ub=np.zeros((0, 2)), b_ub=np.zeros(0),
        A_eq=np.ones((1, 2)), b_eq=np.array([0.625]), upper=np.array([1.0, 0.0]),
        expect_rho=to_fraction(0.625) - to_fraction(0.5),        # = 1/8, exactly
        expect_changed=1,
    )


def A2():
    """MULTI-COORDINATE: three symmetric coordinates, bounds slack, the equality off by an exact
    amount. The minimum L-inf repair MUST spread it across all three (r/3 each) rather than put it
    all on one.

    ⚠ The expected rho is the EXACT RATIONAL implied by the IEEE-754 inputs, not the decimal it
    resembles: (0.9 - 3*0.2)/3 is NOT 1/10 in binary. An earlier version of this fixture asserted
    1/10 and failed against a correct solver — the naive expectation was the bug."""
    r = to_fraction(0.9) - 3 * to_fraction(0.2)
    return dict(
        name="A2 multi-coordinate",
        z=np.array([0.2, 0.2, 0.2]), A_ub=np.zeros((0, 3)), b_ub=np.zeros(0),
        A_eq=np.ones((1, 3)), b_eq=np.array([0.9]), upper=np.ones(3),
        expect_rho=abs(r) / 3, expect_changed=3,
    )


def A3():
    """DEGENERATE, requiring zero-length pivots: at the optimum, row 0 AND row 2 are both exactly
    tight. All coefficients are exact binary, so the optimum is exactly 1/16.

        d0 + d1 <= 0.375 - 0.5 = -0.125,  |d_i| <= rho  =>  rho >= 1/16
        achieved by d = (-1/16, -1/16, +1/16, +1/16), with d0 + d2 = 0 exactly tight."""
    return dict(
        name="A3 degenerate",
        z=np.array([0.25, 0.25, 0.25, 0.25]),
        A_ub=np.array([[1.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 1.0], [1.0, 0.0, 1.0, 0.0]]),
        b_ub=np.array([0.375, 0.75, 0.5]),
        A_eq=np.ones((1, 4)), b_eq=np.array([1.0]), upper=np.ones(4),
        expect_rho=Fraction(1, 16), expect_changed=4,
    )


def A4():
    """REDUNDANT equality-form row: a duplicated inequality makes the standard form carry an
    exactly redundant equation, which Phase-I cleanup must PROVE redundant and remove. The repair
    itself is forced: w0 <= 0.125 while the equality holds the sum at 0.5."""
    return dict(
        name="A4 redundant row",
        z=np.array([0.25, 0.25]),
        A_ub=np.array([[1.0, 0.0], [1.0, 0.0]]),      # exact duplicate
        b_ub=np.array([0.125, 0.125]),
        A_eq=np.ones((1, 2)), b_eq=np.array([0.5]), upper=np.ones(2),
        expect_rho=Fraction(1, 8), expect_changed=2,
    )


def A5():
    """EXACTLY INFEASIBLE: the budget exceeds what the box can hold. Phase I must terminate with a
    POSITIVE exact optimum and report it as a mathematical result, not a numerical failure."""
    return dict(
        name="A5 infeasible",
        z=np.array([0.05, 0.05]), A_ub=np.zeros((0, 2)), b_ub=np.zeros(0),
        A_eq=np.ones((1, 2)), b_eq=np.array([5.0]), upper=np.array([0.1, 0.1]),
        expect_infeasible=True,
    )


def run_case(case):
    z = case["z"]
    args = (case["A_ub"], case["b_ub"], case["A_eq"], case["b_eq"], case["upper"])
    tracemalloc.start()
    try:
        r = exact_repair(z, *args)
    except SimplexUnavailable as e:
        peak = tracemalloc.get_traced_memory()[1] / 1e6
        tracemalloc.stop()
        if case.get("expect_infeasible"):
            ok = "EXACT_PHASE_I_POSITIVE" in str(e)
            print(f"  {case['name']:24} {'PASS' if ok else 'FAIL'}  "
                  f"{'reported EXACT_PHASE_I_POSITIVE' if ok else str(e)[:60]}")
            return ok, {"name": case["name"], "infeasible": True, "peak_mb": peak}
        print(f"  {case['name']:24} FAIL  {str(e)[:70]}")
        return False, {"name": case["name"], "error": str(e)[:120]}
    peak = tracemalloc.get_traced_memory()[1] / 1e6
    tracemalloc.stop()

    if case.get("expect_infeasible"):
        print(f"  {case['name']:24} FAIL  expected infeasible, got rho={float(r['rho_star']):.3e}")
        return False, {"name": case["name"], "error": "expected infeasible"}

    res = r["result"]
    ok = True
    if "expect_rho" in case and r["rho_star"] != case["expect_rho"]:
        print(f"  {case['name']:24} FAIL  rho*={r['rho_star']} != expected {case['expect_rho']}")
        ok = False
    if "expect_changed" in case and r["n_changed"] != case["expect_changed"]:
        print(f"  {case['name']:24} FAIL  moved {r['n_changed']} coords, expected "
              f"{case['expect_changed']}")
        ok = False
    if ok:
        print(f"  {case['name']:24} PASS  rho*={float(r['rho_star']):.3e} "
              f"changed={r['n_changed']} pivots={res.pivots_phase_i}+{res.pivots_phase_ii} "
              f"redundant={len(res.redundant_rows)} {r['seconds']*1000:.0f}ms")
    return ok, {"name": case["name"], "rho": str(r["rho_star"]), "changed": r["n_changed"],
                "pivots_i": res.pivots_phase_i, "pivots_ii": res.pivots_phase_ii,
                "redundant_rows": len(res.redundant_rows), "peak_mb": peak,
                "seconds": r["seconds"]}


def main() -> int:  # noqa: PLR0915
    print("FROZEN RESOURCE CEILINGS:", json.dumps(ceilings(), indent=2)[:300], "...\n")
    print("=== Analytic capability cases (predeclared) ===")
    results, all_ok = [], True
    for case in (A1(), A2(), A3(), A4(), A5()):
        ok, rec = run_case(case)
        all_ok &= ok
        results.append(rec)

    # ---------------------------------------------------------------- corpus cases
    jp._solve_qp = capture
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    for cfg in ("A", "B", "C"):
        run_config(days, CONFIGS[cfg])

    qualifying = []
    for i, inst in enumerate(CORPUS):
        rec = (inst["t"], inst["A_ub"], inst["b_ub"],
               inst["A_eq"], inst["b_eq"], inst["upper"])
        p_ok, _, z1, _, _ = try_solve(PRIMARY, rec)
        f_ok, _, _z2, _, _ = try_solve(FALLBACK, rec)
        if p_ok and f_ok:
            qualifying.append((i, z1, rec))
        if len(qualifying) >= 400:
            break
    # FROZEN selection rule: ascending lowercase SHA-256 content hash.
    qualifying.sort(key=lambda q: fixture_hash(CORPUS[q[0]]))
    chosen = qualifying[:N_CORPUS]

    print(f"\n=== {len(chosen)} corpus repairs (ascending lowercase SHA-256 content hash) ===")
    n_rho_pos = 0
    for idx, z1, rec in chosen:
        ch = fixture_hash(CORPUS[idx])[:16]
        tracemalloc.start()
        try:
            r = exact_repair(z1, *rec[1:])
        except SimplexUnavailable as e:
            tracemalloc.stop()
            print(f"  [{idx:>4}] {ch}  FAIL  {str(e)[:70]}")
            all_ok = False
            results.append({"instance": idx, "error": str(e)[:120]})
            continue
        peak = tracemalloc.get_traced_memory()[1] / 1e6
        tracemalloc.stop()
        res = r["result"]
        if r["rho_star"] > 0:
            n_rho_pos += 1

        # determinism: the same instance twice must give an identical repair
        r2 = exact_repair(z1, *rec[1:])
        det = (r2["zhat"] == r["zhat"] and r2["rho_star"] == r["rho_star"]
               and r2["result"].basis == res.basis)

        # canonical shuffle invariance: permute variables and rows; the repair must not move
        n = len(rec[0])
        perm = np.random.default_rng(idx).permutation(n)
        rp = np.random.default_rng(idx + 1).permutation(rec[1].shape[0])
        r3 = exact_repair(z1[perm], rec[1][np.ix_(rp, perm)], rec[2][rp],
                          rec[3][:, perm], rec[4], rec[5][perm])
        shuf = all(r3["zhat"][k] == r["zhat"][perm[k]] for k in range(n)) \
            and r3["rho_star"] == r["rho_star"]

        M, h, c, *_ = build_standard_form(z1, *rec[1:])
        print(f"  [{idx:>4}] {ch}  PASS  rho*={float(r['rho_star']):.3e} "
              f"changed={r['n_changed']}/{n} pivots={res.pivots_phase_i}+{res.pivots_phase_ii} "
              f"basis={res.full_basis_dim} core={res.core_dim_max} "
              f"bits={res.max_num_bits}/{res.max_den_bits} "
              f"{r['seconds']:.1f}s (core {res.core_seconds:.1f}s cert "
              f"{res.certificate_seconds*1000:.0f}ms) peak={peak:.0f}MB "
              f"det={det} shuffle={shuf}")
        all_ok &= det and shuf
        results.append({
            "instance": idx, "content_hash": fixture_hash(CORPUS[idx]),
            "lp_hash": lp_content_hash(M, h, c),
            "rho_star": str(r["rho_star"]), "rho_positive": r["rho_star"] > 0,
            "n_changed": r["n_changed"], "n": n,
            "pivots_phase_i": res.pivots_phase_i, "pivots_phase_ii": res.pivots_phase_ii,
            "full_basis_dim": res.full_basis_dim, "core_dim_max": res.core_dim_max,
            "singletons_max": res.singletons_max,
            "max_num_bits": res.max_num_bits, "max_den_bits": res.max_den_bits,
            "seconds": r["seconds"], "core_seconds": res.core_seconds,
            "certificate_seconds": res.certificate_seconds,
            "peak_mb": peak, "deterministic": det, "shuffle_invariant": shuf,
            "redundant_rows": len(res.redundant_rows),
        })

    print(f"\nDIAGNOSTIC (predeclared, not a gate): rho* > 0 on {n_rho_pos}/{len(chosen)} corpus "
          f"repairs.")
    print("  A zero exact optimum is permissible — it means the solver point was exactly feasible.")
    print("\n" + "=" * 72)
    print("  CAPABILITY GATE: " + ("PASS" if all_ok else "FAIL"))
    print("=" * 72)

    out = {"gate_pass": all_ok, "ceilings": ceilings(), "results": results,
           "rho_positive_count": n_rho_pos, "corpus_cases": len(chosen),
           "selection_rule": "ascending lowercase SHA-256 of the instance content hash",
           "no_performance_computed": True}
    blob = json.dumps(out, indent=2, default=str)
    with open("/out/MR002_ExactSimplex_CapabilityGate.json", "w", encoding="utf-8") as fh:
        fh.write(blob)
    print("sha256:", hashlib.sha256(blob.encode()).hexdigest())
    print("wrote /out/MR002_ExactSimplex_CapabilityGate.json")
    _ = solve_lp
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
