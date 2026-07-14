"""MR-002 — SAMPLE B, the preregistered DISJOINT prospective sample (owner ruling 2026-07-14 §7-§10).

Sample B is the anti-overfitting control: R2 was designed AFTER observing Sample A's failures, so a
pass on A alone proves only that the diagnosed mechanism is corrected. B is 100 qualifying overlaps
NOT in A, ordered by CONTENT HASH — an order independent of every result, of corpus position, and of
A's membership — so it cannot be contaminated by what was learned from A.

This runner shares the EXACT Sample A code path. It changes only which preregistered slice runs, and
it proves that before any repair begins (§7):

    * the B content-hash list exactly matches preregistration
    * B contains no Sample A content hash (disjointness)
    * B contains no substituted or regenerated instance
    * the solver / certificate / selection / serializer module hashes match the c130149 manifest

§4 CALL-GRAPH BINDING. The evidence must prove the path was
    registered overlap selection -> frozen qualification predicate -> canonical exact min-Linf
    repair -> exact agreement certificates -> corrected directed rounding
with NO silent fallback to R1, R2, R2-C1 or the HiGHS basis oracle. So the retired module
`app.research.mr002.repair` is asserted ABSENT from sys.modules, and the bound module source hashes
are recorded.

§8 DISTRIBUTIONS. Beyond the Sample A per-overlap fields and aggregates, the full DISTRIBUTION (not
only the maximum) of repair wall-clock, pivot count, core dimension, numerator/denominator bit
lengths, rho* and agreement margins is recorded.

§9 STOP. Any failure preserves the failing instance and all partial evidence; the run does not
continue to a cleaner aggregate. A stop is a numerical/implementation finding, not an economic one.

No performance computed. Validation and sealed OOS remain SEALED AND UNREAD. Preflight STOPPED.
"""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import sys
import time
import tracemalloc
from datetime import date
from fractions import Fraction

import numpy as np

sys.path.insert(0, "/work/apps/backend")

from app.research.mr002.certificate import (  # noqa: E402
    MAX_INTERVAL_WIDTH,
    SIGNED_GAP_MAX,
    CertificateDefect,
)
from app.research.mr002.directed import as_fraction  # noqa: E402
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
    PROSPECTIVE_N,
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

FROZEN_B_PATH = "/work/.mr002out/frozen_sample_b.json"

# The c130149 manifest of solver/certificate/selection/serializer module hashes. Sample B must run
# against byte-identical modules (§7). Recorded here from the sealed record so a drift is a STOP,
# not a silent difference. Populated from the immutable record at load.
MANIFEST_HASHES: dict = {}


def _load_manifest() -> dict:
    p = "/work/docs/implementation/evidence/mr_002/MR002_DirectedRounding_ImmutableRecord.json"
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)["source_module_sha256"]


def vec_hash(v) -> str:
    h = hashlib.sha256(b"MR002|repaired-point|v1")
    for x in v:
        f = x if isinstance(x, Fraction) else as_fraction(x)
        h.update(f"{f.numerator}/{f.denominator};".encode())
    return h.hexdigest()


def _dist(xs: list[float]) -> dict:
    """The DISTRIBUTION of a quantity (§8) — not only its maximum."""
    if not xs:
        return {}
    s = sorted(xs)

    def q(p):
        return s[min(len(s) - 1, int(p * (len(s) - 1) + 0.5))]
    return {
        "n": len(s), "min": s[0], "p50": q(0.50), "p90": q(0.90), "p99": q(0.99), "max": s[-1],
        "mean": statistics.fmean(s),
    }


