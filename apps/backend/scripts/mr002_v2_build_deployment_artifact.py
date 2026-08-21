"""Freeze the EXACT deployable archive and prove it, locally, before any host mutation.

The gap this closes is the one the CRLF failure lived in: an APPROVED GIT/SOURCE CLOSURE is not
the same thing as THE EXACT BYTES EXTRACTED ONTO THE HOST. This script produces the second and
binds it to the first.

⚠ THE ARCHIVE INVOCATION IS NOT NEGOTIABLE.
    git -c core.autocrlf=false -c core.eol=lf archive --format=tar <commit> apps/backend
`git archive` is a CHECKOUT-faithful exporter, not a blob-faithful one: it applies CRLF on export
to every file lacking an explicit `eol=lf` gitattribute. And `core.eol=lf` ALONE is a SILENT
NO-OP, because `core.autocrlf=true` overrides it — it produced a byte-identical archive last time,
which is the most dangerous possible failure mode: a fix that looks applied. BOTH flags, always.

Nothing here touches the host, the latch, or any sealed object.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile

# repo root = up FOUR levels from apps/backend/scripts/<this file>. Three levels lands in
# apps/, where `git archive HEAD apps/backend` resolves the pathspec relative to cwd and
# fails with exit 128 looking for apps/apps/backend.
REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
CLOSURE = ("apps/backend/app/research/mr002/phase3c/manifests/"
           "validation2_execution_closure.json")
AGG_SCRIPT = "apps/backend/scripts/mr002_v2_tree_aggregate.py"


def sh(*a: str, binary: bool = False):
    r = subprocess.run(a, cwd=REPO, check=True, capture_output=True)
    return r.stdout if binary else r.stdout.decode("utf-8", "replace").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--emit", required=True)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    commit = sh("git", "rev-parse", "HEAD")
    findings: dict = {"source_commit": commit}

    # ---- 1. build the archive with BOTH canonical export controls -------------------------
    tar_path = os.path.join(args.out_dir, f"mr002_phase3c_src_{commit[:12]}.tar")
    raw = sh("git", "-c", "core.autocrlf=false", "-c", "core.eol=lf",
             "archive", "--format=tar", commit, "apps/backend", binary=True)
    with open(tar_path, "wb") as fh:
        fh.write(raw)
    findings["archive"] = {
        "path": os.path.basename(tar_path),
        "mechanism": ("git -c core.autocrlf=false -c core.eol=lf archive --format=tar "
                      f"{commit} apps/backend"),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
    print(f"archive {findings['archive']['sha256']}  {len(raw):,} B")

    # ---- 2. extract into a scratch candidate ----------------------------------------------
    cand = os.path.join(args.out_dir, "candidate")
    if os.path.exists(cand):
        shutil.rmtree(cand)
    os.makedirs(cand)
    with tarfile.open(tar_path) as tf:
        members = tf.getnames()
        tf.extractall(cand)
    findings["extraction"] = {"root": "candidate/", "entries": len(members)}
    print(f"extracted {len(members)} entries")

    # ---- 3. every closure member must match its REGISTERED content sha256 ------------------
    closure = json.loads(sh("git", "show", f"HEAD:{CLOSURE}", binary=True).decode("utf-8"))
    per_member, mismatched, missing = [], [], []
    for m in closure["members"]:
        rel = m["path"]
        want = m["sha256_over_git_blob_content_lf"]
        disk = os.path.join(cand, rel.replace("/", os.sep))
        if not os.path.exists(disk):
            missing.append(rel)
            per_member.append({"path": rel, "status": "MISSING_FROM_ARCHIVE"})
            continue
        with open(disk, "rb") as fh:
            payload = fh.read()
        got = hashlib.sha256(payload).hexdigest()
        ok = got == want
        if not ok:
            mismatched.append(rel)
        per_member.append({"path": rel, "registered_sha256": want, "in_archive_sha256": got,
                           "status": "MATCH" if ok else "MISMATCH",
                           "bytes": len(payload), "crlf_count": payload.count(b"\r\n")})
    findings["closure_member_verification"] = {
        "closure_identity_sha256": closure["closure_identity_sha256"],
        "expected_members": closure["member_count"],
        "verified_members": len(per_member),
        "matched": sum(1 for r in per_member if r["status"] == "MATCH"),
        "mismatched": mismatched,
        "missing_from_archive": missing,
        "members": per_member,
    }
    print(f"closure members matched {findings['closure_member_verification']['matched']}"
          f"/{closure['member_count']}")

    # ---- 4. CRLF must be ZERO across governed text members ---------------------------------
    crlf = {r["path"]: r["crlf_count"] for r in per_member
            if r.get("crlf_count") and r["path"].endswith((".py", ".json"))}
    findings["crlf_control"] = {
        "scope": "all governed .py/.json closure members, checked in the EXTRACTED candidate",
        "members_checked": sum(1 for r in per_member if r["path"].endswith((".py", ".json"))),
        "members_containing_crlf": crlf,
        "crlf_free": not crlf,
        "why_hashes_alone_are_insufficient": (
            "a byte mismatch could otherwise be re-diagnosed from hashes only, which is how the "
            "CRLF failure was initially mis-read. This asserts the actual property."),
    }
    print(f"CRLF-free: {findings['crlf_control']['crlf_free']}")

    # ---- 5. candidate aggregate, computed by the SHIPPED script inside the candidate --------
    shipped = os.path.join(cand, AGG_SCRIPT.replace("/", os.sep))
    agg_out = os.path.join(args.out_dir, "candidate_aggregate.json")
    proc = subprocess.run([sys.executable, shipped, "--root", cand, "--emit", agg_out,
                           "--quiet"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"aggregate failed: {proc.stdout}{proc.stderr}")
    agg = json.loads(open(agg_out, encoding="utf-8").read())
    findings["candidate_aggregate"] = {
        "aggregate_sha256": agg["aggregate_sha256"],
        "file_count": agg["file_count"],
        "computed_by": "the SHIPPED copy inside the extracted candidate, i.e. the identical code "
                       "that will compute the live aggregate on the host after cutover",
        "shipped_script_sha256": hashlib.sha256(open(shipped, "rb").read()).hexdigest(),
    }
    print(f"candidate aggregate {agg['aggregate_sha256']}  ({agg['file_count']} files)")

    ok = (not mismatched and not missing and not crlf
          and findings["closure_member_verification"]["matched"] == closure["member_count"])
    findings["verdict"] = "CANDIDATE_VERIFIED" if ok else "CANDIDATE_REJECTED"
    with open(args.emit, "wb") as fh:
        fh.write((json.dumps(findings, sort_keys=True, indent=1) + "\n").encode("ascii"))
    print(f"\n{findings['verdict']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
