"""MR-002 ELEVENTH READINESS GATE — the RESOURCE-side counterpart to Amendment A.

    resource_policy_admits_only_the_governed_validation2_reader_to_the_registered_
    validation2_population

Owner ruling 2026-08-21. Gate 10 fixed launcher + manifest coverage. This gate is a DISTINCT
boundary and is stated separately rather than folded into gate 10, because the 2026-08-21 opening
proved that a complete, sealed, byte-verified IDENTITY-side amendment says nothing whatever about
the RESOURCE side: an explicit Deny in a bucket policy defeats any identity Allow.

WHY STATIC HASHING WAS NOT ENOUGH, AND STILL IS NOT
    The bucket policy that refused the opening was BYTE-IDENTICAL to its tracked copy. Hashing
    proves a document has not drifted; it cannot prove the document says the right thing. This
    gate therefore EVALUATES the combined policy semantics, and its static half is explicitly
    NOT sufficient on its own -- see `verdict`, which can never be TRUE without the live
    metadata-only authorization probe recorded alongside it.

THE TWO HALVES
    STATIC (this script, runnable any time, latch CLOSED, zero exposure)
        live bucket-policy identity; the governed reader ARN; the exact oos/* resource scope; the
        absence of the never-provisioned placeholder; the current-role Sid; and a combined
        bucket+identity authorization evaluation over a discrimination matrix.
    LIVE (mr002_v2_head_authorization_probe.py, next authorized latch cycle only)
        six metadata-only HeadObject probes at the exact registered keys and VersionIds, before
        any GetObjectVersion.

    ⭐ A versioned HeadObject and a versioned GetObject authorize under the SAME action,
    s3:GetObjectVersion. The HEAD probe is therefore a SUFFICIENT proof of the authorization
    decision the content read will get -- not a correlated proxy for it -- while transferring no
    body bytes. That is what makes it safe on this side of the consumption boundary.

THE EVALUATOR REFUSES WHAT IT CANNOT MODEL
    Every construct it does not understand raises. A checker that cannot fail is worthless, and
    this program has already shipped three such checks. The evaluator is additionally MUTATION-
    CONTROLLED against the archived defective document: if it does not return DENY for the
    governed reader under the pre-amendment policy, this gate aborts.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import subprocess
import sys

BUCKET = "workbench-mr002-sealed-219024422756"
READER = "arn:aws:iam::219024422756:role/mr002-validation-reader"
RUN_HOST = "arn:aws:iam::219024422756:role/mr002-phase3c-run-host"
ADMIN = "arn:aws:iam::219024422756:user/admin"
PLACEHOLDER_FRAGMENT = "NOT-YET-PROVISIONED"
EXPECTED_SID = "DenyValidation2ReadsToEveryPrincipalButGovernedValidationReader"
STALE_SID = "DenyOOSReadsToEveryPrincipalButTheFutureOOSReader"
OOS_SCOPE = "arn:aws:s3:::workbench-mr002-sealed-219024422756/oos/*"

AMENDED_BUCKET_POLICY_IDENTITY = \
    "7bb73e62066e52303c5d48ed0cd740cb16b4f2825110dde92d9cc4d6dfc164a5"
DEFECTIVE_BUCKET_POLICY_IDENTITY = \
    "b529bb26c5d542b255adf8c94349609180bd4599108debbd8fac693567437baf"
AMENDMENT_A_V12_IDENTITY = \
    "d7b5cf2be0d4523967ff63d121341572c3b111ac5085e04f9c4a7a2b4e25eedd"

REGISTERED = {
    "oos/actions.parquet": "F6m6am6cBahBd95p41C1.aAVmYd8GuNG",
    "oos/anchors.parquet": "RsJZG3TkDXvNPERJhZVanJ.Vqg8_dulw",
    "oos/etf_prices.parquet": "Z3OsUeuucMYIl2v9JDoVNDx1nw.0avDj",
    "oos/prices.parquet": "1ope9PR._oR303.EbZNGPVlIJRy.SZbA",
    "oos/sic_observations.parquet": "DPhtWW3Pca3TKtSa1LOnGKA.yrZ98EIt",
    "oos/universe.parquet": "0gaqJ9TuECc3U_zar99sqls2UHRDnkkY",
}


class UnmodelledConstruct(RuntimeError):
    """The evaluator met a policy construct it does not implement. It refuses rather than guess."""


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


def _as_list(v):
    if v is None:
        return None
    return v if isinstance(v, list) else [v]


def _match_any(value, patterns):
    return any(fnmatch.fnmatchcase(value, p) for p in patterns)


def _condition_holds(cond, ctx):
    """Evaluate the condition block under AWS's missing-key semantics.

    StringEquals on an ABSENT key is FALSE. StringNotEquals on an ABSENT key is TRUE -- the key
    cannot equal the value if it is not there. That asymmetry is load-bearing here: it is what
    makes the version-pinning Deny apply to an UNVERSIONED request.
    """
    if not cond:
        return True
    for op, kv in cond.items():
        for key, expected in kv.items():
            expected = _as_list(expected)
            k = key.lower()
            if k == "aws:securetransport":
                actual = "true" if ctx.get("secure_transport", True) else "false"
                if op != "Bool":
                    raise UnmodelledConstruct("%s on %s" % (op, key))
                if actual not in [str(e).lower() for e in expected]:
                    return False
                continue
            if k == "aws:principalarn":
                actual = ctx["principal_arn"]
            elif k == "s3:versionid":
                actual = ctx.get("version_id")
            elif k == "s3:prefix":
                actual = ctx.get("prefix")
            else:
                raise UnmodelledConstruct("condition key %s" % key)

            if op == "StringEquals":
                if actual is None or actual not in expected:
                    return False
            elif op == "StringNotEquals":
                if actual is not None and actual in expected:
                    return False
            elif op == "StringLike":
                if actual is None or not _match_any(actual, expected):
                    return False
            else:
                raise UnmodelledConstruct("condition operator %s" % op)
    return True


def _statement_applies(st, ctx, resource_policy):
    if resource_policy:
        pr = st.get("Principal")
        if pr != "*":
            raise UnmodelledConstruct("Principal %r" % (pr,))
    if "NotAction" in st:
        if _match_any(ctx["action"], _as_list(st["NotAction"])):
            return False
    elif "Action" in st:
        if not _match_any(ctx["action"], _as_list(st["Action"])):
            return False
    else:
        raise UnmodelledConstruct("statement with neither Action nor NotAction")

    if "NotResource" in st:
        if _match_any(ctx["resource_arn"], _as_list(st["NotResource"])):
            return False
    elif "Resource" in st:
        if not _match_any(ctx["resource_arn"], _as_list(st["Resource"])):
            return False
    else:
        raise UnmodelledConstruct("statement with neither Resource nor NotResource")

    for k in st:
        if k not in ("Sid", "Effect", "Action", "NotAction", "Resource", "NotResource",
                     "Condition", "Principal"):
            raise UnmodelledConstruct("statement element %s" % k)
    return _condition_holds(st.get("Condition"), ctx)


def evaluate(bucket_policy, identity_policy, ctx):
    """Explicit Deny wins; otherwise an Allow is required; otherwise implicit deny."""
    denies, allows = [], []
    for doc, is_res in ((bucket_policy, True), (identity_policy, False)):
        if doc is None:
            continue
        for st in doc["Statement"]:
            if not _statement_applies(st, ctx, is_res):
                continue
            (denies if st["Effect"] == "Deny" else allows).append(
                ("resource" if is_res else "identity", st.get("Sid")))
    if denies:
        return "DENY", denies
    if allows:
        return "ALLOW", allows
    return "IMPLICIT_DENY", []


# ── the discrimination matrix ────────────────────────────────────────────────────────────────
def matrix(bucket, reader_identity):
    """(name, expected, ctx, identity_policy). ADMIN is modelled as Allow-* deliberately: any
    DENY for admin must therefore come from the RESOURCE policy alone."""
    admin_allow_star = {"Statement": [{"Sid": "AdministratorAccess", "Effect": "Allow",
                                       "Action": "*", "Resource": "*"}]}
    cases = []
    for key, vid in sorted(REGISTERED.items()):
        arn = "arn:aws:s3:::%s/%s" % (BUCKET, key)
        cases.append(("reader GetObjectVersion %s @registered" % key, "ALLOW",
                      {"principal_arn": READER, "action": "s3:GetObjectVersion",
                       "resource_arn": arn, "version_id": vid}, reader_identity))
        cases.append(("reader GetObjectVersion %s @WRONG version" % key, "DENY",
                      {"principal_arn": READER, "action": "s3:GetObjectVersion",
                       "resource_arn": arn, "version_id": "wrongVersionIdXXXXXXXXXXXXXXXXXX"},
                      reader_identity))
        cases.append(("reader HeadObject(versioned) %s @registered" % key, "ALLOW",
                      {"principal_arn": READER, "action": "s3:GetObjectVersion",
                       "resource_arn": arn, "version_id": vid}, reader_identity))
    a = "arn:aws:s3:::%s/oos/prices.parquet" % BUCKET
    cases += [
        ("reader UNVERSIONED GetObject on a registered key", "DENY",
         {"principal_arn": READER, "action": "s3:GetObject", "resource_arn": a}, reader_identity),
        ("reader GetObjectVersion on an UNREGISTERED oos key", "DENY",
         {"principal_arn": READER, "action": "s3:GetObjectVersion",
          "resource_arn": "arn:aws:s3:::%s/oos/seventh.parquet" % BUCKET,
          "version_id": "anything"}, reader_identity),
        ("reader PutObject on oos/", "DENY",
         {"principal_arn": READER, "action": "s3:PutObject", "resource_arn": a}, reader_identity),
        ("reader DeleteObjectVersion on oos/", "DENY",
         {"principal_arn": READER, "action": "s3:DeleteObjectVersion", "resource_arn": a},
         reader_identity),
        ("reader read of CONSUMED validation/", "DENY",
         {"principal_arn": READER, "action": "s3:GetObjectVersion",
          "resource_arn": "arn:aws:s3:::%s/validation/prices.parquet" % BUCKET,
          "version_id": "anything"}, reader_identity),
        ("RUN-HOST role reading oos/ directly", "DENY",
         {"principal_arn": RUN_HOST, "action": "s3:GetObjectVersion", "resource_arn": a,
          "version_id": REGISTERED["oos/prices.parquet"]}, admin_allow_star),
        ("ADMIN (modelled Allow-*) reading oos/", "DENY",
         {"principal_arn": ADMIN, "action": "s3:GetObjectVersion", "resource_arn": a,
          "version_id": REGISTERED["oos/prices.parquet"]}, admin_allow_star),
        ("ADMIN (modelled Allow-*) HeadObject oos/ unversioned", "DENY",
         {"principal_arn": ADMIN, "action": "s3:GetObject", "resource_arn": a}, admin_allow_star),
        ("reader read over INSECURE transport", "DENY",
         {"principal_arn": READER, "action": "s3:GetObjectVersion", "resource_arn": a,
          "version_id": REGISTERED["oos/prices.parquet"], "secure_transport": False},
         reader_identity),
        ("reader read of open reference/", "ALLOW",
         {"principal_arn": READER, "action": "s3:GetObject",
          "resource_arn": "arn:aws:s3:::%s/reference/crosswalk.parquet" % BUCKET},
         reader_identity),
    ]
    return cases


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", default=None)
    ap.add_argument("--defective", default=None,
                    help="path to the archived PRE-amendment bucket policy, used as the "
                         "mutation control. Without it the control cannot run and the gate "
                         "reports its absence rather than quietly skipping it.")
    args = ap.parse_args()

    R: dict = {"record_type": "MR002_Validation2_ResourcePolicyGate", "version": "1.0",
               "gate": "resource_policy_admits_only_the_governed_validation2_reader_to_the_"
                       "registered_validation2_population"}

    bucket = json.loads(json.loads(aws(["s3api", "get-bucket-policy",
                                        "--bucket", BUCKET]))["Policy"])
    reader_identity = json.loads(aws(["iam", "get-role-policy", "--role-name",
                                      "mr002-validation-reader", "--policy-name",
                                      "mr002-validation-only"]))["PolicyDocument"]

    R["bound"] = {
        "live_bucket_policy_identity": ident(bucket),
        "expected_bucket_policy_identity": AMENDED_BUCKET_POLICY_IDENTITY,
        "live_reader_identity_policy": ident(reader_identity),
        "expected_reader_identity_policy": AMENDMENT_A_V12_IDENTITY,
        "governed_reader_arn": READER,
        "oos_resource_scope": OOS_SCOPE,
        "expected_sid": EXPECTED_SID,
    }

    sids = [s.get("Sid") for s in bucket["Statement"]]
    stmt = next((s for s in bucket["Statement"] if s.get("Sid") == EXPECTED_SID), None)
    blob = canonical(bucket)

    checks = {
        "live bucket policy == the sealed amended identity":
            ident(bucket) == AMENDED_BUCKET_POLICY_IDENTITY,
        "live reader identity policy == Amendment A v1.2":
            ident(reader_identity) == AMENDMENT_A_V12_IDENTITY,
        "the current-role Sid is present": stmt is not None,
        "the stale Future-OOS Sid is gone": STALE_SID not in sids,
        "no never-provisioned placeholder anywhere in the document":
            PLACEHOLDER_FRAGMENT not in blob,
        "the oos statement admits EXACTLY the governed reader and nobody else":
            stmt is not None
            and stmt["Condition"] == {"StringNotEquals": {"aws:PrincipalArn": READER}},
        "the oos statement scope is exactly the oos/ prefix":
            stmt is not None and stmt["Resource"] == OOS_SCOPE,
        "the oos statement is still a Deny": stmt is not None and stmt["Effect"] == "Deny",
        "the consumed validation/ statement is untouched":
            "DenyValidationReadsToEveryPrincipalButTheValidationReader" in sids,
        "insecure transport still denied": "DenyInsecureTransport" in sids,
        "version deletion still denied": "DenyPermanentDeletionOfSealedObjectVersions" in sids,
    }

    # ── mutation control: the evaluator MUST condemn the document that actually failed ────────
    control = {"ran": False}
    if args.defective:
        with open(args.defective, "rb") as fh:
            bad = json.loads(fh.read())
        if ident(bad) != DEFECTIVE_BUCKET_POLICY_IDENTITY:
            raise SystemExit("REFUSING: --defective is not the archived pre-amendment document")
        verdict, why = evaluate(bad, reader_identity, {
            "principal_arn": READER, "action": "s3:GetObjectVersion",
            "resource_arn": "arn:aws:s3:::%s/oos/actions.parquet" % BUCKET,
            "version_id": REGISTERED["oos/actions.parquet"]})
        control = {"ran": True, "verdict_under_the_defective_policy": verdict, "because": why,
                   "discriminates": verdict == "DENY"}
        checks["mutation control: the evaluator DENIES the reader under the defective policy"] = \
            control["discriminates"]
    else:
        checks["mutation control ran"] = False

    rows = []
    for name, expected, ctx, idp in matrix(bucket, reader_identity):
        got, why = evaluate(bucket, idp, ctx)
        ok = (got == expected) if expected == "ALLOW" else got.endswith("DENY")
        rows.append({"case": name, "expected": expected, "got": got, "pass": ok,
                     "decided_by": why})
    R["authorization_matrix"] = rows
    R["authorization_matrix_summary"] = "%d/%d" % (sum(1 for r in rows if r["pass"]), len(rows))
    checks["combined bucket+identity authorization matrix"] = all(r["pass"] for r in rows)

    R["mutation_control"] = control
    R["static_checks"] = checks
    R["static_half"] = all(checks.values())

    # ── the verdict. The static half CANNOT carry this gate on its own. ───────────────────────
    R["live_head_authorization_probe"] = {
        "status": "NOT YET RUN",
        "why": "the governed reader is assumable only with the latch OPEN, so the live "
               "authorization decision is unobservable from a closed state. This is the same "
               "residual that readiness v4.0 registered and that the 2026-08-21 opening realised.",
        "required_before_any_content_read": [
            "all six exact registered oos/* keys",
            "the exact registered VersionId on each, via the pinned-version HeadObject",
            "six successful metadata-only probes",
            "zero GetObject / GetObjectVersion content calls",
            "zero read_verified journal rows",
            "zero body bytes transferred",
        ],
        "on_any_failure": "restore the latch 7->8 immediately, seal a PRE-READ failure, leave "
                          "Validation-2 UNCONSUMED, do not launch the evaluation.",
        "sufficiency": "a versioned HeadObject authorizes under s3:GetObjectVersion, the SAME "
                       "action as the versioned content read. The probe proves the exact "
                       "authorization decision the read will receive, without a body.",
    }
    R["verdict"] = {
        "gate_11": "PARTIAL — STATIC HALF PASSES" if R["static_half"] else "FAIL",
        "is_true": False,
        "why_not_true": "this gate is defined to be TRUE only when the static half passes AND "
                        "the six live metadata-only authorization probes have succeeded. "
                        "Reporting TRUE on the static half alone would reproduce exactly the "
                        "failure this gate exists to prevent: a faithful hash of a policy that "
                        "is faithfully wrong.",
    }
    if args.emit:
        with open(args.emit, "wb") as fh:
            fh.write((json.dumps(R, sort_keys=True, indent=1, ensure_ascii=True)
                      + "\n").encode("ascii"))

    print("GATE 11 — resource-policy admission")
    for k, v in sorted(checks.items()):
        print("  %-70s %s" % (k[:70], "PASS" if v else "FAIL"))
    print("  authorization matrix                                                   %s"
          % R["authorization_matrix_summary"])
    for r in rows:
        if not r["pass"]:
            print("    FAILING CASE: %s expected %s got %s" % (r["case"], r["expected"],
                                                               r["got"]))
    print("\n  static half : %s" % ("PASS" if R["static_half"] else "FAIL"))
    print("  live probe  : NOT YET RUN")
    print("  GATE 11     : %s" % R["verdict"]["gate_11"])
    return 0 if R["static_half"] else 1


if __name__ == "__main__":
    sys.exit(main())
