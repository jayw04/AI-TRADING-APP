"""MR-002 host decommissioning sweep — enumerate and CLASSIFY every materialization artifact.

Owner standing rule 2026-08-21: before terminating an MR-002 host, enumerate all local
DuckDB / parquet / materialization artifacts and classify each as development, fixture,
failed-pre-read evidence, or consumed-holdout evidence. No consumed-holdout material may remain
solely on EBS.

This closes the CLASS rather than cleaning one generation at a time.

⛔ BYTE-ONLY. Nothing here opens, queries or interprets any artifact. Files are stat'd and hashed.
⛔ UNKNOWN is a real verdict. An artifact this script cannot confidently classify is reported as
   NEEDS_RULING, never quietly folded into a benign bucket — the whole point is that a classifier
   which cannot say "I don't know" will silently misclassify the one file that matters.
"""
import hashlib
import json
import os
import subprocess

ROOTS = ["/opt/mr002", "/root", "/home", "/var/tmp", "/tmp", "/mnt", "/data"]
EXTS = (".duckdb", ".parquet", ".db", ".sqlite", ".arrow", ".feather")

# Evidence-linked identities already established.
KNOWN = {
    "c4cabab228e7824144036afde09f5c949d9dea6144eb0b24d41e1fcad0856c82":
        ("CONSUMED_HOLDOUT_VALIDATION1",
         "the Validation-1 materialization. Its mtime 2026-08-19T12:54:47Z coincides with the "
         "CloudTrail validation/* reads at 12:54:46-47Z by session mr002-p3c-validation-v1 — so "
         "this is identified by ACCESS-LOG CORRELATION, not by its filename."),
    "0dbc2c9e3be28c0770c3ab64461659bbfd177e17f22cfcf96925f216f2d6487d":
        ("FAILED_PRE_READ_EVIDENCE",
         "the 12,288-byte database from the 2026-08-21T12:07:54Z pre-read failure. Zero tables, "
         "zero Validation-2 bytes; it is the artifact behind the PreReadFailure record's claim. "
         "RETAIN."),
}


def classify(path, sha, size):
    if sha in KNOWN:
        return KNOWN[sha]
    p = path.replace(os.sep, "/")
    if "/stage/reh" in p or "/stage/rehout" in p or "/stage/fx/" in p:
        return ("FIXTURE_OR_REHEARSAL",
                "built under the rehearsal path from fixture/development inputs; the rehearsal "
                "runs with --reader fixture --window development and cannot reach sealed data")
    if "/inputs/" in p or "mr002_research.duckdb" in p:
        return ("DEVELOPMENT", "development corpus")
    if "/deps" in p or "/wheels/" in p or "site-packages" in p or "/testvenv/" in p:
        return ("PACKAGING", "dependency bundle or wheel content, not a materialization")
    if "/phase3c_src" in p or "_pre_amendmentC" in p or "_pre_validation2" in p:
        return ("SOURCE_TREE", "deployed source tree content")
    return ("NEEDS_RULING",
            "not matched by any registered rule. Classify it explicitly before host disposal.")


out = {"roots": ROOTS, "artifacts": []}
seen = set()
for root in ROOTS:
    if not os.path.isdir(root):
        continue
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for f in fn:
            if not f.endswith(EXTS):
                continue
            p = os.path.join(dp, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if (st.st_dev, st.st_ino) in seen:
                continue
            seen.add((st.st_dev, st.st_ino))
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            sha = h.hexdigest()
            kind, why = classify(p, sha, st.st_size)
            out["artifacts"].append({"path": p, "bytes": st.st_size, "sha256": sha,
                                     "mtime_utc": __import__("time").strftime(
                                         "%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime(
                                             st.st_mtime)),
                                     "classification": kind, "why": why})

from collections import Counter  # noqa: E402

out["summary"] = dict(Counter(a["classification"] for a in out["artifacts"]))
out["consumed_holdout_on_ebs"] = [a for a in out["artifacts"]
                                  if a["classification"].startswith("CONSUMED_HOLDOUT")]
out["needs_ruling"] = [a for a in out["artifacts"] if a["classification"] == "NEEDS_RULING"]
out["rule"] = ("no consumed-holdout material may remain solely on EBS; NEEDS_RULING must be "
               "empty before host disposal")
print(json.dumps(out, sort_keys=True, indent=1))
