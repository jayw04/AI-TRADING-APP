"""SPQ-1 Phase 3B/C — owner adjudication record + durable authorization state (2026-07-22).

Records the owner's adjudication of the Phase 3B/C execution-authorization request at commit
`ea437ce`: D1 ACCEPTED, D2 AUTHORIZED WITH RESTRICTIONS, D3 DENIED WITHOUT PREJUDICE. Also lays down
the durable authorization-state record that a future D3 grant must compare-and-set against.

The adjudicated request package (v1.0 artifacts) is IMMUTABLE and is not modified here; this package
binds it by recomputed SHA-256. `validation_authorization` stays false. No validation or OOS data is
opened and no performance is computed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[4])
OUT = os.path.dirname(os.path.abspath(__file__))
RVW = os.path.join(ROOT, "docs", "review", "mr002")
P3A = os.path.join(RVW, "phase3a")

ADJUDICATED_COMMIT = "ea437ce9355650ab907079fea10243db5599a1a7"
ADJUDICATION_DATE = "2026-07-22"
PREREG_SHA = "b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c"
PHASE3A_FINAL_COMMIT = "f7319de951b6fd7b84112ad2b207d61376399ac1"


def sha_file(p):  # noqa: ANN001
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read_json(p):  # noqa: ANN001
    return json.loads(Path(p).read_text(encoding="utf-8"))


def dump(obj, name):  # noqa: ANN001
    p = Path(OUT) / name
    p.write_text(json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n",
                 encoding="utf-8", newline="\n")
    return sha_file(p)


def dump_md(text, name):  # noqa: ANN001
    p = Path(OUT) / name
    p.write_text(text, encoding="utf-8", newline="\n")
    return sha_file(p)


# ---- bind the adjudicated package by recomputation (it must not have changed) ----
ADJUDICATED = {
    "ExecutionAuthorizationRequest": "MR002_Phase3BC_ExecutionAuthorizationRequest_v1.0.json",
    "RuntimePrerequisiteRegister": "MR002_Phase3BC_RuntimePrerequisiteRegister_v1.0.json",
    "Phase3ALineageProof": "MR002_Phase3BC_Phase3ALineageProof_v1.0.json",
    "ExecutionGateTable": "MR002_Phase3BC_ExecutionGateTable_v1.0.json",
    "DeliverableRegister": "MR002_Phase3BC_DeliverableRegister_v1.0.json",
    "AuthorizationRequestSubmission": "MR002_Phase3BC_AuthorizationRequestSubmission_v1.0.md",
    "PublicationManifest": "MR002_Phase3BC_PublicationManifest_v1.0.json",
}
adjudicated_sha = {k: sha_file(os.path.join(OUT, v)) for k, v in ADJUDICATED.items()}
req_pub = read_json(os.path.join(OUT, ADJUDICATED["PublicationManifest"]))
for name, want in req_pub["artifact_sha256"].items():
    assert adjudicated_sha[name] == want, f"adjudicated package drifted at {name} -> STOP"

register = read_json(os.path.join(OUT, ADJUDICATED["RuntimePrerequisiteRegister"]))
request = read_json(os.path.join(OUT, ADJUDICATED["ExecutionAuthorizationRequest"]))
assert request["validation_authorization"] is False
assert register["grant_readiness"] == "NOT_READY"
blocking_unsatisfied = register["blocking_unsatisfied_ids"]
producible = [i for i in blocking_unsatisfied if i != "P12"]

# digest over the adjudicated prerequisite state - the CAS compares against THIS
prerequisite_digest = hashlib.sha256(json.dumps(
    {p["id"]: p["status"] for p in register["prerequisites"]},
    sort_keys=True).encode("ascii")).hexdigest()

H = {}

# =====================================================================================
# The adjudication record
# =====================================================================================
adjudication = {
    "record_type": "MR002_Phase3BC_AuthorizationAdjudication", "version": "1.0",
    "adjudication_date": ADJUDICATION_DATE, "adjudicator": "OWNER",
    "reference_commit": ADJUDICATED_COMMIT,
    "submission": ADJUDICATED["AuthorizationRequestSubmission"],
    "adjudicated_artifact_sha256": adjudicated_sha,
    "governing_preregistration_sha256": PREREG_SHA,
    "governing_outcome": "D1 ACCEPTED / D2 AUTHORIZED WITH RESTRICTIONS / D3 DENIED WITHOUT PREJUDICE",
    "validation_authorization": False,

    "D1": {
        "verdict": "ACCEPTED",
        "accepts": [
            "reproducibility and integrity of the Phase 3A lineage",
            "accuracy of the current prerequisite status",
            "the conclusion that the package is NOT_READY",
            "the continued fact that validation_authorization = false"],
        "grants": "NOTHING - no validation access, no performance computation, no change to "
                  "validation_authorization",
        "scope_binding": f"limited to the package as it exists at commit {ADJUDICATED_COMMIT}"},

    "D2": {
        "verdict": "AUTHORIZED_WITH_RESTRICTIONS",
        "authorizes": "the named custodians, evaluator producer, and runtime producer to CREATE and "
                      "VERIFY the P3-P11 prerequisite artifacts within their preregistered "
                      "responsibilities",
        "authorized_prerequisite_ids": producible,
        "character": "PREREQUISITE_PRODUCTION - explicitly NOT the beginning of Phase 3B or 3C",
        "permitted": [
            "each producer creates ONLY its named artifact",
            "using information available WITHOUT validation access",
            "runtime evidence produced PROSPECTIVELY"],
        "prohibited": [
            "opening, reading, querying, sampling, summarizing, or indirectly inferring "
            "validation-partition values",
            "computing model performance",
            "resolving P13 early",
            "changing the preregistered evaluator, model identity, acceptance criteria, trial "
            "design, or structural bindings",
            "substituting retrospective documents for runtime-produced evidence",
            "specification templates, retrospective attestations, inferred state, or placeholder "
            "completion as runtime evidence",
            "beginning Phase 3B or Phase 3C execution"],
        "incompletable_rule": "any prerequisite that cannot be TRUTHFULLY completed without opening "
                              "the partition MUST remain unresolved - never populated with "
                              "placeholders, assumptions, or retrospective attestations",
        "custodian_rule": "P6/P7/P8 must be ACTUAL RUNTIME INSTANCES; the Phase 3A specification "
                          "templates cannot serve as evidence that the partition has remained "
                          "unopened",
        "evaluator_bind_rule": "PENDING_EVALUATOR_BIND must be resolved through the precommitted "
                               "EvaluatorQualificationPlan SS4 process BEFORE any validation "
                               "access; it may NOT be silently replaced, inferred from the current "
                               "code tree, or resolved as part of the authorization event",
        "p13_rule": "P13 remains ABSENT until Phase 3C produces the registered trial-dispersion "
                    "evidence; its intentional absence does not block D2 but blocks any final "
                    "conclusion that requires it"},

    "D3": {
        "verdict": "DENIED_WITHOUT_PREJUDICE",
        "reason": f"only {register['counts']['blocking_satisfied']} of "
                  f"{register['counts']['blocking']} blocking prerequisites are satisfied; granting "
                  "now would be premature and would undermine the pre-access control structure",
        "consequences": [
            "the validation partition remains closed",
            "the single validation opening remains UNCONSUMED",
            "validation_authorization remains false"],
        "readmission_requires_one_closed_verification_run_demonstrating": [
            "C1 every blocking prerequisite other than the authorization event itself is satisfied",
            "C2 P3-P11 are runtime-produced, identity-bound, and hash-bound",
            "C3 the EvaluatorQualificationPlan SS5 acceptance submission is complete and accepted",
            "C4 the SS4 pre-access evaluator binding is resolved",
            "C5 the structural manifest is precommitted and reproduces exactly",
            "C6 the numeric-runtime instance is sealed and reproducible",
            "C7 access-control preconditions prove that no prior validation opening occurred",
            "C8 Phase 3A lineage still reproduces from the then-current tree",
            "C9 zero evaluator drift and zero unbound evaluator code",
            "C10 validation_authorization remains false until the explicit D3 grant event is "
            "durably recorded"],
        "verifier_status": "NOT_BUILT - the closed grant-readiness verification run is part of a "
                           "future D3 submission, not of this adjudication"},

    "oos": "OUT OF SCOPE and under DENY; a sealed OOS run requires a further separate authorization "
           "after an accepted validation outcome",
    "boundary": "Validation and OOS remain SEALED AND UNREAD. No returns, PnL, Sharpe, DSR, "
                "ranking, or verdict exists or is produced by this adjudication.",
}
H["AuthorizationAdjudication"] = dump(
    adjudication, "MR002_Phase3BC_AuthorizationAdjudication_v1.0.json")

# =====================================================================================
# Durable authorization state (the CAS anchor)
# =====================================================================================
state = {
    "record_type": "MR002_Phase3BC_ValidationAuthorizationState", "version": "1.0",
    "validation_authorization": False,
    "_rev": 0,
    "state_established_by": f"owner adjudication {ADJUDICATION_DATE} (D3 DENIED WITHOUT PREJUDICE)",
    "adjudication_sha256": H["AuthorizationAdjudication"],
    "bound_identities": {
        "authorization_request_sha256": adjudicated_sha["ExecutionAuthorizationRequest"],
        "prerequisite_register_sha256": adjudicated_sha["RuntimePrerequisiteRegister"],
        "publication_manifest_sha256": adjudicated_sha["PublicationManifest"],
        "prerequisite_digest": prerequisite_digest,
        "prerequisite_digest_definition": "sha256 of the ascii JSON object {prerequisite_id: status} "
                                          "sorted by key, taken from the adjudicated register",
        "governing_preregistration_sha256": PREREG_SHA,
        "phase3a_final_correction_commit": PHASE3A_FINAL_COMMIT,
        "reference_commit": ADJUDICATED_COMMIT},
    "transition_rule": {
        "operation": "COMPARE_AND_SET",
        "from": False, "to": True, "expected_rev": 0,
        "fail_closed_on_mismatch_of": [
            "stored validation_authorization state",
            "stored _rev",
            "prerequisite digest",
            "code identity (evaluator + SignalDecisionRecord module)",
            "manifest identity (publication manifest)",
            "authorization-request identity"],
        "additional_precondition": "a closed grant-readiness verification run satisfying D3 "
                                   "conditions C1-C10, re-verified against the THEN-current tree",
        "on_mismatch": "FAIL CLOSED - do not open the partition, do not release credentials, do not "
                       "mutate this record",
        "durability": "the grant event must be durably recorded BEFORE any credential release or "
                      "partition access; a released credential without a recorded grant is an "
                      "integrity failure"},
    "note": "a stale digest is a FEATURE: when prerequisites are produced under D2 the register "
            "changes, so the CAS must be re-anchored by a NEW adjudicated D3 submission rather than "
            "silently satisfied against this one",
    "boundary": "validation_authorization is false; this record grants nothing",
}
H["ValidationAuthorizationState"] = dump(
    state, "MR002_Phase3BC_ValidationAuthorizationState_v1.0.json")

# =====================================================================================
# Countersignature + manifest
# =====================================================================================
cs = f"""# MR-002 Phase 3B/C Authorization Adjudication

