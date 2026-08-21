"""MR-002 P1 — Amendment R procedure for the runtime-custody deletion Deny.

PURPOSE. Extend `DenyPermanentDeletionOfSealedObjectVersions` in the MR-002 sealed-store bucket
policy to cover `runtime-custody/*`, so the preserved Stage-3 runtime archive's object versions
are protected on the same footing as validation/ and oos/. This closes the control gap recorded
as P1-CUST-F1.

THE SEMANTIC CHANGE IS EXACTLY ONE ARN. Nothing else may change: not the policy Id, not any Sid,
not the validation/OOS ARNs, not a principal, not a condition. No Allow is added. No resource is
removed. The document is derived by MODIFYING THE LIVE OBJECT, never by reconstructing it from a
template — a reduced template is how a governance surface silently loses an element.

WHY THIS IS A SCRIPT AND NOT AN AD-HOC EDIT. On 2026-08-21 a complete, correct identity-side
amendment was defeated by a resource-side statement nobody had re-pointed, costing a governed
latch cycle. The Amendment R procedure exists for that: seal the proposal BEFORE applying it,
enumerate every top-level element, and REFUSE on any unintended change. This script refuses; it
does not "correct" a surprise interactively.

⚠ NOTE THE SELF-DEFECT AMENDMENT R CAUGHT IN ITSELF: the live policy ALREADY carries a top-level
`Id` (MR002SealedStorePolicy). A draft that writes an Id would REPLACE an existing element while
a naive diff stayed silent, because it only reported Id when the old document had none. This
script enumerates EVERY top-level element unconditionally.

PHASES (run in order; each refuses to proceed if its precondition fails):

    --prepare   fetch live, verify expected identity, derive the amendment, structurally diff,
                refuse unless exactly one semantic delta, then SEAL the proposal + its digest
    --apply     re-fetch live, re-derive, require equality with the sealed digest, then PUT
    --verify    read back from AWS, canonicalize identically, require exact equality with the
                sealed digest, prove the new ARN is covered, and prove nothing else moved

Development/governance operation. Opens no sealed object, reads no holdout content, and touches
no MR-002 research payload.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

BUCKET = "workbench-mr002-sealed-219024422756"
REGION = "us-east-1"

#: The policy identity this amendment is authorized against. Refuse on anything else — a policy
#: that has moved since the finding was recorded is a different governance object.
EXPECTED_LIVE_IDENTITY = "7bb73e62066e52303c5d48ed0cd740cb16b4f2825110dde92d9cc4d6dfc164a5"

TARGET_SID = "DenyPermanentDeletionOfSealedObjectVersions"
NEW_ARN = f"arn:aws:s3:::{BUCKET}/runtime-custody/*"

#: The latch, verified alongside so the amendment cannot silently coincide with a latch movement.
LATCH_ROLE = "mr002-phase3c-run-host"
LATCH_POLICY = "mr002-phase3c-qualification-only"
LATCH_IDENTITY = "44f5549a97042d2829a3027e764105b0ab272774ec3bb343d224bfba999fab48"
LATCH_STATEMENTS = 8

SEAL = Path(__file__).resolve().parents[3] / ".mr002out" / "p1" / "runtime_custody_amendment_seal.json"


# ── the Amendment-R canonicalizer, identical to mr002_v2_resource_policy_gate.canonical ─────────
def canonical(doc) -> str:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"))


def ident(doc) -> str:
    return hashlib.sha256(canonical(doc).encode()).hexdigest()


def aws(*args: str) -> str:
    r = subprocess.run(["aws", *args, "--region", REGION], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"AWS call failed: {' '.join(args)}\n{r.stderr}")
    return r.stdout


def live_policy() -> dict:
    return json.loads(json.loads(aws("s3api", "get-bucket-policy", "--bucket", BUCKET,
                                     "--output", "json"))["Policy"])


def latch_state() -> tuple[int, str]:
    doc = json.loads(aws("iam", "get-role-policy", "--role-name", LATCH_ROLE,
                         "--policy-name", LATCH_POLICY, "--query", "PolicyDocument",
                         "--output", "json"))
    return len(doc["Statement"]), ident(doc)


def amend(live: dict) -> dict:
    """Derive the amended document by MODIFYING A DEEP COPY OF THE LIVE OBJECT.

    Never reconstructed from a template. Every element the live policy carries — including ones
    this code does not know about — survives by construction.
    """
    out = copy.deepcopy(live)
    hits = [s for s in out["Statement"] if s.get("Sid") == TARGET_SID]
    if len(hits) != 1:
        raise SystemExit(f"REFUSE: expected exactly one statement with Sid {TARGET_SID}, found {len(hits)}")
    st = hits[0]
    res = st["Resource"]
    if isinstance(res, str):
        raise SystemExit("REFUSE: target Resource is a scalar; the live shape was a list. Not reshaping it.")
    if NEW_ARN in res:
        raise SystemExit(f"REFUSE: {NEW_ARN} is already present — nothing to amend.")
    st["Resource"] = [*res, NEW_ARN]
    return out


def structural_diff(a: dict, b: dict) -> list[str]:
    """Enumerate EVERY top-level element and every statement, unconditionally.

    The 2026-08-21 self-defect was a diff that reported `Id` only when the old document had none.
    This reports a delta whenever the two documents disagree on any key present in EITHER.
    """
    deltas: list[str] = []
    for k in sorted(set(a) | set(b)):
        if k == "Statement":
            continue
        if a.get(k) != b.get(k):
            deltas.append(f"TOP-LEVEL {k}: {a.get(k)!r} -> {b.get(k)!r}")

    sa = {s.get("Sid"): s for s in a.get("Statement", [])}
    sb = {s.get("Sid"): s for s in b.get("Statement", [])}
    for sid in sorted(set(sa) | set(sb), key=str):
        if sid not in sa:
            deltas.append(f"STATEMENT ADDED: {sid}")
            continue
        if sid not in sb:
            deltas.append(f"STATEMENT REMOVED: {sid}")
            continue
        x, y = sa[sid], sb[sid]
        for k in sorted(set(x) | set(y)):
            if x.get(k) == y.get(k):
                continue
            if sid == TARGET_SID and k == "Resource":
                added = [r for r in y[k] if r not in x[k]]
                removed = [r for r in x[k] if r not in y[k]]
                deltas.append(f"STATEMENT {sid}.Resource: added={added} removed={removed}")
            else:
                deltas.append(f"STATEMENT {sid}.{k}: {x.get(k)!r} -> {y.get(k)!r}")
    return deltas


def expected_single_delta() -> str:
    return f"STATEMENT {TARGET_SID}.Resource: added=['{NEW_ARN}'] removed=[]"


def covered(policy: dict, arn: str) -> bool:
    for s in policy["Statement"]:
        if s.get("Sid") != TARGET_SID:
            continue
        res = s["Resource"]
        res = [res] if isinstance(res, str) else res
        return arn in res
    return False


def snapshot_readdeny(policy: dict) -> dict:
    """The validation/OOS read-Deny scopes, so the amendment cannot quietly move them."""
    out = {}
    for s in policy["Statement"]:
        sid = s.get("Sid") or ""
        if s["Effect"] == "Deny" and "Reads" in sid:
            res = s["Resource"]
            out[sid] = {"resources": sorted([res] if isinstance(res, str) else res),
                        "condition": s.get("Condition")}
    return out


def do_prepare() -> int:
    live = live_policy()
    live_id = ident(live)
    print(f"live policy identity   {live_id}")
    if live_id != EXPECTED_LIVE_IDENTITY:
        raise SystemExit(f"REFUSE: live policy is {live_id}, expected {EXPECTED_LIVE_IDENTITY}. "
                         "The governance object has moved since the finding was recorded.")
    print("                       == expected (Amendment R sealed value) OK")

    n, lid = latch_state()
    print(f"latch                  {n} statements, {lid}")
    if n != LATCH_STATEMENTS or lid != LATCH_IDENTITY:
        raise SystemExit("REFUSE: latch state is not 8/CLOSED at the canonical identity.")
    print("                       8 / CLOSED OK")

    proposed = amend(live)
    deltas = structural_diff(live, proposed)
    print(f"\nstructural deltas ({len(deltas)}):")
    for d in deltas:
        print(f"  {d}")
    if deltas != [expected_single_delta()]:
        raise SystemExit("\nREFUSE: the delta set is not exactly the one authorized semantic change.")
    print("  => exactly one semantic delta, as authorized")

    if proposed.get("Id") != live.get("Id"):
        raise SystemExit("REFUSE: policy Id did not survive.")
    print(f"policy Id survives     {proposed.get('Id')!r}")

    seal = {
        "record_type": "MR002_P1_RUNTIME_CUSTODY_AMENDMENT_SEAL",
        "version": "1.0",
        "bucket": BUCKET,
        "authorized_change": f"add {NEW_ARN} to {TARGET_SID}.Resource — nothing else",
        "live_identity_before": live_id,
        "proposed_identity": ident(proposed),
        "structural_deltas": deltas,
        "policy_id_preserved": proposed.get("Id"),
        "latch_before": {"statements": n, "identity": lid},
        "read_deny_scopes_before": snapshot_readdeny(live),
        "proposed_document": proposed,
        "sealed_before_application": True,
    }
    SEAL.parent.mkdir(parents=True, exist_ok=True)
    tmp = SEAL.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(seal, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(SEAL)
    print(f"\nSEALED proposal identity {seal['proposed_identity']}")
    print(f"sealed to                {SEAL}")
    print("\nPREPARE OK — nothing was applied.")
    return 0


def do_apply() -> int:
    if not SEAL.exists():
        raise SystemExit("REFUSE: no sealed proposal. Run --prepare first.")
    seal = json.loads(SEAL.read_text(encoding="utf-8"))

    live = live_policy()
    if ident(live) != seal["live_identity_before"]:
        raise SystemExit("REFUSE: live policy changed since sealing. Re-run --prepare and re-review.")
    rederived = amend(live)
    if ident(rederived) != seal["proposed_identity"]:
        raise SystemExit("REFUSE: re-derived document does not match the sealed proposal identity.")
    print(f"re-derived == sealed   {seal['proposed_identity']} OK")

    aws("s3api", "put-bucket-policy", "--bucket", BUCKET,
        "--policy", json.dumps(seal["proposed_document"]))
    print("APPLIED.")
    return 0


def do_verify() -> int:
    if not SEAL.exists():
        raise SystemExit("REFUSE: no sealed proposal to verify against.")
    seal = json.loads(SEAL.read_text(encoding="utf-8"))

    back = live_policy()
    back_id = ident(back)
    print(f"read-back identity     {back_id}")
    print(f"sealed proposal        {seal['proposed_identity']}")
    ok_equal = back_id == seal["proposed_identity"]
    print(f"deployed == sealed     {ok_equal}")

    ok_cov = covered(back, NEW_ARN)
    print(f"runtime-custody/* covered by the permanent-deletion deny: {ok_cov}")

    n, lid = latch_state()
    ok_latch = n == LATCH_STATEMENTS and lid == LATCH_IDENTITY
    print(f"latch after            {n} statements, {lid} -> {'UNCHANGED' if ok_latch else 'MOVED'}")

    denies = [s.get("Sid") for s in back["Statement"] if s["Effect"] == "Deny"]
    print(f"bucket deny statements ({len(denies)}): {denies}")

    before = seal["read_deny_scopes_before"]
    after = snapshot_readdeny(back)
    ok_reads = before == after
    print(f"validation/OOS read-deny scopes unchanged: {ok_reads}")
    if not ok_reads:
        print(f"  before {json.dumps(before, sort_keys=True)}")
        print(f"  after  {json.dumps(after, sort_keys=True)}")

    all_ok = ok_equal and ok_cov and ok_latch and ok_reads and len(denies) == 4
    print(f"\nVERIFY {'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


def main() -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--prepare", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--verify", action="store_true")
    a = p.parse_args()
    if a.prepare:
        return do_prepare()
    if a.apply:
        return do_apply()
    return do_verify()


if __name__ == "__main__":
    sys.exit(main())
