"""SPQ-1 Phase 3B — v3.6 rebind/staging record + dry-preflight ceremony record (2026-08-17).

The full owner-authorized Steps 2-9 sequence, executed after the v3.5 provenance correction
(047131fe...). The v3.6 closure originates ONLY from raw Git blob bytes at checkpoint 961c38a; no
closure byte was copied from /opt/mr002/v35; a no-CR guard ran at build and at staging. Non-code
governed inputs were carried forward byte-identically; the configuration was patched hex-for-hex
in exactly the two provenance scalars. Nothing was consumed: no reader assumption, no STS, no
sealed access, zero artifacts.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))

V36_ID = "c4852231019531f58d3f213c782d11dfc375e5b974ea9568e271144f6212b85a"
V35_ID = "ef12de6dcabd8a46a1dfcb69993693bfe316e4b76ecaf8f8dbc45f08669fc25d"


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _write(record: dict, name: str) -> str:
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    with open(os.path.join(_HERE, name), "wb") as fh:
        fh.write(_canonical(record))
    print(f"wrote {name}")
    print(f"identity {record['record_identity_sha256']}")
    return record["record_identity_sha256"]


staging = {
    "record_type": "MR002_Phase3B_StagingRecord",
    "version": "3.6",
    "artifact_kind": "EXECUTION_IDENTITY_REBIND_AND_STAGING",
    "produced_at": "2026-08-17T00:00:00Z",
    "authorized_by": (
        "owner authorization 2026-08-17: v3.6 ceremony Steps 2-9 on the corrected tree, after the "
        "bounded v3.5 provenance diagnostic closed (V35ProvenanceCorrection_v1.0, 047131fe...)."
    ),
    "boundary": "Staging and identity verification plus the NON-CONSUMING dry ceremony. No sealed object opened, no reader assumed, nothing consumed. Openings spent remains 4; research verdict remains NONE.",
    "v36_execution_identity": V36_ID,
    "closure_derivation": {
        "checkpoint": "961c38aba578112bac48884ec31f12cbf357075a (correct(mr-002): spinoffdividend OUT of the gap term)",
        "byte_origin": (
            "RAW GIT BLOB BYTES via `git cat-file blob` - never a filesystem checkout "
            "(core.autocrlf=true makes checkout CRLF-unsafe; this is the exact defect class that "
            "invalidated the v3.5 commit attribution)"
        ),
        "member_authority": (
            "the checkpoint's OWN roster.enumerate_closure()/closure_identity(), executed against "
            "the materialized blob tree with import-provenance asserted - not a hand-maintained list"
        ),
        "members": 41,
        "member_set": "identical to the v3.5/v3.4 closure member sets",
        "changed_members_vs_v35_content": [
            "app/research/mr002/phase3b/candidates.py",
            "app/research/mr002/phase3b/enrichment.py",
        ],
        "independent_recomputation": "a second computation importing NO production code rebuilt every hash from git cat-file and re-derived the identity - EQUAL",
        "no_cr_guard": "zero CR bytes in every member, asserted at materialization, at archive build, and at host staging",
    },
    "package": {
        "archive": "code_v36.tar.gz",
        "archive_bytes": 69406,
        "archive_sha256": "024db8fa9df03bebc4d9e441bb37ad8a4212e3d2bb64999e545fe30fc389c074",
        "deterministic_build": "built twice (mtime=0, uid/gid=0, sorted members, gzip mtime=0) - byte-identical SHA-256 both times",
        "archive_derived_identity": V36_ID,
        "member_root": "apps/backend (extraction target; tar member names are app/...)",
        "members": 41,
    },
    "staged_as_one_operation": {
        "host": "i-00c1034f7026db45e (mr002-phase3c-run-host, c6a.xlarge)",
        "ssm_command_id": "b76fc9da-b627-46b5-b2d9-7c3b40a01d43",
        "mechanics": (
            "one SSM invocation: refuse if /opt/mr002/v36 exists; verify the transferred archive "
            "sha AFTER transfer before extracting; extract; verify extracted==archive members and "
            "tree identity; copy the v3.5 governed inputs (source config verified against its "
            "bound sha 16a25ac9... first); patch the two scalars; re-read and hash."
        ),
        "staged_tree": "/opt/mr002/v36 - apps/backend, inputs, code_v36.tar.gz",
        "v35_untouched": "config 16a25ac9... and archive 32800572... byte-identical after all operations",
    },
    "staged_configuration": {
        "bytes": 3896,
        "path": "/opt/mr002/v36/inputs/config.json",
        "sha256": "1959dcd3fa1208ec5c7b5deec4c2a32a00dd0b19face8f3ca17a936c02a6aea9",
        "superseded_config_sha256": "16a25ac9d41e44d397169cb35bdb3924291f234f50299c25f8f0516ba50bc1f7",
        "fields_patched": ["identities.code_identity", "observed_identities.execution_closure_sha256"],
        "guard": (
            "refused unless EXACTLY two occurrences of the superseded identity; byte length "
            "unchanged at 3896; zero CR before and after; post-patch counts new=2 old=0; byte-diff "
            "vs v3.5 = 20 spans / 110 bytes, ALL inside the two 64-hex scalar spans"
        ),
        "carried_forward_inputs_byte_identical": {
            "reference_manifest.json": "fc8e91e9... (equals the entrypoint-bound REFERENCE_MANIFEST_SHA256)",
            "sessions.json": "66d080fe...",
            "structural_manifest.json": "6b81a319...",
            "upload_manifest.json": "b16bc89f...",
        },
    },
    "four_way_identity_proof": {
        "executed": "INSIDE the bound image, --network=none (SSM 14408d3e-3f04-4bd6-bd8d-0bde8a824929; re-proven post-ceremony)",
        "image": (
            "ECR repo digest sha256:194efbdf... == configuration runtime_facts.image_digest == "
            "identities.runtime_identity; local image ID sha256:226643c4...; the candidate tag is "
            "the same image"
        ),
        "result": f"ALL FOUR EQUAL {V36_ID[:16]}... - config-declared, config-observed, archive-derived (re-hashed from inside the tarball), live mount (roster.closure_identity() over the executing bytes)",
        "counts": "41 live == 41 archive == 41 declared",
        "unchanged_set_reconfirmed": {
            "config_mapping": "{A: 1.75, B: 2.00, C: 2.25} == FROZEN_CONFIG_MAPPING",
            "contract_identities": "== FROZEN_CONTRACT_IDENTITIES (in-closure authorities)",
            "runtime_P10": "runtime identity unchanged; no capacity rerun, no requalification (owner)",
            "sealed_input_digests": "carried in the byte-identical manifests and the non-scalar config bytes",
            "reader_transition_authority": "VALIDATION_READER_ROLE_ARN constant inside the bound closure (entrypoint.py unchanged)",
            "superseded_identities_absent": "neither ef12de6d... nor 7c972455... appears in the staged config",
        },
    },
    "supersedes": {
        "v35_staged_package_identity": V35_ID,
        "wording": (
            "v3.6 supersedes the staged v3.5 package identity ef12de6d..., whose Git checkpoint "
            "attribution was subsequently found non-reproducible "
            "(V35ProvenanceCorrection_v1.0). NOT 'v3.5 ef12de6d @ b93e770'."
        ),
        "classification": "SUPERSEDED_SEMANTICS_ADJUDICATED (relation/spinoff adjudication + owner corrigendum) AND provenance-corrected",
    },
    "grants": "NOTHING. Staging evidence only.",
    "state": {"openings_spent": 4, "next_opening": "NOT granted, NOT requested", "research_verdict": "NONE", "v36": "STAGED AND BOUND"},
}

ceremony = {
    "record_type": "MR002_Phase3B_DryPreflightCeremony",
    "version": "3.6",
    "artifact_kind": "NON_CONSUMING_EXECUTION_CEREMONY_REHEARSAL",
    "produced_at": "2026-08-17T00:00:00Z",
    "authorized_by": "owner authorization 2026-08-17 (Steps 5-9 as one uninterrupted host ceremony)",
    "boundary": (
        "NON-CONSUMING BY CONSTRUCTION AND PROVEN OPERATIONALLY. --mode dry stops at "
        "S7_PRE_ACCESS_READY, before _assume_reader(); s3_reader() is lazy. Openings spent "
        "remains 4; research verdict remains NONE."
    ),
    "bound_package": {
        "code_identity": V36_ID,
        "archive_sha256": "024db8fa9df03bebc4d9e441bb37ad8a4212e3d2bb64999e545fe30fc389c074",
        "staged_config_sha256": "1959dcd3fa1208ec5c7b5deec4c2a32a00dd0b19face8f3ca17a936c02a6aea9",
        "host": "i-00c1034f7026db45e",
        "image": "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51",
        "checkpoint": "961c38a",
    },
    "ssm_command_id": "5d82397a-3dea-4ef2-8872-314f49084742",
    "window_utc": ["2026-08-17T22:48:12Z", "2026-08-17T22:48:18Z"],
    "results": {
        "1a_correct_offline": {"network": "none", "disposition": "PASS", "exit_code": 0, "state": "S7_PRE_ACCESS_READY", "opening_consumed": False, "artifacts_written": 0},
        "1b_correct_networked": {"network": "ENABLED - full ceremony fidelity", "disposition": "PASS", "exit_code": 0, "state": "S7_PRE_ACCESS_READY", "opening_consumed": False, "artifacts_written": 0},
        "2_stale_identity": {
            "mutation": "BOTH scalars -> the superseded staged v3.5 package identity ef12de6d... - internally CONSISTENT, catchable only by the live-mount comparison",
            "network": "none", "disposition": "REFUSED", "exit_code": 2, "state": "S0_INIT", "opening_consumed": False, "artifacts_written": 0,
            "error": "execution closure identity mismatch: live mount c4852231... != declared ef12de6d...",
        },
        "3_self_disagreement": {"mutation": "identities.code_identity alone -> ef12de6d...", "network": "none", "disposition": "REFUSED", "exit_code": 2, "state": "S0_INIT", "opening_consumed": False, "artifacts_written": 0, "error": "configuration disagrees with itself"},
        "4_contract_drift": {"mutation": "contract_identities.corrected_development_reconciliation zeroed", "network": "none", "disposition": "REFUSED", "exit_code": 2, "state": "S1_CODE_IDENTITY_VERIFIED", "opening_consumed": False, "artifacts_written": 0, "error": "contract identity drift"},
        "5_config_drift": {"mutation": "config_mapping B 2.00 -> 2.01", "network": "none", "disposition": "REFUSED", "exit_code": 2, "state": "S2_CONTRACT_IDENTITY_VERIFIED", "opening_consumed": False, "artifacts_written": 0, "error": "configuration mismatch"},
    },
    "affirmative_zero_access_evidence": {
        "why_recorded": (
            "owner requirement: the absence of a successful sealed GetObject must be RECORDED "
            "operationally, not inferred from stop_at=S7. The v3.5 ceremony's CloudTrail check was "
            "a 20-most-recent sample and correctly self-labelled CORROBORATING ONLY; this one is "
            "windowed with a positive delivery control."
        ),
        "iam_latch": (
            "simulate-principal-policy: role/mr002-phase3c-run-host -> sts:AssumeRole on "
            "role/mr002-validation-reader = explicitDeny AT CEREMONY TIME. The only sanctioned "
            "path to a sealed object is that assumption; it was structurally impossible."
        ),
        "cloudtrail_windowed": (
            "lookup-events, EventName=AssumeRole, window 2026-08-17T22:40:00Z..23:05:00Z: exactly "
            "two events, both the unrelated workbench-paper instance-role refresh on "
            "i-084f47fe4e69192e9 at 22:48:47Z. ZERO events name mr002-validation-reader or the "
            "mr002 host role."
        ),
        "positive_delivery_control": (
            "the unrelated events arrived FROM INSIDE the ceremony minute (22:48), proving "
            "CloudTrail was delivering for this exact window - the absence of mr002 events is "
            "evidence of absence, not consistency lag."
        ),
        "structural": "4 of 6 cases ran --network=none; the runner returns before _assume_reader(); the reader is lazy; zero artifacts in every output root; no S8/S9 in any case",
        "sts_calls": 0,
        "successful_sealed_getobject_calls": 0,
    },
    "post_ceremony_rehash": {
        "ssm_command_id_step9": "(fourway re-run + input rehash in one invocation)",
        "staged_config_unchanged": "1959dcd3... byte-identical after the full ceremony",
        "archive_unchanged": "024db8fa... byte-identical",
        "four_way_re_proven": "all four equal c4852231..., counts 41",
        "negative_control_copies": "each negative ran from its OWN copy under /opt/mr002/qual/v36/dry; the staged tree was mounted read-only throughout",
        "host_stopped_after": True,
    },
    "grants": "NOTHING. Rehearsal evidence only. The next opening remains NOT granted.",
    "state": {"openings_spent": 4, "research_verdict": "NONE", "v36": "STAGED, BOUND, AND REHEARSED"},
}

sid = _write(staging, "MR002_Phase3B_StagingRecord_v3.6.json")
ceremony["staging_record_identity"] = sid
_write(ceremony, "MR002_Phase3B_DryPreflightCeremony_v3.6.json")
