"""P12 — the owner grant, the CAS, and the SR-GRANT-1 credential release.

Authorized by the owner on 2026-08-11: D3 GRANTED, P12 AUTHORIZED, bound to
submission MR002_Phase3BC_ExecutionAuthorizationRequest_v2.0.json (identity
4c984a4b...) and prerequisite anchor 2b8f7920....

===============================================================================
WHY THIS IS A SCRIPT AND NOT A SEQUENCE OF COMMANDS
===============================================================================

P12 is one governed operation with an ORDER that matters more than any
individual step. A credential must never become usable before the authorization
exists durably, so the ordering is enforced in code, fail-closed at every
boundary, rather than trusted to whoever is at the keyboard:

  1. re-read and compare ELEVEN preconditions, immediately before granting
  2. write the durable grant record FIRST
  3. compare-and-set false/_rev 0 -> true/_rev 1
  4. ONLY THEN edit the reader trust policy -- this edit IS the credential release
  5. snapshot the post-grant state without touching a sealed object

Any mismatch at step 1 aborts with no grant and no trust-policy edit. A failure
at step 3 aborts before any credential exists. The trust policy is the last
thing to move, because it is the only step that makes data reachable.

===============================================================================
K4 REMAINS BINDING
===============================================================================

This module issues no S3 object read of any kind. The post-grant snapshot uses
IAM policy simulation and control-state inspection only. The validation opening
must be spent on the governed Phase 3B execution path, not on a control test --
so this script deliberately cannot read a sealed object even after the grant it
performs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REVIEW = REPO / "docs" / "review" / "mr002"
P3BC = REVIEW / "phase3bc"

STATE = P3BC / "MR002_Phase3BC_ValidationAuthorizationState_v1.0.json"
SUBMISSION = P3BC / "MR002_Phase3BC_ExecutionAuthorizationRequest_v2.0.json"
REGISTER = P3BC / "MR002_Phase3BC_RuntimePrerequisiteRegister_v1.3.json"
WPF = P3BC / "MR002_WPF_GrantReadinessRun_v1.0.json"
FREEZE = P3BC / "MR002_Phase3CHostFreeze_v1.0.json"
GRANT = P3BC / "MR002_Phase3BC_P12AuthorizationGrant_v1.0.json"
SNAPSHOT = P3BC / "MR002_Phase3BC_PostGrantStateSnapshot_v1.0.json"
TRUST_GRANTED = Path(__file__).parent / "aws" / "validation-reader-trust-granted.json"

ANCHOR = "2b8f792081d6285e1a7619a6faa362d0502fa728a46333eb5c23e48a81e6a06d"
STALE_ANCHOR = "088d700bb1b3000a707ab58ca880bf6c71319587284161b373064927b6abc7d6"
SUBMISSION_IDENTITY = "4c984a4b015bb6825df1f57f549dde6bfc22a2b55ec6e0fed609157b3e1eb3f6"
BOUND_INDEX = "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51"
HOST_ROLE = "arn:aws:iam::219024422756:role/mr002-phase3c-run-host"
PLACEHOLDER = "arn:aws:iam::219024422756:role/mr002-phase3c-run-host-NOT-YET-PROVISIONED"
READER_ROLE = "mr002-validation-reader"
SEALED_BUCKET = "workbench-mr002-sealed-219024422756"


class GrantRefused(Exception):
    """A precondition failed. No grant, no CAS, no credential release."""


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _identity(rec: dict, exclude: str) -> str:
    body = {k: v for k, v in rec.items() if k != exclude}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()


def _write(rec: dict, path: Path, identity_key: str) -> str:
    rec[identity_key] = _identity(rec, identity_key)
    path.write_text(json.dumps(rec, indent=1, sort_keys=True, ensure_ascii=True) + "\n",
                    encoding="utf-8", newline="\n")
    return rec[identity_key]


# ---------------------------------------------------------------------------
# STEP 1 — preconditions
# ---------------------------------------------------------------------------


def check_preconditions(iam) -> list:
    """Eleven checks, re-read immediately before granting. Any mismatch aborts."""
    checks = []

    def add(name, ok, detail):
        checks.append({"precondition": name, "status": "PASS" if ok else "FAIL",
                       "detail": detail})

    state = _load(STATE)
    add("validation_authorization == false", state["validation_authorization"] is False,
        f"observed={state['validation_authorization']}")
    add("_rev == 0", state["_rev"] == 0, f"observed={state['_rev']}")

    reg = _load(REGISTER)
    anchor_src = {p["id"]: p["status"] for p in reg["prerequisites"]}
    computed = hashlib.sha256(
        json.dumps(anchor_src, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode("ascii")).hexdigest()
    add("prerequisite anchor == 2b8f7920...", computed == ANCHOR,
        f"recomputed={computed}")

    sub = _load(SUBMISSION)
    add("submission identity == 4c984a4b...",
        sub["submission_identity_sha256"] == SUBMISSION_IDENTITY,
        f"observed={sub['submission_identity_sha256'][:24]}...")

    by_id = {p["id"]: p["status"] for p in reg["prerequisites"]}
    unsat = [i for i in ("P6", "P7", "P8", "P9", "P10", "P11") if by_id.get(i) != "SATISFIED"]
    add("P6-P11 == SATISFIED", not unsat, f"unsatisfied={unsat or 'none'}")

    wpf = _load(WPF)
    add("WP-F == accepted PASS", wpf["verdict"] == "PASS",
        f"verdict={wpf['verdict']}, conditions={wpf['conditions_evaluated']}")

    freeze = _load(FREEZE)
    live_host = None
    try:
        live_host = iam.get_role(RoleName="mr002-phase3c-run-host")["Role"]["Arn"]
    except Exception as exc:  # noqa: BLE001
        live_host = f"UNAVAILABLE: {exc}"
    add("qualified host identity unchanged (SR-HOST-1)",
        freeze["frozen_host"]["instance_id"] == "i-00c1034f7026db45e"
        and live_host == HOST_ROLE,
        f"frozen instance={freeze['frozen_host']['instance_id']}; live role={live_host}")

    p10_digest = _load(
        P3BC / "MR002_NumericRuntimeIdentityManifest_RuntimeInstance_v1.0.json"
    )["bindings"]["container_image_digest"]["digest"]
    add("governed evaluator index == sha256:194efbdf...", p10_digest == BOUND_INDEX,
        f"P10 binds={p10_digest[:24]}...")

    trust = iam.get_role(RoleName=READER_ROLE)["Role"]["AssumeRolePolicyDocument"]
    named = [s.get("Condition", {}).get("StringEquals", {}).get("aws:PrincipalArn")
             for s in trust["Statement"]]
    add("reader trust still holds the unassumable placeholder", PLACEHOLDER in named,
        f"named principal={named}")

    p7 = _load(P3BC / "ValidationPartitionAccessHistory_v1.1.json")
    g = p7["observed_gate_values"]
    add("validation opening still unconsumed",
        g["validation_access_events_before_authorization"] == 0,
        f"successful validation reads={g['validation_access_events_before_authorization']}")

    p11 = _load(P3BC / "MR002_ValidationAccessControlPreconditions_v1.0.json")
    dec = p11["access_decisions"]
    add("OOS DENY still in force",
        dec["dedicated_reader"]["oos"] == "explicitDeny"
        and dec["ordinary_development_principal"]["oos"] == "explicitDeny",
        f"reader={dec['dedicated_reader']['oos']}, "
        f"ordinary={dec['ordinary_development_principal']['oos']}")

    return checks


# ---------------------------------------------------------------------------
# STEPS 2-5
# ---------------------------------------------------------------------------


def write_grant(checks, produced_at, owner) -> tuple:
    rec = {
        "record_type": "MR002_Phase3BC_P12AuthorizationGrant",
        "version": "1.0",
        "artifact_kind": "RUNTIME_INSTANCE",
        "grant": "GRANTED",
        "granted_by": owner,
        "authorization_time_utc": produced_at,
        "d3_disposition": "GRANTED",
        "bound_submission": SUBMISSION.name,
        "bound_submission_identity_sha256": SUBMISSION_IDENTITY,
        "bound_prerequisite_anchor_sha256": ANCHOR,
        "rejected_anchor_sha256": STALE_ANCHOR,
        "rejected_anchor_status": "PERMANENTLY STALE FOR THIS GRANT",
        "expected_state_at_grant": {"validation_authorization": False, "_rev": 0},
        "qualified_host_role_arn": HOST_ROLE,
        "host_binding_rule": (
            "P12 binds the IAM ROLE identity, never the EC2 instance id. SR-HOST-1 "
            "separately binds the actual execution host."
        ),
        "governed_evaluator_index": BOUND_INDEX,
        "governed_runtime": (
            "the frozen Phase 3C runtime identity recorded in "
            "MR002_Phase3CHostFreeze_v1.0.json and bound by P10"
        ),
        "scope": "VALIDATION ONLY - one transition into authorized validation execution",
        "oos_prohibition": (
            "EXPLICIT. OOS access is NOT authorized by this grant and the OOS partition "
            "remains under DENY throughout Phase 3B/3C. OOS requires its own separate "
            "later authorization."
        ),
        "credential_release_mechanism": (
            "SR-GRANT-1: editing the mr002-validation-reader trust policy from the "
            "unassumable placeholder to the qualified host role IS the credential release. "
            "It occurs ONLY after a successful CAS."
        ),
        "does_not_authorize": [
            "OOS access",
            "changing Config A/B/C or evaluator logic",
            "changing the runtime image or Linux dependency lock",
            "replacing the qualified host without requalification and a P10 refresh",
            "altering P6-P11 evidence",
            "changing metric roles, bootstrap rules, DSR design, costs, or execution endpoints",
            "product integration",
            "Phase 4 / OOS execution",
        ],
        "execution_rule": (
            "The validation opening must NOT be spent on a control test. The first use of "
            "the released reader is the governed Phase 3B execution path itself - no "
            "exploratory query, manual inspection, sample read, schema check, or 'quick "
            "verification' against sealed validation objects beforehand."
        ),
        "preconditions_verified_immediately_before_grant": checks,
        "ordering_rule": (
            "This record is written and durable BEFORE the CAS and BEFORE any trust-policy "
            "edit. A released credential without a recorded grant is an integrity failure."
        ),
    }
    ident = _write(rec, GRANT, "grant_identity_sha256")
    return rec, ident


def execute_cas(grant_identity, produced_at) -> dict:
    """Compare-and-set. Aborts before any credential exists if the state moved."""
    state = _load(STATE)
    if state["validation_authorization"] is not False or state["_rev"] != 0:
        raise GrantRefused(
            f"CAS precondition lost: validation_authorization="
            f"{state['validation_authorization']}, _rev={state['_rev']}"
        )
    previous = {"validation_authorization": False, "_rev": 0,
                "prerequisite_digest": state["bound_identities"].get("prerequisite_digest")}
    state["validation_authorization"] = True
    state["_rev"] = 1
    state["bound_identities"]["prerequisite_digest"] = ANCHOR
    state["bound_identities"]["prerequisite_digest_note"] = (
        f"Rebound at P12 to the fresh anchor. The previously adjudicated digest "
        f"{STALE_ANCHOR} is PERMANENTLY STALE for this grant."
    )
    state["bound_identities"]["p12_grant_record"] = GRANT.name
    state["bound_identities"]["p12_grant_identity_sha256"] = grant_identity
    state["bound_identities"]["authorization_request_sha256"] = SUBMISSION_IDENTITY
    state["state_established_by"] = (
        f"owner adjudication 2026-08-11 - D3 GRANTED, P12 AUTHORIZED (was: "
        f"{state['state_established_by']})"
    )
    state["boundary"] = (
        "validation_authorization is TRUE. This grants ONE validation execution against "
        "the bound contract. OOS remains under DENY and requires separate authorization."
    )
    state["granted_at_utc"] = produced_at
    state["previous_state"] = previous
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True, ensure_ascii=True) + "\n",
                     encoding="utf-8", newline="\n")
    return state


def release_credential(iam) -> dict:
    """SR-GRANT-1. The LAST step, because it is the only one that makes data reachable."""
    doc = TRUST_GRANTED.read_text(encoding="utf-8")
    iam.update_assume_role_policy(RoleName=READER_ROLE, PolicyDocument=doc)
    live = iam.get_role(RoleName=READER_ROLE)["Role"]["AssumeRolePolicyDocument"]
    named = [s.get("Condition", {}).get("StringEquals", {}).get("aws:PrincipalArn")
             for s in live["Statement"]]
    if HOST_ROLE not in named:
        raise GrantRefused(f"trust policy did not take effect; named={named}")
    if PLACEHOLDER in named:
        raise GrantRefused("placeholder still present after the edit")
    return {
        "trust_policy_document": live,
        "trust_policy_sha256": hashlib.sha256(
            json.dumps(live, sort_keys=True).encode()).hexdigest(),
        "now_assumable_by": HOST_ROLE,
        "placeholder_removed": True,
    }


def snapshot(iam, state, grant_identity, release, produced_at) -> dict:
    """Post-grant state, via control-state inspection only. K4 remains binding."""
    reader = f"arn:aws:iam::219024422756:role/{READER_ROLE}"
    sim = iam.simulate_custom_policy(
        PolicyInputList=[json.dumps(
            iam.get_role_policy(RoleName=READER_ROLE,
                                PolicyName=iam.list_role_policies(
                                    RoleName=READER_ROLE)["PolicyNames"][0])["PolicyDocument"])],
        ResourceOwner="arn:aws:iam::219024422756:root",
        CallerArn=reader,
        ActionNames=["s3:GetObject"],
        ResourceArns=[f"arn:aws:s3:::{SEALED_BUCKET}/oos/prices.parquet"],
        ContextEntries=[{"ContextKeyName": "aws:PrincipalArn",
                         "ContextKeyValues": [reader], "ContextKeyType": "string"}],
    )["EvaluationResults"][0]["EvalDecision"]

    rec = {
        "record_type": "MR002_Phase3BC_PostGrantStateSnapshot",
        "version": "1.0",
        "artifact_kind": "RUNTIME_INSTANCE",
        "produced_at_utc": produced_at,
        "method": (
            "IAM policy simulation and control-state inspection ONLY. K4 remains binding: "
            "no live HeadObject or GetObject was issued against any sealed object."
        ),
        "validation_authorization": state["validation_authorization"],
        "cas_rev": state["_rev"],
        "grant_event_identity_sha256": grant_identity,
        "prerequisite_anchor_sha256": ANCHOR,
        "rejected_anchor_sha256": STALE_ANCHOR,
        "trust_policy": release,
        "qualified_host_role": HOST_ROLE,
        "qualified_host_instance": "i-00c1034f7026db45e (frozen under SR-HOST-1)",
        "governed_evaluator_index": BOUND_INDEX,
        "oos_deny_still_active": sim == "explicitDeny",
        "oos_simulation_decision": sim,
        "validation_opening": "GRANTED BUT UNSPENT - reserved for the governed Phase 3B run",
        "execution_rule_restated": (
            "Do NOT spend the opening on a control test. The first use of the released "
            "reader is the governed Phase 3B execution path."
        ),
    }
    ident = _write(rec, SNAPSHOT, "snapshot_identity_sha256")
    return rec, ident


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="P12 grant, CAS and credential release")
    parser.add_argument("--produced-at", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--execute", action="store_true",
                        help="without this, preconditions are checked and NOTHING changes")
    args = parser.parse_args(argv)

    import boto3  # noqa: PLC0415

    iam = boto3.client("iam", region_name="us-east-1")

    print("STEP 1 — preconditions, re-read immediately before granting")
    checks = check_preconditions(iam)
    for c in checks:
        print(f"  {c['status']:4s} {c['precondition']:52s} {c['detail'][:60]}")
    failed = [c for c in checks if c["status"] != "PASS"]
    if failed:
        print(f"\nFAIL CLOSED — {len(failed)} precondition(s) unmet. "
              f"No grant, no CAS, no trust-policy edit.")
        return 2
    print(f"  all {len(checks)} preconditions PASS")

    if not args.execute:
        print("\nDRY RUN — nothing was changed. Re-run with --execute to perform P12.")
        return 0

    print("\nSTEP 2 — writing the durable grant record FIRST")
    _, grant_id = write_grant(checks, args.produced_at, args.owner)
    print(f"  {GRANT.name}  identity={grant_id}")

    print("\nSTEP 3 — compare-and-set  false/_rev 0 -> true/_rev 1")
    state = execute_cas(grant_id, args.produced_at)
    print(f"  validation_authorization={state['validation_authorization']}  _rev={state['_rev']}")

    print("\nSTEP 4 — SR-GRANT-1 credential release (trust policy)")
    release = release_credential(iam)
    print(f"  now assumable by {release['now_assumable_by']}")
    print(f"  placeholder removed={release['placeholder_removed']}")

    print("\nSTEP 5 — post-grant snapshot (simulation only; no sealed-object read)")
    snap, snap_id = snapshot(iam, state, grant_id, release, args.produced_at)
    print(f"  OOS DENY still active={snap['oos_deny_still_active']} ({snap['oos_simulation_decision']})")
    print(f"  {SNAPSHOT.name}  identity={snap_id}")
    print("\nP12 COMPLETE. The validation opening is GRANTED BUT UNSPENT.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
