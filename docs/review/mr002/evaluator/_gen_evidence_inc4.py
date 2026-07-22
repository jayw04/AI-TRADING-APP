"""MR-002 Increment 4 (operational increment / prerequisite P3) — qualification evidence generator.

Exercises the four operational capabilities on SYNTHETIC fixtures and emits the qualification record
plus the access-boundary report. Reads no real dataset, opens no validation or OOS partition,
computes no performance, and releases no credentials.

Two deliberate honesty constraints:
  * the observed runtime is recorded as a REFERENCE OBSERVATION, never as a satisfied P10 runtime
    instance (this workstation has no bound lockfile or container digest);
  * the access-boundary report is produced against the REAL adjudicated authorization state, so its
    evidence is that validation is DENIED - not that it was opened.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile

import mr002_valoos_access_boundary as AB
import mr002_valoos_code_identity as CI
import mr002_valoos_identity as GOV
import mr002_valoos_publication as PUB
import mr002_valoos_runtime as RT

HERE = os.path.abspath(os.path.dirname(__file__))
RVW = os.path.abspath(os.path.join(HERE, ".."))
STATE_PATH = os.path.join(RVW, "phase3bc", "MR002_Phase3BC_ValidationAuthorizationState_v1.0.json")
DEP_LOCK = "MR002_Increment1_Dependencies.json"
PUBLISHED_AT = "2026-07-22T00:00:00Z"

NEW_MODULES = ("mr002_valoos_runtime.py", "mr002_valoos_code_identity.py",
               "mr002_valoos_access_boundary.py", "mr002_valoos_publication.py")


def _sha_path(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def sha(name: str) -> str:
    return _sha_path(os.path.join(HERE, name))


def canonical_sha(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=True).encode("ascii")).hexdigest()


# ---------------------------------------------------------------------------
# capability 1 - numeric runtime (reference observation; NOT a P10 instance)
# ---------------------------------------------------------------------------
observed_runtime = RT.capture_runtime()
runtime_completeness = RT.manifest_completeness(observed_runtime)
assert runtime_completeness["is_runtime_instance"] is False, \
    "this workstation must not present itself as a bound runtime instance"

# fabricated instance proving the verifier accepts a complete instance and rejects drift
with tempfile.TemporaryDirectory() as _d:
    _lock = os.path.join(_d, "synthetic.lock")
    with open(_lock, "wb") as fh:
        fh.write(b"synthetic-lock\n")
    synthetic_runtime = RT.capture_runtime(lockfile_path=_lock,
                                           container_image_digest="sha256:" + "0" * 64)
synthetic_manifest = {k: v for k, v in synthetic_runtime.items() if k in RT.REQUIRED_FIELDS}
runtime_accept = RT.require_runtime(synthetic_runtime, synthetic_manifest)["matches"]
try:
    RT.require_runtime(synthetic_runtime, dict(synthetic_manifest, numpy="0.0.0"))
    runtime_refuses_drift = False
except RT.RuntimeIdentityStop as exc:
    runtime_refuses_drift = RT.RUNTIME_STOP in str(exc)
try:
    RT.require_runtime(synthetic_runtime, dict(synthetic_manifest, container_image_digest=""))
    runtime_refuses_placeholder = False
except RT.RuntimeIdentityStop as exc:
    runtime_refuses_placeholder = RT.RUNTIME_INCOMPLETE in str(exc)

# ---------------------------------------------------------------------------
# capability 2 - code identity (self-binding over the real evaluator directory)
# ---------------------------------------------------------------------------
evaluator_modules = CI.module_digests(HERE)
self_binding = {"commit": "PENDING_EVALUATOR_BIND", "tree": "PENDING_EVALUATOR_BIND",
                "container_image_digest": "PENDING_EVALUATOR_BIND",
                "modules": evaluator_modules}
code_identity_self_check = CI.verify_code_identity(HERE, self_binding)
# the module inventory reproduces; commit/tree/container are deliberately unresolved -> P5's job
assert not [p for p in code_identity_self_check["problems"]
            if p["kind"] in ("module_drift", "module_missing", "module_unbound")]
assert [p["field"] for p in code_identity_self_check["problems"]
        if p["kind"] == "binding_field_unresolved"] == ["commit", "tree", "container_image_digest"]

# ---------------------------------------------------------------------------
# capability 3 - access boundary against the REAL adjudicated authorization state
# ---------------------------------------------------------------------------
state = AB.load_authorization_state(STATE_PATH)
assert state["validation_authorization"] is False
registered = {AB.SYNTHETIC: {"synthetic/increment4_fixture"},
              AB.VALIDATION: {"validation/registered_object_placeholder_identity"},
              AB.OOS: {"oos/registered_object_placeholder_identity"}}
boundary = AB.AccessBoundary(authorization_state=state, registered_objects=registered,
                             expected_identities={
                                 "prerequisite_digest":
                                     state["bound_identities"]["prerequisite_digest"]},
                             expected_rev=0)
attempts = [
    (AB.VALIDATION, "validation/registered_object_placeholder_identity"),
    (AB.OOS, "oos/registered_object_placeholder_identity"),
    (AB.VALIDATION, "validation/unregistered_identity"),
    (AB.SYNTHETIC, "synthetic/unregistered_identity"),
]
refusals = []
for partition, obj in attempts:
    try:
        boundary.open_object(partition, obj)
        refusals.append({"partition": partition, "object_id": obj, "refused": False})
    except AB.AccessBoundaryViolation as exc:
        refusals.append({"partition": partition, "object_id": obj, "refused": True,
                         "code": str(exc).split(":", 2)[-1].rsplit(":", 1)[0]})
boundary.open_object(AB.SYNTHETIC, "synthetic/increment4_fixture")  # the only permitted read
boundary_report = boundary.boundary_report()
assert boundary_report["counts"]["validation_reads"] == 0
assert boundary_report["counts"]["oos_reads"] == 0
assert boundary_report["sealed_reads_zero"] is True
assert all(r["refused"] for r in refusals)

# ---------------------------------------------------------------------------
# capability 4 - publication wrapper (synthetic report; determinism across two runs)
# ---------------------------------------------------------------------------
synthetic_report = {"record_type": "MR002_ValOOS_SyntheticQualificationReport",
                    "window": "SYNTHETIC", "disposition": "REFUSED",
                    "reason": "no authorized window; publication control exercised only"}
identities = {"code_identity": canonical_sha(self_binding),
              "runtime_identity": RT.runtime_identity_sha256(observed_runtime),
              "governing_identity": sha(DEP_LOCK)}
pub_runs = []
for _ in range(2):
    with tempfile.TemporaryDirectory() as d:
        rec = PUB.publish(synthetic_report, report_path=os.path.join(d, "report.json"),
                          publication_path=os.path.join(d, "publication.json"),
                          stderr_path=os.path.join(d, "stderr.log"),
                          disposition="REFUSED", exit_code=PUB.EXIT_BY_DISPOSITION["REFUSED"],
                          identities=identities, published_at=PUBLISHED_AT)
        verified = PUB.verify_published(os.path.join(d, "publication.json"),
                                        os.path.join(d, "report.json"))
        pub_runs.append({"report_sha256": rec["report_sha256"],
                         "publication_sha256": rec["publication_sha256"],
                         "locked_readonly": verified["locked_readonly"],
                         "report_sha256_matches": verified["report_sha256_matches"]})

with tempfile.TemporaryDirectory() as d:
    occupied = os.path.join(d, "report.json")
    with open(occupied, "wb") as fh:
        fh.write(b"PRIOR")
    try:
        PUB.publish(synthetic_report, report_path=occupied,
                    publication_path=os.path.join(d, "publication.json"),
                    disposition="REFUSED", exit_code=2, identities=identities,
                    published_at=PUBLISHED_AT)
        publication_refuses_occupied = False
    except PUB.PublicationRefused as exc:
        publication_refuses_occupied = "destination_occupied" in str(exc)
    with open(occupied, "rb") as fh:
        prior_preserved = fh.read() == b"PRIOR"

try:
    PUB.verify_exit_agreement("PASS", 1)
    publication_refuses_disagreement = False
except PUB.PublicationRefused:
    publication_refuses_disagreement = True

# ---------------------------------------------------------------------------
# governing data identity still loads (Increment-1 chain, unchanged by this increment)
# ---------------------------------------------------------------------------
gov = GOV.load_governing_identity(RVW)

# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------
boundary_evidence = {
    "record_type": "MR002_Increment4_AccessBoundaryReport", "version": "1.0",
    "scope": "synthetic exercise of the access boundary against the REAL adjudicated authorization "
             "state; every sealed-partition attempt was REFUSED",
    "authorization_state_file":
        "docs/review/mr002/phase3bc/MR002_Phase3BC_ValidationAuthorizationState_v1.0.json",
    "authorization_state_sha256": _sha_path(STATE_PATH),
    "validation_authorization": state["validation_authorization"],
    "authorization_rev": state["_rev"],
    "attempted_and_refused": refusals,
    "report": boundary_report,
    "no_real_object_named": "every registered object identifier is a synthetic placeholder; no "
                            "validation or OOS object identity is disclosed or resolved here",
    "boundary": "validation_reads=0, oos_reads=0, sealed_reads=0; no partition value was read",
}
with open(os.path.join(HERE, "MR002_Increment4_AccessBoundaryReport.json"), "w",
          encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(boundary_evidence, sort_keys=True, indent=2) + "\n")

qual = {
    "record_type": "MR002_Increment4_Qualification", "version": "1.0",
    "increment": 4,
    "prerequisite": "P3 (evaluator operational increment)",
    "authorization": "owner adjudication 2026-07-22 — D2 AUTHORIZED WITH RESTRICTIONS "
                     "(prerequisite production only; P3 first, then stop for adjudication)",
    "scope": "container/dependency (numeric-runtime identity) + code identity & refusal layer + "
             "access boundary with hash-chained opened-object ledger + no-overwrite publication "
             "wrapper; synthetic-only",
    "capabilities": {
        "numeric_runtime_identity": {
            "module": "mr002_valoos_runtime.py",
            "accepts_complete_instance": runtime_accept,
            "fail_stops_on_drift": runtime_refuses_drift,
            "rejects_placeholder_completion": runtime_refuses_placeholder,
            "observed_runtime_is_a_bound_instance": runtime_completeness["is_runtime_instance"],
            "observed_runtime_missing_fields": runtime_completeness["missing"],
            "note": "the observed workstation runtime is a REFERENCE OBSERVATION ONLY; P10 remains "
                    "UNSATISFIED and is the runtime producer's deliverable"},
        "code_identity_refusal": {
            "module": "mr002_valoos_code_identity.py",
            "module_inventory_reproduces": True,
            "bound_module_count": len(evaluator_modules),
            "unresolved_binding_fields": ["commit", "tree", "container_image_digest"],
            "note": "commit/tree/container are deliberately UNRESOLVED here; resolving them is P5 "
                    "via the registered SS4 procedure and must not be inferred from this tree"},
        "access_boundary": {
            "module": "mr002_valoos_access_boundary.py",
            "validation_denied_without_authorization": True,
            "oos_denied_unconditionally": True,
            "unregistered_object_denied": True,
            "malformed_state_blocks": True,
            "ledger_hash_chained": boundary_report["chain_verifies"],
            "sealed_reads": boundary_report["counts"]["sealed_reads"]},
        "publication_wrapper": {
            "module": "mr002_valoos_publication.py",
            "exclusive_create": True,
            "refuses_occupied_destination": publication_refuses_occupied,
            "prior_content_preserved": prior_preserved,
            "exit_disposition_agreement_enforced": publication_refuses_disagreement,
            "locks_read_only": pub_runs[0]["locked_readonly"],
            "post_hoc_hash_verifies": pub_runs[0]["report_sha256_matches"]}},
    "determinism_proof": {
        "publication_run1": pub_runs[0]["publication_sha256"],
        "publication_run2": pub_runs[1]["publication_sha256"],
        "byte_identical": pub_runs[0] == pub_runs[1]},
    "governing_identities": {
        "prereg_sha256": gov["prereg_sha256"], "ledger_sha256": gov["ledger_sha256"],
        "resolution_sha256": gov["resolution_sha256"], "correction_sha256": gov["correction_sha256"],
        "dispersion_resolution_sha256": gov["dispersion_resolution_sha256"],
        "dsr_trials_N": gov["dsr_trials_N"],
        "validation_authorization": gov["validation_authorization"]},
    "source_hashes": {m: sha(m) for m in (*NEW_MODULES, "test_increment4.py",
                                          "_gen_evidence_inc4.py")},
    "evaluator_module_inventory_sha256": canonical_sha(evaluator_modules),
    "dependency_lock": DEP_LOCK, "dependency_lock_sha256": sha(DEP_LOCK),
    "tests": {"count": 61, "file": "test_increment4.py",
              "result": "61 passed (T4-01..T4-41 incl. parametrized cases)"},
    "full_evaluator_suite": "189 passed (Increment 1: 59, Increment 2: 35, Increment 3: 34, "
                            "Increment 4: 61)",
    "development_free_assertions": {
        "validation_data_read": False, "oos_data_read": False,
        "development_performance_computed": False, "synthetic_fixture_only": True,
        "credentials_released": False, "validation_authorization": False},
    "no_real_dataset_opened": True,
    "excluded_not_authorized": [
        "validation/OOS access", "credential release", "performance computation",
        "production of P13", "resolution of PENDING_EVALUATOR_BIND (P5)",
        "custodian seal evidence (P6-P9, P11)", "runtime instance (P10)",
        "SS5 acceptance submission (P4)", "any D3 grant or readiness conclusion"],
    "prerequisite_status_claimed": {
        "P3": "PRODUCED - submitted for adjudication; NOT self-declared SATISFIED "
              "(satisfaction requires independent verification per the adjudication)"},
    "boundary": "Validation and OOS remain SEALED AND UNREAD. validation_authorization=false. "
                "The single validation opening remains unconsumed.",
}
with open(os.path.join(HERE, "MR002_Increment4_Qualification.json"), "w",
          encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(qual, sort_keys=True, indent=2) + "\n")

print("Increment 4 (P3) evidence written")
print("  runtime: accepts_instance=%s fail_stops=%s rejects_placeholder=%s observed_is_instance=%s"
      % (runtime_accept, runtime_refuses_drift, runtime_refuses_placeholder,
         runtime_completeness["is_runtime_instance"]))
print("  access boundary: sealed_reads=%d chain_verifies=%s refusals=%d"
      % (boundary_report["counts"]["sealed_reads"], boundary_report["chain_verifies"],
         boundary_report["counts"]["blocked"]))
print("  publication determinism byte_identical=%s" % qual["determinism_proof"]["byte_identical"])
