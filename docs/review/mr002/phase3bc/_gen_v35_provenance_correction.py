"""SPQ-1 Phase 3B — v3.5 provenance correction (2026-08-17).

Records the owner-authorized bounded read-only host diagnostic that closed the v3.5 provenance
finding: the staged v3.5 package is internally coherent at ef12de6d... but its commit attribution
"@ b93e770" is byte-false. Four of the 41 members carried CRLF line endings; normalized to LF they
are byte-exact to the b93e770 blobs, so the executed semantics were the commit's. No sealed access,
no entrypoint invocation, no staging mutation occurred during the diagnostic.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


record = {
    "record_type": "MR002_Phase3B_V35ProvenanceCorrection",
    "version": "1.0",
    "artifact_kind": "PROVENANCE_CORRECTION",
    "produced_at": "2026-08-17T00:00:00Z",
    "authorized_by": (
        "owner authorization 2026-08-17: bounded read-only v3.5 provenance diagnostic on "
        "i-00c1034f7026db45e before v3.6 Steps 3-9; strictly limited to existing local EBS "
        "artifacts; no entrypoint, no reader assumption, no sealed S3, no patch, no extraction, "
        "no v3.6 staging."
    ),
    "finding_being_corrected": (
        "the v3.5 execution identity has been represented as 'ef12de6d... @ b93e770', a "
        "commit-bound claim. Local blob sweeps (every commit 259b751..df2d5b5, and per-member "
        "sweeps over every commit touching the four differing files) prove NO committed tree "
        "reproduces ef12de6d... The claim is RETIRED as a commit-bound identity."
    ),
    "diagnostic_evidence": {
        "boundary": "READ ONLY - hash and read; nothing written, patched, extracted or staged",
        "host": "i-00c1034f7026db45e (mr002-phase3c-run-host, c6a.xlarge)",
        "ssm_command_ids": {
            "hash_sweep": "16192493-22e6-4ce4-bc5c-9b3611e447b9",
            "member_reads": "four per-file AWS-RunShellScript reads (gzip|base64 to stdout)",
        },
        "archive_sha256_matches_bound": "32800572... VERIFIED on host",
        "staged_config_sha256_matches_bound": "16a25ac9... VERIFIED on host",
        "tree_equals_tarball": (
            "TRUE - all 41 members hash identically in /opt/mr002/v35/apps/backend and inside "
            "code_v35.tar.gz (archive read without modification); both derive ef12de6d... "
            "The staging-integrity stop condition did NOT fire."
        ),
    },
    "exact_member_deltas": {
        "byte_identical_to_b93e770": "37 of 41 members",
        "differing_members": {
            "app/research/__init__.py": {
                "staged_sha256": "71b8c4dc057a8e3e5a633d7aea5fa2ff1001f21a74cc9d0f8e9b162f9eabd362",
                "b93e770_sha256": "ced96b0efddea52ce59e22ad82b3e727b1ec5bf465fe7cd73efe8617c1f88e04",
                "delta": "CRLF x7 lines; LF-normalized bytes == blob EXACTLY; zero stray CR",
            },
            "app/research/mr002/phase3b/candidates.py": {
                "staged_sha256": "cddd3ef512c3b564765a1ef92b4027b897457da3aa88771ce19995aeb60e6c26",
                "b93e770_sha256": "9bef81814dcd0db7795683a99b2f2d8bbf9f61adf617a7f804bf8c1b4dee5d28",
                "delta": "CRLF x782 lines; LF-normalized bytes == blob EXACTLY; zero stray CR",
            },
            "app/research/mr002/phase3b/publish.py": {
                "staged_sha256": "97226556c8f921cf4783b1453ad719b2035e557a0cd012470625747e5a66911f",
                "b93e770_sha256": "53d8452ffbdd2fc2ff841e15a61da6b9983a64236f5ef27afe34978a0485df09",
                "delta": "CRLF x193 lines; LF-normalized bytes == blob EXACTLY; zero stray CR",
            },
            "app/research/mr002/phase3b/runner.py": {
                "staged_sha256": "723a2caa7310e86f490447d6aeb00d2f1ccfa2e096bd97ec367a7facd06f5ced",
                "b93e770_sha256": "3fb34537b99bf193e7deb2805b8a27e64c49bb8c82f2d27a4452a0bbedbafe02",
                "delta": "CRLF x387 lines; LF-normalized bytes == blob EXACTLY; zero stray CR",
            },
        },
        "characterization": (
            "pure line-ending byte-custody drift on exactly the four files freshly written on the "
            "Windows working tree (core.autocrlf=true) when the v3.5 archive was built from the "
            "working tree rather than from Git blob bytes. Content is line-for-line identical."
        ),
        "no_commit_matches": (
            "for each of the four members, every commit that ever touched the file was swept; no "
            "blob reproduces the staged bytes - expected, since Git stores the LF form."
        ),
    },
    "accurate_v35_representation_going_forward": {
        "v35_staged_execution_package_identity": "ef12de6dcabd8a46a1dfcb69993693bfe316e4b76ecaf8f8dbc45f08669fc25d",
        "claimed_git_checkpoint": "b93e770",
        "commit_correspondence": "INVALID / DOES NOT REPRODUCE (byte level)",
        "package_provenance": (
            "host-staged bytes; internally self-consistent between archive, tree and "
            "configuration, but not reproducible from the claimed or any examined committed tree"
        ),
        "semantic_mitigation": (
            "LF-normalization makes all four members byte-exact to b93e770, and Python treats "
            "CRLF and LF sources identically, so run 4 EXECUTED the b93e770 logic. The four-way "
            "ceremony proved what it proved - the running package matched its staged "
            "archive/config identity; what it failed to prove was Git custody correspondence."
        ),
        "run_4_disposition": "UNCHANGED - outcome C, qualification FAIL, evidence inadmissible, opening spent",
        "methodology_validation": (
            "the bound v3.4 identity 7c972455... DOES reproduce exactly from Git blob bytes "
            "(commits 39a6d6c..6e64e35), so the encoding and blob-based procedure are sound; the "
            "v3.5 basis alone was working-tree-contaminated."
        ),
    },
    "rules_for_v36": {
        "supersession_wording": (
            "v3.6 supersedes the staged v3.5 package identity ef12de6d..., whose Git checkpoint "
            "attribution was subsequently found non-reproducible. It must NOT say "
            "'supersedes v3.5 ef12de6d @ b93e770' as though that pair were valid."
        ),
        "v36_origin": (
            "the v3.6 executable tree/archive originates ONLY from raw Git blob bytes at 961c38a "
            "(identity c4852231019531f58d3f213c782d11dfc375e5b974ea9568e271144f6212b85a, derived "
            "twice independently). Closure bytes are NEVER copied from /opt/mr002/v35. Only "
            "non-code bound inputs that are already independently governed may be copied forward."
        ),
        "new_guard": (
            "the v3.6 archive build and staging verify NO CR byte in any closure member, so this "
            "defect class cannot recur silently."
        ),
    },
    "grants": "NOTHING. Provenance correction only. Openings spent: 4. Next opening: NOT granted.",
}

body = _canonical(record)
record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
out = os.path.join(_HERE, "MR002_Phase3B_V35ProvenanceCorrection_v1.0.json")
with open(out, "wb") as fh:
    fh.write(_canonical(record))
print(f"wrote {os.path.basename(out)}")
print(f"identity {record['record_identity_sha256']}")