**Reference commit:** `{ADJUDICATED_COMMIT}`
**Submission:** `{ADJUDICATED['AuthorizationRequestSubmission']}`
**Adjudicated:** {ADJUDICATION_DATE} by the owner.
**Governing outcome:** **D1 ACCEPTED / D2 AUTHORIZED WITH RESTRICTIONS / D3 DENIED WITHOUT
PREJUDICE.**

## D1 — Accepted

The Phase 3A lineage proof and Phase 3B/C prerequisite register are accepted as complete and correct
for the referenced commit.

This acceptance confirms the reported lineage integrity, prerequisite inventory, and `NOT_READY`
determination. It grants no authority to open the validation partition, inspect validation values,
compute performance, or change `validation_authorization`.

## D2 — Authorized with Restrictions

The named custodians, evaluator producer, and runtime producer are authorized to create and verify
the **{', '.join(producible)}** prerequisite artifacts within their preregistered responsibilities.

This authorization is limited to **prerequisite production**. It does not authorize direct or
indirect access to validation-partition values, performance computation, Phase 3B/C execution,
production of P13, or modification of any preregistered model, evaluator, acceptance criterion,
trial rule, or binding.

All runtime evidence must be produced **prospectively**. Specification templates, retrospective
attestations, inferred state, and placeholder completion do not satisfy runtime-evidence
prerequisites.

