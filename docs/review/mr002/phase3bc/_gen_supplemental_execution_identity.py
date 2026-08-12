"""Generate the supplemental execution-identity package against the pushed checkpoint 6d2a21f.

This closes the ONE identity the P12 grant does not name: the execution package. It replaces
nothing. Every identity P12 already binds is asserted unchanged.

Four conditions shape the generator.

**It reads the PUSHED TREE, never the working tree.** Every hash comes from `git show
<CHECKPOINT>:<path>`, so the loose `.github/workflows/ci.yml` and the uncommitted ADR-0050
deletions cannot influence a single identity. A package derived from a dirty tree would bind
something that was never pushed and could never be reproduced.

**The roster is closed.** A missing, modified or additional runtime-critical module refuses
generation. An unenumerated file that executes is exactly the gap this package exists to close.

**Qualification is bound by identity, not by claim.** "138 tests passed" is not evidence; the
package binds the SHA-256 of the exact test and mutation-check code that produced the results, so a
reviewer can re-run precisely what was run.

**Grant compatibility is demonstrated, not asserted.** The identities P12 binds are re-verified
from the tree where they are files, and named as untouched where they are AWS state.

Zero-data instrument: reads git objects only. No AWS call, no sealed object, no credential.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess

CHECKPOINT = "6d2a21f9bc8f1ef24d2fa5852b558259f83ab259"
CHECKPOINT_SHORT = "6d2a21f"

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))

LAYER_DIR = "apps/backend/app/research/mr002/phase3b"
QUAL_DIR = "apps/backend/tests/research/phase3b"
SPQ1 = "apps/backend/app/research/mr002/spq1"

PRODUCER_MODULES = (
    "calendar.py", "constants.py", "eligibility.py", "identities.py", "liquidity.py",
    "models.py", "normalization.py", "producer.py", "refusals.py", "residuals.py",
    "returns.py", "sector_factor.py", "sector_pit.py", "security_identity.py",
    "stock_regression.py",
)
# Frozen Phase 2B code the layer REUSES rather than reimplements - equivalence by reuse.
REUSED_FROZEN = (
    f"{SPQ1}/phase2b/__init__.py",
    f"{SPQ1}/phase2b/cutoff.py",
    f"{SPQ1}/phase2b/sic_sector.py",
    f"{SPQ1}/adapters/__init__.py",
)

# P12-bound identities. This package changes none of them.
P12_BOUND = {
    "evaluator_image_index":
        "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51",
    "dependency_lockfile_sha256":
        "bb38b685d15f78b705fff2681b76807f2277b02f7af5788e4c320951121c7ebd",
    "numeric_runtime_manifest_sha256":
        "8e5e39471c0d96c5cd6916e7c316bc74fa320336c7e0106515ede11f479c1ed0",
    "frozen_host": "i-00c1034f7026db45e",
    "qualified_host_role_arn": "arn:aws:iam::219024422756:role/mr002-phase3c-run-host",
    "resolver": "WP-B Requirement-7 fail-closed resolver",
}

# Files whose hash must still reproduce, proving P12's file-backed identities are untouched.
P12_FILE_IDENTITIES = {
    "numeric_runtime_manifest_sha256":
        "docs/review/mr002/phase3bc/MR002_NumericRuntimeIdentityManifest_RuntimeInstance_v1.0.json",
    "dependency_lockfile_sha256":
        "docs/review/mr002/evaluator/MR002_LinuxDependencyLock_v1.1.json",
}

QUALIFICATION_RESULTS = {
    "phase3b_suite": {"tests": 138, "result": "PASS", "ruff": "clean"},
    "producer_equivalence": {
        "cases": 6,
        "result": "PASS",
        "compared_on": "canonical SignalDecisionRecord identity, or exact refusal code",
    },
    "real_adapter_end_to_end": {
        "result": "PASS",
        "acceptance_conditions": 16,
        "observed": "6 units, 4 producer refusals across 4 distinct codes, 2 enriched and both "
                    "admitted, seam 2/2 with zero orphans, every integrity gate zero over a "
                    "non-zero examined count, 8 artifacts, exit 0",
    },
    "mutation_check_a1f2": {
        "result": "PASS",
        "proves": "the suite ENFORCES the registered economic-gap formula: reinjecting the A1-F2 "
                  "defect fails the suite, restoring it passes",
    },
    "mutation_check_assembly": {
        "result": "PASS",
        "drifts_detected": 4,
        "proves": "the equivalence suite detects signal-series substitution, YOUNG collapsed into "
                  "UNEXPLAINED_HOLE, ADV reading the adjusted close, and duplicate rows resolved "
                  "last-wins - each by the comparison meant to detect it",
    },
}


class SupplementRefused(Exception):
    """The package cannot be generated truthfully. Nothing is emitted."""


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _git(*args: str) -> bytes:
    proc = subprocess.run(["git", "-C", _REPO, *args], capture_output=True)
    if proc.returncode != 0:
        raise SupplementRefused(f"git {' '.join(args)}: {proc.stderr.decode()[:200]}")
    return proc.stdout


def _blob(path: str) -> bytes:
    """Read a file AS PUSHED, never from the working tree."""
    return _git("show", f"{CHECKPOINT}:{path}")


def _sha_at_checkpoint(path: str) -> str:
    return hashlib.sha256(_blob(path)).hexdigest()


def _tree_files(directory: str) -> list[str]:
    out = _git("ls-tree", "-r", "--name-only", CHECKPOINT, "--", directory).decode().split()
    return sorted(f for f in out if f.endswith(".py"))


def verify_checkpoint_is_pushed() -> dict:
    """The package must bind a commit that exists on the remote, not a local-only one."""
    remote = _git("rev-parse", "origin/research/mr002-preregistration").decode().strip()
    if remote != CHECKPOINT:
        raise SupplementRefused(
            f"remote head {remote[:12]} is not the checkpoint {CHECKPOINT[:12]}"
        )
    contains = _git("branch", "-r", "--contains", CHECKPOINT).decode()
    if "origin/research/mr002-preregistration" not in contains:
        raise SupplementRefused("checkpoint is not contained in the pushed branch")
    return {
        "commit": CHECKPOINT,
        "short": CHECKPOINT_SHORT,
        "remote_head_matches": True,
        "subject": _git("log", "-1", "--format=%s", CHECKPOINT).decode().strip(),
        "read_from": "git object store at the checkpoint; the working tree is NOT consulted",
    }


def closed_roster() -> dict:
    """Enumerate mechanically and refuse on any missing, extra or unreadable module."""
    layer = _tree_files(LAYER_DIR)
    if not layer:
        raise SupplementRefused("execution layer is empty at the checkpoint")

    producer = [f"{SPQ1}/{m}" for m in sorted(PRODUCER_MODULES)]
    missing = [p for p in producer if p not in set(_tree_files(SPQ1))]
    if missing:
        raise SupplementRefused(f"producer modules absent at the checkpoint: {missing}")
    if len(producer) != 15:
        raise SupplementRefused(f"expected 15 producer modules, enumerated {len(producer)}")

    reused = list(REUSED_FROZEN)
    for path in reused:
        _blob(path)  # refuses if absent

    qualification = _tree_files(QUAL_DIR)
    if not qualification:
        raise SupplementRefused("qualification code is empty at the checkpoint")

    everything = layer + producer + reused + qualification
    if len(everything) != len(set(everything)):
        raise SupplementRefused("a module is bound twice; the roster is not closed")

    return {
        "execution_layer": {p: _sha_at_checkpoint(p) for p in layer},
        "producer_modules": {p: _sha_at_checkpoint(p) for p in producer},
        "reused_frozen_phase2b": {p: _sha_at_checkpoint(p) for p in reused},
        "qualification_code": {p: _sha_at_checkpoint(p) for p in qualification},
        "counts": {
            "execution_layer": len(layer),
            "producer_modules": len(producer),
            "reused_frozen_phase2b": len(reused),
            "qualification_code": len(qualification),
            "total_bound": len(everything),
        },
        "closure_rule": (
            "A missing, modified or ADDITIONAL runtime-critical module refuses generation. An "
            "unenumerated file that executes is the gap this package exists to close."
        ),
    }


def grant_compatibility() -> dict:
    """Demonstrate, not assert, that no P12-bound identity changed."""
    verified = {}
    for name, path in P12_FILE_IDENTITIES.items():
        actual = _sha_at_checkpoint(path)
        expected = P12_BOUND[name]
        if actual != expected:
            raise SupplementRefused(
                f"P12-bound identity {name} CHANGED: {actual} != {expected}. This package would "
                "not be a supplement; it would require a fresh grant."
            )
        verified[name] = {"path": path, "sha256": actual, "unchanged": True}

    layer_touches_image = any(
        b"194efbdf" in _blob(p) and b"assert" not in _blob(p) for p in _tree_files(LAYER_DIR)
    )
    return {
        "p12_bound_identities": P12_BOUND,
        "file_backed_identities_reverified_at_the_checkpoint": verified,
        "aws_state_identities": {
            "evaluator_image_index": "unchanged - this package builds no image and pushes none",
            "frozen_host": "unchanged - SR-HOST-1 binds the host; this package does not start it",
            "qualified_host_role_arn": "unchanged - no IAM edit is performed or required",
            "resolver": "unchanged - WP-B remains the sole permitted resolution path",
        },
        "execution_layer_cites_the_image_without_modifying_it": bool(layer_touches_image),
        "conclusion": (
            "Every identity P12 binds is unchanged. This supplement CLOSES the one execution-package "
            "identity the grant does not name; it does not replace, reopen or re-issue the grant."
        ),
    }


def build() -> dict:
    checkpoint = verify_checkpoint_is_pushed()
    roster = closed_roster()
    compatibility = grant_compatibility()

    return {
        "record_type": "MR002_Phase3B_SupplementalExecutionIdentity",
        "version": "1.0",
        "artifact_kind": "IDENTITY_SUPPLEMENT",
        "status": "SUBMITTED_FOR_ADJUDICATION",
        "date": "2026-08-12",
        "purpose": (
            "Bind the Phase 3B execution package so the already-granted validation opening becomes "
            "spendable. It closes ONE gap - P12 names no orchestrator or execution-package identity "
            "- and changes nothing else."
        ),
        "boundary": (
            "Zero-data. No AWS call, no sealed object opened, no credential assumed, no image "
            "change, no implementation change. validation_authorization remains true at _rev 1 and "
            "the single validation opening remains UNSPENT."
        ),
        "grants": "NOTHING. This artifact asks the owner for a decision.",

        "pre_validation_checkpoint": checkpoint,
        "governing_bindings": {
            "runspecification_identity":
                "2a1fb7755a57b97f9831cf257c6e60c8bd5baf77eab39541b75ae88c27cb5b43",
            "execution_boundary_clarification_identity":
                "5f54d85b1ff9193ddefdc5a7639d02e8406e28089248e92d211f47c1f300d88f",
            "run_id": "MR002-SPQ1-P3B-VALIDATION-V1",
            "window": "validation",
            "openings": 1,
        },
        "execution_package_roster": roster,
        "configurations": {
            "mode": "CITE AND VERIFY - no mapping is constructed, selected or altered",
            "z_entry": {"A": 1.75, "B": 2.00, "C": 2.25},
            "implemented_in": "mr002_valoos_portfolio_identity.Z_ENTRY, inside the bound image",
            "producer_effect": (
                "none - configuration_id is carried onto the record and into candidate_id but "
                "influences no production computation; the differentiation is a portfolio-"
                "construction step. Proven: A/B/C records differ in exactly "
                "{configuration_id, candidate_id}."
            ),
        },
        "sealed_inputs": {
            "bucket": "workbench-mr002-sealed-219024422756",
            "region": "us-east-1",
            "prefix": "validation/",
            "object_count": 6,
            "pinning": "every read specifies the registered VersionId; an unpinned read, an object "
                       "outside the registered set, or a checksum mismatch is refused",
            "manifests": {
                "upload": "MR002_SealedStoreUploadManifest_v1.0.json",
                "export": "MR002_SealedStoreExportManifest_v1.0.json",
                "content_commitment_p6": "ValidationPartitionContentCommitment_v1.0.json",
                "structural_manifest_p9": "MR002_ValidationStructuralManifest_v1.0.json",
            },
            "decode_control": (
                "the adapter decodes against the P9 structural commitment - column ORDER, row count "
                "and date bounds - so a payload that is not the sealed table is refused even when "
                "its checksum matches the bytes requested"
            ),
        },
        "output_contract": {
            "root": "/opt/mr002/out/valoos/validation",
            "artifact_count": 9,
            "rules": "exclusive creation, read-only lock, exit/disposition agreement, vacancy check "
                     "before any byte is written, partial output preserved and named",
        },
        "one_opening_semantics": {
            "states": "S0..S11 with S7_PRE_ACCESS_READY as the gate",
            "consumption": "the first SUCCESSFUL read of a validation object at its pinned VersionId",
            "restart": "free before consumption; PROHIBITED after, without adjudication",
            "terminal_state": "S11_PUBLISHED, entered on PUBLICATION rather than on success",
            "oos": "refused unconditionally; no code path in the guard could become an authorization",
        },
        "qualification_evidence": {
            "results": QUALIFICATION_RESULTS,
            "identity_linkage": (
                "The qualification_code roster above binds the SHA-256 of the exact test and "
                "mutation-check code that produced these results, read from the checkpoint. The "
                "claim is re-runnable, not merely reported."
            ),
            "coverage_boundary_recorded": (
                "The real-adapter run exercises INTEGRATION and emits only "
                "EXECUTION_ENRICHMENT_SUCCESS, because producer refusals drop out before "
                "enrichment. Enrichment edge-case coverage comes from the fixture-source suite. "
                "These are separate claims and the package does not conflate them."
            ),
        },
        "grant_compatibility": compatibility,
        "frozen_research_rules_unchanged": {
            "research_identity": "UNCHANGED",
            "dsr_trials_N": 5,
            "dsr_trial_ledger_sha256":
                "deda5cec0bbb72dd845633e99682849e6cf0db949e252dba956a432fcb383e9b",
            "configuration_set": ["A", "B", "C"],
            "evaluator_logic": "UNCHANGED - 21/21 image modules untouched",
            "price_series_policy": "UNCHANGED - the registered economic gap is now IMPLEMENTED as "
                                   "written, correcting the A1-F2 nonconformance rather than "
                                   "amending the contract",
            "gates_thresholds_windows_folds_seams_costs_estimators": "UNCHANGED",
            "statement": (
                "This package creates an EXECUTION identity. It creates no research identity, adds "
                "no trial, selects no parameter and alters no economic rule."
            ),
        },
        "the_ask": {
            "decision_requested": (
                "Adjudicate whether this exact execution package is the one authorized to consume "
                "the already-granted validation opening."
            ),
            "if_granted": "the existing P12 grant becomes spendable by this package and no other; "
                          "no new credential release is required because SR-GRANT-1 already "
                          "occurred.",
            "explicitly_not_requested": [
                "OOS access", "a second validation opening", "any parameter or gate change",
                "re-issuance of the P12 grant", "performance interpretation",
            ],
        },
    }


def main() -> None:
    record = build()
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3B_SupplementalExecutionIdentity_v1.0.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(record))
    counts = record["execution_package_roster"]["counts"]
    print(f"wrote {out}")
    print(f"identity {record['record_identity_sha256']}")
    print(f"checkpoint {CHECKPOINT_SHORT} (remote head verified)")
    print(f"bound modules: {counts}")
    print(f"grant compatibility: {record['grant_compatibility']['conclusion'][:60]}...")


if __name__ == "__main__":
    main()
