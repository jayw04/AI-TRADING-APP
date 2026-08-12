"""Generate the Phase-3B launch-preflight blocker register (Step 1 of the owner launch direction).

Zero-data instrument. Reads only repository files, frozen Phase 3A/3B specifications, and P6-P12
evidence already committed. Issues NO AWS call, opens NO sealed object, and assumes NO credential.

Step 1 of the owner's 2026-08-12 launch direction requires that every launch parameter be RESOLVED
from the frozen contract before the granted validation opening is spent, and that a value which the
frozen contract does not specify is a STOP rather than an inference. This script records the outcome
of that resolution: which parameters resolved, which did not, and what is missing beneath them.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))

EVALUATOR_DIR = os.path.join(_REPO, "docs", "review", "mr002", "evaluator")
SPQ1_DIR = os.path.join(_REPO, "apps", "backend", "app", "research", "mr002", "spq1")

ENTRY_POINT_PATTERN = re.compile(r"argparse|__main__|^def main\b", re.MULTILINE)
NETWORK_PATTERN = re.compile(r"\bboto3\b|\bbotocore\b|\burllib\b|\brequests\b|s3://")


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _py_files(root: str) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".pytest_cache", ".ruff_cache")]
        out.extend(os.path.join(dirpath, f) for f in filenames if f.endswith(".py"))
    return sorted(out)


def _scan(paths: list[str], pattern: re.Pattern) -> list[str]:
    """Repo-relative paths whose text matches. A scan that examined nothing is a defect, not a pass."""
    if not paths:
        raise SystemExit("REFUSED: scan target set is empty; a zero-file scan proves nothing")
    hits = []
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as fh:
            if pattern.search(fh.read()):
                hits.append(os.path.relpath(p, _REPO).replace("\\", "/"))
    return hits


def _bound_module_names() -> list[str]:
    with open(os.path.join(EVALUATOR_DIR, "MR002_EvaluatorImageManifest_Runtime_v1.0.json"),
             encoding="ascii") as fh:
        return sorted(json.load(fh)["module_digests_in_image"])


def build() -> dict:
    bound_modules = _bound_module_names()
    bound_paths = [os.path.join(EVALUATOR_DIR, m) for m in bound_modules]
    missing = [m for m, p in zip(bound_modules, bound_paths) if not os.path.exists(p)]
    if missing:
        raise SystemExit(f"REFUSED: bound module absent from the working tree: {missing}")
    spq1_paths = _py_files(SPQ1_DIR)

    prereg = os.path.join(_REPO, "docs", "review", "mr002",
                          "MR002_ValidationOOS_Preregistration_v1.0.4.json")
    prereg_sha = _sha256_file(prereg)
    registered_prereg_sha = "b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c"

    return {
        "record_type": "MR002_Phase3B_LaunchPreflightBlockerRegister",
        "version": "1.0",
        "artifact_kind": "PREFLIGHT_FINDING",
        "date": "2026-08-12",
        "stage": "Phase 3B launch preflight, Step 1 (parameter resolution from the frozen contract)",
        "verdict": "STOP_BEFORE_SPENDING_THE_OPENING",
        "classification": "EXECUTION_READINESS_BLOCK - AUTHORIZATION_VALID, OPENING_UNSPENT",
        "classification_note": (
            "This is NOT a validation failure and NOT a governance defect. The authorization "
            "machinery is complete; the execution machinery is not."
        ),
        "owner_ruling_2026_08_12": {
            "authorized": [
                "commit this blocker register",
                "draft MR002_Phase3B_RunSpecification_v1.0 with zero validation access",
                "implement and qualify the missing execution path on synthetic/non-validation data",
            ],
            "not_authorized": [
                "validation access",
                "Phase 3B real execution",
                "weakening PartitionGuard",
                "changing Config A/B/C by inference",
                "rebuilding sha256:194efbdf... without an explicit identity ruling",
                "Phase 3C metrics",
                "OOS access",
            ],
            "deferred_decision": (
                "Whether P12 must be amended or re-granted is decided AFTER the execution "
                "specification is frozen, not now. If the evaluator image, its module roster, the "
                "P10 runtime, or any other P12-bound identity changes, the current grant must not "
                "be used as though nothing happened: recompute the affected prerequisite chain and "
                "obtain a fresh authorization first."
            ),
            "open_architectural_question": (
                "What exactly must be identity-bound as THE EVALUATOR, and what may be a separately "
                "governed execution/orchestration layer? That enrichment sits outside the 21-module "
                "identity does not by itself mean it must move inside: the boundary was never "
                "specified. Do not choose the separate-layer model merely to avoid a rebind."
            ),
        },
        "durable_findings": [
            "P1-P12 and the D3 grant remain VALID.",
            "Validation authorization is GRANTED and the single opening remains UNCONSUMED.",
            "No Phase 3B executable exists.",
            "The development producer CORRECTLY refuses validation data and must not be weakened.",
            "execution_enrichment.py is outside the currently bound runtime identity.",
            "Config A/B/C parameters are not concretely bound.",
            "Input identity is inconsistent between the local DuckDB and the sealed S3 objects.",
            "The output contract is internally inconsistent and incomplete.",
            "Therefore no launch manifest can truthfully be produced.",
        ],
        "boundary": (
            "Zero-data instrument. No AWS API call, no sealed object opened, no credential assumed, "
            "no reader role used. validation_authorization remains true at _rev 1 and the single "
            "granted validation opening remains UNSPENT."
        ),
        "governing_direction": (
            "Owner launch direction 2026-08-12, Step 1: resolve every launch parameter from the "
            "frozen contract; do not infer a missing value; STOP before spending the opening if the "
            "frozen contract does not specify one."
        ),
        "authorization_state_unchanged_by_this_record": {
            "_rev": 1,
            "note": "This register grants nothing, revokes nothing, and edits no authorization state.",
            "opening_consumed": False,
            "validation_authorization": True,
        },
        "governing_preregistration": {
            "file": "MR002_ValidationOOS_Preregistration_v1.0.4.json",
            "recomputed_sha256": prereg_sha,
            "registered_sha256": registered_prereg_sha,
            "matches": prereg_sha == registered_prereg_sha,
        },
        "parameter_resolution": _parameter_resolution(),
        "implementation_gap_evidence": {
            "bound_image_digest": (
                "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51"
            ),
            "bound_module_count": len(bound_modules),
            "entry_point_scan": {
                "pattern": "argparse | __main__ | ^def main",
                "bound_evaluator_modules_scanned": len(bound_paths),
                "bound_evaluator_modules_with_entry_point": _scan(bound_paths, ENTRY_POINT_PATTERN),
                "spq1_modules_scanned": len(spq1_paths),
                "spq1_modules_with_entry_point": _scan(spq1_paths, ENTRY_POINT_PATTERN),
            },
            "sealed_store_reader_scan": {
                "pattern": "boto3 | botocore | urllib | requests | s3://",
                "bound_evaluator_modules_matching": _scan(bound_paths, NETWORK_PATTERN),
                "spq1_modules_matching": _scan(spq1_paths, NETWORK_PATTERN),
                "finding": (
                    "No module in the bound evaluator image or the SPQ-1 producer package can read "
                    "the sealed S3 store the released reader grants access to."
                ),
            },
            "enrichment_implementation_location": {
                "implementation": "apps/backend/app/research/mr002/spq1/execution_enrichment.py",
                "in_bound_image": "mr002_valoos_execution_enrichment.py" in bound_modules,
                "finding": (
                    "The frozen ExecutionEnrichmentSchema is implemented OUTSIDE the bound evaluator "
                    "identity. The 21 modules bound by P5/P10 contain no enrichment code."
                ),
            },
            "producer_partition_binding": {
                "dev_start": "2013-01-02",
                "dev_end": "2019-10-02",
                "validation_start": "2019-10-03",
                "guard": "apps/backend/app/research/mr002/spq1/adapters/partition_guard.py",
                "forbidden_prefixes": ["validation", "oos", "sealed"],
                "finding": (
                    "The SPQ-1 signal producer is hard-bound to the DEVELOPMENT partition. Every "
                    "validation session lies beyond dev_end, so PartitionGuard.guard_range would "
                    "raise INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS on the first validation read. "
                    "This guard is correct and must not be relaxed to force a launch."
                ),
            },
            "deliverable_emitters_absent": [
                "ValidationOpenedObjectLedger_v1.0.json",
                "ValidationExecutionEnrichmentManifest_v1.0.json",
                "ValidationDecisionExecutionBindingReport_v1.0.json",
                "ValidationUnitReconciliation_v1.0.json",
                "ExecutionEnrichmentEdgeCaseCensus_v1.0.json",
                "ValidationSealVerificationReport_v1.0.json",
            ],
            "deliverable_emitter_scan_finding": (
                "No Python module in apps/ or scripts/ names any of the six Phase-3B deliverable "
                "record types. Nothing exists that could emit them."
            ),
        },
        "phase_2b_precedent": {
            "artifact": "MR002_SPQ1_Phase2B_RunSpecification_v1.1.json",
            "run_id": "MR002-SPQ1-P2B-DEV-V1",
            "increments": ["2B-0 run specification (no computation)",
                           "2B-1 dry-run + limited-shard qualification gate",
                           "2B-2 full run", "2B-3 reconciliation/determinism/closeout"],
            "finding": (
                "The DEVELOPMENT window - which is not sealed and carries no one-time opening - "
                "required a full run specification, two amendments, and a four-increment staged "
                "qualification before it was executed. The sealed validation window has no "
                "equivalent artifact of any version."
            ),
        },
        "what_is_NOT_blocked": [
            "The P12 grant is valid and needs no re-authorization.",
            "P1-P12 are satisfied; the governance layer is complete.",
            "The sealed store exists, is pinned by Version ID + SHA-256, and enforces the OOS DENY.",
            "The evaluator image is published, bound, and P10-qualified.",
            "This is an execution-readiness gap, not a governance defect.",
        ],
        "consequence_if_ignored": (
            "Launching against the frozen contract as it stands would assume the reader, fail at the "
            "first sealed read (no reader implementation exists), and spend the one-time opening on "
            "a defect rather than on the validation run - the precise outcome the owner direction "
            "and the one-validation-execution rule exist to prevent."
        ),
        "steps_2_through_5_status": (
            "NOT ATTEMPTED. Step 2 (Phase3BLaunchManifest) cannot bind an executable, launch "
            "command, or output location that does not exist; Steps 3-5 depend on it. Producing a "
            "launch manifest over inferred values would defeat its purpose."
        ),
        "recommended_next_action": (
            "Owner decision on scope: a Phase-3B execution program must be specified and built "
            "before the opening can be spent. It is NOT covered by the bounded 'get to validation' "
            "authorization as currently written, because that scope assumed the executable existed."
        ),
    }


def _parameter_resolution() -> dict:
    """Each Step-1 required parameter, with its resolution status and the source consulted."""
    return {
        "phase_3b_entry_point": {
            "status": "UNRESOLVED",
            "detail": "No executable, module entry point, CLI, or __main__ exists in the bound "
                      "evaluator image or in the SPQ-1 producer package.",
        },
        "cli_arguments": {
            "status": "UNRESOLVED",
            "detail": "No CLI exists; no frozen artifact specifies an argument contract.",
        },
        "config_A_B_C_identities": {
            "status": "UNRESOLVED",
            "detail": "configuration_id is an opaque caller-supplied string in both the producer "
                      "and the evaluator. No frozen artifact carries the A/B/C parameter values "
                      "(Z_entry thresholds) or their hashes. Preregistration v1.0.4 names the "
                      "configs and gates Config B, but never defines them.",
        },
        "validation_partition_root_and_pins": {
            "status": "RESOLVED",
            "detail": "s3://workbench-mr002-sealed-219024422756/validation/ - 6 parquet objects "
                      "(actions, anchors, etf_prices, prices, sic_observations, universe) pinned by "
                      "Version ID + SHA-256 in MR002_SealedStoreUploadManifest_v1.0.json.",
        },
        "evaluator_runtime_identity": {
            "status": "RESOLVED",
            "detail": "OCI index sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237"
                      "432f51, resolved live by the WP-B fail-closed resolver.",
        },
        "execution_enrichment_contract": {
            "status": "SPECIFIED_BUT_UNBOUND",
            "detail": "ExecutionEnrichmentSchema 5b2480c1 and ExecutionEnrichmentCodeRegistry "
                      "0bddd73c are frozen. Their implementation lives outside the bound evaluator "
                      "image, so the enrichment that Phase 3B must perform is not covered by the "
                      "evaluator identity that P5/P10/P12 bind.",
        },
        "bound_input_source": {
            "status": "CONFLICTING",
            "detail": "MR002_EvaluatorBinding.json binds data_manifest_identity to the local file "
                      "apps/backend/data/mr002_research.duckdb (sha256 24e5153c). The sealed store "
                      "the released reader grants is S3 parquet. The frozen contract does not say "
                      "which is the governed Phase-3B input, and no code reads the S3 form.",
        },
        "output_directory_and_filenames": {
            "status": "CONFLICTING",
            "detail": "MR002_EvaluatorBinding.json expected_output_paths declares two files "
                      "(valoos/<window>/MR002_ValOOS_<window>_Report.json and _Publication.json). "
                      "MR002_Phase3BC_DeliverableRegister_v1.0.json declares six different Phase-3B "
                      "deliverables. The two are never reconciled, and <window> is never bound to a "
                      "literal. No filesystem or S3 root is specified for either.",
        },
        "output_artifact_schema": {
            "status": "UNRESOLVED",
            "detail": "No schema exists for any of the six Phase-3B deliverables, and no emitter "
                      "exists for any of them.",
        },
        "run_id": {
            "status": "PROPOSED_ONLY",
            "detail": "ValidationRunSpecification_v1.0 carries "
                      "'MR002-SPQ1-VALIDATION-V1 (PROPOSED; not authorized to execute)'. The "
                      "parenthetical is part of the frozen string; no artifact promotes it to a "
                      "bound run identity.",
        },
        "terminal_and_exit_semantics": {
            "status": "RESOLVED",
            "detail": "mr002_valoos_publication.py: PASS=0, FAIL=1, REFUSED=2, INTEGRITY_STOP=3; "
                      "wrapper/publication-control failure = 3; exit/disposition agreement enforced; "
                      "occupied destination refused, never overwritten.",
        },
        "failure_behavior": {
            "status": "RESOLVED",
            "detail": "Fail-closed throughout: EXECUTION_ENRICHMENT_STOP:* codes, "
                      "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED, coverage REFUSED_* codes, and "
                      "the fail-closed AccessBoundary. No silent fallback is permitted.",
        },
        "oos_prohibition": {
            "status": "RESOLVED_AND_ENFORCED",
            "detail": "AccessBoundary.partition_permitted denies OOS unconditionally in code; the "
                      "S3 DENY remains active and was re-confirmed by policy simulation after the "
                      "grant. A validation grant never unlocks OOS.",
        },
    }


def main() -> None:
    record = build()
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3B_LaunchPreflight_BlockerRegister_v1.0.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(record))
    print(f"wrote {out}")
    print(f"identity (over the body, self-excluded) {record['record_identity_sha256']}")
    print(f"verdict {record['verdict']}")


if __name__ == "__main__":
    main()
