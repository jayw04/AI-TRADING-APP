"""Extend the consumed-holdout resource denial to EVERY validation generation.

Owner ruling 2026-08-21. The v1.0 denial protected only
`mr002/consumed-validation2-custody/`, so a new Validation-1 custody object would not be covered
by it. This amends the deny-only backups-bucket policy so the same enumerated principals are denied
on BOTH consumed-holdout custody prefixes.

TWO DECISIONS MADE HERE, BOTH FLAGGED RATHER THAN ASSUMED
    1. The statement is RENAMED. Its v1.0 Sid named Validation-2 specifically. Adding the
       Validation-1 prefix to that statement's Resource list while keeping a V2-specific name is
       precisely the `FutureOOSReader` defect this program has now paid for twice: a statement
       whose name asserts a narrower scope than it enforces. The new Sid is generation-neutral and
       states the invariant the owner wrote:

           consumed holdout custody -- irrespective of validation generation -- is inaccessible
           to the evaluator, reader, publisher, paper and forward-validation planes.

    2. The V1 prefix is `mr002/consumed-validation1-custody/`, the exact PEER of the V2 prefix,
       rather than the prospectively tidier `mr002/consumed-holdout-custody/validation1/`. The V2
       object's location is now evidentiary identity and cannot move. Introducing a second naming
       scheme for a class of exactly two members would leave the two generations under different
       conventions -- the same split that has produced six role-transfer defects in this program.
       Symmetry with the immovable member beats tidiness that only half the class can adopt.

The policy remains DENY-ONLY. It grants nothing, and custody/audit/administrative principals
retain access by design.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

BUCKET = "workbench-backups-219024422756"
V1_PREFIX = "mr002/consumed-validation1-custody/"
V2_PREFIX = "mr002/consumed-validation2-custody/"
OLD_SID = "DenyTheEvaluatorAndResearchPlanesTheConsumedValidation2Materialization"
NEW_SID = "DenyTheEvaluatorAndResearchPlanesEveryConsumedHoldoutMaterialization"
V1_IDENTITY = "d44230f45ed3d94af5bacfdd9f35529c0999186aa0661e7fb59dc3014aed0176"

_HERE = os.path.dirname(os.path.abspath(__file__))
TRACKED = os.path.join(_HERE, "aws", "backups-consumed-holdout-custody-policy.json")


def canonical(doc) -> str:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"))


def ident(doc) -> str:
    return hashlib.sha256(canonical(doc).encode()).hexdigest()


def aws(args):
    r = subprocess.run(["aws"] + args + ["--region", "us-east-1", "--output", "json"],
                       capture_output=True)
    if r.returncode != 0:
        raise SystemExit("aws failed: " + r.stderr.decode(errors="replace"))
    return r.stdout


def live():
    return json.loads(json.loads(aws(["s3api", "get-bucket-policy",
                                      "--bucket", BUCKET]))["Policy"])


def amend(doc):
    out = {k: v for k, v in doc.items()}
    stmts, hits = [], 0
    for st in doc["Statement"]:
        if st.get("Sid") != OLD_SID:
            stmts.append(st)
            continue
        hits += 1
        if st["Effect"] != "Deny":
            raise SystemExit("REFUSING: the target statement is not a Deny")
        st2 = {k: v for k, v in st.items()}
        st2["Sid"] = NEW_SID
        st2["Resource"] = ["arn:aws:s3:::%s/%s*" % (BUCKET, V1_PREFIX),
                           "arn:aws:s3:::%s/%s*" % (BUCKET, V2_PREFIX)]
        # principals, actions, effect and condition are carried over untouched
        for k in ("Effect", "Principal", "Action", "Condition"):
            st2[k] = st[k]
        stmts.append(st2)
    if hits != 1:
        raise SystemExit("REFUSING: expected exactly one %s statement, found %d" % (OLD_SID, hits))
    out["Statement"] = stmts
    return out


def diff(old, new):
    rows = []
    for k in sorted(set(old) | set(new)):
        if k == "Statement":
            continue
        same = canonical(old.get(k)) == canonical(new.get(k))
        rows.append({"element": "top-level %s" % k, "unchanged": same, "value": new.get(k)})
        if not same:
            raise SystemExit("REFUSING: top-level element %r changed" % k)
    if len(old["Statement"]) != len(new["Statement"]):
        raise SystemExit("REFUSING: statement count changed")
    o = {s.get("Sid"): s for s in old["Statement"]}
    n = {s.get("Sid"): s for s in new["Statement"]}
    rows.append({"element": "Sid", "old": OLD_SID, "new": NEW_SID,
                 "why": "the v1.0 Sid named Validation-2 specifically. A statement whose name "
                        "asserts a narrower scope than it enforces is the FutureOOSReader defect."})
    rows.append({"element": "Resource", "old": o[OLD_SID]["Resource"],
                 "new": n[NEW_SID]["Resource"],
                 "why": "the V1 custody prefix is added so a new V1 object is covered from the "
                        "moment it exists"})
    for k in ("Effect", "Principal", "Action", "Condition"):
        rows.append({"element": "%s.%s" % (NEW_SID, k),
                     "unchanged": canonical(o[OLD_SID][k]) == canonical(n[NEW_SID][k])})
    allows = [s for s in new["Statement"] if s["Effect"] != "Deny"]
    rows.append({"element": "allow statements", "count": len(allows),
                 "invariant": "the policy must remain deny-only"})
    if allows:
        raise SystemExit("REFUSING: an Allow statement appeared")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("plan", "apply"))
    ap.add_argument("--emit", default=None)
    args = ap.parse_args()

    old = live()
    print("live policy identity   %s" % ident(old))
    if ident(old) != V1_IDENTITY:
        raise SystemExit("REFUSING: live policy is not the sealed v1.0 identity %s" % V1_IDENTITY)
    new = amend(old)
    new_id = ident(new)
    print("SEALED amended identity %s" % new_id)
    d = diff(old, new)
    print("prefixes covered:")
    for r in new["Statement"][0]["Resource"]:
        print("   %s" % r)

    report = {
        "record_type": "MR002_ConsumedHoldoutCustodyDenial",
        "version": "2.0",
        "date": "2026-08-21",
        "authority": "owner ruling 2026-08-21 — extend the deny-only resource policy to the "
                     "Validation-1 custody prefix, AUTHORIZED / REQUIRED",
        "supersedes": "MR002_ConsumedValidation2_CustodyDenial_v1.0 / " + V1_IDENTITY,
        "identity_before": ident(old),
        "sealed_identity_after": new_id,
        "sealed_before_application": True,
        "statement_count_before": len(old["Statement"]),
        "statement_count_after": len(new["Statement"]),
        "allow_statements": 0,
        "sid_renamed": {"from": OLD_SID, "to": NEW_SID,
                        "why": "the v1.0 Sid named Validation-2 specifically. Adding the V1 "
                               "prefix while keeping that name would leave a statement whose "
                               "name asserts a narrower scope than it enforces — the "
                               "FutureOOSReader defect, which this program has already paid for "
                               "twice."},
        "invariant": "consumed holdout custody — irrespective of validation generation — is "
                     "inaccessible to the evaluator, reader, publisher, paper and "
                     "forward-validation planes.",
        "prefix_naming_decision": {
            "chosen": V1_PREFIX,
            "rejected": "mr002/consumed-holdout-custody/validation1/",
            "why": "the V2 object's location is now evidentiary identity and cannot move. A "
                   "second naming scheme for a class of exactly two members would leave the two "
                   "generations under different conventions — the same split that has produced "
                   "six role-transfer defects here. Symmetry with the immovable member beats "
                   "tidiness only half the class can adopt.",
        },
        "principals_unchanged": True,
        "actions_unchanged": True,
        "condition_unchanged": True,
        "retained_by_design": {
            "user/admin": "the custody verification principal",
            "MR002CustodyMonitorRole": "custody monitoring",
            "WorkbenchFleetAuditRole": "audit",
        },
        "diff": d,
    }
    if args.emit:
        with open(args.emit, "wb") as fh:
            fh.write((json.dumps(report, sort_keys=True, indent=1, ensure_ascii=True)
                      + "\n").encode("ascii"))

    if args.mode == "plan":
        print("\n--- DIFF ---")
        print(json.dumps(d, indent=1))
        print("\nPLAN ONLY. Nothing changed.")
        return 0

    pf = os.path.join(_HERE, "_custody_denial_v2.json")
    with open(pf, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(new, fh)
    aws(["s3api", "put-bucket-policy", "--bucket", BUCKET, "--policy", "file://" + pf])
    back = live()
    print("\napplied.  read-back %s  deployed == sealed: %s"
          % (ident(back), ident(back) == new_id))
    if ident(back) != new_id:
        raise SystemExit("DEPLOYED POLICY DOES NOT EQUAL THE SEALED IDENTITY")
    with open(TRACKED, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(back, fh, indent=2)
        fh.write("\n")
    print("tracked copy updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
