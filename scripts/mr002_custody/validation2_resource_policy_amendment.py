"""MR-002 — the minimal sealed-store RESOURCE-POLICY repair (Amendment R).

Owner ruling 2026-08-21, following the pre-read failure of the authorized opening
(MR002_Validation2_OpeningPreReadFailure_v1.0 = d1303229...).

WHAT THIS REPAIRS
    The bucket policy's oos/ statement still enforced the PRE-Cycle-2C role of that prefix: it
    denied every read of oos/* to any principal that was not
    `mr002-oos-reader-NOT-YET-PROVISIONED`, a role that has never existed. Under Cycle-2C the
    oos/ prefix IS the Validation-2 population, so the governed reader was denied. An explicit
    Deny in a resource policy defeats any identity Allow, which is why the correct, sealed,
    deployed identity-side Amendment A v1.2 could not override it.

WHAT THIS DELIBERATELY DOES NOT DO
    It does not add a blanket validation/* deny. Owner ruling: Validation-1 is permanently
    inadmissible to EVALUATION, which is not the same as its bytes being unreadable by every
    custody, forensic or administrative principal forever. An unconditional Deny would block
    legitimate evidence verification until the bucket policy itself were edited again. A narrower
    consumed-partition guard, expressed in governance-role terms with its custody principals
    enumerated, is a SEPARATE strengthening.

    It does not broaden the admitted principal beyond mr002-validation-reader, does not touch any
    other statement, and does not authorize any opening.

MODES
    plan   -- verify the live policy equals the tracked defective identity, emit the exact
              old->new diff and the SEALED amended identity. Changes nothing.
    apply  -- re-verify, apply, read back, and require deployed == sealed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

BUCKET = "workbench-mr002-sealed-219024422756"
READER = "arn:aws:iam::219024422756:role/mr002-validation-reader"
PLACEHOLDER = "arn:aws:iam::219024422756:role/mr002-oos-reader-NOT-YET-PROVISIONED"
OLD_SID = "DenyOOSReadsToEveryPrincipalButTheFutureOOSReader"
NEW_SID = "DenyValidation2ReadsToEveryPrincipalButGovernedValidationReader"
DEFECTIVE_CANONICAL = "b529bb26c5d542b255adf8c94349609180bd4599108debbd8fac693567437baf"

# The invariant the owner required be stated explicitly in the policy record:
#
#   oos/ is a PHYSICAL STORAGE PREFIX; its CURRENT GOVERNANCE ROLE is Validation-2.
#
# It is carried by the SID, which is the element of a policy document that names what a statement
# enforces, and it is restated in full in the sealed amendment record.
#
# ⛔ It is deliberately NOT carried in the top-level `Id`. The live policy ALREADY has one
# ("MR002SealedStorePolicy"). Writing the invariant there would REPLACE an existing element, which
# is broader than the authorized minimal change — and an earlier draft of this script did exactly
# that while the diff silently omitted it, because the diff only reported `Id` when the old policy
# had none. Quietly-modified elements are how this defect family keeps recurring. The top-level
# elements are now asserted unchanged instead.
GOVERNANCE_INVARIANT = ("oos/ is a PHYSICAL STORAGE PREFIX; its CURRENT GOVERNANCE ROLE is "
                        "Validation-2, readable only by "
                        "arn:aws:iam::219024422756:role/mr002-validation-reader at its six "
                        "registered VersionIds. validation/ is the CONSUMED Validation-1 "
                        "partition, permanently inadmissible to evaluation.")

_HERE = os.path.dirname(os.path.abspath(__file__))
TRACKED = os.path.join(_HERE, "aws", "sealed-store-bucket-policy.json")


def canonical(doc) -> str:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"))


def ident(doc) -> str:
    return hashlib.sha256(canonical(doc).encode()).hexdigest()


def aws(args) -> bytes:
    r = subprocess.run(["aws"] + args + ["--region", "us-east-1", "--output", "json"],
                       capture_output=True)
    if r.returncode != 0:
        raise SystemExit("aws failed: " + r.stderr.decode(errors="replace"))
    return r.stdout


def live_policy() -> dict:
    raw = json.loads(aws(["s3api", "get-bucket-policy", "--bucket", BUCKET]))["Policy"]
    return json.loads(raw)


def amend(doc: dict) -> dict:
    """Return the amended document. Exactly one statement changes; nothing else is touched."""
    out = {k: v for k, v in doc.items()}
    new_statements = []
    hits = 0
    for st in doc["Statement"]:
        if st.get("Sid") != OLD_SID:
            new_statements.append(st)                       # byte-for-byte untouched
            continue
        hits += 1
        cond = st["Condition"]["StringNotEquals"]
        if cond.get("aws:PrincipalArn") != PLACEHOLDER:
            raise SystemExit("REFUSING: the oos/ statement does not carry the expected "
                             "placeholder principal; the live policy is not the one this "
                             "amendment was written against.")
        st2 = {k: v for k, v in st.items()}
        st2["Sid"] = NEW_SID
        st2["Condition"] = {"StringNotEquals": {"aws:PrincipalArn": READER}}
        # every other element of this statement is carried over unchanged
        for k in ("Effect", "Principal", "Action", "Resource"):
            st2[k] = st[k]
        new_statements.append(st2)
    if hits != 1:
        raise SystemExit("REFUSING: expected exactly one %s statement, found %d" % (OLD_SID, hits))
    out["Statement"] = new_statements
    return out


def diff(old: dict, new: dict) -> list:
    rows = []
    # EVERY top-level element other than Statement must be unchanged, and the diff must SAY SO
    # for each one by name. Reporting a key only when it is absent from the old document is how a
    # silent overwrite hides; this enumerates the union instead.
    for k in sorted(set(old) | set(new)):
        if k == "Statement":
            continue
        same = canonical(old.get(k)) == canonical(new.get(k))
        rows.append({"element": "top-level %s" % k, "unchanged_byte_for_byte": same,
                     "value": new.get(k)})
        if not same:
            raise SystemExit("REFUSING: top-level element %r changed; this amendment is "
                             "authorized to change one statement only" % k)
    o = {s.get("Sid"): s for s in old["Statement"]}
    n = {s.get("Sid"): s for s in new["Statement"]}
    rows.append({"element": "Sid", "old": OLD_SID, "new": NEW_SID,
                 "why": "the stale Future-OOS terminology is the semantic debt that caused this "
                        "defect family; the name must state the CURRENT governance role"})
    rows.append({"element": "Condition.StringNotEquals.aws:PrincipalArn",
                 "old": PLACEHOLDER, "new": READER,
                 "why": "the placeholder role has never existed, so the statement denied the "
                        "governed reader"})
    for sid in sorted(set(o) | set(n)):
        if sid in (OLD_SID, NEW_SID):
            continue
        same = canonical(o.get(sid)) == canonical(n.get(sid))
        rows.append({"element": "statement %s" % sid,
                     "unchanged_byte_for_byte": same})
    # what did NOT change inside the amended statement
    oo, nn = o[OLD_SID], n[NEW_SID]
    for k in ("Effect", "Principal", "Action", "Resource"):
        rows.append({"element": "%s.%s" % (NEW_SID, k),
                     "unchanged_byte_for_byte": canonical(oo[k]) == canonical(nn[k]),
                     "value": nn[k]})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("plan", "apply"))
    ap.add_argument("--emit", default=None)
    args = ap.parse_args()

    old = live_policy()
    old_id = ident(old)
    print("live bucket policy identity   %s" % old_id)
    if old_id != DEFECTIVE_CANONICAL:
        raise SystemExit("REFUSING: the live policy is not the tracked defective identity %s"
                         % DEFECTIVE_CANONICAL)
    with open(TRACKED, "rb") as fh:
        tracked = json.loads(fh.read())
    if ident(tracked) != old_id:
        raise SystemExit("REFUSING: the tracked copy no longer equals the live policy")
    print("live == tracked defective identity: True")

    new = amend(old)
    new_id = ident(new)
    print("SEALED amended identity       %s" % new_id)
    print("statements  %d -> %d" % (len(old["Statement"]), len(new["Statement"])))

    report = {
        "record_type": "MR002_Validation2_SealedStoreResourcePolicyAmendment",
        "version": "1.0",
        "date": "2026-08-21",
        "authority": "owner ruling 2026-08-21 — minimal oos/* resource-policy repair, AUTHORIZED "
                     "TO SEAL AND APPLY",
        "repairs": "MR002_Validation2_OpeningPreReadFailure_v1.0 / d1303229...",
        "bucket": BUCKET,
        "defective_identity_before": old_id,
        "sealed_identity_after": new_id,
        "sealed_before_application": True,
        "statement_count_before": len(old["Statement"]),
        "statement_count_after": len(new["Statement"]),
        "admitted_principal": READER,
        "admitted_principal_broadened": False,
        "placeholder_removed": PLACEHOLDER,
        "sid_renamed": {"from": OLD_SID, "to": NEW_SID},
        "governance_invariant": GOVERNANCE_INVARIANT,
        "where_the_invariant_is_stated": "in the SID of the amended statement, which is the element that names what a statement enforces, and in full in this record. It is "
                                        "deliberately NOT written into the top-level Id: the live policy already has one (MR002SealedStorePolicy), so writing it there would REPLACE an existing element rather than add one, which is broader than the authorized change. An earlier draft of this script did exactly that while the diff omitted it — the diff now enumerates every top-level element and refuses if any changed.",
        "diff": diff(old, new),
        "explicitly_not_done": {
            "blanket_validation_deny": "NOT APPROVED and NOT INCLUDED. Validation-1 is "
                                       "permanently inadmissible to EVALUATION; that is not the "
                                       "same as its bytes being unreadable by every custody, "
                                       "forensic or administrative principal forever. An "
                                       "unconditional Deny would block legitimate evidence "
                                       "verification until the bucket policy were edited again. "
                                       "A narrower evaluator-path guard with its custody "
                                       "principals enumerated is a SEPARATE strengthening.",
            "other_statements": "DenyInsecureTransport, "
                                "DenyValidationReadsToEveryPrincipalButTheValidationReader and "
                                "DenyPermanentDeletionOfSealedObjectVersions are carried over "
                                "byte-for-byte.",
            "identity_side": "Amendment A v1.2 is correct as deployed and is NOT touched.",
        },
        "authorizes": "NOTHING. Applying this amendment does not open Validation-2. A fresh "
                      "opening requires its own owner ruling, and readiness must first carry the "
                      "eleventh gate.",
    }
    if args.emit:
        with open(args.emit, "wb") as fh:
            fh.write((json.dumps(report, sort_keys=True, indent=1, ensure_ascii=True)
                      + "\n").encode("ascii"))

    if args.mode == "plan":
        print("\n--- DIFF ---")
        print(json.dumps(report["diff"], indent=1))
        print("\nPLAN ONLY. Nothing was changed.")
        return 0

    pf = os.path.join(_HERE, "_amended_bucket_policy.json")
    with open(pf, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(new, fh)
    aws(["s3api", "put-bucket-policy", "--bucket", BUCKET, "--policy", "file://" + pf])
    print("\napplied.")

    back = live_policy()
    back_id = ident(back)
    print("read-back identity            %s" % back_id)
    print("deployed == sealed:           %s" % (back_id == new_id))
    if back_id != new_id:
        raise SystemExit("DEPLOYED POLICY DOES NOT EQUAL THE SEALED IDENTITY")
    sids = [s.get("Sid") for s in back["Statement"]]
    assert OLD_SID not in sids and NEW_SID in sids, sids
    assert PLACEHOLDER not in canonical(back)
    print("placeholder absent:           True")
    print("Sid now:                      %s" % NEW_SID)
    return 0


if __name__ == "__main__":
    sys.exit(main())
