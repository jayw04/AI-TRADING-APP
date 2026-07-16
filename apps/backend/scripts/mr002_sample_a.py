"""MR-002 — SAMPLE A, under the frozen specification (owner ruling 2026-07-14 §7–§9).

WHY THIS IS A NEW RUNNER AND NOT `MR002_SAMPLE=A` ON THE OLD ONE
---------------------------------------------------------------
`mr002_coverage_signed_gap.py` imports its repair from `app.research.mr002.repair` — the RETIRED
R2/absorber module. Run as-wired, Sample A would re-execute the very path that produced 40/50
REPAIR_CERTIFICATE_UNAVAILABLE in `MR002_R2_RegressionSampleA.json`, and it would contradict §7,
which requires the canonical exact rational minimum-L-infinity repair and the shared exact basis
decomposition. So the repair is rewired; NOTHING ELSE IS.

FROZEN, and asserted rather than assumed:
  * the selection rule            A = the first 50 QUALIFYING OVERLAPS in canonical corpus order.
                                  The selection is compared against the recorded frozen list and a
                                  mismatch is a STOP (§9) — a sample may not be substituted,
                                  reordered, filtered or regenerated after observing outcomes.
  * instance identity             the CONTENT HASH. The index is a label.
  * the cascade                   QUADPROG_SQRT -> PIQP_P2
  * the predicate                 registered KKT LIMITS  AND  two-sided signed Lagrangian gap
  * the pivot path                Bland's rule, unchanged
  * the certificates              exact, unchanged
  * the ceiling                   600 s per repair, unchanged
  * the serializer                the corrected directed rounding

A STOP IS A NUMERICAL OR IMPLEMENTATION FINDING. IT IS NOT AN ECONOMIC RESULT.
No performance is computed. Validation and sealed OOS remain SEALED AND UNREAD.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import tracemalloc
from datetime import date
from fractions import Fraction

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002.certificate import (  # noqa: E402
    MAX_INTERVAL_WIDTH,
    SIGNED_GAP_MAX,
    CertificateDefect,
)
from app.research.mr002.directed import as_fraction  # noqa: E402

# THE CANONICAL EXACT REPAIR. `app.research.mr002.repair` (R2/absorber) is RETIRED and is not
# imported here — importing it at all would leave the retired path one edit away from the evidence.
from app.research.mr002.exact_repair import (  # noqa: E402
    RepairUnavailable,
    agreement,
    certify_repair,
    objective_agreement,
)
from app.research.mr002.exact_repair import manifest as repair_manifest  # noqa: E402
from app.research.mr002.exact_simplex import ceilings  # noqa: E402
from scripts.mr002_coverage_signed_gap import (  # noqa: E402
    CORPUS,
    FALLBACK,
    PRIMARY,
    REGRESSION_N,
    capture,
    fixture_hash,
    try_solve,
)
from scripts.mr002_directed_rounding_correction import source_hashes  # noqa: E402
from scripts.mr002_solver_intersection import (  # noqa: E402
    LIMITS,
    REGISTERED_CORPUS_HASH,
)

FROZEN_A_PATH = "/work/.mr002out/frozen_sample_a.json"


def vec_hash(v) -> str:
    """A repaired point's identity: the EXACT rationals, not a rounded rendering of them."""
    h = hashlib.sha256(b"MR002|repaired-point|v1")
    for x in v:
        f = x if isinstance(x, Fraction) else as_fraction(x)
        h.update(f"{f.numerator}/{f.denominator};".encode())
    return h.hexdigest()


