"""MR-002 — FULL OVERLAP POPULATION repair run (owner ruling 2026-07-14 §7-§13).

Authorized after Sample A + Sample B-C1 replicated. This runs the registered exact-repair and
agreement-certificate path over the COMPLETE qualifying overlap population — every corpus row where
BOTH the primary (QUADPROG_SQRT) and the fallback (PIQP_P2) qualify — under the frozen implementation,
with an immutable population manifest, deterministic checkpoint/resume, per-record evidence,
population aggregates + distributions, and immediate stop-and-preserve.

FROZEN PATH (unchanged from Sample A / B-C1): QUADPROG_SQRT -> PIQP_P2, registered KKT gates,
two-sided signed Lagrangian gap, canonical exact rational min-Linf repair, exact Phase I + II, Bland
pivots, shared exact basis decomposition, full unreduced-system verification, corrected directed
rounding, registered agreement certificates. No R1/R2/R2-C1/HiGHS.

§7 MANIFEST. Before the first repair, a population manifest is built and bound: corpus identity =
the registered 3,895-instance hash; population-selection rule = the frozen overlap definition
(sorted(set(PRIMARY) & set(FALLBACK))); every expected record present exactly once BY CORPUS ROW;
duplicate rows are KEPT and reported as members of their canonical-content equivalence class (never
deleted/renumbered/substituted); source + config hashes == the declared baseline; validation/OOS
inaccessible. On a resume the re-derived manifest must match the checkpoint's bound manifest hash.

§9 CHECKPOINT/RESUME. The checkpoint is an append-only JSONL record stream, one line per completed
corpus row, each binding the manifest hash + a per-record hash and flushed+fsynced on write. A resume
continues from the first uncompleted registered record in the FROZEN index order; it never reruns
only favorable cases, skips a stopped case, changes order/code/config, or merges incompatible
manifests. A process interruption is not a gate failure if the record stream stays complete and
byte-verifiable. Aggregates are derived SOLELY from completed records.

§12 STOP. On the first population-manifest mismatch / source mismatch / missing-or-duplicated record /
exact-certificate failure / unexpected Phase-I infeasibility / unclassified result / non-finite
interval / directed-enclosure failure / determinism failure / shuffle failure / >600 s / >4000 pivots
/ >200,000 bits / memory breach: STOP and preserve the complete partial record. Do not exclude,
replace or rerun a failing case under altered conditions.

Performance NOT computed. Validation and sealed OOS SEALED AND UNREAD. Preflight STOPPED.
"""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import sys
import time
import tracemalloc
from collections import defaultdict
from datetime import date
from fractions import Fraction

import numpy as np

sys.path.insert(0, "/work/apps/backend")

from app.research.mr002.certificate import CertificateDefect  # noqa: E402
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
    capture,
    fixture_hash,
    try_solve,
)
from scripts.mr002_directed_rounding_correction import source_hashes  # noqa: E402
from scripts.mr002_solver_intersection import LIMITS, REGISTERED_CORPUS_HASH  # noqa: E402

OUT = os.environ.get("MR002_OUT", "/out")
CHECKPOINT = os.environ.get("MR002_CHECKPOINT", f"{OUT}/MR002_FullPopulation_checkpoint.jsonl")
POP_LIMIT = int(os.environ.get("MR002_POP_LIMIT", "0"))          # smoke only; 0 = full population
MANIFEST_C130149 = "/work/docs/implementation/evidence/mr_002/MR002_DirectedRounding_ImmutableRecord.json"

SOLVER_PATH = ("app/research/mr002/directed.py", "app/research/mr002/certificate.py",
               "app/research/mr002/joint_portfolio.py", "scripts/mr002_coverage_signed_gap.py",
               "scripts/mr002_solver_intersection.py")

# ---------------------------------------------------------------------------- AMENDMENT v1.0
# Countersigned 2026-07-16 after the row-2307 adjudication (disposition A) and the completed
# population exact-feasibility census (3,838 feasible / 1 infeasible / 0 unresolved).
# See docs/implementation/evidence/mr_002/MR002_FullPopulation_Amendment_v1.0.md
AMENDMENT_ID = "MR002_FullPopulation_Amendment_v1.0"
AMENDED_INFEASIBLE = "EXACTLY_INFEASIBLE_REGISTERED_MODEL"

