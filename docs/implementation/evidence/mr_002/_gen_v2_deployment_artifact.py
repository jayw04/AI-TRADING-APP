"""Seal the EXACT deployment artifact identity, before any host mutation.

This record closes the gap the CRLF failure lived in: an approved Git/source closure is not the
same thing as the exact bytes extracted onto the host. It binds the second to the first.

It authorizes NOTHING. Host extraction and cutover remain a separate owner ruling.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
_SCRATCH = os.environ["MR002_DEPLOY_DIR"]


def _canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


V = json.load(open(os.path.join(_SCRATCH, "candidate_verification.json"), encoding="utf-8"))
CLOSURE = json.loads(subprocess.run(
    ["git", "show", "HEAD:apps/backend/app/research/mr002/phase3c/manifests/"
     "validation2_execution_closure.json"], cwd=_REPO, check=True,
    capture_output=True).stdout)

REC: dict = {
    "record_type": "MR002_Validation2_DeploymentArtifact",
    "version": "1.0",
    "date": "2026-08-20",
    "purpose": "bind ONE exact, byte-verified deployment artifact to the approved source closure "
               "before the host is touched.",
    "authorizes": "NOTHING. Host extraction and cutover require a separate owner ruling.",
}

# ── what this artifact is bound to ───────────────────────────────────────────────────────────
REC["binds"] = {
    "execution_package": {
        "record": "MR002_Validation2_ExecutionPackage_v2.0",
        "identity_sha256": "e22c4d4f9e1007340d7c30385af0ee6a95c0c0be8a1a8cd8b4a4e8140c832d23",
        "owner_disposition": "APPROVED; substantive package changes FROZEN",
    },
    "execution_closure": {
        "identity_sha256": CLOSURE["closure_identity_sha256"],
        "member_count": CLOSURE["member_count"],
        "unjustified_members": CLOSURE["unjustified_members"],
    },
    "source_commit": V["source_commit"],
    "archive_sha256": V["archive"]["sha256"],
    "archive_bytes": V["archive"]["bytes"],
    "candidate_aggregate_sha256": V["candidate_aggregate"]["aggregate_sha256"],
    "candidate_aggregate_file_count": V["candidate_aggregate"]["file_count"],
    "closure_identities_verified": (
        f"{V['closure_member_verification']['matched']}/"
        f"{V['closure_member_verification']['expected_members']}"),
    "host": "i-00c1034f7026db45e",
    "destination": "/opt/mr002/phase3c_src",
}

# ── the package under review did not change ──────────────────────────────────────────────────
REC["package_unchanged_proof"] = {
    "owner_constraint": "no new substantive code changes; if anything in the closure changes, "
                        "this package is no longer the package being reviewed.",
    "method": "the closure was RE-DERIVED into a scratch file at the new HEAD and its MEMBERS "
              "compared against the sealed closure. The sealed artifact itself was NOT "
              "overwritten, because its canonical payload includes derived_at_commit and "
              "re-deriving it would change its identity without any member changing.",
    "result": "25/25 members byte-identical; 0 added, 0 removed, 0 changed",
    "files_added_since_the_approved_package": {
        "apps/backend/scripts/mr002_v2_tree_aggregate.py":
            "the canonical aggregate, SHIPPED INSIDE THE ARCHIVE so candidate and post-cutover "
            "live are computed by identical code",
        "apps/backend/scripts/mr002_v2_build_deployment_artifact.py":
            "local build + candidate verification; runs before any host mutation",
    },
    "why_these_are_not_substantive": "neither is imported by the launcher, neither can select a "
        "partition, key, VersionId, window, fold, authority, solver, threshold, disposition or "
        "custody status, and neither is a closure member by the closure's own rule. Verified, "
        "not asserted: the re-derived closure is unchanged.",
}

# ── how the archive was produced ─────────────────────────────────────────────────────────────
REC["archive_production"] = {
    "mechanism": V["archive"]["mechanism"],
    "⛔ both_flags_are_mandatory": (
        "git archive is a CHECKOUT-faithful exporter, not a blob-faithful one: it applies CRLF "
        "on export to every file lacking an explicit eol=lf gitattribute. core.eol=lf ALONE is a "
        "SILENT NO-OP because core.autocrlf=true overrides it - last time it produced a "
        "byte-identical archive, i.e. a fix that looked applied. Both flags, always."),
    "determinism": "two independent builds produced the identical archive SHA-256 and the "
                   "identical candidate aggregate.",
    "archive_need_not_be_archived": (
        "the tar is byte-reproducible from the source commit with the pinned invocation, proven "
        "by the double build. The commit plus this record is the durable artifact; the 8.7 MB "
        "tar is regenerable bulk and is not committed to Git (ADR 0050)."),
}

# ── the candidate verification, before any host mutation ─────────────────────────────────────
REC["candidate_verification"] = {
    "performed": "LOCALLY, into a scratch candidate. The host was not touched.",
    "extracted_entries": V["extraction"]["entries"],
    "closure_members_matched": V["closure_member_verification"]["matched"],
    "closure_members_expected": V["closure_member_verification"]["expected_members"],
    "mismatched": V["closure_member_verification"]["mismatched"],
    "missing_from_archive": V["closure_member_verification"]["missing_from_archive"],
    "crlf_control": {
        "members_checked": V["crlf_control"]["members_checked"],
        "members_containing_crlf": V["crlf_control"]["members_containing_crlf"],
        "crlf_free": V["crlf_control"]["crlf_free"],
        "why": V["crlf_control"]["why_hashes_alone_are_insufficient"],
    },
    "verdict": V["verdict"],
}

# ── operational proof from the EXACT deployable bytes ────────────────────────────────────────
REC["operational_proof_from_the_extracted_candidate"] = {
    "why": "byte identity proves what the archive SAYS. Running from it proves what it DOES. "
           "The whole cycle's lesson is that a file can be intact and its behaviour wrong.",
    "import_resolution": "PASS - 11 governed modules imported from the extracted candidate; "
                         "app.research.mr002.phase3c resolves to "
                         "/work/apps/backend/app/research/mr002/phase3c/__init__.py. This also "
                         "confirms the archive carries the parent package __init__ files, which "
                         "are NOT closure members and would not have been caught by hashes.",
    "positive_closed_latch_rehearsal": "PASS from the candidate tree - 6 consuming / 4 reference "
                                       "/ 0 unclassified, REHEARSAL_NO_VERDICT, "
                                       "integrity_admissible true",
    "static_launcher_invariants": "20/20 PASS from the candidate tree",
    "negative_matrix": "10/10 fail closed from the candidate tree, "
                       "reader_acquisition_attempted=False in every case",
    "fold_gate_rehearsal": "ALL PASS from the candidate tree",
}

# ── rollback ─────────────────────────────────────────────────────────────────────────────────
REC["rollback"] = {
    "preserved_as": "/opt/mr002/phase3c_src_pre_amendmentC (moved, never deleted)",
    "⛔ if_that_path_already_exists": "STOP rather than overwrite it - it is the only copy of the "
                                     "pre-Amendment-C tree.",
    "historical_rollback_aggregate": "ff0308be99dd82087b03ef3b48006f4a7c4b87ca37bd951a8be42794c03f4bbc",
    "⚠ NOT_COMPARABLE_TO_THIS_ARTIFACT": {
        "finding": "that value is NOT reproducible locally. Seven plausible formula variants over "
                   "two candidate file sets, at the recorded checkpoint 34eeee00, all failed to "
                   "reproduce it - because the host's live tree is not the Git content of that "
                   "commit and the implementation that produced it is preserved nowhere in this "
                   "repository.",
        "consequence": "it is retained ONLY as a historical marker of the pre-deployment tree. It "
                       "must NOT be compared against any aggregate from "
                       "mr002_v2_tree_aggregate.py, and nobody should later 'reconcile' the two.",
        "required_before_cutover": "RE-DERIVE the rollback aggregate on the host by running the "
                                   "shipped mr002_v2_tree_aggregate.py against the LIVE tree, "
                                   "read-only, and record it. Only that value is comparable.",
    },
}

# ── the procedure this artifact is for ───────────────────────────────────────────────────────
REC["authorized_next_procedure_NOT_YET_APPROVED"] = {
    "staging": ["phase3c_src (live)", "phase3c_src_candidate (new)",
                "phase3c_src_pre_amendmentC (rollback)"],
    "order": "extract to candidate -> verify candidate ON THE HOST -> only then atomic "
             "same-filesystem rename",
    "post_cutover_required": [
        "pre-cutover candidate aggregate == post-cutover live aggregate, both from the shipped "
        "mr002_v2_tree_aggregate.py",
        "25/25 closure identities against their registered content SHA-256",
        "import resolution inside the exact run container",
        "state-machine / static invariant suite",
        "positive rehearsal FROM the deployed tree",
        "latch still 8/CLOSED and withheld reads still 0",
    ],
    "then": "issue the corrected readiness record for the TENTH GATE.",
    "disk_check_first": "confirm free space on the host before extracting; a redeploy has "
                        "previously consumed several GB and starved a later capture.",
}

REC["boundary"] = {
    "latch": "8 statements / CLOSED",
    "withheld_reads": 0,
    "opening_consumed": False,
    "validation_2_population": "UNCONSUMED",
    "host_mutated": False,
    "host_state": "i-00c1034f7026db45e stopped; live tree untouched",
    "deployment_extraction": "NOT YET AUTHORIZED",
    "validation_2_opening": "NOT AUTHORIZED",
}
REC["what_was_NOT_done"] = [
    "the host was not started, contacted or modified",
    "no file was extracted onto the host",
    "the latch was not released",
    "no reader was assumed and no STS call was made",
    "no Validation-2 object was read at any version",
    "no closure member was changed",
]
REC["record_status"] = "SEALED" if V["verdict"] == "CANDIDATE_VERIFIED" else "DRAFT"


def main() -> int:
    ident = hashlib.sha256(_canonical(REC)).hexdigest()
    REC["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_DeploymentArtifact_v1.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(REC))
    os.replace(tmp, out)
    b = REC["binds"]
    print("MR-002 VALIDATION-2 DEPLOYMENT ARTIFACT v1.0")
    print(f"  status              {REC['record_status']}")
    print(f"  identity            {ident}")
    print(f"  source commit       {b['source_commit']}")
    print(f"  archive sha256      {b['archive_sha256']}")
    print(f"  archive bytes       {b['archive_bytes']:,}")
    print(f"  candidate aggregate {b['candidate_aggregate_sha256']}")
    print(f"  closure identities  {b['closure_identities_verified']}")
    print(f"  CRLF-free           {REC['candidate_verification']['crlf_control']['crlf_free']}")
    print(f"  host extraction     {REC['boundary']['deployment_extraction']}")
    print(f"  wrote               {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