Any prerequisite that cannot be completed without validation access must remain **unsatisfied**.

Specifically:

- The operational increment is a **prerequisite-production authorization**, not the beginning of
  Phase 3B or 3C.
- P6/P7/P8 must be **actual runtime instances**; the Phase 3A specification templates cannot serve
  as evidence that the partition has remained unopened.
- `PENDING_EVALUATOR_BIND` must be resolved through the precommitted §4 process before any
  validation access — not silently replaced, not inferred from the current code tree, and not
  resolved as part of the authorization event.
- P13 remains absent until Phase 3C produces the registered trial-dispersion evidence.

## D3 — Denied Without Prejudice

Phase 3B/C execution authorization is **not granted**. Only
{register['counts']['blocking_satisfied']} of {register['counts']['blocking']} blocking prerequisites
are currently satisfied. The validation partition remains closed, the single validation opening
remains **unconsumed**, and `validation_authorization` remains **false**.

D3 may be resubmitted only after every pre-access blocking prerequisite has been produced,
independently verified, identity-bound, and revalidated together in **one closed grant-readiness
run** demonstrating conditions C1–C10 recorded in
`MR002_Phase3BC_AuthorizationAdjudication_v1.0.json`.

The final grant is a **compare-and-set** transition `false → true` at `_rev 0`, failing closed if the
stored state, prerequisite digest, code identity, manifest identity, or authorization-request
identity differs from the adjudicated package. The durable anchor is
`MR002_Phase3BC_ValidationAuthorizationState_v1.0.json`.