# §2 — the SOLE authorized exactly-infeasible identity. BOTH must match: the index guards against
# substitution, the content hash against index drift. Anything else is a mandatory STOP.
COUNTERSIGNED_INFEASIBLE_INDEX = 2307
COUNTERSIGNED_INFEASIBLE_HASH = (
    "cfdc115e46f16226fafbe59b73890adca2f0c2f27b6f42c3ebebdce4d18ea30f"
)
# Bound evidence for the amendment's factual basis.
ADJUDICATION_ARTIFACT_SHA = "179d571d5c6b1db201fda235198c10aaff5623a348f3b31e263f711ad1a3cdef"
CENSUS_ARTIFACT_SHA = "2dd7a6c0f9dac24b2ae686a82550727091b6ce5c8ed8122b298992596f8ee1e3"
EXACTLY_FEASIBLE_POPULATION = 3838      # §4 — the repair PASS denominator
EXACTLY_INFEASIBLE_MODELS = 1
DISTINCT_MODELS = 3819


def is_countersigned_infeasible(i: int, content_hash: str) -> bool:
    """§2 — row 2307 ONLY, by index AND content hash together."""
    return i == COUNTERSIGNED_INFEASIBLE_INDEX and content_hash == COUNTERSIGNED_INFEASIBLE_HASH


def amendment_exact_path_binding() -> dict:
    """§3 — bind the exact evidentiary authority and this runner.

    The qualification manifest binds the SELECTION/floating path but not the exact repair authority:
    `build_manifest` keeps only `repair_manifest()["method"]` and DISCARDS the source hash that
    `repair_manifest()` computes. So the implementation that produced the exact evidence was
    unidentified, as was this runner. This block is an additive, countersigned COMPANION — the
    original manifest is preserved and never revised.
    """
    import platform
    import sysconfig

    import app.research.mr002.certificate as _cert
    import app.research.mr002.exact_repair as _er
    import app.research.mr002.exact_simplex as _es

    def _sha(path: str) -> str:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    root = "/work/apps/backend"
    files = {
        "scripts/mr002_full_population.py": f"{root}/scripts/mr002_full_population.py",
        "app/research/mr002/exact_repair.py": f"{root}/app/research/mr002/exact_repair.py",
        "app/research/mr002/exact_simplex.py": f"{root}/app/research/mr002/exact_simplex.py",
        "app/research/mr002/certificate.py": f"{root}/app/research/mr002/certificate.py",
    }
    return {
        "amendment_id": AMENDMENT_ID,
        "runner_commit_sha": os.environ.get("MR002_COMMIT_SHA"),
        "source_sha256": {k: _sha(v) for k, v in files.items()},
        # the hash build_manifest threw away
        "repair_manifest_source_sha256": repair_manifest().get("source_sha256"),
        "container_image_digest": os.environ.get("MR002_IMAGE_DIGEST"),
        "python_version": sys.version.split()[0],
        "python_abi": sysconfig.get_config_var("SOABI"),
        "platform": platform.platform(),
        # callable provenance: module PRESENT is not the same as function INVOKED
        "callable_provenance": {
            "certify_repair.__module__": certify_repair.__module__,
            "agreement.__module__": agreement.__module__,
            "objective_agreement.__module__": objective_agreement.__module__,
            "exact_repair.solve_lp is exact_simplex.solve_lp": _er.solve_lp is _es.solve_lp,
            "certificate.to_fraction is exact_repair.to_fraction": _cert.to_fraction
            is _er.to_fraction,
        },
        "bound_evidence": {
            "row_2307_adjudication_sha256": ADJUDICATION_ARTIFACT_SHA,
            "feasibility_census_sha256": CENSUS_ARTIFACT_SHA,
        },
    }


def vec_hash(v) -> str:
    h = hashlib.sha256(b"MR002|repaired-point|v1")
    for x in v:
        f = x if isinstance(x, Fraction) else as_fraction(x)
        h.update(f"{f.numerator}/{f.denominator};".encode())
    return h.hexdigest()


