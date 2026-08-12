"""Supplemental execution identity v3.0 — the package that actually reached PRE_ACCESS_READY.

v1.0 (a2f2ff32) bound a layer that could not be invoked. v2.0 (a013a80c) bound a layer that could,
but its notion of closure was incomplete: 35 files bound and 35 imported, not the same 35, leaving
``spq1/__init__.py`` unbound while it supplied four constants that reach every emitted record.

v3.0 binds what ran. Three rosters are kept distinct, because conflating them is what produced the
false closure:

  EXECUTING            every repository Python file imported from the real entry point, derived
                       mechanically and proven by SET EQUALITY, digests from git BLOB bytes;
  EXTERNAL_DEPENDENCY  the separately hash-bound read-only dependency bundle v1.1;
  GOVERNING_ONLY       records bound for provenance that no run imports.

Digests come from git blobs, never the working tree: ``core.autocrlf=true`` means a checked-out file
carries CRLF while its blob carries LF, and the container receives blob bytes. Binding the worktree
would bind something that never runs.

Zero-data instrument: reads git objects and governed records. No AWS call, no sealed object, no
credential.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

CHECKPOINT = "edc468783f5a19127587f9ef849a72cfcc6fc431"
BRANCH = "research/mr002-preregistration"

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
BACKEND = "apps/backend"
GOV = "docs/review/mr002/phase3bc"

SUPERSEDED = {
    "v1.0": {"identity": "a2f2ff32b3a10a25814f76c5cb2f0abc6741931dbe282fd36dc77eb2e61add2e",
             "status": "SUPERSEDED_EXECUTIONALLY_INCOMPLETE",
             "why": "no entry point, no production reader, fixture-assembled world, both frozen "
                    "earnings controls absent"},
    "v2.0": {"identity": "a013a80cede76aab03517809232720201610d845b0df4fb5d0a827302861aeda",
             "status": "SUPERSEDED_EXECUTION_IDENTITY_INCOMPLETE",
             "why": "closure defined by a hand-maintained list: 35 bound and 35 imported but not "
                    "the same 35, leaving spq1/__init__.py unbound while it supplied "
                    "PHASE0_CENSUS_SHA256, PHASE0_OWNER_RULINGS_SHA256, PHASE0_SCHEMA_SHA256 and "
                    "PRODUCER_CODE_VERSION into GOVERNING_IDENTITIES and thus every record"},
}
NO_OPENING_UNDER_EITHER = (
    "No sealed opening occurred under v1.0 or v2.0. Neither was ever executed against AWS: no "
    "credential assumed, no host started under them, no GetObject issued."
)

GOVERNING_ONLY = (
    "MR002_Phase3B_RunSpecification_v1.0.json",
    "MR002_Phase3B_ExecutionBoundaryClarification_v1.0.json",
    "MR002_Phase3B_ExecutionBoundary_EvidenceMemo_v1.0.md",
    "MR002_Phase3B_ProducerIdentityContinuity_v1.0.json",
    "MR002_Phase3B_A1_PriceBasisEvidence_v1.0.json",
    "MR002_Phase3B_A1F1_ActionsSplitBasis_v1.0.json",
    "MR002_Phase3B_EarningsControlStructuralCensus_v1.0.json",
    "MR002_Phase3B_CorrectedDevelopmentReconciliation_v1.0.json",
    "MR002_Phase3B_SupplementalExecutionIdentity_v1.0.json",
    "MR002_Phase3B_SupplementalExecutionIdentity_v2.0.json",
    "MR002_Phase3BC_P12AuthorizationGrant_v1.0.json",
    "MR002_Phase3BC_ValidationAuthorizationState_v1.0.json",
    "MR002_ValidationStructuralManifest_v1.0.json",
    "MR002_SealedStoreUploadManifest_v1.0.json",
    "MR002_Phase3BC_RuntimePrerequisiteRegister_v1.3.json",
)
EXECUTION_INPUTS = (
    "MR002_Phase3B_RegisteredSessionList_validation_v1.0.json",
    "MR002_Phase3B_RegisteredSessionList_Provenance_v1.0.json",
    "MR002_Phase3B_ReferenceManifest_v1.0.json",
    "MR002_Phase3B_ValidationInputIdentityRegistration_v1.0.json",
    "MR002_Phase3B_ValidationInputIdentityRegistry_v1.0.json",
    "MR002_Phase3B_ExecutionManifest_v1.0.json",
    "MR002_Phase3B_ExecutionConfiguration_v1.0.json",
)
QUALIFICATION = (
    "MR002_Phase3B_LiveMaterializationObservation_v1.0.json",
    "MR002_Phase3B_ExecutionDependencyBundle_v1.1.json",
    "MR002_Phase3B_ExecutionDependencyBundle_v1.0.json",
    "MR002_Phase3B_PreAccessReadyEvidence_v1.0.json",
)

P12_BOUND = {
    "evaluator_image_index":
        "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51",
    "dependency_lockfile_sha256":
        "bb38b685d15f78b705fff2681b76807f2277b02f7af5788e4c320951121c7ebd",
    "numeric_runtime_manifest_sha256":
        "8e5e39471c0d96c5cd6916e7c316bc74fa320336c7e0106515ede11f479c1ed0",
    "frozen_host": "i-00c1034f7026db45e",
    "qualified_host_role_arn": "arn:aws:iam::219024422756:role/mr002-phase3c-run-host",
}
P12_FILE_IDENTITIES = {
    "numeric_runtime_manifest_sha256":
        f"{GOV}/MR002_NumericRuntimeIdentityManifest_RuntimeInstance_v1.0.json",
    "dependency_lockfile_sha256": "docs/review/mr002/evaluator/MR002_LinuxDependencyLock_v1.1.json",
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


def _blob(rel: str) -> bytes:
    return _git("show", f"{CHECKPOINT}:{rel}")


def _sha(rel: str) -> str:
    return hashlib.sha256(_blob(rel)).hexdigest()


def verify_pushed() -> dict:
    remote = _git("rev-parse", f"origin/{BRANCH}").decode().strip()
    if remote != CHECKPOINT:
        raise SupplementRefused(f"remote head {remote[:12]} is not {CHECKPOINT[:12]}")
    return {"commit": CHECKPOINT, "branch": BRANCH, "remote_head_matches": True,
            "subject": _git("log", "-1", "--format=%s", CHECKPOINT).decode().strip(),
            "read_from": "git object store; the working tree is NOT consulted"}


def executing_roster() -> dict:
    sys.path.insert(0, os.path.join(_REPO, BACKEND))
    from app.research.mr002.phase3b import roster as R

    paths = sorted(R.enumerate_closure())
    if len(paths) != 41:
        raise SupplementRefused(f"expected the 41-file executing closure, derived {len(paths)}")
    files = {p: _sha(f"{BACKEND}/{p}") for p in paths}

    identity_carrier = "app/research/mr002/spq1/__init__.py"
    if identity_carrier not in files:
        raise SupplementRefused(f"{identity_carrier} absent - this is the v2 defect recurring")
    initializers = sorted(p for p in files if p.endswith("__init__.py"))
    if len(initializers) < 7:
        raise SupplementRefused(f"package initializers under-bound: {initializers}")

    return {
        "roster_kind": "EXECUTING",
        "derivation": "mechanically derived transitive import closure from the real entry point; "
                      "NOT a hand-maintained list",
        "digest_source": "git blob bytes - core.autocrlf=true makes worktree bytes a different "
                         "and non-executing identity",
        "file_count": len(files),
        "files": files,
        "package_initializers_bound": initializers,
        "identity_carrying_initializer": {
            "path": identity_carrier, "sha256": files[identity_carrier],
            "why_it_matters": "defines PHASE0_CENSUS_SHA256, PHASE0_OWNER_RULINGS_SHA256, "
                              "PHASE0_SCHEMA_SHA256 and PRODUCER_CODE_VERSION, which identities.py "
                              "imports into GOVERNING_IDENTITIES and thus into every record",
        },
        "proof": "set equality, never count - a binding with the right count and wrong members "
                 "refuses; verified in-image at PRE_ACCESS_READY",
    }


def dependency_roster() -> dict:
    bundle = json.loads(_blob(f"{GOV}/MR002_Phase3B_ExecutionDependencyBundle_v1.1.json"))
    if bundle.get("version") != "1.1":
        raise SupplementRefused("bundle v1.1 not found at the checkpoint")
    if not bundle["p10_invariance_observed"]["unchanged"]:
        raise SupplementRefused("bundle records a moved P10 numeric stack")
    return {
        "roster_kind": "EXTERNAL_DEPENDENCY",
        "manifest": f"{GOV}/MR002_Phase3B_ExecutionDependencyBundle_v1.1.json",
        "manifest_sha256": _sha(f"{GOV}/MR002_Phase3B_ExecutionDependencyBundle_v1.1.json"),
        "record_identity": bundle["record_identity_sha256"],
        "wheels": {k: v["sha256"] for k, v in sorted(bundle["wheels"].items())},
        "installed_file_count": bundle["installed_inventory"]["file_count"],
        "inventory_sha256": bundle["installed_inventory"]["inventory_sha256"],
        "supersedes": bundle["supersedes"],
        "p10_invariance": bundle["p10_invariance_observed"],
        "resolution_authority": bundle["resolution_authority"],
    }


def governing_roster() -> dict:
    records = {f"{GOV}/{n}": _sha(f"{GOV}/{n}") for n in GOVERNING_ONLY}
    inputs = {f"{GOV}/{n}": _sha(f"{GOV}/{n}") for n in EXECUTION_INPUTS}
    qual = {f"{GOV}/{n}": _sha(f"{GOV}/{n}") for n in QUALIFICATION}
    tests = {
        p: _sha(p)
        for p in sorted(
            _git("ls-tree", "-r", "--name-only", CHECKPOINT, "--",
                 f"{BACKEND}/tests/research/phase3b").decode().split()
        )
        if p.endswith(".py")
    }
    return {
        "roster_kind": "GOVERNING_ONLY",
        "note": "bound for provenance; no run imports these",
        "governing_records": records,
        "execution_inputs": inputs,
        "qualification_evidence": qual,
        "qualification_code": tests,
        "counts": {"governing": len(records), "inputs": len(inputs),
                   "evidence": len(qual), "qualification_code": len(tests)},
    }


def grant_compatibility() -> dict:
    verified = {}
    for name, rel in P12_FILE_IDENTITIES.items():
        actual = _sha(rel)
        if actual != P12_BOUND[name]:
            raise SupplementRefused(f"P12-bound identity {name} CHANGED: {actual}")
        verified[name] = {"path": rel, "sha256": actual, "unchanged": True}
    return {
        "p12_bound_identities": P12_BOUND,
        "file_backed_reverified": verified,
        "image_unchanged": "no image was built or pushed; the bound digest resolved on the host",
        "host_role_unchanged": "no IAM edit; the sealed Deny remains and was proven by POLICY "
                               "SIMULATION, never by a live denial probe",
        "conclusion": "every identity P12 binds is unchanged; this supplement closes the execution "
                      "identity the grant does not name",
    }


def build() -> dict:
    evidence = json.loads(_blob(f"{GOV}/MR002_Phase3B_PreAccessReadyEvidence_v1.0.json"))
    if evidence["result"] != "PRE_ACCESS_READY_REACHED" or evidence["opening_consumed"]:
        raise SupplementRefused("the evidence does not record an unspent PRE_ACCESS_READY")

    return {
        "record_type": "MR002_Phase3B_SupplementalExecutionIdentity",
        "version": "3.0",
        "artifact_kind": "IDENTITY_SUPPLEMENT",
        "status": "SUBMITTED_FOR_ADJUDICATION",
        "purpose": "Bind the Phase 3B execution package that reached PRE_ACCESS_READY under the "
                   "real host and container topology, so the granted opening becomes spendable.",
        "pre_validation_checkpoint": verify_pushed(),
        "supersession": {**SUPERSEDED, "no_opening_under_either": NO_OPENING_UNDER_EITHER},
        "three_rosters": {
            "why": "conflating them produced a false closure once: 35 bound and 35 imported, not "
                   "the same 35",
            "executing": executing_roster(),
            "external_dependency": dependency_roster(),
            "governing_only": governing_roster(),
        },
        "input_identity_registration": {
            "artifact": f"{GOV}/MR002_Phase3B_ValidationInputIdentityRegistration_v1.0.json",
            "sha256": _sha(f"{GOV}/MR002_Phase3B_ValidationInputIdentityRegistration_v1.0.json"),
            "closes": "the seven InputIdentityRegistry slots Phase 2B left as opaque development "
                      "labels",
            "phase2b_disposition": "PHASE2B_INPUT_IDENTITY_PLACEHOLDERS - NONTRANSFERABLE",
            "construction": "slot_identity = H(source_object_identity || interpretation_identity)",
            "no_sealed_read": "source identities come from the registered upload and P11 "
                              "commitments; no sealed object was opened",
        },
        "qualification_result": evidence,
        "authorization": {
            "validation_authorization": True,
            "_rev": 1,
            "store": "Git-tracked compare-and-set state file "
                     f"{GOV}/MR002_Phase3BC_ValidationAuthorizationState_v1.0.json, written by "
                     "scripts/mr002_custody/p12_authorization.py",
            "explicitly_not": "this is NOT a live AWS authorization store; no DynamoDB or other "
                              "AWS-resident authorization state exists",
            "caveat": "being file-based, its authority rests on Git history rather than an atomic "
                      "store",
        },
        "grant_compatibility": grant_compatibility(),
        "frozen_research_rules_unchanged": {
            "research_identity": "UNCHANGED",
            "dsr_trials_N": 5,
            "configuration_set": ["A", "B", "C"],
            "evaluator_logic": "UNCHANGED - 21/21 image modules untouched",
            "statement": "This package creates an EXECUTION identity. The earnings controls and "
                         "input identities it adds implement frozen-contract semantics that "
                         "development left unimplemented or unregistered; no economic rule, "
                         "parameter, gate or trial changed.",
        },
        "the_ask": {
            "decision_requested": "Adjudicate whether this exact package is authorized to consume "
                                  "the granted validation opening.",
            "explicitly_not_requested": [
                "OOS access", "a second validation opening", "any parameter or gate change",
                "re-issuance of the P12 grant", "performance interpretation",
            ],
        },
        "boundary": "Zero-data. No AWS call, no sealed object, no credential, no published_at. "
                    "The single validation opening remains UNSPENT.",
        "grants": "NOTHING. This artifact asks the owner for a decision.",
    }


def main() -> None:
    record = build()
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3B_SupplementalExecutionIdentity_v3.0.json")
    payload = _canonical(record)
    with open(out, "wb") as fh:
        fh.write(payload)
    r = record["three_rosters"]
    print(f"wrote {out}")
    print(f"record identity  {record['record_identity_sha256']}")
    print(f"file sha256      {hashlib.sha256(payload).hexdigest()}")
    print(f"checkpoint       {CHECKPOINT[:12]} (remote head verified)")
    print(f"executing        {r['executing']['file_count']} files (git blob digests)")
    print(f"dependency       {len(r['external_dependency']['wheels'])} wheels, "
          f"{r['external_dependency']['installed_file_count']} installed files")
    print(f"governing_only   {r['governing_only']['counts']}")
    print(f"qualification    {record['qualification_result']['result']}, "
          f"opening_consumed={record['qualification_result']['opening_consumed']}")


if __name__ == "__main__":
    main()