OOS access and evaluation remain outside scope and under DENY.
"""
H["AuthorizationAdjudicationCountersignature"] = dump_md(
    cs, "MR002_Phase3BC_AuthorizationAdjudication_v1.0.md")

MANIFEST_NAME = "MR002_Phase3BC_AdjudicationManifest_v1.0.json"
manifest = {
    "record_type": "MR002_Phase3BC_AdjudicationManifest", "version": "1.0",
    "package": "SPQ-1 Phase 3B/C owner adjudication (D1 accepted / D2 restricted / D3 denied)",
    "adjudication_date": ADJUDICATION_DATE,
    "reference_commit": ADJUDICATED_COMMIT,
    "artifact_sha256": H,
    "manifest_bound_artifact_count": len(H),
    "publication_manifest_self_excluded": True,
    "adjudicated_package_sha256": adjudicated_sha,
    "adjudicated_package_unmodified": True,
    "governing_outcome": adjudication["governing_outcome"],
    "validation_authorization": False,
    "grant_readiness": register["grant_readiness"],
    "boundary": "ADJUDICATION RECORD. validation_authorization=false; validation/OOS SEALED AND "
                "UNREAD; the single validation opening remains unconsumed; no credentials released; "
                "no performance computed.",
}
dump(manifest, MANIFEST_NAME)

print(f"adjudication recorded: {adjudication['governing_outcome']}")
print(f"D2 authorizes production of: {', '.join(producible)}")
print(f"authorization state: validation_authorization=False _rev=0 "
      f"prerequisite_digest={prerequisite_digest[:16]}...")