def record_hash(rec: dict) -> str:
    return hashlib.sha256(
        json.dumps({k: v for k, v in rec.items() if k != "record_sha256"},
                   sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def dist(xs: list[float]) -> dict:
    if not xs:
        return {}
    s = sorted(xs)

    def q(p):
        return s[min(len(s) - 1, int(p * (len(s) - 1) + 0.5))]
    return {"n": len(s), "min": s[0], "p50": q(0.50), "p90": q(0.90), "p99": q(0.99),
            "max": s[-1], "mean": statistics.fmean(s)}


def call_graph_ok(stops: list) -> bool:
    import inspect

    import app.research.mr002.exact_repair as er
    import app.research.mr002.exact_simplex as es
    ok = True
    for fn in (certify_repair, agreement, objective_agreement):
        if fn.__module__ != "app.research.mr002.exact_repair":
            stops.append({"stop": "CALL_GRAPH_NONCANONICAL_REPAIR", "function": fn.__name__})
            ok = False
    if er.solve_lp is not es.solve_lp:
        stops.append({"stop": "REPAIR_NOT_ON_CANONICAL_SIMPLEX"})
        ok = False
    if "app.research.mr002.repair" in inspect.getsource(er):
        stops.append({"stop": "CANONICAL_REPAIR_DEPENDS_ON_RETIRED_MODULE"})
        ok = False
    return ok


def build_manifest(qualifying: list[int], corpus_hash: str, dup_classes: dict) -> dict:
    bound = source_hashes()
    with open(MANIFEST_C130149, encoding="utf-8") as fh:
        c130149 = json.load(fh)["source_module_sha256"]
    solver_drift = {k for k in SOLVER_PATH if bound.get(k) != c130149.get(k)}
    return {
        "schema": "MR002_PopulationManifest/v1",
        "corpus_hash": corpus_hash,
        "corpus_matches_registered": corpus_hash == REGISTERED_CORPUS_HASH,
        "population_selection_rule": "sorted(set(PRIMARY_qualifies) & set(FALLBACK_qualifies)) by corpus index",
        "population_indices": qualifying,
        "population_count": len(qualifying),
        "each_row_once": len(qualifying) == len(set(qualifying)),
        "duplicate_equivalence_classes_in_population": {
            h: idxs for h, idxs in dup_classes.items() if len(idxs) > 1},
        "duplicates_kept_not_removed": True,
        "solver_path_hashes_match_c130149": not solver_drift,
        "source_sha256": bound,
        "config": {"cascade": [PRIMARY, FALLBACK], "LIMITS": LIMITS,
                   "repair": repair_manifest()["method"], "ceilings": ceilings()},
        "validation_and_sealed_oos": "SEALED AND UNREAD (not opened by this run)",
    }


def read_checkpoint(manifest_hash: str, stops: list) -> dict[int, dict]:
    """Return {corpus_index: record} for completed rows, verifying each binds THIS manifest hash and
    its own record hash. A trailing partial line (interrupted mid-write) is skipped."""
    done: dict[int, dict] = {}
    if not os.path.exists(CHECKPOINT):
        return done
    with open(CHECKPOINT, encoding="utf-8") as fh:
        lines = fh.readlines()
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue                                    # trailing partial line — ignore, will redo
        if rec.get("manifest_sha256") != manifest_hash:
            stops.append({"stop": "POPULATION_MANIFEST_MISMATCH", "corpus_index": rec.get("i")})
            raise SystemExit(_stop(stops, "checkpoint bound a DIFFERENT manifest"))
        want = rec.get("record_sha256")
        if want != record_hash(rec):
            stops.append({"stop": "CHECKPOINT_RECORD_HASH_MISMATCH", "corpus_index": rec.get("i")})
            raise SystemExit(_stop(stops, "a checkpoint record failed its own hash"))
        done[rec["i"]] = rec
    return done


def _stop(stops: list, msg: str) -> int:
    print(f"STOP: {msg}", file=sys.stderr)
    for s in stops[-5:]:
        print(f"  {s}", file=sys.stderr)
    return 1


def main() -> int:  # noqa: PLR0912, PLR0915
    stops: list[dict] = []
    if not call_graph_ok(stops):
        return _stop(stops, "call graph is not canonical")
    print("[ok] §4 call graph canonical; solver-path hashes checked against c130149\n")

    import app.research.mr002.joint_portfolio as jp
    jp._solve_qp = capture
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    for cfg in ("A", "B", "C"):
        run_config(days, CONFIGS[cfg])

    corpus_hash = hashlib.sha256("|".join(i["hash"] for i in CORPUS).encode()).hexdigest()
    print(f"corpus {len(CORPUS)}  hash {corpus_hash}")
    if corpus_hash != REGISTERED_CORPUS_HASH:
        return _stop(stops, "corpus hash mismatch")
    print("[ok] corpus reproduced EXACTLY\n")

    # ---- cascade -> the qualifying overlap population (by corpus index) -------------------------
    print("resolving the cascade over all 3,895 rows ...")
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

    qualifying = sorted(set(zs[PRIMARY]) & set(zs[FALLBACK]))   # THE FROZEN OVERLAP DEFINITION
    if POP_LIMIT:
        qualifying = qualifying[:POP_LIMIT]
        print(f"\n⚠ SMOKE — {len(qualifying)} of the full population. NOT EVIDENCE.")

    dup_classes: dict[str, list[int]] = defaultdict(list)
    for i in qualifying:
        dup_classes[fixture_hash(CORPUS[i])].append(i)

    manifest = build_manifest(qualifying, corpus_hash, dup_classes)
    manifest_blob = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str)
    manifest_hash = hashlib.sha256(manifest_blob.encode()).hexdigest()
    with open(f"{OUT}/MR002_Population_Manifest.json", "w", encoding="utf-8") as fh:
        json.dump({**manifest, "manifest_sha256": manifest_hash}, fh, indent=2, default=str)
    if not (manifest["corpus_matches_registered"] and manifest["each_row_once"]
            and manifest["solver_path_hashes_match_c130149"]):
        stops.append({"stop": "POPULATION_MANIFEST_INVALID"})
        return _stop(stops, "population manifest failed its own preconditions")
    print(f"\n[ok] §7 population manifest: {len(qualifying)} rows, each once, "
          f"{sum(1 for v in dup_classes.values() if len(v) > 1)} duplicate classes kept; "
          f"manifest {manifest_hash[:16]}\n")

    # ---- §9 resume from the checkpoint ---------------------------------------------------------
    done = read_checkpoint(manifest_hash, stops)
    todo = [i for i in qualifying if i not in done]
    print(f"--- full-population repair: {len(done)} done, {len(todo)} to go "
          f"(checkpoint {CHECKPOINT}) ---")
    print(f"    method {repair_manifest()['method']}  ceiling {ceilings()['max_seconds_per_repair']}s\n")

    ck = open(CHECKPOINT, "a", encoding="utf-8")  # noqa: SIM115 — long-lived append handle
    rng_seed = 0
    t0 = time.perf_counter()
    for k, i in enumerate(todo):
        inst = CORPUS[i]
        rec = (inst["t"], inst["A_ub"], inst["b_ub"], inst["A_eq"], inst["b_eq"], inst["upper"])
        chash = fixture_hash(inst)
        n = len(inst["t"])
        row: dict = {
            "i": i, "content_hash": chash,
            "duplicate_class": dup_classes[chash] if len(dup_classes[chash]) > 1 else None,
            "n": n, "m_ub": int(np.asarray(inst["A_ub"]).shape[0]),
            "solvers": {PRIMARY: status[PRIMARY][i], FALLBACK: status[FALLBACK][i]},
            "signed_gap": {name: {"interval": [certs[name][i].gamma_lower, certs[name][i].gamma_upper],
                                  "qualifies": certs[name][i].qualifies} for name in (PRIMARY, FALLBACK)},
            "manifest_sha256": manifest_hash,
        }
        tracemalloc.start()
        ts = time.perf_counter()
        try:
            r1 = certify_repair(zs[PRIMARY][i], certs[PRIMARY][i], *rec)
            r2 = certify_repair(zs[FALLBACK][i], certs[FALLBACK][i], *rec)
        except RepairUnavailable as e:
            peak = tracemalloc.get_traced_memory()[1] / 1e6
            tracemalloc.stop()
            reason = str(e).split(":")[0]
            if "PHASE_I_POSITIVE" in reason and is_countersigned_infeasible(i, chash):
                # AMENDMENT v1.0 §2 — the ONE countersigned exactly-infeasible registered model.
                # Terminal and recorded; not a pass, not a repair failure, not a defect.
                row.update({"exact_repair_status": AMENDED_INFEASIBLE, "detail": str(e)[:200],
                            "amendment_id": AMENDMENT_ID, "repair_status": "NOT_APPLICABLE",
                            "agreement_certificates": "NOT_APPLICABLE",
                            "population_inclusion": "INCLUDED",
                            "feasible_population_inclusion": "EXCLUDED",
                            "reason": "verified exact Farkas certificate"})
                _flush_row(ck, row)
                continue
            if "RESOURCE_LIMIT" in reason or "PHASE_I_POSITIVE" in reason:
                # §12 stop. For a Phase-I positive OUTSIDE the row-2307 identity this is mandatory
                # and NOT recordable under the amendment (§2): the census certified every other
                # registered row FEASIBLE with a verified primal witness, so a Farkas certificate
                # here would contradict it. Two contradicting verified certificates mean a broken
                # verifier/constructor, not a model property — recording it would launder a harness
                # failure into a model finding. A candidate certificate does NOT rescue it.
                if "PHASE_I_POSITIVE" in reason:
                    reason = "PHASE_I_POSITIVE_CONTRADICTS_FEASIBILITY_CENSUS"
                row.update({"exact_repair_status": reason, "detail": str(e)[:200]})
                stops.append({"stop": reason, "corpus_index": i, "content_hash": chash})
                _flush_row(ck, row)
                return _stop(stops, f"{reason} on qualifying row {i} — preserved, halting")
            row.update({"exact_repair_status": reason, "detail": str(e)[:200], "seconds":
                        time.perf_counter() - ts, "peak_mb": peak})
            stops.append({"stop": reason, "corpus_index": i})
            _flush_row(ck, row)
            return _stop(stops, f"{reason} on row {i}")
        except CertificateDefect as e:
            tracemalloc.stop()
            row.update({"exact_repair_status": "CERTIFICATE_DEFECT", "detail": str(e)[:200]})
            stops.append({"stop": "EXACT_CERTIFICATE_FAILURE", "corpus_index": i})
            _flush_row(ck, row)
            return _stop(stops, f"certificate defect on row {i} — preserved, halting")
        peak = tracemalloc.get_traced_memory()[1] / 1e6
        tracemalloc.stop()
        secs = time.perf_counter() - ts

        ok_a, dz, bnd = agreement(r1, r2, zs[PRIMARY][i], zs[FALLBACK][i])
        ok_o, df, obnd = objective_agreement(r1, r2, certs[PRIMARY][i], certs[FALLBACK][i])
        r1b = certify_repair(zs[PRIMARY][i], certs[PRIMARY][i], *rec)
        det = (r1b.zhat == r1.zhat and r1b.rho_star == r1.rho_star)
        rng = np.random.default_rng(rng_seed + i)
        p = rng.permutation(n)
        rp = rng.permutation(rec[1].shape[0])
        r1s = certify_repair(zs[PRIMARY][i][p], certs[PRIMARY][i], rec[0][p],
                             rec[1][np.ix_(rp, p)], rec[2][rp], rec[3][:, p], rec[4], rec[5][p])
        shuf = (r1s.rho_star == r1.rho_star and all(r1s.zhat[j] == r1.zhat[p[j]] for j in range(n)))

        for tag, r in ((PRIMARY, r1), (FALLBACK, r2)):
            row[f"repair_{tag}"] = {
                "rho_star": f"{r.rho_star.numerator}/{r.rho_star.denominator}",
                "rho_star_is_zero": r.rho_star == 0,
                "repaired_point_hash": vec_hash(r.zhat),
                "pivots": [r.pivots_phase_i, r.pivots_phase_ii],
                "basis_dim": r.basis_dim, "core_dim": r.core_dim,
                "max_bits": [r.max_num_bits, r.max_den_bits], "solve_seconds": r.solve_seconds,
            }
        verdict = "PASS" if (ok_a and ok_o and det and shuf) else "FAIL"
        row.update({
            "exact_repair_status": "EXACT_REPAIR_OK",
            "agreement": {"pass": ok_a, "dz": dz, "bound": bnd, "margin": bnd - dz},
            "objective_agreement": {"pass": ok_o, "df": df, "bound": obnd, "margin": obnd - df},
            "deterministic": det, "shuffle_invariant": shuf,
            "seconds": secs, "peak_mb": peak, "final_certified_verdict": verdict,
        })
        _flush_row(ck, row)

        if verdict != "PASS":
            which = ("determinism" if not det else "shuffle" if not shuf
                     else "agreement" if not ok_a else "objective")
            stops.append({"stop": f"{which.upper()}_FAILURE", "corpus_index": i})
            return _stop(stops, f"{which} failure on row {i} — preserved, halting")

        if (k + 1) % 50 == 0 or secs > 30:
            el = time.perf_counter() - t0
            rate = (k + 1) / el
            eta = (len(todo) - k - 1) / rate if rate > 0 else 0
            print(f"  [{len(done)+k+1}/{len(qualifying)}] row {i} {chash[:12]} "
                  f"rho*={float(r1.rho_star):.1e} basis={r1.basis_dim} core={r1.core_dim} "
                  f"{secs:.1f}s  | {el/60:.0f}m elapsed, ETA {eta/60:.0f}m", flush=True)
    ck.close()

    # ---- §11 aggregates + distributions, from the COMPLETED record stream ----------------------
    all_done = read_checkpoint(manifest_hash, stops)
    return finalize(qualifying, all_done, manifest_hash, corpus_hash, dup_classes,
                    time.perf_counter() - t0)


def _flush_row(ck, row: dict) -> None:
    row["record_sha256"] = record_hash(row)
    ck.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
    ck.flush()
    os.fsync(ck.fileno())


def finalize(qualifying, done, manifest_hash, corpus_hash, dup_classes, secs) -> int:
    recs = [done[i] for i in qualifying if i in done]
    ok = [r for r in recs if r.get("exact_repair_status") == "EXACT_REPAIR_OK"]

    # AMENDMENT §2/§4. Row 2307's ORIGINAL record is preserved byte-identical and is NOT rewritten;
    # it is reclassified here, at aggregate time, from the record the frozen run wrote. `ok` already
    # excludes it (its status is not EXACT_REPAIR_OK), so every distribution and pass-rate below —
    # agreement, objective agreement, runtime, pivots, determinism, shuffle — is computed over `ok`
    # and therefore excludes it by construction, as §4 requires.
    def _is_amended_infeasible(r: dict) -> bool:
        if not is_countersigned_infeasible(r.get("i"), r.get("content_hash", "")):
            return False
        st = str(r.get("exact_repair_status"))
        # accept BOTH the frozen run's original wording and the amended terminal, so the preserved
        # 2,269-record checkpoint reclassifies without being rewritten
        return "PHASE_I_POSITIVE" in st or st == AMENDED_INFEASIBLE

    infeasible_recs = [r for r in recs if _is_amended_infeasible(r)]
    feasible_population = [i for i in qualifying
                           if not is_countersigned_infeasible(
                               i, done.get(i, {}).get("content_hash", ""))]

    def rho_zero(r):
        return any(r.get(f"repair_{t}", {}).get("rho_star_is_zero") for t in (PRIMARY, FALLBACK))

    agg = {
        # §4 — TWO DENOMINATORS, never collapsed into one success rate.
        "expected_records": len(qualifying),                       # 3839 floating-qualified
        "exactly_feasible_repair_population": len(feasible_population),   # 3838 = PASS denominator
        "exactly_infeasible_registered_models": len(infeasible_recs),     # 1 (row 2307)
        "evaluated_records": len(recs),
        "successful_exact_repairs": len(ok),
        "rho_star_zero_count": sum(1 for r in ok if rho_zero(r)),
        "rho_star_positive_count": sum(1 for r in ok if not rho_zero(r)),
        # AMENDMENT: the amended terminal is a RECOGNISED outcome, not an invalid run. The
        # checkpoint currently carries the frozen run's original `EXACT_PHASE_I_POSITIVE` wording,
        # but the amended path WRITES `EXACTLY_INFEASIBLE_REGISTERED_MODEL` — so a later resume
        # would have re-read it, scored it `invalid_runs=1`, and made `passed` unreachable forever.
        # Both spellings must be excluded here; `_is_amended_infeasible` is the single source of
        # truth for "is this the countersigned row 2307".
        "invalid_runs": sum(1 for r in recs
                            if r.get("exact_repair_status") != "EXACT_REPAIR_OK"
                            and not _is_amended_infeasible(r)),
        "resource_ceiling_breaches": sum(1 for r in recs if "RESOURCE_LIMIT" in str(r.get("exact_repair_status"))),
        "agreement_passes": sum(1 for r in ok if r["agreement"]["pass"]),
        "agreement_failures": sum(1 for r in ok if not r["agreement"]["pass"]),
        "objective_agreement_passes": sum(1 for r in ok if r["objective_agreement"]["pass"]),
        "objective_agreement_failures": sum(1 for r in ok if not r["objective_agreement"]["pass"]),
        "determinism_failures": sum(1 for r in ok if not r["deterministic"]),
        "shuffle_invariance_failures": sum(1 for r in ok if not r["shuffle_invariant"]),
        "unclassified_records": sum(1 for r in recs if r.get("exact_repair_status") is None),
    }
    # distributions, and by problem size / core dimension
    wc = [r["seconds"] for r in ok]
    piv = [sum(r[f"repair_{PRIMARY}"]["pivots"]) for r in ok]
    core = [max(r[f"repair_{PRIMARY}"]["core_dim"], r[f"repair_{FALLBACK}"]["core_dim"]) for r in ok]
    numb = [max(r[f"repair_{PRIMARY}"]["max_bits"][0], r[f"repair_{FALLBACK}"]["max_bits"][0]) for r in ok]
    denb = [max(r[f"repair_{PRIMARY}"]["max_bits"][1], r[f"repair_{FALLBACK}"]["max_bits"][1]) for r in ok]
    am = [r["agreement"]["margin"] for r in ok]
    om = [r["objective_agreement"]["margin"] for r in ok]

    by_n: dict = defaultdict(list)
    by_core: dict = defaultdict(list)
    for r in ok:
        by_n[r["n"]].append(r["seconds"])
        by_core[max(r[f"repair_{PRIMARY}"]["core_dim"], r[f"repair_{FALLBACK}"]["core_dim"])].append(r["seconds"])

    complete = (agg["evaluated_records"] == agg["expected_records"]
                and agg["unclassified_records"] == 0)
    # §4 — the PASS denominator is the EXACTLY FEASIBLE population (3,838), not the floating-
    # qualified population (3,839). Row 2307 is neither a success nor a failure: a repair cannot
    # exist for it, because its feasible set is empty. Comparing against 3,839 would make PASS
    # unreachable and would misattribute a property of the MODEL to the METHOD.
    passed = (complete
              and agg["successful_exact_repairs"] == agg["exactly_feasible_repair_population"]
              and agg["exactly_infeasible_registered_models"] == EXACTLY_INFEASIBLE_MODELS
              and agg["agreement_failures"] == 0 and agg["objective_agreement_failures"] == 0
              and agg["determinism_failures"] == 0 and agg["shuffle_invariance_failures"] == 0
              and agg["resource_ceiling_breaches"] == 0 and agg["invalid_runs"] == 0)
    rates = {
        "exact_repair_success_rate": (
            f"{agg['successful_exact_repairs']}/{agg['exactly_feasible_repair_population']}"),
        "floating_predicate_exact_feasibility_admission_rate":
            f"{EXACTLY_FEASIBLE_POPULATION}/{len(qualifying)}",
        "floating_predicate_exact_infeasibility_false_admission_rate":
            f"{EXACTLY_INFEASIBLE_MODELS}/{len(qualifying)}",
        "false_admission_rate_by_distinct_model":
            f"{EXACTLY_INFEASIBLE_MODELS}/{DISTINCT_MODELS}",
    }

    print("\n=== §11 population aggregate ===")
    for k, v in agg.items():
        print(f"  {k:34} {v}")
    print("\n=== distributions ===")
    for name, xs in (("wall_clock", wc), ("pivots", piv), ("core_dim", core),
                     ("num_bits", numb), ("den_bits", denb), ("agree_margin", am),
                     ("obj_margin", om)):
        d = dist([float(x) for x in xs])
        if d:
            print(f"  {name:14} min {d['min']:.3g} p50 {d['p50']:.3g} p90 {d['p90']:.3g} "
                  f"p99 {d['p99']:.3g} max {d['max']:.3g}")

    # §5 — NEVER an unqualified "FULL POPULATION: PASS". This run completed under a countersigned
    # amendment after the original frozen run correctly STOPPED at row 2307, and its PASS
    # denominator is 3,838 (exactly feasible), not the 3,839 the original protocol froze. A reader
    # who saw a bare PASS would reasonably assume the original denominator and the original
    # protocol. The banner travels with the result; a detached amendment doc is not enough.
    print("\n" + "=" * 74)
    print("  FULL POPULATION — " + ("AMENDED PASS" if passed else "INCOMPLETE / STOP"))
    print("=" * 74)
    print(f"  Completed under {AMENDMENT_ID} after the original frozen run correctly stopped at")
    print(f"  row {COUNTERSIGNED_INFEASIBLE_INDEX}. Repair PASS denominator: "
          f"{agg['exactly_feasible_repair_population']:,} exactly feasible rows "
          f"(NOT the {agg['expected_records']:,} floating-qualified).")
    print(f"  Row {COUNTERSIGNED_INFEASIBLE_INDEX} is separately recorded as a certified exactly")
    print("  infeasible registered model — counted as NEITHER a repair success nor a failure.")
    print("\n  --- the two denominators (§4) ---")
    for k, v in rates.items():
        print(f"  {k:58} {v}")
    print("=" * 74)

    doc = {
        "schema": "MR002_FullPopulation/v1.1",
        # §5 — the amendment banner travels INSIDE the artifact. A future reader must not be able
        # to mistake this result for the originally frozen protocol/denominator.
        "protocol_status": "AMENDED_AFTER_AUTHORIZED_STOP",
        "amendment_id": AMENDMENT_ID,
        "amendment_reason": "Certified exact infeasibility of registered row 2307",
        "amendment_doc": ("docs/implementation/evidence/mr_002/"
                          "MR002_FullPopulation_Amendment_v1.0.md"),
        "original_stop_remains_valid": (
            "The frozen protocol stopped CORRECTLY at row 2307: certified exact infeasibility was "
            "not an anticipated terminal category. This amendment does not retroactively remove or "
            "redefine that STOP, and row 2307's original checkpoint record is preserved "
            "byte-identical (never rewritten; reclassified only at aggregate time)."),
        "denominator_change": {
            "original_expected_records": len(qualifying),
            "exactly_feasible_repair_population": len(feasible_population),
            "exactly_infeasible_registered_models": len(infeasible_recs),
            "note": ("the repair PASS denominator is the EXACTLY FEASIBLE population; row 2307 is "
                     "counted as NEITHER a repair success nor a repair failure — no repair exists "
                     "for it because its feasible set is empty"),
        },
        "rates": rates,
        "row_2307_disposition": {
            "index": COUNTERSIGNED_INFEASIBLE_INDEX,
            "content_hash": COUNTERSIGNED_INFEASIBLE_HASH,
            "status": AMENDED_INFEASIBLE,
            "repair_status": "NOT_APPLICABLE",
            "agreement_certificates": "NOT_APPLICABLE",
            "population_inclusion": "INCLUDED",
            "feasible_population_inclusion": "EXCLUDED",
            "reason": "verified exact Farkas certificate (M'y <= 0 on every column, h'y > 0)",
            "excluded_from": ["agreement", "objective_agreement", "wall_clock", "pivots",
                              "determinism", "shuffle_invariance"],
        },
        "amendment_exact_path_binding": amendment_exact_path_binding(),
        "predicate_conclusion": (
            "The registered floating-point qualification predicate is NOT an exact-feasibility "
            "test. It admitted one certified exactly infeasible binary64 model among 3,839 "
            "qualifying overlaps. The observed incidence is contained but nonzero. Exact "
            "feasibility must therefore be established by the exact evidentiary path, not inferred "
            "from floating KKT and signed-gap qualification. The predicate is NOT invalid in "
            "general — it remains useful as a solver-overlap selection rule; what is disproved is "
            "its SUFFICIENCY as exact-feasibility evidence."),
        "authorization": "owner ruling 2026-07-14 §7-§13 + countersigned amendment 2026-07-16",
        "scope_boundary": ("a full-population pass authorizes only submission of its evidence for "
                           "adjudication — NOT preflight, development performance, validation, sealed "
                           "OOS, economic conclusions, erratum, or production registration"),
        "corpus_hash": corpus_hash, "manifest_sha256": manifest_hash,
        "aggregate": agg,
        "distributions": {n: dist([float(x) for x in xs]) for n, xs in
                          (("wall_clock", wc), ("pivots", piv), ("core_dim", core),
                           ("num_bits", numb), ("den_bits", denb), ("agree_margin", am),
                           ("obj_margin", om))},
        "wall_clock_by_problem_size": {str(k): dist(v) for k, v in sorted(by_n.items())},
        "wall_clock_by_core_dim": {str(k): dist(v) for k, v in sorted(by_core.items())},
        "duplicate_classes_in_population": {h: idxs for h, idxs in dup_classes.items() if len(idxs) > 1},
        "checkpoint": CHECKPOINT, "repair_seconds": secs,
        "provenance": {"commit": os.environ.get("MR002_COMMIT_SHA"),
                       "image": os.environ.get("MR002_IMAGE_DIGEST"),
                       "source_sha256": source_hashes()},
        "full_population_pass": passed, "complete": complete,
        "no_performance_computed": True, "validation_and_sealed_oos": "SEALED AND UNREAD",
    }
    blob = json.dumps(doc, indent=2, default=str)
    with open(f"{OUT}/MR002_FullPopulation.json", "w", encoding="utf-8") as fh:
        fh.write(blob)
    print(f"\nfull-population sha256 {hashlib.sha256(blob.encode()).hexdigest()}")
    print(f"repair wall-clock {secs/3600:.1f}h")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
