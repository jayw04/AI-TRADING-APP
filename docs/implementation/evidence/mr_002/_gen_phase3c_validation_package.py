"""MR-002 — the successor VALIDATION execution package.

Supersedes MR002_Stage3_ExecutionPackage_v2.1 (e5c6a419...) as the package a validation opening
may be granted against. v2.1 remains correct for what it covered -- the Stage-3 numerical path --
but it never described the sealed-side input contract, so it cannot be the validation package.

Every code identity here is taken from GIT BLOBS, never from the working tree. That is not a
stylistic choice: binding working-tree hashes on Windows is exactly the defect the pushed-Git
re-derivation caught in the previous package.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
REV = "HEAD"
BUCKET = "workbench-mr002-sealed-219024422756"


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob_sha(path: str) -> str:
    out = subprocess.run(["git", "-C", REPO, "show", f"{REV}:{path}"], capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"not committed: {path}")
    return hashlib.sha256(out.stdout).hexdigest()


def _load(rel: str) -> dict:
    with open(os.path.join(REPO, rel), "rb") as fh:
        return json.loads(fh.read())


LEDGER = _load("docs/review/mr002/phase3bc/v36_published/ValidationOpenedObjectLedger_v1.0.json")
REGISTER = _load("docs/review/mr002/phase3bc/MR002_Phase3BC_RuntimePrerequisiteRegister_v1.3.json")
QUAL = _load("docs/implementation/evidence/mr_002/MR002_Phase3C_MaterializerQualification_v1.0.json")
STAGE3_PKG = "docs/implementation/evidence/mr_002/MR002_Stage3_ExecutionPackage_v2.1.json"

_by_key = {e["object_id"]: e["version_id"] for e in LEDGER["ledger"]}
_ref = REGISTER["reference_layer"]["tables"]

SEALED_TABLES = ("actions", "anchors", "etf_prices", "prices", "sic_observations", "universe")
REFERENCE_TABLES = ("crosswalk", "predecessor_overrides", "security_sector_overrides",
                    "sic_mapping")

MATERIALIZER = "apps/backend/app/research/mr002/phase3c/materialize.py"
READER = "apps/backend/app/research/mr002/phase3b/readers.py"
SYNTH_TESTS = "apps/backend/tests/research/phase3c/test_phase3c_materialize.py"
QUAL_EVIDENCE = "docs/implementation/evidence/mr_002/MR002_Phase3C_MaterializerQualification_v1.0.json"
PHASE3C = [
    "apps/backend/app/research/mr002/phase3c/__init__.py",
    "apps/backend/app/research/mr002/phase3c/adopted.py",
    "apps/backend/app/research/mr002/phase3c/exits.py",
    "apps/backend/app/research/mr002/phase3c/folds.py",
    "apps/backend/app/research/mr002/phase3c/gates.py",
    "apps/backend/app/research/mr002/phase3c/materialize.py",
    "apps/backend/app/research/mr002/phase3c/replay.py",
]

_h = hashlib.sha256()
for p in sorted(PHASE3C):
    _h.update(f"{p}:{blob_sha(p)}\n".encode("ascii"))
PHASE3C_IDENTITY = _h.hexdigest()

PACKAGE = {
    "record_type": "MR002_PHASE3C_VALIDATION_EXECUTION_PACKAGE",
    "version": "1.0",
    "produced_at": "2026-08-18T00:00:00Z",
    "supersedes_for_validation_purposes": {
        "path": STAGE3_PKG,
        "sha256": blob_sha(STAGE3_PKG),
        "why": (
            "v2.1 remains correct for the Stage-3 numerical path it covered, but it never "
            "described the sealed-side input contract, so it cannot be the package a validation "
            "opening is granted against."
        ),
    },
    "execution_authorized": False,
    "awaiting": "the replacement sealed-validation-opening ruling",
    "purpose": (
        "produce the single frozen MR-002 validation-stage economic decision from the sealed "
        "validation partition"
    ),

    # ---- the input contract, stated as 6 sealed + 4 reference and NEVER as 8 sealed -----------
    "input_contract": {
        "validation_sealed_inputs": {
            "count": 6,
            "authority": "the existing governed validation reader ONLY",
            "consumes_the_validation_opening": True,
            "must_be_entered_in": "ValidationOpenedObjectLedger",
            "bucket": BUCKET,
            "objects": [
                {"table": t, "key": f"validation/{t}.parquet",
                 "version_id": _by_key[f"validation/{t}.parquet"]}
                for t in SEALED_TABLES
            ],
        },
        "reference_inputs": {
            "count": 4,
            "authority": (
                "the existing reference-layer authority. The RuntimePrerequisiteRegister v1.3 "
                "classifies these COMMITTED AND IDENTITY-BOUND BUT NOT SEALED, explicitly NOT a "
                "sealed partition object, NOT under the OOS DENY, and NOT covered by the "
                "validation-only read restriction."
            ),
            "consumes_the_validation_opening": False,
            "bucket": BUCKET,
            "objects": [
                {"table": t, "key": _ref[t]["object_key"],
                 "version_id": _ref[t]["version_id"],
                 "object_sha256": _ref[t]["object_sha256"]}
                for t in REFERENCE_TABLES
            ],
            "do_not_broaden": (
                "the validation reader's authority must NOT be extended to these objects merely "
                "to make the package uniform. The separation is preserved deliberately."
            ),
        },
        "materialized_output": {
            "form": "a single DuckDB database presenting exactly ten tables",
            "tables": sorted(SEALED_TABLES + REFERENCE_TABLES),
            "consumed_by": "unchanged Phase 3C via FrozenDataset",
        },
        "why_six_not_eight": (
            "the v3.6 run opened eight objects, but two of them -- crosswalk and sic_mapping -- "
            "are reference-layer objects. FrozenDataset additionally requires "
            "predecessor_overrides and security_sector_overrides, which the v3.6 run never "
            "opened. The sealed count is six; the reference count is four."
        ),
    },

    # ---- the materializer -----------------------------------------------------------------
    "materializer": {
        "path": MATERIALIZER,
        "sha256": blob_sha(MATERIALIZER),
        "reuses_existing_reader": {"path": READER, "sha256": blob_sha(READER)},
        "introduces_a_second_reader": False,
        "performs_its_own_aws_call": False,
        "representation_only": True,
        "prohibited_and_absent": [
            "synthetic rows", "filtering", "imputation", "date/price/action alteration",
            "column derivation", "alternative signal construction",
            "observable reordering",
        ],
        "schema_contract": "REQUIRED_COLUMNS — the ten tables and the minimum columns each "
                           "consumer touches; a missing table, an unregistered table or an "
                           "absent required column REFUSES",
        "checksum_gate": "PinnedObject.verify runs before anything is parsed",
        "parquet_reader": "DuckDB read_parquet — no Arrow/pyarrow dependency in the governed path",
    },

    # ---- the determinism gate ---------------------------------------------------------------
    "determinism_gate": {
        "why_it_exists": (
            "three FrozenDataset consumers resolve FIRST-MATCH-WINS over an unordered SELECT -- "
            "crosswalk (eligibility.py:122), security_sector_overrides (:135) and sic_mapping "
            "(:150). Their answers would depend on row order if two rows could match the same "
            "lookup key on the same date. Zero-overlap is what makes the existing implementation "
            "determinate."
        ),
        "rule": "any true overlapping applicable interval for the same lookup key/date REFUSES",
        "does_not": "impose an ordering or a precedence to resolve overlap",
        "order_insensitive_by_construction": {
            "prices / etf_prices / sic_observations": "ORDER BY in their own SQL",
            "universe / actions": "consumed through dicts, sets and predicates",
            "anchors": "sorted by EarningsBlackout.__init__ (eligibility.py:50)",
        },
        "measured_on_the_development_registries": QUAL["materialization_evidence"][
            "determinism_preconditions"],
    },

    "logical_content_identity_algorithm": (
        "sha256 over the read-ordered lines '<key>@<version_id>:<sha256>\\n' for every opened "
        "object. It identifies the CONTENT SET consumed, independently of the physical DuckDB "
        "file bytes, which are not reproducible and are deliberately not bound."
    ),

    # ---- qualification evidence --------------------------------------------------------------
    "qualification": {
        "synthetic_fail_closed": {
            "path": SYNTH_TESTS,
            "sha256": blob_sha(SYNTH_TESTS),
            "cases": [
                "checksum mismatch", "unpinned read", "missing registered table",
                "unregistered table", "absent required column",
                "true interval overlap in crosswalk",
                "true interval overlap in security_sector_overrides",
                "overlapping (sic-range x date-range) in sic_mapping",
                "disjoint open-ended intervals must NOT refuse (regression guard)",
                "overlapping SIC ranges on disjoint dates must NOT refuse",
                "6 VALIDATION + 4 REFERENCE read split reported",
                "logical-content identity stable and content-sensitive",
            ],
            "result": "12 passed; whole phase3c suite 208 passed inside the frozen image",
        },
        "development_equivalence": {
            "path": QUAL_EVIDENCE,
            "sha256": blob_sha(QUAL_EVIDENCE),
            "result": QUAL["result"],
            "stage_A": {
                "what": "DayInputs equality over every development session, 20 fields per session",
                "sessions": QUAL["stage_A"]["sessions"],
                "mismatches": QUAL["stage_A"]["mismatch_count"],
            },
            "stage_B": {
                "what": "full Phase 3C A/B/C replay through the successor Stage-3 cascade",
                "exact": {k: v["EXACT"] for k, v in QUAL["stage_B"].items()},
                "compared": [
                    "run hash", "NAV curve", "daily returns", "reductions", "exits", "entries",
                    "exit reasons", "costs", "borrow", "traded notional", "session outcomes",
                    "zero-entry reasons", "per-trade reason and net P&L", "Stage-3 dispositions",
                ],
            },
            "equality_asserted": "semantic, not physical DuckDB file bytes",
        },
    },

    # ---- the indivisible sequence -------------------------------------------------------------
    "atomic_sequence": {
        "steps": [
            "1. sealed reader — the 6 validation objects, version-pinned and checksum-verified",
            "2. opened-object ledger — every sealed read entered",
            "3. reference reads — the 4 identity-bound reference objects, separate authority",
            "4. materialization — the ten-table DuckDB, determinism gate enforced",
            "5. Phase 3C A/B/C replay — unchanged code, frozen folds and gates",
        ],
        "indivisible": True,
        "why": (
            "materialization itself reveals the sealed validation data, so there must be no "
            "'materialize now, replay later' split and no manual inspection interval between "
            "them. One opening covers the whole sequence."
        ),
    },

    # ---- runtime ------------------------------------------------------------------------------
    "runtime": {
        "image": "mr002-research:v1.4",
        "image_id": "sha256:aa930021c072d01a5a14f389b53bea9d338e53b71e2aac08550972060a08610a",
        "frozen_thread_env": {
            "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1", "OPENBLAS_CORETYPE": "HASWELL",
        },
        "image_provides": ["duckdb 1.1.3", "quadprog 0.1.13", "piqp 0.6.3", "numpy 2.2.6",
                           "scipy 1.18.0"],
        "image_does_NOT_provide": ["boto3", "botocore", "pyarrow", "pandas"],
        "dependency_bundle_required": {
            "why": (
                "the real S3PinnedReader needs boto3, which the image does not carry. Phase 3B "
                "supplied it from the bound ExecutionDependencyBundle mounted at /opt/mr002/deps. "
                "Omitting that mount is exactly what caused the earlier released-but-refused "
                "execution, so the validation launch MUST bind and mount it."
            ),
            "bundle": "ExecutionDependencyBundle v1.1",
            "identity": "61bd7d98...",
            "clean_projection_inventory": "7c50b2ab... (2,919 files)",
            "pyarrow_no_longer_needed": (
                "the materializer uses DuckDB's native Parquet reader, so only boto3/botocore are "
                "still required from the bundle"
            ),
        },
    },

    "phase3c": {
        "identity": PHASE3C_IDENTITY,
        "note": (
            "this now INCLUDES materialize.py, so it necessarily differs from the pre-materializer "
            "identity c26230b6... No Phase 3C semantic file was modified: __init__, adopted, exits, "
            "folds, gates and replay are byte-unchanged."
        ),
        "modules": {p: blob_sha(p) for p in PHASE3C},
        "semantic_modules_unchanged": True,
    },

    "stage3_authority_carried_forward": {
        "countersignature_id": "MR002_Stage3ExecutionCountersignature_v1.0",
        "cascade": "QUADPROG_SQRT -> PIQP_P2, fallback at most once",
        "prohibited": ["third attempt", "jitter", "tolerance/epsilon change",
                       "per-instance tuning or routing by observed outcome",
                       "fallback by analogy"],
    },

    "validation_decision": {
        "VALIDATION_ADVANCE_REQUEST": (
            "Config B >= 3 of 5 folds net-positive AND Config A cumulative net return > 0 AND "
            "Config C cumulative net return > 0 AND replay integrity admissible"
        ),
        "otherwise": ["VALIDATION_DO_NOT_ADVANCE", "VALIDATION_INCONCLUSIVE", "INTEGRITY_FAILURE"],
        "not_an_oos_pass": (
            "VALIDATION_ADVANCE_REQUEST authorizes only returning for the separate decision "
            "whether to open the OOS seal"
        ),
        "prohibited_at_this_stage": ["net_oos_sharpe >= 0.70", "stationary bootstrap", "DSR",
                                     "OOS cost-stress gates"],
        "config_C_sparsity": "disclose; do NOT reinterpret after seeing the result",
    },

    "affirmations": {
        "validation_bytes_read_to_build_this": False,
        "oos_bytes_read_to_build_this": False,
        "phase3c_semantics_modified": False,
        "all_identities_from_git_blobs": True,
    },
    "grants": "NOTHING. A package awaiting the replacement opening ruling.",
}


def main() -> None:
    PACKAGE["record_identity_sha256"] = hashlib.sha256(_canonical(PACKAGE)).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3C_ValidationExecutionPackage_v1.0.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(PACKAGE))
    print(json.dumps({
        "package_identity": PACKAGE["record_identity_sha256"],
        "materializer": PACKAGE["materializer"]["sha256"],
        "phase3c_identity": PHASE3C_IDENTITY,
        "sealed_objects": PACKAGE["input_contract"]["validation_sealed_inputs"]["count"],
        "reference_objects": PACKAGE["input_contract"]["reference_inputs"]["count"],
    }, indent=1))


if __name__ == "__main__":
    main()
