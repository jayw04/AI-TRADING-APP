"""MR-002 — research-side prerequisite closeout record (P3/P4/P5 SATISFIED).

Records the owner's P5 final adjudication and the resulting prerequisite state, and recomputes the
current-state prerequisite digest from the authoritative register.

Deliberately lives OUTSIDE docs/review/mr002/evaluator: adding any .py there would enter the SS4
inventory and invalidate the now-RESOLVED binding.

Writes a record only. It amends nothing, touches no sealed package, creates no authorization event,
and leaves validation_authorization false.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
P3BC = os.path.join(HERE, "phase3bc")
EVAL = os.path.join(HERE, "evaluator")

ANCHOR_COMMIT = "953bda934fbf8619cbcfed28ed09ec8e1a0bc75d"
SATISFIED_NOW = {"P3": "SATISFIED", "P4": "SATISFIED", "P5": "SATISFIED"}


def git(*args) -> str:
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True,
                          check=True).stdout


def sha_file(p) -> str:  # noqa: ANN001
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def canonical_sha(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=True).encode("ascii")).hexdigest()


def load(p) -> dict:  # noqa: ANN001
    return json.loads(Path(p).read_text(encoding="utf-8"))


register = load(os.path.join(P3BC, "MR002_Phase3BC_RuntimePrerequisiteRegister_v1.0.json"))
anchor = load(os.path.join(P3BC, "MR002_Phase3BC_ValidationAuthorizationState_v1.0.json"))
binding = load(os.path.join(EVAL, "MR002_EvaluatorBinding.json"))
image = load(os.path.join(EVAL, "MR002_EvaluatorImageManifest.json"))

adjudicated_statuses = {p["id"]: p["status"] for p in register["prerequisites"]}
current_statuses = dict(adjudicated_statuses, **SATISFIED_NOW)
current_digest = canonical_sha(current_statuses)

assert anchor["validation_authorization"] is False and anchor["_rev"] == 0
assert binding["binding_state"] == "RESOLVED" and binding["unresolved_elements"] == []
sealed_untouched = git("diff", "--name-only", ANCHOR_COMMIT, "HEAD", "--",
                       "docs/review/mr002/phase3a", "docs/review/mr002/phase3bc").strip()
assert sealed_untouched == "", sealed_untouched

record = {
    "record_type": "MR002_ResearchSidePrerequisiteCloseout", "version": "1.0",
    "date": "2026-07-22",
    "adjudication": "owner P5 final adjudication — P5 ACCEPTED, PARTIALLY_RESOLVED -> SATISFIED; "
                    "research-side prerequisite production COMPLETE",
    "governing_binding": {
        "file": "docs/review/mr002/evaluator/MR002_EvaluatorBinding.json",
        "sha256": sha_file(os.path.join(EVAL, "MR002_EvaluatorBinding.json")),
        "binding_commit": "ef5af66090b28ec9841eb60412bbaff05cf9e91c",
        "source_commit": binding["section4_elements"]["source_commit"]["value"],
        "source_tree": binding["section4_elements"]["source_tree"]["value"],
        "container_image_digest":
            binding["section4_elements"]["container_image_digest"]["value"],
        "included_module_count": binding["included_module_count"],
        "binding_state": binding["binding_state"],
        "note": "the count is binding-specific, not a permanent constant; any source change "
                "requires complete re-enumeration and a superseding binding"},
    "superseded_binding": {
        "file": "docs/review/mr002/evaluator/MR002_EvaluatorBinding_superseded_6708c59.json",
        "sha256": sha_file(os.path.join(EVAL,
                                        "MR002_EvaluatorBinding_superseded_6708c59.json")),
        "disposition": "historical evidence; NOT a candidate execution binding"},
    "image_manifest": {
        "file": "docs/review/mr002/evaluator/MR002_EvaluatorImageManifest.json",
        "sha256": sha_file(os.path.join(EVAL, "MR002_EvaluatorImageManifest.json")),
        "image_digest": image["image_digest"], "platform": image["platform"]},
    "prerequisite_state": {
        "P3": "SATISFIED — evaluator operational increment ONLY; establishes no access-path "
              "coverage, no numeric runtime, no readiness",
        "P4": "SATISFIED — SS5 acceptance submission",
        "P5": "SATISFIED — SS4 pre-access evaluator binding (source + roster + container legs)",
        "P6": adjudicated_statuses["P6"], "P7": adjudicated_statuses["P7"],
        "P8": adjudicated_statuses["P8"], "P9": adjudicated_statuses["P9"],
        "P10": "UNSATISFIED — numeric-runtime instance; NO implication from P5 to P10 is granted",
        "P11": adjudicated_statuses["P11"], "P12": adjudicated_statuses["P12"],
        "P13": adjudicated_statuses["P13"]},
    "prerequisite_digest": {
        "current_state_digest": current_digest,
        "derivation": "sha256 of the ascii JSON object {prerequisite_id: status} sorted by key, "
                      "recomputed from the authoritative register with P3/P4/P5 SATISFIED",
        "adjudicated_anchor_digest": anchor["bound_identities"]["prerequisite_digest"],
        "relationship_to_anchor": "CURRENT-STATE ONLY. It does not amend, activate, or satisfy the "
                                  f"historical CAS anchor at {ANCHOR_COMMIT}, which remains bound "
                                  "to its own adjudicated digest",
        "anchor_unmodified": True},
    "authorization_state": {
        "validation_authorization": anchor["validation_authorization"], "_rev": anchor["_rev"],
        "validation_opening": "UNCONSUMED", "validation_partition": "CLOSED", "oos": "UNDER DENY"},
    "sealed_packages_unmodified_since_anchor_commit": True,
    "p5_scope_limits_carried_forward": [
        "instance identity, NOT bit-for-bit build reproducibility — do not claim reproducible "
        "builds, do not rebuild and assume equivalence, do not replace the bound digest with a "
        "later rebuild without a superseding qualification",
        "no numerical library/BLAS/LAPACK/CPU-dispatch/threading/floating-point/seed/determinism "
        "claim; P10 is not implied"],
    "image_custody_requirements_before_p10_or_readiness": [
        "retain the exact image digest in a content-addressable registry",
        "retrieval by digest reproduces the same manifest and configuration objects",
        "record registry location and platform manifest",
        "the image cannot be overwritten under the bound digest",
        "local-only availability must not be mistaken for durable custody",
        "superseded and current bindings remain independently verifiable",
        "the binding resolver fails if the exact image digest is unavailable"],
    "custody_note": "these are custody and availability requirements, NOT permission to begin P10",
    "next_workstreams_not_mine": {
        "P6-P9, P11": "custodian-side evidence",
        "P10": "numeric-runtime producer",
        "P13": "Phase 3C runtime only"},
    "explicitly_not_authorized": [
        "further research-side prerequisite production",
        "grant-readiness verifier", "D3 submission or authorization event",
        "validation or OOS access", "credential release", "performance computation"],
    "governing_disposition": "P5 SATISFIED; research-side prerequisite production COMPLETE; the "
                             "validation partition is closed, the single opening is unconsumed, "
                             "and validation_authorization = false",
}
out = os.path.join(HERE, "MR002_ResearchSidePrerequisiteCloseout_v1.0.json")
Path(out).write_text(json.dumps(record, sort_keys=True, indent=2) + "\n",
                     encoding="utf-8", newline="\n")

print("research-side closeout recorded")
print(f"  P3/P4/P5 SATISFIED; P10 UNSATISFIED; anchor untouched={record['prerequisite_digest']['anchor_unmodified']}")
print(f"  current-state digest {current_digest[:16]}…  (anchor "
      f"{anchor['bound_identities']['prerequisite_digest'][:16]}… unchanged)")
print(f"  binding {binding['binding_state']} image {image['image_digest'][:19]}…")
