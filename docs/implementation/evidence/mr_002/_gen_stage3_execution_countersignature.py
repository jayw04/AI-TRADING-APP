"""MR-002 Stage-3 — complete the ExecutionPackage (v2.0) and close the execution countersignature.

Owner authorization 2026-08-18. Promotes the existing v1.9 DRAFT by filling ONLY the bindings its
own protocol already requires; introduces no new requirement and no new governance framework.

The authorization is deliberately narrow: QUADPROG_SQRT -> PIQP_P2, fallback at most once. No third
attempt, no tolerance/epsilon change, no jitter, no per-instance tuning or routing by observed
outcome, and no validation or OOS access during qualification.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))

SOURCE_CHECKPOINT = "8e8f07880be56c7cc5466f33e0f8b42bb9a86475"   # the manifest describes THIS tree
IMAGE = "mr002-research:v1.4"
IMAGE_ID = "sha256:aa930021c072d01a5a14f389b53bea9d338e53b71e2aac08550972060a08610a"
COUNTERSIGNATURE_ID = "MR002_Stage3ExecutionCountersignature_v1.0"

FROZEN_THREAD_ENV = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "OPENBLAS_CORETYPE": "HASWELL",
}


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha(rel: str) -> str:
    with open(os.path.join(REPO, rel), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _blob_sha(rel: str, rev: str = "HEAD") -> str:
    out = subprocess.run(["git", "-C", REPO, "show", f"{rev}:{rel}"],
                         capture_output=True).stdout
    return hashlib.sha256(out).hexdigest() if out else None


MANIFEST = "docs/implementation/evidence/mr_002/MR002_Stage3_SourceManifest_v1.0.json"
CASCADE = "apps/backend/app/research/mr002/stage3_cascade.py"
SEAM = "apps/backend/app/research/mr002/stage3_route.py"
LAUNCHER = "apps/backend/scripts/mr002_stage3_governed_dev_qualification.py"
POP_RUNNER = "apps/backend/scripts/mr002_stage3_population_runner.py"
POP_TEST = "apps/backend/tests/research/test_mr002_stage3_population_runner.py"
FIXTURES = "apps/backend/scripts/mr002_stage3_cascade_fixtures.py"
DESIGN_COUNTERSIGN = ("docs/implementation/evidence/mr_002/"
                      "MR002_Stage3ProspectiveAdjudication_Countersign_v1.0.json")
DESIGN_ADJUDICATION = ("docs/implementation/evidence/mr_002/"
                       "MR002_Erratum_Stage3_Cascade_ProspectiveAdjudication_v1.0_DRAFT.md")
ELIGIBILITY = ("docs/implementation/evidence/mr_002/"
               "MR002_Stage3EligibilityStatusMapping_v1.0.json")
PKG_V19 = "docs/implementation/evidence/mr_002/MR002_Stage3_ExecutionPackage_v1.9.json"
CERTIFIER = "apps/backend/scripts/mr002_coverage_signed_gap.py"
PIQP = "apps/backend/scripts/mr002_piqp.py"
JOINT = "apps/backend/app/research/mr002/joint_portfolio.py"

with open(os.path.join(REPO, MANIFEST), "rb") as fh:
    manifest_doc = json.loads(fh.read())

BINDINGS = {
    "exact_source_checkpoint": {
        "commit": SOURCE_CHECKPOINT,
        "note": (
            "the Phase-A source manifest was regenerated on Linux, inside the pinned image, from a "
            "CLEAN worktree materialized at this commit -- not from the modified Windows checkout"
        ),
    },
    "source_manifest": {
        "path": MANIFEST,
        "sha256": _sha(MANIFEST),
        "manifest_phase": manifest_doc.get("manifest_phase"),
        "members": len(manifest_doc.get("files", {})),
        "files_missing": manifest_doc.get("files_missing"),
        "correspondence_proof": {
            "lf_only_differences_under_clean_materialization": 0,
            "members_matching_previous_manifest_as_is": 17,
            "members_newly_bound": 3,
            "members_added": 0,
            "members_removed": 0,
            "self_consistency_against_clean_tree": "20/20",
            "newly_bound": [CASCADE, POP_RUNNER, POP_TEST],
            "why_newly_bound": (
                "these three legitimately advanced at ecaa262 (2026-07-19, 'COMMIT AUTHORIZED'), "
                "AFTER the 2026-07-18 manifest. The implementation was NOT edited to satisfy the "
                "stale manifest; the manifest was regenerated to describe the authorized "
                "implementation."
            ),
        },
    },
    "stage3_cascade": {"path": CASCADE, "sha256": _sha(CASCADE)},
    "stage3_route_seam": {
        "path": SEAM,
        "sha256": _sha(SEAM),
        "role": (
            "runtime seam only: replaces joint_portfolio._solve_qp with a cascade-routed function. "
            "Edits no bound bytes, changes no numerical parameter, and refuses to install without "
            "this countersignature identity."
        ),
    },
    "launcher": {
        "path": LAUNCHER,
        "sha256": _sha(LAUNCHER),
        "role": "THE governed development qualification launcher; one run, development corpus only",
    },
    "population_runner": {"path": POP_RUNNER, "sha256": _sha(POP_RUNNER)},
    "population_runner_test": {"path": POP_TEST, "sha256": _sha(POP_TEST)},
    "qualification_fixtures": {"path": FIXTURES, "sha256": _sha(FIXTURES)},
    "eligibility_status_mapping": {"path": ELIGIBILITY, "sha256": _sha(ELIGIBILITY)},
    "successor_design_countersignature": {
        "path": DESIGN_COUNTERSIGN, "sha256": _sha(DESIGN_COUNTERSIGN),
        "note": "the DESIGN countersignature; it never authorized execution on the corpus",
    },
    "successor_design_adjudication": {
        "path": DESIGN_ADJUDICATION, "sha256": _sha(DESIGN_ADJUDICATION)},
    "certifier_and_solver_registry": {
        "path": CERTIFIER, "sha256": _sha(CERTIFIER),
        "certifier": "canonical_qualify — registered KKT LIMITS + two-sided signed Lagrangian gap",
        "primary": "QUADPROG_SQRT",
        "fallback": "PIQP_P2",
    },
    "fallback_profile": {
        "path": PIQP, "sha256": _sha(PIQP),
        "profile": "P2 — preconditioner_scale_cost = true, everything else identical to BASE",
    },
    "governing_construction": {
        "path": JOINT, "sha256": _sha(JOINT),
        "note": "unmodified; its identity as the governing construction is unchanged by the seam",
    },
    "runtime": {
        "image": IMAGE,
        "image_id": IMAGE_ID,
        "network": "none",
        "frozen_thread_env": FROZEN_THREAD_ENV,
        "thread_env_is_load_bearing": (
            "MEASURED: without it the frozen solver's own KKT acceptance check fails inside the "
            "accepted development runner (stationarity_residual 5.032e+00 > 1e-08). "
            "threading_policy_branch is FROZEN because the alternative branch was never performed."
        ),
        "solver_pin": {"quadprog": "0.1.13",
                       "artifact_sha256":
                           "cc1996a0e3de1d423f8662fe21368948afdc91d851910b77320caaf7c15357ff"},
    },
    "data_boundary": {
        "corpus": "the already-authorized DEVELOPMENT research corpus",
        "corpus_sha256": "24e5153cc0ebed77c7b422562e5a8ebfa147aad3019b27035b5314aaaacfad5a",
        "corpus_identity_is_bound_in": [
            "docs/review/mr002/evaluator/MR002_EvaluatorBinding.json (data_manifest_identity)",
            "docs/review/mr002/custody_review/sealed_partition_commitment.py (SNAPSHOT_SHA256)",
        ],
        "window": ["2013-01-02", "2019-10-02"],
        "validation_start_excluded": "2019-10-03",
        "oos_start_excluded": "2023-05-30",
        "enforcement": (
            "the launcher asserts the window BEFORE any replay and aborts on a session at or "
            "beyond the validation start; validation and OOS reads are zero STRUCTURALLY because "
            "no sealed reader is constructed anywhere in the qualification path"
        ),
    },
    "supersedes_package": {"path": PKG_V19, "sha256": _sha(PKG_V19),
                           "prior_status": "DRAFT, execution_authorized: false"},
}

PACKAGE = {
    "record_type": "MR002_STAGE3_EXECUTION_PACKAGE",
    "version": "2.0",
    "supersedes": "MR002_Stage3_ExecutionPackage_v1.9.json",
    "status": (
        "COMPLETE. The v1.9 open items were the final commit, the pinned image and the launcher; "
        "all three are now bound. Promoted by filling ONLY the bindings the package protocol "
        "already required."
    ),
    "prepared": "2026-08-18",
    "execution_authorized": True,
    "authorized_by": "owner authorization 2026-08-18",
    "authorization_scope": {
        "cascade": "QUADPROG_SQRT -> PIQP_P2, fallback at most once",
        "third_attempt": "PROHIBITED",
        "tolerance_or_epsilon_change": "PROHIBITED",
        "jitter": "PROHIBITED",
        "per_instance_tuning_or_routing_by_observed_outcome": "PROHIBITED",
        "validation_or_oos_access_during_qualification": "PROHIBITED",
        "runs_authorized": "ONE governed development qualification",
    },
    "package_binds": BINDINGS,
    "scope_boundary": (
        "This package authorizes exactly one governed DEVELOPMENT qualification of the successor "
        "Stage-3 cascade. It authorizes NO validation access, NO OOS access, and NO economic "
        "interpretation. The sealed validation opening remains ungranted and unrequested."
    ),
    "governing_pass_criteria": [
        "A completes", "B completes", "C completes",
        "Phase 3C completes for all three",
        "every Stage-3 invocation reconciles",
        "only registered dispositions",
        "zero UNRESOLVED_NUMERICAL_FAILURE",
        "zero INVALID_RUN",
        "fallback at most once per invocation",
        "R6A proofs pass",
        "deterministic/reconciliation checks pass",
        "development-only boundary proves validation reads = 0 and OOS reads = 0",
    ],
    "counts_are_not_a_pass_condition": (
        "if the governed run reproduces the feasibility probe's 3,891 primary / 4 fallback split, "
        "record it as strong corroboration -- it is NEVER the pass condition. The governing "
        "requirement is semantic completion under the frozen decision table."
    ),
    "phase3c_identity_frozen": "7788ada561625bf160f9a569a26eac9fc28ceb7d12032e61c0f6f69ee67c3bc7",
}

COUNTERSIGNATURE = {
    "record_type": "MR002_STAGE3_EXECUTION_COUNTERSIGNATURE",
    "countersignature_id": COUNTERSIGNATURE_ID,
    "version": "1.0",
    "produced_at": "2026-08-18T00:00:00Z",
    "authorized_by": "owner authorization 2026-08-18",
    "closes": (
        "the execution countersignature that stage3_cascade.py's own header demands and that the "
        "design countersignature (2026-07-17) explicitly did NOT provide"
    ),
    "what_the_design_countersignature_did_not_authorize": (
        "'EXECUTION IS NOT AUTHORIZED BY THE DESIGN COUNTERSIGNATURE... This module must not be "
        "pointed at the registered corpus, the frozen dataset, or any population-selection loop "
        "until that countersignature exists.'"
    ),
    "execution_authorized": True,
    "authorization": {
        "cascade": "QUADPROG_SQRT -> PIQP_P2",
        "fallback_invocations_per_instance_max": 1,
        "third_attempt": False,
        "tolerance_or_epsilon_change": False,
        "jitter": False,
        "per_instance_tuning_or_routing_by_observed_outcome": False,
        "fallback_by_analogy": False,
        "validation_access": False,
        "oos_access": False,
        "corpus": "DEVELOPMENT only",
        "runs": 1,
    },
    "binds": BINDINGS,
    "execution_package": {"path": "docs/implementation/evidence/mr_002/"
                                  "MR002_Stage3_ExecutionPackage_v2.0.json"},
    "enforcement_in_code": (
        "app/research/mr002/stage3_route.routed() refuses to install unless the caller passes "
        f"{COUNTERSIGNATURE_ID!r}, so the seam cannot be used without this countersignature."
    ),
    "grants": (
        "ONE governed development qualification of the successor Stage-3 cascade. NOTHING else. "
        "No validation opening, no OOS access, no economic interpretation."
    ),
}


def main() -> None:
    pkg_body = _canonical(PACKAGE)
    PACKAGE["record_identity_sha256"] = hashlib.sha256(pkg_body).hexdigest()
    pkg_path = os.path.join(_HERE, "MR002_Stage3_ExecutionPackage_v2.0.json")
    with open(pkg_path, "wb") as fh:
        fh.write(_canonical(PACKAGE))

    COUNTERSIGNATURE["execution_package"]["sha256"] = hashlib.sha256(
        _canonical(PACKAGE)).hexdigest()
    cs_body = _canonical(COUNTERSIGNATURE)
    COUNTERSIGNATURE["record_identity_sha256"] = hashlib.sha256(cs_body).hexdigest()
    cs_path = os.path.join(_HERE, "MR002_Stage3ExecutionCountersignature_v1.0.json")
    with open(cs_path, "wb") as fh:
        fh.write(_canonical(COUNTERSIGNATURE))

    print(json.dumps({
        "execution_package_v2.0": PACKAGE["record_identity_sha256"],
        "countersignature": COUNTERSIGNATURE["record_identity_sha256"],
        "source_checkpoint": SOURCE_CHECKPOINT,
        "source_manifest": BINDINGS["source_manifest"]["sha256"],
        "cascade": BINDINGS["stage3_cascade"]["sha256"],
        "seam": BINDINGS["stage3_route_seam"]["sha256"],
        "launcher": BINDINGS["launcher"]["sha256"],
    }, indent=1))


if __name__ == "__main__":
    main()