def main() -> int:  # noqa: PLR0915
    out_dir = os.environ.get("MR002_OUT", "/out")
    stops: list[dict] = []

    jp._solve_qp = capture
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    for cfg in ("A", "B", "C"):
        run_config(days, CONFIGS[cfg])

    ch = hashlib.sha256("|".join(i["hash"] for i in CORPUS).encode()).hexdigest()
    print(f"corpus {len(CORPUS)}  hash {ch}")
    if ch != REGISTERED_CORPUS_HASH:
        print("STOP: corpus hash mismatch", file=sys.stderr)
        return 1
    print("[ok] corpus reproduced EXACTLY\n")

    # ---- the cascade, over the whole corpus, to find the qualifying overlaps -------------------
    print("resolving the cascade to find qualifying overlaps ...")
    zs: dict[str, dict[int, np.ndarray]] = {PRIMARY: {}, FALLBACK: {}}
    certs: dict[str, dict[int, object]] = {PRIMARY: {}, FALLBACK: {}}
    status: dict[str, dict[int, str]] = {PRIMARY: {}, FALLBACK: {}}
    t0 = time.perf_counter()
    for i, inst in enumerate(CORPUS):
        rec = (inst["t"], inst["A_ub"], inst["b_ub"], inst["A_eq"], inst["b_eq"], inst["upper"])
        for name in (PRIMARY, FALLBACK):
            ok, why, z, _lam, cert = try_solve(name, rec)
            status[name][i] = "QUALIFIES" if ok else why
            if ok:
                zs[name][i] = z
                certs[name][i] = cert
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(CORPUS)}  ({time.perf_counter()-t0:.0f}s)", flush=True)

    qualifying = sorted(set(zs[PRIMARY]) & set(zs[FALLBACK]))
    sample_a = qualifying[:REGRESSION_N]          # THE FROZEN RULE. Canonical corpus order.
    print(f"\nqualifying overlaps: {len(qualifying)}   Sample A: {len(sample_a)}")

    # ---- §9: the selection must reproduce the FROZEN list, or STOP ----------------------------
    with open(FROZEN_A_PATH, encoding="utf-8") as fh:
        frozen = json.load(fh)
    if sample_a != frozen:
        stops.append({"stop": "CONTENT_HASH_SELECTION_MISMATCH",
                      "frozen": frozen, "selected": sample_a})
        print("STOP: Sample A selection does not reproduce the frozen list", file=sys.stderr)
        print(f"  frozen   {frozen[:12]}...\n  selected {sample_a[:12]}...", file=sys.stderr)
        return 1
    print("[ok] Sample A reproduces the FROZEN preregistered selection exactly\n")

    # ---- the exact repair + agreement certificates, per overlap --------------------------------
    print(f"--- exact min-Linf repair (canonical) on {len(sample_a)} overlaps ---")
    print(f"    method   : {repair_manifest()['method']}")
    print(f"    ceilings : {ceilings()['max_seconds_per_repair']}s / repair\n")

    records: list[dict] = []
    agg = {"total_overlaps": len(sample_a), "successful_exact_repairs": 0,
           "exactly_infeasible_repairs": 0, "invalid_runs": 0, "resource_ceiling_breaches": 0,
           "agreement_passes": 0, "agreement_failures": 0,
           "objective_agreement_passes": 0, "objective_agreement_failures": 0,
           "determinism_failures": 0, "shuffle_invariance_failures": 0}

    rng = np.random.default_rng(0)
    t0 = time.perf_counter()
    for k, i in enumerate(sample_a):
        inst = CORPUS[i]
        rec = (inst["t"], inst["A_ub"], inst["b_ub"], inst["A_eq"], inst["b_eq"], inst["upper"])
        chash = fixture_hash(inst)
        rowrec: dict = {
            "instance_label": i, "content_hash": chash,
            "solvers": {PRIMARY: status[PRIMARY][i], FALLBACK: status[FALLBACK][i]},
        }
        for name in (PRIMARY, FALLBACK):
            c = certs[name][i]
            rowrec[f"signed_gap_{name}"] = {
                "interval": [c.gamma_lower, c.gamma_upper],
                "primal": [c.primal_lower, c.primal_upper],
                "dual": [c.dual_lower, c.dual_upper],
                "widths": [c.primal_interval_width, c.dual_interval_width],
                "qualifies": c.qualifies,
                "multipliers_clipped": c.n_multipliers_clipped,
            }

        tracemalloc.start()
        ts = time.perf_counter()
        try:
            r1 = certify_repair(zs[PRIMARY][i], certs[PRIMARY][i], *rec)
            r2 = certify_repair(zs[FALLBACK][i], certs[FALLBACK][i], *rec)
            outcome = "EXACT_REPAIR_OK"
            agg["successful_exact_repairs"] += 1
        except RepairUnavailable as e:
            peak = tracemalloc.get_traced_memory()[1] / 1e6
            tracemalloc.stop()
            reason = str(e).split(":")[0]
            breach = "RESOURCE_LIMIT" in reason
            infeasible = "PHASE_I_POSITIVE" in reason
            agg["resource_ceiling_breaches"] += int(breach)
            agg["exactly_infeasible_repairs"] += int(infeasible)
            agg["invalid_runs"] += int(not breach and not infeasible)
            rowrec.update({"exact_repair_status": reason, "detail": str(e)[:200],
                           "seconds": time.perf_counter() - ts, "peak_mb": peak})
            records.append(rowrec)
            stops.append({"stop": reason, "instance": i, "content_hash": chash})
            print(f"  [{k+1:>2}/{len(sample_a)}] {chash[:16]} STOP {reason}")
            continue
        except CertificateDefect as e:
            tracemalloc.stop()
            agg["invalid_runs"] += 1
            stops.append({"stop": "CERTIFICATE_DEFECT", "instance": i, "detail": str(e)[:200]})
            print(f"  [{k+1:>2}/{len(sample_a)}] {chash[:16]} STOP CERTIFICATE_DEFECT")
            records.append({**rowrec, "exact_repair_status": "CERTIFICATE_DEFECT"})
            continue
        peak = tracemalloc.get_traced_memory()[1] / 1e6
        tracemalloc.stop()
        secs = time.perf_counter() - ts

        ok_a, dz, bound = agreement(r1, r2, zs[PRIMARY][i], zs[FALLBACK][i])
        ok_o, df, obound = objective_agreement(r1, r2, certs[PRIMARY][i], certs[FALLBACK][i])
        agg["agreement_passes" if ok_a else "agreement_failures"] += 1
        agg["objective_agreement_passes" if ok_o else "objective_agreement_failures"] += 1

        # determinism: the same instance twice must give an IDENTICAL exact repair
        r1b = certify_repair(zs[PRIMARY][i], certs[PRIMARY][i], *rec)
        det = (r1b.zhat == r1.zhat and r1b.rho_star == r1.rho_star)
        if not det:
            agg["determinism_failures"] += 1
            stops.append({"stop": "DETERMINISM_FAILURE", "instance": i, "content_hash": chash})

        # canonical shuffle invariance: relabel variables and rows; the repair must not move
        n = len(rec[0])
        p = rng.permutation(n)
        rp = rng.permutation(rec[1].shape[0])
        r1s = certify_repair(
            zs[PRIMARY][i][p], certs[PRIMARY][i], rec[0][p],
            rec[1][np.ix_(rp, p)], rec[2][rp], rec[3][:, p], rec[4], rec[5][p])
        shuf = (r1s.rho_star == r1.rho_star
                and all(r1s.zhat[j] == r1.zhat[p[j]] for j in range(n)))
        if not shuf:
            agg["shuffle_invariance_failures"] += 1
            stops.append({"stop": "SHUFFLE_INVARIANCE_FAILURE", "instance": i,
                          "content_hash": chash})

        for tag, r in ((PRIMARY, r1), (FALLBACK, r2)):
            rowrec[f"repair_{tag}"] = {
                "rho_star": f"{r.rho_star.numerator}/{r.rho_star.denominator}",
                "rho_star_float": float(r.rho_star),
                "repaired_point_hash": vec_hash(r.zhat),
                "n_coords_changed": r.n_coords_changed,
                "pivots_phase_i": r.pivots_phase_i, "pivots_phase_ii": r.pivots_phase_ii,
                "basis_dim": r.basis_dim, "core_dim": r.core_dim,
                "singletons_eliminated": r.singletons_eliminated,
                "max_num_bits": r.max_num_bits, "max_den_bits": r.max_den_bits,
                "delta_upper": r.delta_upper, "ghat_upper": r.ghat_upper,
                "radius_upper": r.radius_upper,
                "objective_bound_upper": r.objective_bound_upper,
                "solve_seconds": r.solve_seconds,
                "empty_rows": len(r.empty_rows),
            }
        rowrec.update({
            "exact_repair_status": outcome,
            "agreement_distance_certificate": {"pass": ok_a, "dz": dz, "bound": bound},
            "objective_agreement_certificate": {"pass": ok_o, "df": df, "bound": obound},
            "deterministic": det, "shuffle_invariant": shuf,
            "seconds": secs, "peak_mb": peak,
            "final_overlap_verdict": "PASS" if (ok_a and ok_o and det and shuf) else "FAIL",
        })
        records.append(rowrec)
        print(f"  [{k+1:>2}/{len(sample_a)}] {chash[:16]} {outcome}  "
              f"rho*={float(r1.rho_star):.2e}/{float(r2.rho_star):.2e} "
              f"basis={r1.basis_dim}/{r2.basis_dim} core={r1.core_dim}/{r2.core_dim} "
              f"agree={'ok' if ok_a else 'FAIL'} obj={'ok' if ok_o else 'FAIL'} "
              f"det={det} shuf={shuf} {secs:.1f}s {peak:.0f}MB", flush=True)

    secs_total = time.perf_counter() - t0

    print("\n=== Sample A aggregate (§8) ===")
    for k2, v in agg.items():
        print(f"  {k2:32} {v}")
    worst = max((r.get("seconds", 0.0) for r in records), default=0.0)
    peakmax = max((r.get("peak_mb", 0.0) for r in records), default=0.0)
    print(f"  {'worst repair wall-clock':32} {worst:.1f}s  (ceiling "
          f"{ceilings()['max_seconds_per_repair']}s)")
    print(f"  {'peak memory':32} {peakmax:.0f}MB")

    ok = (not stops
          and agg["successful_exact_repairs"] == len(sample_a)
          and agg["agreement_failures"] == 0
          and agg["objective_agreement_failures"] == 0
          and agg["determinism_failures"] == 0
          and agg["shuffle_invariance_failures"] == 0)
    print("\n" + "=" * 74)
    print("  SAMPLE A: " + ("PASS" if ok else "STOP FOR ADJUDICATION"))
    print("=" * 74)
    for s in stops[:10]:
        print(f"    {s['stop']}  instance={s.get('instance')}")

    doc = {
        "schema": "MR002_SampleA/v1",
        "authorization": "owner ruling 2026-07-14 §7-§9 (Sample A only)",
        "scope_boundary": ("a successful Sample A authorizes NOTHING further: not Sample B, not the "
                           "full overlap population, not preflight, not development performance, "
                           "not validation, not sealed OOS, not an erratum"),
        "frozen_specification": {
            "selection_rule": ("A = the first 50 QUALIFYING OVERLAPS in canonical corpus order; "
                               "identity is the CONTENT HASH, the index is a label. Asserted against "
                               "the recorded frozen list; a mismatch is a STOP."),
            "selection_matches_frozen_list": True,
            "cascade": [PRIMARY, FALLBACK],
            "predicate": "registered KKT LIMITS AND two-sided signed Lagrangian gap",
            "signed_gap_band": [-SIGNED_GAP_MAX, SIGNED_GAP_MAX],
            "max_interval_width": MAX_INTERVAL_WIDTH,
            "LIMITS": LIMITS,
            "repair": repair_manifest(),
            "resource_ceilings": ceilings(),
            "pivot_rule": "Bland's rule over canonical column identities — unchanged",
            "serializer": "corrected directed (outward) binary64 — see app/research/mr002/directed.py",
            "retired_and_not_imported": "app.research.mr002.repair (R2 / absorber family)",
        },
        "corpus_hash": ch,
        "sample_a": sample_a,
        "sample_a_content_hashes": [fixture_hash(CORPUS[i]) for i in sample_a],
        "qualifying_overlaps": len(qualifying),
        "records": records,
        "aggregate": agg,
        "worst_repair_seconds": worst,
        "peak_memory_mb": peakmax,
        "stops": stops,
        "wall_clock_seconds": secs_total,
        "provenance": {
            "commit": os.environ.get("MR002_COMMIT_SHA"),
            "image": os.environ.get("MR002_IMAGE_DIGEST"),
            "mounted_source_sha256": source_hashes(),
        },
        "sample_a_pass": ok,
        "no_performance_computed": True,
        "validation_and_sealed_oos": "SEALED AND UNREAD",
    }
    blob = json.dumps(doc, indent=2, default=str)
    with open(f"{out_dir}/MR002_SampleA.json", "w", encoding="utf-8") as fh:
        fh.write(blob)
    print(f"\nSample A sha256 {hashlib.sha256(blob.encode()).hexdigest()}")
    print(f"wall-clock {secs_total:.0f}s")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
