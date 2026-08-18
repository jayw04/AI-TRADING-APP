"""Correct the Stage-3 ExecutionPackage / countersignature identities to GIT-BLOB values.

Found by re-deriving every bound identity from PUSHED Git rather than the local checkout. Two
distinct defects, neither of which changes any artifact byte:

  D1  three members were bound at WORKING-TREE hashes carrying CRLF, because they were computed
      on a Windows checkout. Their Git blobs are LF and LF-normalise to an exact match, so this is
      a checkout artifact and not source drift. The Phase-A source manifest -- generated from the
      clean worktree -- already carried the correct LF values, which is why the
      manifest-describes-pushed-source check passed while these three failed.

  D2  `phase3c_identity_frozen` recorded 7788ada5..., which was computed at commit 4b1df12,
      BEFORE the owner-authorized R6A change at 4274912 modified phase3c/replay.py. It is a
      superseded value. replay.py is LF in both blob and worktree, so this is not a CRLF issue.

v2.0 and countersignature v1.0 are NOT edited or deleted. The countersignature ID
(MR002_Stage3ExecutionCountersignature_v1.0) is the authorization token the code enforces and is
UNCHANGED, so the governed qualification executed under it stands: the artifacts it ran against are
byte-identical, only their recorded identities were wrong.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
REF = "origin/research/mr002-preregistration"
COUNTERSIGNATURE_ID = "MR002_Stage3ExecutionCountersignature_v1.0"


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob_sha(path: str) -> str:
    out = subprocess.run(["git", "-C", REPO, "show", f"{REF}:{path}"], capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"missing from pushed Git: {path}")
    return hashlib.sha256(out.stdout).hexdigest()


PKG_V20 = "docs/implementation/evidence/mr_002/MR002_Stage3_ExecutionPackage_v2.0.json"
CS_V10 = "docs/implementation/evidence/mr_002/MR002_Stage3ExecutionCountersignature_v1.0.json"

with open(os.path.join(REPO, PKG_V20), "rb") as fh:
    pkg = json.loads(fh.read())

CORRECTED = {
    "certifier_and_solver_registry": "apps/backend/scripts/mr002_coverage_signed_gap.py",
    "fallback_profile": "apps/backend/scripts/mr002_piqp.py",
    "governing_construction": "apps/backend/app/research/mr002/joint_portfolio.py",
}
PHASE3C = [
    "apps/backend/app/research/mr002/phase3c/__init__.py",
    "apps/backend/app/research/mr002/phase3c/adopted.py",
    "apps/backend/app/research/mr002/phase3c/exits.py",
    "apps/backend/app/research/mr002/phase3c/folds.py",
    "apps/backend/app/research/mr002/phase3c/gates.py",
    "apps/backend/app/research/mr002/phase3c/replay.py",
]

h = hashlib.sha256()
for p in sorted(PHASE3C):
    h.update(f"{p}:{blob_sha(p)}\n".encode("ascii"))
phase3c_identity = h.hexdigest()

d1 = {}
for key, path in CORRECTED.items():
    d1[key] = {
        "path": path,
        "was_bound": pkg["package_binds"][key]["sha256"],
        "corrected_to_git_blob": blob_sha(path),
        "cause": "working-tree CRLF; the blob is LF and LF-normalises to an exact match",
        "source_bytes_changed": False,
    }

new_pkg = json.loads(json.dumps(pkg))
new_pkg.pop("record_identity_sha256", None)
new_pkg["version"] = "2.1"
new_pkg["supersedes"] = "MR002_Stage3_ExecutionPackage_v2.0.json"
new_pkg["supersedes_sha256"] = blob_sha(PKG_V20)
new_pkg["supersession_note"] = (
    "identity corrections only. v2.0 is unedited and retained. No artifact byte changed, no "
    "authorization scope changed, and the governed qualification executed under v2.0 stands."
)
for key, fix in d1.items():
    new_pkg["package_binds"][key]["sha256"] = fix["corrected_to_git_blob"]
    new_pkg["package_binds"][key]["identity_basis"] = "git blob (LF), re-derived from pushed Git"
new_pkg["phase3c_identity_frozen"] = phase3c_identity
new_pkg["phase3c_identity_note"] = (
    "corrected. v2.0 recorded 7788ada5..., computed at 4b1df12 BEFORE the owner-authorized R6A "
    "change at 4274912 modified phase3c/replay.py. 7788ada5 is SUPERSEDED, not wrong-at-the-time; "
    "the frozen Phase 3C is the post-R6A tree."
)
new_pkg["all_identities_basis"] = (
    "every bound identity re-derives from PUSHED Git (git blob bytes), not from a local checkout"
)
new_pkg["record_identity_sha256"] = hashlib.sha256(_canonical(new_pkg)).hexdigest()

CORRECTION = {
    "record_type": "MR002_STAGE3_COUNTERSIGNATURE_IDENTITY_CORRECTION",
    "version": "1.0",
    "produced_at": "2026-08-18T00:00:00Z",
    "record_status": "IMMUTABLE",
    "authorized_by": "owner authorization 2026-08-18 (push-then-reproduce-from-pushed-Git step)",
    "found_by": (
        "re-deriving every bound identity from the pushed remote-tracking ref instead of the local "
        "working tree -- the step exists precisely to catch this, and it did"
    ),
    "countersignature_id_unchanged": COUNTERSIGNATURE_ID,
    "why_the_governed_run_still_stands": (
        "the countersignature ID is the authorization token the code enforces "
        "(stage3_route.routed refuses without it), and it is unchanged. The artifacts the governed "
        "qualification ran against are byte-identical; only their RECORDED identities were wrong. "
        "No numerical parameter, scope, or artifact changed."
    ),
    "defect_1_working_tree_crlf_identities": {
        "class": "CHECKOUT ARTIFACT, not source drift",
        "detail": (
            "three members were bound at working-tree hashes carrying CRLF because they were "
            "computed on a Windows checkout. Their Git blobs are LF and LF-normalise to an exact "
            "match."
        ),
        "corroboration": (
            "the Phase-A source manifest, generated from the CLEAN worktree, already carried the "
            "correct LF values -- which is why manifest_describes_pushed_source_exactly PASSED "
            "while these three failed"
        ),
        "members": d1,
    },
    "defect_2_superseded_phase3c_identity": {
        "class": "STALE VALUE",
        "was_bound": pkg["phase3c_identity_frozen"],
        "corrected_to": phase3c_identity,
        "detail": (
            "7788ada5... was computed at commit 4b1df12, BEFORE the owner-authorized R6A change at "
            "4274912 modified phase3c/replay.py. replay.py is LF in both blob and worktree, so "
            "this is not a CRLF issue -- the recorded value was simply superseded."
        ),
        "source_bytes_changed_by_this_correction": False,
    },
    "corrected_package": {
        "path": "docs/implementation/evidence/mr_002/MR002_Stage3_ExecutionPackage_v2.1.json",
        "sha256": new_pkg["record_identity_sha256"],
    },
    "superseded": {"package": PKG_V20, "countersignature_record": CS_V10,
                   "retained": "both are unedited and retained"},
    "generalization": (
        "identities bound for governance must be derived from Git blobs, never from a Windows "
        "working tree. This is the third occurrence of the CRLF custody class in MR-002 -- after "
        "the v3.5 provenance retirement and the *_published evidence directories."
    ),
    "grants": "NOTHING. An identity correction.",
}
CORRECTION["record_identity_sha256"] = hashlib.sha256(_canonical(CORRECTION)).hexdigest()

with open(os.path.join(_HERE, "MR002_Stage3_ExecutionPackage_v2.1.json"), "wb") as fh:
    fh.write(_canonical(new_pkg))
with open(os.path.join(_HERE,
                       "MR002_Stage3_CountersignatureIdentityCorrection_v1.0.json"), "wb") as fh:
    fh.write(_canonical(CORRECTION))

print(json.dumps({
    "package_v2.1": new_pkg["record_identity_sha256"],
    "correction": CORRECTION["record_identity_sha256"],
    "phase3c_identity_corrected": phase3c_identity,
    "crlf_members_corrected": list(d1),
}, indent=1))
