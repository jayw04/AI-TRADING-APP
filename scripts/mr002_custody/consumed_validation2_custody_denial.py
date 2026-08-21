"""Resource-side denial protecting the CONSUMED Validation-2 materialization.

Owner ruling 2026-08-21: archive the materialized DuckDB into custody that the evaluator and
research planes cannot reach, then delete the host copy. The label is secondary; IAM/resource-policy
denial of the research/evaluator path is the actual control.

WHY A RESOURCE-SIDE DENY AND NOT JUST IDENTITY-SIDE ABSENCE
    The evaluator host role grants no read on this bucket at all, so today it has no route by
    OMISSION. Omission is not a control: it holds only until someone attaches a policy. The
    2026-08-21 pre-read failure was the mirror image of this -- an identity-side amendment that was
    complete and correct, defeated by the resource side nobody had re-pointed. The enforceable form
    is an explicit Deny naming the principals that must never reach these bytes.

SCOPE, AND WHAT IS DELIBERATELY NOT DENIED
    The bucket has NO policy today, so this creates one. It contains ONLY Deny statements and no
    Allow, which means it grants nothing and removes nothing from any other prefix: absent an
    explicit Deny, evaluation falls through to identity policies exactly as before. The Deny is
    scoped to one prefix and an enumerated principal list.

    Custody, audit and administrative principals RETAIN access BY DESIGN. Someone must be able to
    verify custody, and an unconditional Deny would block exactly the evidence verification this
    archive exists to support -- the same reasoning that made a blanket validation/* deny the wrong
    answer. This is stated plainly rather than dressed up as "nobody can read it".
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

BUCKET = "workbench-backups-219024422756"
PREFIX = "mr002/consumed-validation2-custody/"
SID = "DenyTheEvaluatorAndResearchPlanesTheConsumedValidation2Materialization"

# Every principal on an evaluation or research path. Enumerated, never a wildcard.
DENIED_PRINCIPALS = [
    "arn:aws:iam::219024422756:role/mr002-phase3c-run-host",
    "arn:aws:iam::219024422756:role/mr002-validation-reader",
    "arn:aws:iam::219024422756:role/mr002-evaluator-publisher",
    "arn:aws:iam::219024422756:role/mr002-validation2-evidence-publisher",
    "arn:aws:iam::219024422756:role/mr002-validation2-publish-host-role",
    "arn:aws:iam::219024422756:role/workbench-paper-InstanceRole-4P2Tvq7FaG1E",
    "arn:aws:iam::219024422756:role/workbench-forward-validation-session",
    "arn:aws:iam::219024422756:role/workbench-forward-validation-witness",
]
# Retained by design, and named here so the omission is a decision rather than an oversight.
RETAINED_BY_DESIGN = {
    "arn:aws:iam::219024422756:user/admin": "the custody verification principal",
    "arn:aws:iam::219024422756:role/MR002CustodyMonitorRole": "custody monitoring",
    "arn:aws:iam::219024422756:role/WorkbenchFleetAuditRole": "audit",
}

_HERE = os.path.dirname(os.path.abspath(__file__))
TRACKED = os.path.join(_HERE, "aws", "backups-consumed-validation2-custody-policy.json")


def canonical(doc) -> str:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"))


def ident(doc) -> str:
    return hashlib.sha256(canonical(doc).encode()).hexdigest()


def aws(args, allow_fail=False):
    r = subprocess.run(["aws"] + args + ["--region", "us-east-1", "--output", "json"],
                       capture_output=True)
    if r.returncode != 0 and not allow_fail:
        raise SystemExit("aws failed: " + r.stderr.decode(errors="replace"))
    return r.stdout, r.returncode, r.stderr.decode(errors="replace")


def live_policy():
    out, rc, err = aws(["s3api", "get-bucket-policy", "--bucket", BUCKET], allow_fail=True)
    if rc != 0:
        if "NoSuchBucketPolicy" in err:
            return None
        raise SystemExit("unexpected: " + err)
    return json.loads(json.loads(out)["Policy"])


def build():
    return {
        "Version": "2012-10-17",
        "Id": "WorkbenchBackupsConsumedHoldoutCustody",
        "Statement": [{
            "Sid": SID,
            "Effect": "Deny",
            "Principal": "*",
            "Action": ["s3:GetObject", "s3:GetObjectVersion", "s3:GetObjectAttributes",
                       "s3:GetObjectVersionAttributes"],
            "Resource": "arn:aws:s3:::%s/%s*" % (BUCKET, PREFIX),
            "Condition": {"StringEquals": {"aws:PrincipalArn": DENIED_PRINCIPALS}},
        }],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("plan", "apply"))
    ap.add_argument("--emit", default=None)
    args = ap.parse_args()

    old = live_policy()
    print("live bucket policy: %s" % ("NONE - this creates one" if old is None else ident(old)))
    if old is not None:
        raise SystemExit("REFUSING: a bucket policy already exists. This script was written for "
                         "a bucket with none; amending an existing policy needs its own review.")

    new = build()
    new_id = ident(new)
    print("SEALED policy identity  %s" % new_id)
    print("statements              %d  (Deny: %d, Allow: 0)"
          % (len(new["Statement"]),
             sum(1 for s in new["Statement"] if s["Effect"] == "Deny")))
    print("prefix                  %s" % PREFIX)
    print("denied principals       %d" % len(DENIED_PRINCIPALS))
    for p in DENIED_PRINCIPALS:
        print("   DENY  %s" % p.split("/")[-1])
    for p, why in sorted(RETAINED_BY_DESIGN.items()):
        print("   keep  %-42s %s" % (p.split("/")[-1], why))

    report = {
        "record_type": "MR002_ConsumedValidation2_CustodyDenial",
        "version": "1.0",
        "date": "2026-08-21",
        "authority": "owner ruling 2026-08-21 — archive to inaccessible evidence custody",
        "bucket": BUCKET,
        "prefix": PREFIX,
        "policy_existed_before": False,
        "sealed_identity": new_id,
        "sealed_before_application": True,
        "allow_statements": 0,
        "grants_nothing": "the policy contains only Deny. It grants no access and removes none "
                          "from any other prefix: absent an explicit Deny, evaluation falls "
                          "through to identity policies exactly as before.",
        "denied_principals": DENIED_PRINCIPALS,
        "retained_by_design": RETAINED_BY_DESIGN,
        "why_resource_side": "the evaluator host role grants no read on this bucket, so today it "
                             "has no route by OMISSION. Omission is not a control — it holds only "
                             "until someone attaches a policy. The 2026-08-21 pre-read failure "
                             "was the mirror image: a complete and correct identity-side "
                             "amendment defeated by the resource side nobody had re-pointed.",
        "honest_scope": "custody, audit and administrative principals RETAIN access by design. "
                        "An unconditional Deny would block the evidence verification this "
                        "archive exists to support. This is a scoped control, not a claim that "
                        "nobody can read the object.",
    }
    if args.emit:
        with open(args.emit, "wb") as fh:
            fh.write((json.dumps(report, sort_keys=True, indent=1, ensure_ascii=True)
                      + "\n").encode("ascii"))

    if args.mode == "plan":
        print("\nPLAN ONLY. Nothing was changed.")
        print(json.dumps(new, indent=1))
        return 0

    pf = os.path.join(_HERE, "_custody_denial.json")
    with open(pf, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(new, fh)
    aws(["s3api", "put-bucket-policy", "--bucket", BUCKET, "--policy", "file://" + pf])
    print("\napplied.")
    back = live_policy()
    print("read-back identity      %s" % ident(back))
    print("deployed == sealed:     %s" % (ident(back) == new_id))
    if ident(back) != new_id:
        raise SystemExit("DEPLOYED POLICY DOES NOT EQUAL THE SEALED IDENTITY")
    os.makedirs(os.path.dirname(TRACKED), exist_ok=True)
    with open(TRACKED, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(back, fh, indent=2)
        fh.write("\n")
    print("tracked copy written:   %s" % os.path.relpath(TRACKED))
    return 0


if __name__ == "__main__":
    sys.exit(main())
