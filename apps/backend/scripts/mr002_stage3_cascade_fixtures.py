"""MR-002 Stage-3 — IN-IMAGE realism harness for the finalized cascade (review findings 18-21).

Companion to `tests/research/test_mr002_stage3_cascade_dispA.py`. Those fixtures validate the §7
decision-table CONTROL FLOW in isolation (they run without the numerical stack). THIS harness binds the
real frozen implementations — `QUADPROG_SQRT` (primary), `PIQP_P2` (fallback) and the single registered
certifier (`canonical_qualify`) — and exercises the load-bearing paths on tiny, hand-solvable problems.
It NEVER touches the registered corpus, the frozen dataset, or any population-selection loop.

★ This harness is a PRE-EXECUTION GATE (finding 18): because it uses only tiny hand-built problems, it
can and MUST run inside the pinned image and PASS *before* the execution countersignature. Its PASS
artifact (`MR002_Stage3_CascadeRealismHarness.json`) is part of the execution package. Deferring the
first real primary/fallback/certifier integration to the authorized run would leave the countersignature
signing untested numerical wiring.

WHAT IT DOES / DOES NOT EXERCISE (finding 19 — the earlier "producibility of each enum" claim was too
broad and is withdrawn). It exercises, against the REAL numerics on tiny problems:
  * PRIMARY_QUALIFIED            — real QUADPROG_SQRT + real certifier accept a well-posed QP;
  * FALLBACK_QUALIFIED          — real PIQP_P2 + real certifier resolve the rescue path (the primary
                                  raise is injected as the registered ValueError, so the FALLBACK
                                  numerics are real);
  * CERTIFICATE_NONQUALIFICATION — the real certifier REJECTS a deliberately suboptimal candidate.
It does NOT synthesize, and does not claim to: the real registered QUADPROG_SQRT `ValueError` (that
false-infeasibility is a property of specific corpus rows — established admissibly by the §6
characterization corpus, not reproducible on a tiny problem), a real UNRESOLVED_NUMERICAL_FAILURE, or a
real certifier-exception INTEGRITY_DEFECT. Those are covered by the §6 corpus evidence and the
decision-table fixtures.

It binds and reports the full runtime (finding 21) and FAILS if it cannot persist its artifact
(finding 20).

    docker run --rm --network none --read-only --tmpfs /tmp \\
      -e OPENBLAS_CORETYPE=HASWELL -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \\
      -v <repo>:/work:ro -v <fresh-out>:/out \\
      mr002-research@sha256:<full-digest> \\
      python /work/apps/backend/scripts/mr002_stage3_cascade_fixtures.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

import numpy as np

sys.path.insert(0, "/work/apps/backend")

from app.research.mr002 import stage3_cascade as sc  # noqa: E402


def _rec(t, A_ub, b_ub, A_eq, b_eq, upper):
    return (np.asarray(t, float), np.asarray(A_ub, float), np.asarray(b_ub, float),
            np.asarray(A_eq, float), np.asarray(b_eq, float), np.asarray(upper, float))


def hand_solvable_problems() -> list[tuple[str, tuple]]:
    """Registered-form problems with a known active optimum (cf. mr002_piqp.verify_signs)."""
    return [
        ("active_inequality",
         _rec([0.008, 0.008], [[1.0, 1.0]], [0.01], np.zeros((0, 2)), np.zeros(0), [0.02, 0.02])),
        ("active_equality",
         _rec([0.008, 0.008], np.zeros((0, 2)), np.zeros(0), [[1.0, 1.0]], [0.01], [0.02, 0.02])),
        ("active_upper_bound",
         _rec([0.02], np.zeros((0, 1)), np.zeros(0), np.zeros((0, 1)), np.zeros(0), [0.01])),
    ]


def _rec_hash(rec) -> str:
    h = hashlib.sha256(b"MR002|stage3|realism|rec")
    for a in rec:
        arr = np.ascontiguousarray(np.asarray(a, np.float64))
        h.update(str(arr.shape).encode())
        h.update(arr.tobytes())
    return h.hexdigest()


def _out_hash(o: sc.Outcome, rec) -> str:
    """Hash the COMPLETE numerical evidence (finding 25), not just the disposition/codes — two
    numerically different accepted solutions must produce different hashes."""
    ev = sc.numerical_evidence(o, rec)
    return hashlib.sha256(json.dumps(ev, sort_keys=True, default=str).encode()).hexdigest()


def run_cases() -> list[dict]:
    results: list[dict] = []

    # 1) PRIMARY_QUALIFIED — real primary + real certifier.
    for name, rec in hand_solvable_problems():
        o = sc.resolve_instance(rec)
        results.append({"case": f"primary_qualified/{name}", "expected": sc.PRIMARY_QUALIFIED,
                        "pass": o.disposition == sc.PRIMARY_QUALIFIED and not o.fallback_invoked,
                        "rec_sha256": _rec_hash(rec), "outcome_sha256": _out_hash(o, rec), **o.summary()})

    # 2) FALLBACK_QUALIFIED — real PIQP_P2 + real certifier on the rescue path.
    def _raise_registered(*_a):
        raise ValueError("constraints are inconsistent, no solution")

    for name, rec in hand_solvable_problems():
        o = sc.resolve(rec, primary=_raise_registered, fallback=sc._default_fallback,
                       certify_fn=sc._default_certifier)
        results.append({"case": f"fallback_qualified/{name}", "expected": sc.FALLBACK_QUALIFIED,
                        "pass": o.disposition == sc.FALLBACK_QUALIFIED and o.fallback_invoked
                        and o.accepted_by == sc.FALLBACK_SOLVER_ID,
                        "rec_sha256": _rec_hash(rec), "outcome_sha256": _out_hash(o, rec), **o.summary()})

    # 3) CERTIFICATE_NONQUALIFICATION — the REAL certifier REJECTS a deliberately wrong candidate.
    #    NOTE (finding 26): the origin is not "feasible but suboptimal" for every problem — for the
    #    active-equality problem it VIOLATES z1+z2=0.01, i.e. it is primal-INFEASIBLE. Either way the
    #    real certifier returns predicate-false; the claim under test is only that the real certifier
    #    rejects the candidate → primary enum CERTIFICATE_NONQUALIFICATION. The candidate kind is
    #    labelled per problem so the artifact does not misstate feasibility.
    def _bad_candidate_primary(t, A_ub, b_ub, A_eq, b_eq, upper):
        n = len(t)
        lam_len = A_eq.shape[0] + A_ub.shape[0] + 2 * n
        return np.zeros(n), np.zeros(lam_len)                 # origin, zero multipliers

    for name, rec in hand_solvable_problems():
        kind = "primal_infeasible_origin" if rec[3].shape[0] else "feasible_but_suboptimal_origin"
        o = sc.resolve(rec, primary=_bad_candidate_primary, fallback=sc._default_fallback,
                       certify_fn=sc._default_certifier)
        # ★ this is a CERTIFIER-CLASSIFICATION test, not a complete cascade-realism case (cycle-3
        # finding 25): the claim is only that the real certifier classifies the bad candidate as
        # predicate-false (primary CERTIFICATE_NONQUALIFICATION). The subsequent real-fallback
        # disposition is RECORDED for completeness but is not the pass criterion.
        results.append({"case": f"certifier_classification/{name}",
                        "candidate_kind": kind,
                        "claim": "primary enum only; cascade disposition recorded, not asserted",
                        "expected_primary_enum": sc.CERTIFICATE_NONQUALIFICATION,
                        "pass": o.primary.enum == sc.CERTIFICATE_NONQUALIFICATION,
                        "rec_sha256": _rec_hash(rec), "outcome_sha256": _out_hash(o, rec), **o.summary()})

    return results


def runtime_block() -> dict:
    """Bind and report the full runtime (finding 21)."""
    try:
        from scripts.mr002_stage3_preflight import gather_env
        env = gather_env("/work")
        return {
            "git_commit": env.git_commit, "git_tree": env.git_tree,
            "working_tree_clean": env.working_tree_clean,
            "image_digest": env.image_digest, "oci_config_digest": env.oci_config_digest,
            "python_version": env.python_version, "python_abi": env.python_abi,
            "package_versions": env.package_versions,
            "cpu_flags_available": env.cpu_flags_available,
            "avx2": "avx2" in env.cpu_flags, "avx512f": "avx512f" in env.cpu_flags,
            "env_vars": env.env_vars,
            "fingerprints": env.fingerprints,
            "cascade_module_imports": env.live_config.get("cascade_module_imports"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"runtime_error": str(exc)[:200]}


def _preflight_gate() -> tuple[bool, dict]:
    """A valid harness PASS requires a FULL preflight PASS against the countersigned pins (cycle-3
    finding 6) — not merely a non-None runtime block. The pins + static-manifest artifacts and their
    hashes are supplied by the launcher; if absent, the harness CANNOT pass."""
    pins_path = os.environ.get("MR002_EXPECTED_PINS")
    pins_sha = os.environ.get("MR002_EXPECTED_PINS_SHA256")
    man_path = os.environ.get("MR002_SOURCE_MANIFEST")
    man_sha = os.environ.get("MR002_SOURCE_MANIFEST_SHA256")
    if not all((pins_path, pins_sha, man_path, man_sha)):
        return False, {"error": "PINS_OR_MANIFEST_ABSENT — harness cannot PASS without the "
                                "countersigned expected-pins + static source manifest"}
    try:
        from scripts.mr002_stage3_population_runner import (
            load_expected_pins,
            load_static_manifest,
        )
        from scripts.mr002_stage3_preflight import evaluate, gather_env
        from scripts.mr002_stage3_source_manifest import verify_source
        pins = load_expected_pins(pins_path, pins_sha)
        manifest = load_static_manifest(man_path, man_sha)
        rep = evaluate(gather_env("/work"), pins, verify_source(manifest, "/work"))
        return rep.passed, rep.summary()
    except Exception as exc:  # noqa: BLE001 — any gate fault fails the harness, never skips it
        return False, {"error": f"{type(exc).__name__}:{str(exc)[:200]}"}


def main() -> int:
    # ★ cycle-4 finding 1 (highest priority): preflight runs FIRST. The real QUADPROG/PIQP/certifier
    # are numerical executions — none may run before provenance/image/package/manifest/fingerprint
    # checks pass. On failure a FAIL artifact is persisted and NO case is executed.
    preflight_ok, preflight_report = _preflight_gate()
    runtime = runtime_block()   # cycle-5 finding 16 note: displayed runtime is a fresh snapshot;
    # the gate's own observed env is inside preflight_report — both are serialized.
    if not preflight_ok:
        # cycle-5 findings 1, 17: the FAIL artifact follows the IDENTICAL byte-binding protocol as
        # the PASS artifact; a persistence failure is loud, tries a sidecar, and returns distinctly.
        doc = {"record_type": "MR002_STAGE3_CASCADE_REALISM_HARNESS",
               "verdict": "FAIL", "reason": "PREFLIGHT_FAILED_BEFORE_ANY_NUMERICAL_CASE",
               "preflight_gate": preflight_report, "runtime": runtime, "cases": [],
               "evidence_persisted": False}   # cycle-6 f12: claimed true only in the persisted payload
        print(json.dumps(doc, indent=2, default=str))
        out = "/out/MR002_Stage3_CascadeRealismHarness.json"
        try:
            from scripts.mr002_stage3_population_runner import _atomic_write_json, _sha256_file
            doc["evidence_persisted"] = True          # set in the exact persisted payload only
            expected = _atomic_write_json(out, doc)
            if _sha256_file(out) != expected:
                print("FAIL: preflight-refusal artifact byte verification failed", file=sys.stderr)
                return 4
            print(f"wrote {out} (sha256 {expected[:16]}…)")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: could not persist the preflight-refusal artifact: {exc}", file=sys.stderr)
            try:
                from scripts.mr002_stage3_population_runner import _emergency_preserve
                ok = _emergency_preserve(out, {**doc, "evidence_persisted": False})
            except Exception:  # noqa: BLE001
                ok = False
            print(f"emergency sidecar: {'written' if ok else 'FAILED'}", file=sys.stderr)
            return 4
        return 1

    results = run_cases()
    cases_pass = all(r["pass"] for r in results)
    passed = cases_pass and preflight_ok       # finding 6 — full preflight PASS required
    doc = {
        "record_type": "MR002_STAGE3_CASCADE_REALISM_HARNESS",
        "scope": "in-image realism only; no corpus/dataset/population; no performance; OOS sealed",
        "is_pre_execution_gate": True,
        "binds_real": {"primary": sc.PRIMARY_SOLVER_ID, "fallback": sc.FALLBACK_SOLVER_ID,
                       "certifier": "canonical_qualify (registered KKT LIMITS + two-sided signed gap)"},
        "not_exercised": ["real registered QUADPROG ValueError (corpus-row property, see §6)",
                          "real UNRESOLVED_NUMERICAL_FAILURE", "real certifier-exception INTEGRITY"],
        "runtime": runtime,
        "preflight_gate": preflight_report,
        "preflight_passed": preflight_ok,
        "cases": results,
        "cases_pass": cases_pass,
        "verdict": "PASS" if passed else "FAIL",
        "evidence_persisted": False,   # cycle-8 issue 1: flipped True only in the persisted payload
    }
    print(json.dumps(doc, indent=2, default=str))

    # findings 20/26/27 — atomic persistence + FULL-document verification: the persisted bytes must
    # re-serialize to the identical canonical hash, not merely carry the same verdict string.
    out = "/out/MR002_Stage3_CascadeRealismHarness.json"
    try:
        from scripts.mr002_stage3_population_runner import _atomic_write_json
        doc["evidence_persisted"] = True     # set in the exact persisted payload only (issue 1)
        canonical = hashlib.sha256(
            json.dumps(doc, sort_keys=True, default=str).encode()).hexdigest()
        _atomic_write_json(out, doc)
        with open(out, encoding="utf-8") as fh:
            reparsed = json.load(fh)
        got = hashlib.sha256(
            json.dumps(reparsed, sort_keys=True, default=str).encode()).hexdigest()
        if got != canonical:
            print(f"FAIL: persisted document hash {got[:16]} != canonical {canonical[:16]}",
                  file=sys.stderr)
            return 3
    except OSError as exc:
        print(f"FAIL: could not persist evidence artifact {out}: {exc}", file=sys.stderr)
        return 3
    print(f"\nwrote {out} (canonical sha256 {canonical[:16]}…)")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
