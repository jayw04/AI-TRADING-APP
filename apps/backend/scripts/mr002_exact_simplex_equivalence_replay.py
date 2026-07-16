"""MR-002 — FROZEN EQUIVALENCE REPLAY for the exact rational simplex (owner ruling §7).

The shared basis decomposition is an ACCELERATION. It is authorized only if it changes nothing:

    "A faster result with any different pivot or exact output is not accepted under this
     authorization."

So this harness does not check that the accelerated solver is *correct* — the certificates inside
`solve_lp` already do that, and a correct-but-different pivot path would still be a rejection. It
checks that it is IDENTICAL. It runs the same five analytic cases and the same eight content-hashed
corpus repairs, and records an equivalence record with no room to hide in:

    Phase-I pivot sequence            entering + leaving identity at every pivot
    Phase-II pivot sequence           basis content hash after every pivot
    Phase-I optimum                   artificial-cleanup basis + redundant rows
    rho*                              the exact repaired point
    the exact dual vector             ALL exact reduced costs
    the primal/dual objective identity
    the certificate inputs (the canonical LP content hash) and outputs

A pivot COUNT is not a pivot sequence, and a float is not an exact value. Both would let a divergent
computation report agreement.

TWO MODES
    --emit  <path>   run and write the record (used to freeze the REFERENCE, from the pre-change
                     implementation, before the acceleration is written)
    --check <path>   run and require EXACT equality with a frozen record; any difference is a STOP

Timings are recorded SEPARATELY from the equivalence record and are excluded from its hash — the
whole point of the change is that they differ.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
import tracemalloc
from fractions import Fraction

sys.path.insert(0, "/work/apps/backend")

from app.research.mr002.exact_repair import (  # noqa: E402
    build_standard_form,
    exact_repair,
    lp_content_hash,
)
from app.research.mr002.exact_simplex import (  # noqa: E402
    SimplexUnavailable,
    ceilings,
)
from scripts.mr002_coverage_signed_gap import CORPUS, fixture_hash  # noqa: E402
from scripts.mr002_exact_simplex_capability_gate import (  # noqa: E402
    A1,
    A2,
    A3,
    A4,
    A5,
    select_corpus,
)


def _run(z, args, label):
    """One repair. Returns (equivalence_record, resource_record). Never raises for A5-style exact
    infeasibility — that IS the expected exact output there, and it must replay identically too."""
    M, h, c, *_ = build_standard_form(z, *args)
    trace: dict = {}
    tracemalloc.start()
    t0 = time.perf_counter()
    try:
        r = exact_repair(z, *args, trace=trace)
        outcome, err = "SOLVED", None
    except SimplexUnavailable as exc:
        r, outcome, err = None, "SIMPLEX_UNAVAILABLE", str(exc).split(":")[0]
    seconds = time.perf_counter() - t0
    peak_mb = tracemalloc.get_traced_memory()[1] / 1e6
    tracemalloc.stop()

    eq = {
        "label": label,
        "lp_content_hash": lp_content_hash(M, h, c),      # the certificate INPUT
        "outcome": outcome,
        "reason_code": err,
        "phase_i_pivots": trace.get("phase_i_pivots"),
        "phase_i_optimum": trace.get("phase_i_optimum"),
        "phase_i_basis_sha256": trace.get("phase_i_basis_sha256"),
        "cleanup_basis_sha256": trace.get("cleanup_basis_sha256"),
        "redundant_rows": trace.get("redundant_rows"),
        "phase_ii_pivots": trace.get("phase_ii_pivots"),
        "final_basis": trace.get("final_basis"),
        "final_basis_sha256": trace.get("final_basis_sha256"),
        "x": trace.get("x"),
        "y": trace.get("y"),
        "reduced_costs": trace.get("reduced_costs"),
        "objective_primal": trace.get("objective_primal"),
        "objective_dual": trace.get("objective_dual"),
        "objective_identity": trace.get("objective_identity"),
    }
    if r is not None:
        eq["rho_star"] = f"{r['rho_star'].numerator}/{r['rho_star'].denominator}"
        eq["zhat"] = [f"{v.numerator}/{v.denominator}" for v in r["zhat"]]
        eq["n_changed"] = r["n_changed"]

    res = r["result"] if r is not None else None
    rec = {
        "label": label,
        "seconds": seconds,
        "peak_mb": peak_mb,
        "n_pivots_i": len(trace.get("phase_i_pivots") or []),
        "n_pivots_ii": len(trace.get("phase_ii_pivots") or []),
    }
    if res is not None:
        rec.update({
            "full_basis_dim": res.full_basis_dim,
            "core_dim_max": res.core_dim_max,
            "singletons_max": res.singletons_max,
            "max_num_bits": res.max_num_bits,
            "max_den_bits": res.max_den_bits,
            "core_seconds": res.core_seconds,
            "certificate_seconds": res.certificate_seconds,
            # §8 breakdown — present only once the shared decomposition exists.
            "decomposition_seconds": getattr(res, "decomposition_seconds", None),
            "core_factor_seconds": getattr(res, "core_factor_seconds", None),
            "primal_solve_seconds": getattr(res, "primal_solve_seconds", None),
            "direction_solve_seconds": getattr(res, "direction_solve_seconds", None),
            "dual_solve_seconds": getattr(res, "dual_solve_seconds", None),
            "verify_seconds": getattr(res, "verify_seconds", None),
            "n_decompositions": getattr(res, "n_decompositions", None),
        })
    return eq, rec


def eq_hash(equivalence) -> str:
    """Hash the EXACT record only. Timings are deliberately outside it."""
    blob = json.dumps(equivalence, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def diff(ref, new) -> list[str]:
    """Every field that moved, named. A count of differences is not a finding; the field is."""
    out = []
    by_ref = {c["label"]: c for c in ref}
    by_new = {c["label"]: c for c in new}
    if set(by_ref) != set(by_new):
        out.append(f"CASE SET DIFFERS: reference-only={sorted(set(by_ref) - set(by_new))} "
                   f"replay-only={sorted(set(by_new) - set(by_ref))}")
    for label in sorted(set(by_ref) & set(by_new)):
        a, b = by_ref[label], by_new[label]
        for k in sorted(set(a) | set(b)):
            va, vb = a.get(k), b.get(k)
            if va == vb:
                continue
            if k in ("phase_i_pivots", "phase_ii_pivots") and va and vb:
                if len(va) != len(vb):
                    out.append(f"{label}.{k}: LENGTH {len(va)} -> {len(vb)}")
                for i, (pa, pb) in enumerate(zip(va, vb, strict=False)):
                    if pa != pb:
                        out.append(f"{label}.{k}[{i}]: {pa} -> {pb}")
                        break
            else:
                out.append(f"{label}.{k}: {str(va)[:70]} -> {str(vb)[:70]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit")
    ap.add_argument("--check")
    a = ap.parse_args()
    if bool(a.emit) == bool(a.check):
        print("exactly one of --emit / --check", file=sys.stderr)
        return 2

    equivalence, resources = [], []

    print("=== 5 analytic cases ===")
    for case in (A1(), A2(), A3(), A4(), A5()):
        args = (case["A_ub"], case["b_ub"], case["A_eq"], case["b_eq"], case["upper"])
        eq, rec = _run(case["z"], args, case["name"])
        equivalence.append(eq)
        resources.append(rec)
        print(f"  {case['name']:24} {eq['outcome']:20} "
              f"pivots={rec['n_pivots_i']}+{rec['n_pivots_ii']} {rec['seconds']*1000:.0f}ms")

    chosen = select_corpus()
    print(f"\n=== {len(chosen)} corpus repairs (ascending lowercase SHA-256 content hash) ===")
    for idx, z1, rc in chosen:
        label = f"corpus:{fixture_hash(CORPUS[idx])}"
        eq, rec = _run(z1, rc[1:], label)
        equivalence.append(eq)
        resources.append(rec)
        rho = eq.get("rho_star", "-")
        rhof = float(Fraction(rho)) if rho != "-" else 0.0
        print(f"  [{idx:>4}] {label[7:23]}  {eq['outcome']:20} rho*={rhof:.3e} "
              f"pivots={rec['n_pivots_i']}+{rec['n_pivots_ii']} "
              f"basis={rec.get('full_basis_dim')} core={rec.get('core_dim_max')} "
              f"bits={rec.get('max_num_bits')}/{rec.get('max_den_bits')} "
              f"{rec['seconds']:.1f}s peak={rec['peak_mb']:.0f}MB")

    h = eq_hash(equivalence)
    doc = {
        "schema": "MR002_ExactSimplex_EquivalenceRecord/v1",
        "equivalence_sha256": h,
        "ceilings": ceilings(),
        "python": sys.version.split()[0],
        "platform_machine": platform.machine(),
        "equivalence": equivalence,
        "resources": resources,
        "note": ("`equivalence_sha256` covers the EXACT record only. Timings live in `resources` "
                 "and are deliberately outside the hash — the acceleration is expected to change "
                 "them and nothing else."),
        "no_performance_computed": True,
    }
    print(f"\nequivalence sha256: {h}")

    if a.emit:
        with open(a.emit, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
        print(f"wrote reference record -> {a.emit}")
        return 0

    with open(a.check, encoding="utf-8") as fh:
        ref = json.load(fh)
    print(f"reference sha256:   {ref['equivalence_sha256']}")
    ds = diff(ref["equivalence"], equivalence)
    print("\n" + "=" * 72)
    if not ds and ref["equivalence_sha256"] == h:
        ref_s = sum(r["seconds"] for r in ref["resources"])
        new_s = sum(r["seconds"] for r in resources)
        print("  EQUIVALENCE REPLAY: PASS — every pivot and every exact value is identical.")
        print(f"  wall-clock {ref_s:.1f}s -> {new_s:.1f}s  ({ref_s / max(new_s, 1e-9):.1f}x)")
        print("=" * 72)
        with open("/out/MR002_ExactSimplex_EquivalenceReplay.json", "w", encoding="utf-8") as fh:
            json.dump({**doc, "reference_sha256": ref["equivalence_sha256"], "replay_pass": True,
                       "reference_resources": ref["resources"]}, fh, indent=2)
        return 0

    print("  EQUIVALENCE REPLAY: FAIL — the acceleration changed the computation. STOP.")
    for d in ds[:40]:
        print(f"    {d}")
    if len(ds) > 40:
        print(f"    ... and {len(ds) - 40} more")
    print("=" * 72)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
