"""MR-002 Phase 3C — the separate EXECUTION AUTHORIZATION record.

This is the ONLY artifact that carries authority. It changes execution_authorized from false to
true. It rewrites nothing: the validation package v2.0 and the sealed countersignature are left
byte-unchanged so their sealed identities survive.

It adds NO implementation, runtime, numerical, economic, data or gate semantics. It authorizes
exactly one indivisible Phase 3C validation execution under the already-defined 6+4 sequence.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
REV = "HEAD"

E = "docs/implementation/evidence/mr_002/"
CS = E + "MR002_Phase3C_ExecutionCountersignature_v1.0_DRAFT.json"
PKG = E + "MR002_Phase3C_ValidationExecutionPackage_v2.0.json"
CUSTODY = E + "MR002_Phase3C_RuntimeCompositionCustodyEvidence_v1.0.json"


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob_sha(path: str) -> str:
    out = subprocess.run(["git", "-C", REPO, "show", f"{REV}:{path}"], capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"not committed: {path}")
    return hashlib.sha256(out.stdout).hexdigest()


def bound(path: str) -> dict:
    out = {"path": path, "file_blob_sha256": blob_sha(path)}
    with open(os.path.join(REPO, path), "rb") as fh:
        doc = json.loads(fh.read())
    if "record_identity_sha256" in doc:
        out["record_identity_sha256"] = doc["record_identity_sha256"]
    return out


AUTH = {
    "record_type": "MR002_PHASE3C_EXECUTION_AUTHORIZATION",
    "version": "1.0",
    "produced_at": "2026-08-18T00:00:00Z",
    "authorized_by": "owner ruling 2026-08-18",

    "execution_authorized": True,
    "what_this_changes": (
        "authority ONLY: execution_authorized false -> true. Nothing else. No implementation, "
        "runtime, numerical, economic, data or gate semantics is added, altered or reinterpreted "
        "by this record."
    ),
    "what_this_does_not_do": [
        "it does NOT rewrite the validation package v2.0",
        "it does NOT rewrite the sealed countersignature",
        "it does NOT change the 6+4 input contract",
        "it does NOT change Phase 3C, Stage-3, cost, borrow, exit, fold, construction or "
        "reduction semantics",
        "it does NOT change the validation gates or the verdict domain",
        "it does NOT authorize any OOS access",
    ],

    "sealed_countersignature": {
        **bound(CS),
        "countersignature_id": "MR002_Phase3C_ExecutionCountersignature_v1.0",
        "sealed_by": "owner ruling 2026-08-18",
        "sealed_at_pushed_checkpoint": "4988e4457bac9bc410688c9eeb59151bfdc7581d",
        "filename_note": (
            "the file retains its _DRAFT name and its internal status string, deliberately. The "
            "owner sealed the exact draft identity 109da07f..., and renaming or editing the file "
            "would change that identity and break the seal. The seal is carried HERE, by "
            "reference, not by mutating the sealed artifact."
        ),
    },
    "validation_execution_package": bound(PKG),
    "composition_custody_evidence": bound(CUSTODY),
    "pushed_checkpoint": "4988e4457bac9bc410688c9eeb59151bfdc7581d",

    "authorizes": {
        "scope": "EXACTLY ONE indivisible Phase 3C validation execution",
        "sequence": [
            "1. 6 sealed validation reads through the governed validation reader",
            "2. ValidationOpenedObjectLedger entries for those reads",
            "3. 4 identity-bound reference reads under their existing reference authority",
            "4. deterministic 10-table DuckDB materialization",
            "5. immediate frozen A/B/C Phase 3C replay -- no inspection interval",
            "6. validation decision",
            "7. containment restoration",
        ],
        "indivisible": True,
        "why_indivisible": (
            "materialization itself reveals the sealed validation data, so there is no "
            "materialize-now-replay-later split and no manual inspection interval"
        ),
        "sealed_objects_consuming_the_opening": 6,
        "reference_objects_not_consuming_the_opening": 4,
        "runs": 1,
        "automatic_replacement_opening_on_stop": False,
    },

    "prohibited": [
        "any OOS read",
        "Sharpe >= 0.70 evaluation",
        "stationary bootstrap",
        "DSR",
        "OOS cost-stress gates",
        "parameter tuning",
        "changing A/B/C, exits, reduction mechanics, costs, borrow, folds or gates",
        "solver tolerance/epsilon change, jitter, third attempt, fallback by analogy",
        "retrying with a modified package",
        "manual inspection followed by a second validation run",
    ],

    "economic_decision_unchanged": {
        "VALIDATION_ADVANCE_REQUEST": (
            "Config B >= 3 of 5 folds net-positive AND Config A cumulative net return > 0 AND "
            "Config C cumulative net return > 0 AND replay integrity admissible"
        ),
        "otherwise": ["VALIDATION_DO_NOT_ADVANCE", "VALIDATION_INCONCLUSIVE",
                      "INTEGRITY_FAILURE"],
        "not_an_oos_pass": (
            "VALIDATION_ADVANCE_REQUEST authorizes only returning for the separate decision "
            "whether to open the OOS seal"
        ),
        "config_C_sparsity": "disclose; do NOT reinterpret after seeing the result",
    },

    "pre_release_requirement": {
        "rule": (
            "before the latch may move from canonical explicitDeny to the authorized "
            "validation-read state, this record must reproduce from PUSHED Git and the complete "
            "pre-release preflight must pass again"
        ),
        "preflight": [
            "this authorization record and the sealed countersignature re-derive from pushed Git",
            "validation package record identity and file blob unchanged",
            "pushed checkpoint resolves and is an ancestor of the ref",
            "Phase 3C identity 6fe8ed33... unchanged",
            "three typed runtime identities reproduce on the authorized host",
            "dependency bundle v1.2 inventory reproduces; read-only mount; correct PYTHONPATH",
            "boto3 and governed-reader import succeed in the exact host composition, offline",
            "native stack unshadowed at the bound versions; frozen thread environment intact",
            "materialization destination fresh",
            "6 sealed + 4 reference declarations match the package exactly",
            "IAM latch still canonical 44f5549a... / explicitDeny immediately before release",
        ],
        "on_any_difference": "STOP WITHOUT OPENING",
    },

    "no_sealed_byte_before_latch_release": (
        "no sealed validation or OOS byte may be read before the latch opens, and none has been"
    ),
    "grants": (
        "ONE indivisible Phase 3C validation execution, under the sealed countersignature and the "
        "bound package. NOTHING else. OOS remains prohibited."
    ),
}

AUTH["record_identity_sha256"] = hashlib.sha256(_canonical(AUTH)).hexdigest()
out = os.path.join(_HERE, "MR002_Phase3C_ExecutionAuthorization_v1.0.json")
with open(out, "wb") as fh:
    fh.write(_canonical(AUTH))
print(json.dumps({
    "authorization_record": AUTH["record_identity_sha256"],
    "execution_authorized": AUTH["execution_authorized"],
    "sealed_countersignature_record_identity":
        AUTH["sealed_countersignature"].get("record_identity_sha256"),
    "package_record_identity":
        AUTH["validation_execution_package"].get("record_identity_sha256"),
}, indent=1))