def main() -> int:  # noqa: PLR0915
    out_dir = os.environ.get("MR002_OUT", "/out")
    stops: list[dict] = []

    # ---- §4 CALL-GRAPH BINDING: prove the canonical path, no retired fallback loaded -----------
    if "app.research.mr002.repair" in sys.modules:
        print("STOP: the RETIRED R2 module is imported — a silent fallback is possible", file=sys.stderr)
        return 1
    bound = source_hashes()
    manifest = _load_manifest()
    drift = {k: (manifest.get(k), bound.get(k)) for k in bound if manifest.get(k) != bound.get(k)}
    # The runner file itself legitimately differs from Sample A; the SOLVER PATH must not.
    solver_path = ("app/research/mr002/directed.py", "app/research/mr002/certificate.py",
                   "app/research/mr002/joint_portfolio.py", "scripts/mr002_coverage_signed_gap.py",
                   "scripts/mr002_solver_intersection.py")
    solver_drift = {k: v for k, v in drift.items() if k in solver_path}
    if solver_drift:
        print(f"STOP: solver-path module hashes differ from the c130149 manifest: "
              f"{list(solver_drift)}", file=sys.stderr)
        return 1
    print("[ok] §4 call graph: canonical exact repair; retired R2 module ABSENT; "
          "solver-path hashes == c130149\n")

    jp_ok = True
    try:
        import app.research.mr002.exact_repair as er
        import app.research.mr002.exact_simplex as es
        # the repair must resolve to the canonical simplex, not any oracle
        assert er.solve_lp is es.solve_lp  # noqa: S101
    except Exception as exc:  # noqa: BLE001
        jp_ok = False
        stops.append({"stop": "CALL_GRAPH_BINDING_FAILED", "detail": str(exc)[:160]})
    if not jp_ok:
        print("STOP: exact repair does not resolve to the canonical simplex", file=sys.stderr)
        return 1

    import app.research.mr002.joint_portfolio as jp
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

    # ---- resolve the cascade; build the frozen A and B selections --------------------------------
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
    sample_a = qualifying[:REGRESSION_N]
    rest = [i for i in qualifying if i not in set(sample_a)]
    sample_b = sorted(rest, key=lambda i: fixture_hash(CORPUS[i]))[:PROSPECTIVE_N]   # THE FROZEN RULE

    # ---- §7 PRE-PROOFS, before any repair --------------------------------------------------------
    with open(FROZEN_B_PATH, encoding="utf-8") as fh:
        frozen = json.load(fh)
    checks = {
        "matches_preregistration": sample_b == frozen["prospective_B"],
        "content_hashes_match": [fixture_hash(CORPUS[i]) for i in sample_b] == frozen["content_hashes"],
        "disjoint_from_A": not (set(sample_b) & set(frozen["regression_A"])),
        "no_A_content_hash": not (set(fixture_hash(CORPUS[i]) for i in sample_b)
                                  & set(fixture_hash(CORPUS[i]) for i in sample_a)),
        "size_100": len(sample_b) == PROSPECTIVE_N,
    }
    print("--- §7 pre-proofs ---")
    for k, v in checks.items():
        print(f"    [{'ok' if v else 'STOP'}] {k}")
    if not all(checks.values()):
        stops.append({"stop": "SAMPLE_B_PREREGISTRATION_MISMATCH", "checks": checks})
        print("STOP: Sample B does not match preregistration", file=sys.stderr)
        return 1
    print()

    # ---- exact repair + agreement certificates, per overlap --------------------------------------
    print(f"--- exact min-Linf repair (canonical) on {len(sample_b)} B overlaps ---")
    print(f"    method   : {repair_manifest()['method']}")
    print(f"    ceilings : {ceilings()['max_seconds_per_repair']}s / repair\n")

    records: list[dict] = []
    agg = {"total_overlaps": len(sample_b), "successful_exact_repairs": 0,
           "exactly_infeasible_repairs": 0, "invalid_runs": 0, "resource_ceiling_breaches": 0,
           "agreement_passes": 0, "agreement_failures": 0,
           "objective_agreement_passes": 0, "objective_agreement_failures": 0,
           "determinism_failures": 0, "shuffle_invariance_failures": 0}
    dists: dict[str, list[float]] = {"wall_clock": [], "pivots": [], "core_dim": [],
                                     "num_bits": [], "den_bits": [], "rho_star_log10": [],
                                     "agreement_margin": [], "objective_margin": []}

    rng = np.random.default_rng(0)
    t0 = time.perf_counter()
    for k, i in enumerate(sample_b):
        inst = CORPUS[i]
        rec = (inst["t"], inst["A_ub"], inst["b_ub"], inst["A_eq"], inst["b_eq"], inst["upper"])
        chash = fixture_hash(inst)
        n = len(inst["t"])
        m_ub = int(np.asarray(inst["A_ub"]).shape[0])
        rowrec: dict = {
            "instance_label": i, "content_hash": chash, "n": n, "m_ub": m_ub,
            "solvers": {PRIMARY: status[PRIMARY][i], FALLBACK: status[FALLBACK][i]},
        }
        for name in (PRIMARY, FALLBACK):
            c = certs[name][i]
            rowrec[f"signed_gap_{name}"] = {
                "interval": [c.gamma_lower, c.gamma_upper],
                "qualifies": c.qualifies, "multipliers_clipped": c.n_multipliers_clipped,
            }

        tracemalloc.start()
        ts = time.perf_counter()
        try:
            r1 = certify_repair(zs[PRIMARY][i], certs[PRIMARY][i], *rec)
            r2 = certify_repair(zs[FALLBACK][i], certs[FALLBACK][i], *rec)
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
            print(f"  [{k+1:>3}/{len(sample_b)}] {chash[:16]} STOP {reason}")
            break                                       # §9: preserve; do not continue for a cleaner aggregate
        except CertificateDefect as e:
            tracemalloc.stop()
            agg["invalid_runs"] += 1
            stops.append({"stop": "CERTIFICATE_DEFECT", "instance": i, "detail": str(e)[:200]})
            records.append({**rowrec, "exact_repair_status": "CERTIFICATE_DEFECT"})
            print(f"  [{k+1:>3}/{len(sample_b)}] {chash[:16]} STOP CERTIFICATE_DEFECT")
            break
        peak = tracemalloc.get_traced_memory()[1] / 1e6
        tracemalloc.stop()
        secs = time.perf_counter() - ts

        ok_a, dz, bound = agreement(r1, r2, zs[PRIMARY][i], zs[FALLBACK][i])
        ok_o, df, obound = objective_agreement(r1, r2, certs[PRIMARY][i], certs[FALLBACK][i])
        agg["agreement_passes" if ok_a else "agreement_failures"] += 1
        agg["objective_agreement_passes" if ok_o else "objective_agreement_failures"] += 1

        r1b = certify_repair(zs[PRIMARY][i], certs[PRIMARY][i], *rec)
        det = (r1b.zhat == r1.zhat and r1b.rho_star == r1.rho_star)
        if not det:
            agg["determinism_failures"] += 1
            stops.append({"stop": "DETERMINISM_FAILURE", "instance": i, "content_hash": chash})

        p = rng.permutation(n)
        rp = rng.permutation(rec[1].shape[0])
        r1s = certify_repair(zs[PRIMARY][i][p], certs[PRIMARY][i], rec[0][p],
                             rec[1][np.ix_(rp, p)], rec[2][rp], rec[3][:, p], rec[4], rec[5][p])
        shuf = (r1s.rho_star == r1.rho_star
                and all(r1s.zhat[j] == r1.zhat[p[j]] for j in range(n)))
        if not shuf:
            agg["shuffle_invariance_failures"] += 1
            stops.append({"stop": "SHUFFLE_INVARIANCE_FAILURE", "instance": i, "content_hash": chash})

        for r in (r1, r2):
            dists["wall_clock"].append(r.solve_seconds)
            dists["pivots"].append(r.pivots_phase_i + r.pivots_phase_ii)
            dists["core_dim"].append(r.core_dim)
            dists["num_bits"].append(r.max_num_bits)
            dists["den_bits"].append(r.max_den_bits)
            dists["rho_star_log10"].append(float(np.log10(float(r.rho_star))) if r.rho_star > 0
                                           else -99.0)
        dists["agreement_margin"].append(bound - dz)
        dists["objective_margin"].append(obound - df)

        rowrec.update({
            "exact_repair_status": "EXACT_REPAIR_OK",
            "rho_star": {PRIMARY: f"{r1.rho_star.numerator}/{r1.rho_star.denominator}",
                         FALLBACK: f"{r2.rho_star.numerator}/{r2.rho_star.denominator}"},
            "repaired_point_hash": {PRIMARY: vec_hash(r1.zhat), FALLBACK: vec_hash(r2.zhat)},
            "pivots": {PRIMARY: [r1.pivots_phase_i, r1.pivots_phase_ii],
                       FALLBACK: [r2.pivots_phase_i, r2.pivots_phase_ii]},
            "basis_dim": {PRIMARY: r1.basis_dim, FALLBACK: r2.basis_dim},
            "core_dim": {PRIMARY: r1.core_dim, FALLBACK: r2.core_dim},
            "max_bits": {PRIMARY: [r1.max_num_bits, r1.max_den_bits],
                         FALLBACK: [r2.max_num_bits, r2.max_den_bits]},
            "agreement_distance_certificate": {"pass": ok_a, "dz": dz, "bound": bound},
            "objective_agreement_certificate": {"pass": ok_o, "df": df, "bound": obound},
            "deterministic": det, "shuffle_invariant": shuf, "seconds": secs, "peak_mb": peak,
            "final_overlap_verdict": "PASS" if (ok_a and ok_o and det and shuf) else "FAIL",
        })
        records.append(rowrec)
        print(f"  [{k+1:>3}/{len(sample_b)}] {chash[:16]} OK rho*={float(r1.rho_star):.2e} "
              f"basis={r1.basis_dim} core={r1.core_dim} agree={'ok' if ok_a else 'FAIL'} "
              f"det={det} shuf={shuf} {secs:.1f}s {peak:.0f}MB", flush=True)

    secs_total = time.perf_counter() - t0
    processed = len([r for r in records if r.get("exact_repair_status")])

    print("\n=== Sample B aggregate (§8) ===")
    for k2, v in agg.items():
        print(f"  {k2:32} {v}")
    print("\n=== distributions (§8 — not only the maximum) ===")
    dist_out = {k: _dist(v) for k, v in dists.items()}
    for k2, dv in dist_out.items():
        if dv:
            print(f"  {k2:18} min {dv['min']:.3g}  p50 {dv['p50']:.3g}  p90 {dv['p90']:.3g}  "
                  f"p99 {dv['p99']:.3g}  max {dv['max']:.3g}")

    ok = (not stops
          and agg["successful_exact_repairs"] == len(sample_b)
          and agg["agreement_failures"] == 0 and agg["objective_agreement_failures"] == 0
          and agg["determinism_failures"] == 0 and agg["shuffle_invariance_failures"] == 0)
    print("\n" + "=" * 74)
    print("  SAMPLE B: " + ("PASS" if ok else "STOP FOR ADJUDICATION"))
    print("=" * 74)
    for s in stops[:10]:
        print(f"    {s['stop']}  instance={s.get('instance')}")

    doc = {
        "schema": "MR002_SampleB/v1",
        "authorization": "owner ruling 2026-07-14 §7-§10 (Sample B only; nothing beyond)",
        "scope_boundary": ("a successful Sample B establishes replication on a second disjoint "
                           "preregistered sample. It authorizes NOTHING further: not the full "
                           "population, not preflight, not development performance, not validation, "
                           "not sealed OOS, not an erratum."),
        "call_graph_binding": {
            "path": "registered selection -> frozen predicate -> canonical exact min-Linf repair "
                    "-> exact agreement certificates -> corrected directed rounding",
            "retired_R2_module_imported": False,
            "solver_path_hashes_match_c130149": True,
            "bound_module_sha256": bound,
        },
        "preregistration_checks": checks,
        "frozen_specification": {
            "cascade": [PRIMARY, FALLBACK],
            "predicate": "registered KKT LIMITS AND two-sided signed Lagrangian gap",
            "signed_gap_band": [-SIGNED_GAP_MAX, SIGNED_GAP_MAX],
            "max_interval_width": MAX_INTERVAL_WIDTH, "LIMITS": LIMITS,
            "repair": repair_manifest(), "resource_ceilings": ceilings(),
            "pivot_rule": "Bland's rule over canonical column identities",
            "serializer": "corrected directed (outward) binary64",
        },
        "corpus_hash": ch,
        "sample_b": sample_b,
        "sample_b_content_hashes": [fixture_hash(CORPUS[i]) for i in sample_b],
        "records": records, "aggregate": agg, "distributions": dist_out,
        "overlaps_processed": processed, "stops": stops, "wall_clock_seconds": secs_total,
        "provenance": {"commit": os.environ.get("MR002_COMMIT_SHA"),
                       "image": os.environ.get("MR002_IMAGE_DIGEST"),
                       "mounted_source_sha256": bound},
        "sample_b_pass": ok, "no_performance_computed": True,
        "validation_and_sealed_oos": "SEALED AND UNREAD",
    }
    blob = json.dumps(doc, indent=2, default=str)
    with open(f"{out_dir}/MR002_SampleB.json", "w", encoding="utf-8") as fh:
        fh.write(blob)
    print(f"\nSample B sha256 {hashlib.sha256(blob.encode()).hexdigest()}")
    print(f"wall-clock {secs_total:.0f}s")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
