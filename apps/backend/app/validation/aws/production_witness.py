"""The Step 4D production witness preflight (ADR 0047).

Run as a module, never imported — `check_aws_sdk_isolation.sh` forbids anything outside this package
from importing it, so the governed entry point stays the one CI polices:

    python -m app.validation.aws.production_witness attest      --bucket … --key-arn … --out …
    python -m app.validation.aws.production_witness install-key --key-arn … --path … --out …
    python -m app.validation.aws.production_witness preflight   --key-arn … --bucket … --out …
    python -m app.validation.aws.production_witness negatives   --key-arn … --bucket … --out …

## Why this is a separate module from `integration_proof.py`

Step 4C's harness is the record of what was proven in a fixture that no longer exists. Its strings say
4C, its tags say `workbench-production=false`, and its bucket has been torn down. Editing it to also
mean production would make the 4C evidence harder to read later, and 4D's requirements are a superset
rather than a variant: four of its nine negative classes were never reachable in 4C at all.

## What it deliberately does NOT do

**It does not provision.** There is no `create_key` and no `create_bucket` here, so the instance role
never needs `kms:CreateKey` or `s3:CreateBucket` and the eight-action witness contract of ADR 0047 (4)
stays exactly eight. Provisioning is operator-side, by recorded command, and its output enters the
evidence package as an operator journal — the same discipline that let 4C mark its resources
`OPERATOR_PROVISIONED`.

**It does not touch the observation workflow.** No `append_anchor`, no observation store, no chain. The
synthetic tip goes straight to `signer.attest` and `sink.publish`. Step 4D must not be able to write an
observation even by accident, and the way to guarantee that is to never construct the machinery.

**It does not write to the operational prefix.** Everything here publishes under the preflight prefix
(ADR 0047 (3)). A synthetic tip in `witness/` would be a permanent sequence-1 record in the production
chain — permanent literally, since Object Lock is COMPLIANCE/2555 days.

## Single-use, and the flag 4C wished it had

`preflight` fresh-attests, so it is single-use per prefix and sequence: a second run produces a
different signature over the same tip and is correctly refused as divergent. `negatives` is a separate
subcommand precisely so the battery can be re-run without that — the gap the Step 4C closure asked to
be closed before the 4C harness was reused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.validation.aws.kms_signer import (
    KMS_KEY_SPEC,
    KMS_SIGNING_ALGORITHM,
    parse_key_arn,
)
from app.validation.aws.platform_guard import capture_runtime
from app.validation.aws.s3_sink import S3SinkError
from app.validation.witness_config import load_witness_config
from app.validation.witness_enforcement import WitnessEnforcementError, enforce_production_witness
from app.validation.witness_platform import assert_supported_platform
from app.validation.witness_protocol import (
    ALGORITHM_ECDSA_SHA256_P256,
    WitnessedTip,
    WitnessError,
    serialize_receipt,
)

STEP = "4D"

SIGNER_FACTORY = "app.validation.aws.kms_signer:build_kms_anchor_signer"
SINK_FACTORY = "app.validation.aws.s3_sink:build_s3_object_lock_sink"

WITNESS_IDENTITY = "kms-witness-forward-validation"

#: ADR 0047 (3). The operational prefix is never written by this module.
OPERATIONAL_PREFIX = "witness"
PREFLIGHT_PREFIX = "preflight"

#: ADR 0047 (2). What the bucket must report, or the deployment is not the one that was ratified.
REQUIRED_LOCK_MODE = "COMPLIANCE"
REQUIRED_RETENTION_DAYS = 2555

#: The synthetic tip. `session_date` is deliberately not a trading date and both digests derive from a
#: fixed marker, so the receipt is self-evidently synthetic in any later audit of the witness bucket.
SYNTHETIC_MARKER = b"workbench.step4d.production-witness-preflight"
SYNTHETIC_SESSION = "0001-01-01"

IMDS_BASE = "http://169.254.169.254"


class PreflightError(WitnessError):
    """The production witness preflight could not be completed. Fails closed."""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _client(service: str, region: str) -> Any:
    return boto3.client(service, region_name=region, config=Config(
        retries={"mode": "standard", "max_attempts": 3}, connect_timeout=5, read_timeout=10))


# ── observed identity ────────────────────────────────────────────────────────────────────────────────

def _imds(path: str, token: str | None = None) -> str | None:
    try:
        if token is None:
            token_req = urllib.request.Request(
                f"{IMDS_BASE}/latest/api/token", method="PUT",
                headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"})
            with urllib.request.urlopen(token_req, timeout=2) as response:  # noqa: S310 - link-local
                token = response.read().decode("ascii")
        req = urllib.request.Request(f"{IMDS_BASE}/{path}",
                                     headers={"X-aws-ec2-metadata-token": token})
        with urllib.request.urlopen(req, timeout=2) as response:            # noqa: S310 - link-local
            return response.read().decode("utf-8")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def instance_identity() -> dict[str, Any]:
    """The IMDSv2 instance identity document, or `{}` off-EC2.

    IMDSv2 token-first because IMDSv1 is disabled on hardened AMIs and a silent fallback would hide
    that. Recorded, never required: the package states where it ran.
    """
    raw = _imds("latest/dynamic/instance-identity/document")
    if raw is None:
        return {}
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return {k: document.get(k) for k in
            ("instanceId", "imageId", "instanceType", "region", "accountId", "architecture",
             "availabilityZone")}


def host_identity() -> dict[str, Any]:
    """Who this host says it is, from IMDS and STS.

    The role's *permissions* are not read here and cannot be: the witness contract withholds
    `iam:GetRole` and `iam:SimulatePrincipalPolicy`, correctly. The runner reports the identity it is
    running as; the operator's provisioning journal reports what that identity is allowed. Two sources
    that a reader can cross-check beats one source that grants itself the authority to introspect.
    """
    identity: dict[str, Any] = {"instance": instance_identity()}

    profile = _imds("latest/meta-data/iam/info")
    if profile:
        try:
            identity["iam_info"] = json.loads(profile)
        except json.JSONDecodeError:
            identity["iam_info"] = {"raw": profile[:200]}

    name_tag = _imds("latest/meta-data/tags/instance/Name")
    if name_tag:
        identity["name_tag"] = name_tag

    region = (identity.get("instance") or {}).get("region") or "us-east-1"
    try:
        identity["caller"] = _client("sts", region).get_caller_identity()
        identity["caller"].pop("ResponseMetadata", None)
    except Exception as exc:                          # noqa: BLE001 - identity is evidence, not a gate
        identity["caller_error"] = f"{type(exc).__name__}: {exc}"
    return identity


def installed_distributions() -> dict[str, str]:
    """The runtime dependency set, observed from the interpreter that is about to do the work."""
    from importlib.metadata import distributions

    found: dict[str, str] = {}
    for dist in distributions():
        name = dist.metadata["Name"]
        if name:
            found[name] = dist.version or ""
    return dict(sorted(found.items()))


# ── the deployment-installed trust root ──────────────────────────────────────────────────────────────

def install_public_key(*, key_arn: str, path: Path, mode: int = 0o444) -> dict[str, Any]:
    """Export the KMS public key as DER SPKI and install it as the deployment trust root.

    Written through a fresh `O_CREAT|O_EXCL` descriptor and chmod'ed before anything reads it: the
    installed key is what the signer challenge is judged against, so it must never exist briefly in a
    state something else could rewrite. Refuses to replace an existing file — reinstalling a trust root
    over a live one is an operator decision, not a side effect of re-running a command.
    """
    region = parse_key_arn(key_arn)
    kms = _client("kms", region)
    response = kms.get_public_key(KeyId=key_arn)

    returned = response.get("KeyId")
    if returned != key_arn:
        raise PreflightError(f"GetPublicKey returned KeyId {returned!r}, not the pinned {key_arn!r}",
                             code="WITNESS_KEY_IDENTITY_MISMATCH")
    if response.get("KeySpec") != KMS_KEY_SPEC:
        raise PreflightError(f"key {key_arn} is {response.get('KeySpec')!r}, not {KMS_KEY_SPEC}",
                             code="WITNESS_ALGORITHM_NOT_PINNED")
    if KMS_SIGNING_ALGORITHM not in (response.get("SigningAlgorithms") or []):
        raise PreflightError(f"key {key_arn} cannot sign with {KMS_SIGNING_ALGORITHM}",
                             code="WITNESS_ALGORITHM_NOT_PINNED")

    der = bytes(response["PublicKey"])
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    try:
        os.write(fd, der)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, mode)

    st = path.stat()
    parent = path.parent.stat()
    return {
        "path": str(path), "sha256": hashlib.sha256(der).hexdigest(), "bytes": len(der),
        "owner_uid": st.st_uid, "owner_gid": st.st_gid, "mode": oct(stat.S_IMODE(st.st_mode)),
        "parent_owner_uid": parent.st_uid, "parent_mode": oct(stat.S_IMODE(parent.st_mode)),
        "symlink": path.is_symlink(), "verified_against_kms": True,
        "key_arn": returned, "key_spec": response.get("KeySpec"),
        "signing_algorithms": list(response.get("SigningAlgorithms") or []),
    }


def verify_installed_key(*, key_arn: str, path: Path) -> dict[str, Any]:
    """Re-verify an already-installed trust root against KMS, without writing anything.

    Separate from `install_public_key` because the evidence package must be able to state the
    fingerprint agreement at preflight time, not merely at install time — the two are different claims
    and a deployment can be re-imaged between them.
    """
    region = parse_key_arn(key_arn)
    response = _client("kms", region).get_public_key(KeyId=key_arn)
    kms_der = bytes(response["PublicKey"])
    installed = path.read_bytes()
    st = path.stat()
    parent = path.parent.stat()
    return {
        "path": str(path),
        "installed_sha256": hashlib.sha256(installed).hexdigest(),
        "kms_sha256": hashlib.sha256(kms_der).hexdigest(),
        "fingerprints_agree": installed == kms_der,
        "owner_uid": st.st_uid, "owner_gid": st.st_gid, "mode": oct(stat.S_IMODE(st.st_mode)),
        "parent_owner_uid": parent.st_uid, "parent_mode": oct(stat.S_IMODE(parent.st_mode)),
        "symlink": path.is_symlink(),
        "returned_key_id": response.get("KeyId"), "key_spec": response.get("KeySpec"),
    }


# ── the governed configuration ───────────────────────────────────────────────────────────────────────

def synthetic_tip(sequence: int = 1) -> WitnessedTip:
    commit = hashlib.sha256(SYNTHETIC_MARKER).hexdigest()
    return WitnessedTip(sequence=sequence, session_date=SYNTHETIC_SESSION, commit_sha256=commit,
                        anchor_sha256=hashlib.sha256(commit.encode()).hexdigest())


def witness_config(*, key_arn: str, bucket: str, prefix: str, region: str, public_key_path: Path,
                   trusted_root: Path, sink_identity: str | None = None) -> Any:
    """The governed configuration a deployment installs, built here and parsed by the REAL loader.

    Routed through `load_witness_config` rather than constructing `WitnessConfig` directly: the
    private-key-material scan and the PRODUCTION-profile algorithm/key checks are part of what the
    preflight demonstrates, and a hand-built config would skip them.
    """
    identity = sink_identity or (f"s3://{bucket}/{prefix.strip('/')}" if prefix else f"s3://{bucket}")
    return load_witness_config({
        "profile": "PRODUCTION",
        "algorithm": ALGORITHM_ECDSA_SHA256_P256,
        "key_id": key_arn,
        "public_key_path": str(public_key_path),
        "trusted_root": str(trusted_root),
        "signer": {"factory": SIGNER_FACTORY, "identity": WITNESS_IDENTITY,
                   "options": {"key_arn": key_arn, "witness_identity": WITNESS_IDENTITY}},
        "sink": {"factory": SINK_FACTORY, "identity": identity,
                 "options": {"bucket": bucket, "prefix": prefix, "region": region}},
    })


# ── storage attestation, read without writing ────────────────────────────────────────────────────────

def storage_attestation(*, bucket: str, region: str) -> dict[str, Any]:
    """What the bucket reports about itself, and whether it is what ADR 0047 ratified.

    Read through the same three configuration calls the sink makes, so the evidence and the gate see
    one bucket state rather than two.
    """
    s3 = _client("s3", region)
    versioning = s3.get_bucket_versioning(Bucket=bucket).get("Status", "")
    lock = s3.get_object_lock_configuration(Bucket=bucket).get("ObjectLockConfiguration", {})
    location = s3.get_bucket_location(Bucket=bucket).get("LocationConstraint")

    retention = (lock.get("Rule") or {}).get("DefaultRetention") or {}
    mode, days = retention.get("Mode"), retention.get("Days")
    # us-east-1 is reported as an absent LocationConstraint, which is the one case where "no value" is
    # the answer rather than a missing one.
    actual_region = location or "us-east-1"

    return {
        "bucket": bucket, "configured_region": region, "reported_region": actual_region,
        "region_agrees": actual_region == region,
        "versioning": versioning,
        "object_lock": lock,
        "retention_mode": mode, "retention_days": days,
        "matches_governed_policy": (versioning == "Enabled"
                                    and lock.get("ObjectLockEnabled") == "Enabled"
                                    and mode == REQUIRED_LOCK_MODE
                                    and days == REQUIRED_RETENTION_DAYS),
    }


def operational_prefix_is_empty(*, bucket: str, region: str,
                                prefix: str = OPERATIONAL_PREFIX) -> dict[str, Any]:
    """That the operational prefix holds nothing.

    The completion gate asserts the forward window is not open; an object under `witness/` would be a
    recorded observation and would contradict it. Checked from storage rather than inferred from the
    session count, because the two could disagree and that disagreement is the finding.
    """
    s3 = _client("s3", region)
    listing = s3.list_objects_v2(Bucket=bucket, Prefix=f"{prefix.strip('/')}/", MaxKeys=10)
    keys = [item["Key"] for item in listing.get("Contents", [])]
    return {"prefix": prefix, "object_count": len(keys), "empty": not keys, "keys": keys[:10]}


# ── the preflight ────────────────────────────────────────────────────────────────────────────────────

def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"check": name, "passed": bool(passed), "detail": detail}


def run_preflight(*, key_arn: str, bucket: str, region: str, public_key_path: Path,
                  trusted_root: Path, prefix: str = PREFLIGHT_PREFIX,
                  sequence: int = 1) -> dict[str, Any]:
    """P1–P9. Synthetic evidence only, preflight prefix only, one tip.

    Ordering mirrors what a real session does, so a failure here is a failure a session would have had.
    """
    if prefix.strip("/") == OPERATIONAL_PREFIX:
        raise PreflightError(
            f"refusing to publish synthetic evidence to the operational prefix {OPERATIONAL_PREFIX!r}: "
            f"under COMPLIANCE retention that record could never be removed, and it would appear in "
            f"every subsequent read of the production chain",
            code="WITNESS_SINK_STORAGE_MISBOUND")

    checks: list[dict[str, Any]] = []

    # P1 — platform. Already asserted by main(), re-recorded here so the bundle states it positively.
    runtime = capture_runtime(instance_identity=instance_identity())
    checks.append(_check("P1", runtime.system == "Linux" and runtime.os_name == "posix",
                         f"{runtime.system}/{runtime.os_name}; truststore_injected="
                         f"{runtime.truststore_injected}; ssl_context={runtime.ssl_context_module}"))

    # P2 — the trust root, verified against KMS independently of the signer that will be challenged.
    key_evidence = verify_installed_key(key_arn=key_arn, path=public_key_path)
    checks.append(_check("P2", bool(key_evidence["fingerprints_agree"]),
                         f"installed={key_evidence['installed_sha256'][:16]}… "
                         f"kms={key_evidence['kms_sha256'][:16]}… "
                         f"mode={key_evidence['mode']} uid={key_evidence['owner_uid']}"))

    storage = storage_attestation(bucket=bucket, region=region)
    checks.append(_check("P5", bool(storage["matches_governed_policy"]),
                         f"versioning={storage['versioning']} mode={storage['retention_mode']} "
                         f"days={storage['retention_days']} region_agrees={storage['region_agrees']}"))

    operational = operational_prefix_is_empty(bucket=bucket, region=region)
    checks.append(_check("P0", bool(operational["empty"]),
                         f"{OPERATIONAL_PREFIX}/ holds {operational['object_count']} object(s)"))

    # The real gate, the real factories, the real challenge.
    config = witness_config(key_arn=key_arn, bucket=bucket, prefix=prefix, region=region,
                            public_key_path=public_key_path, trusted_root=trusted_root)
    nonce = _now()
    witness = enforce_production_witness(config, nonce=nonce)

    signer_evidence = witness.evidence.get("signer", {})
    checks.append(_check("P3", bool(signer_evidence.get("key_challenge", {}).get("challenged")),
                         json.dumps(signer_evidence.get("key_challenge", {}), sort_keys=True)[:400]))

    sink_evidence = witness.evidence.get("sink", {})
    checks.append(_check("P4", sink_evidence.get("storage_identities_agree", True) is not False,
                         json.dumps(sink_evidence, sort_keys=True)[:400]))

    tip = synthetic_tip(sequence)
    receipt = witness.signer.attest(tip)
    witness.verifier.verify(tip, receipt)             # the installed key must accept what KMS produced
    witness.sink.publish(tip, receipt)

    external = witness.sink.read_all()
    match = [(t, r) for t, r in external if t.sequence == tip.sequence]
    if not match:
        raise PreflightError(f"the published tip {tip.sequence} was not readable back from {bucket}",
                             code="EXTERNAL_WITNESS_BEHIND")
    read_tip, read_receipt = match[0]
    canonical_equal = (read_tip == tip
                       and serialize_receipt(read_receipt) == serialize_receipt(receipt))
    checks.append(_check("P6", canonical_equal,
                         f"records={len(external)} canonical_equal={canonical_equal}"))

    # P7 — idempotency. Only the STORED bytes can be byte-identical: ECDSA signing is randomised and
    # `signed_at` advances, so re-attesting the same tip always produces a different receipt. The first
    # Step 4C run re-attested and called the result identical, which exercised divergence twice and
    # never tested idempotency at all.
    #
    # "No write occurred" is asserted from the record, not inferred from the absence of an error. It is
    # NOT asserted from the S3 version count: that needs `s3:ListBucketVersions`, which the witness
    # contract deliberately withholds, and widening a standing role to make a check convenient is the
    # wrong trade. The version count is operator-captured evidence.
    before = serialize_receipt(read_receipt)
    republished_cleanly = True
    republish_detail = "republished the stored receipt bytes"
    try:
        witness.sink.publish(read_tip, read_receipt)
    except (WitnessError, S3SinkError, ClientError) as exc:
        republished_cleanly = False
        republish_detail = f"refused: {getattr(exc, 'code', type(exc).__name__)}: {exc}"[:400]
    after = [(t, r) for t, r in witness.sink.read_all() if t.sequence == tip.sequence]
    unchanged = len(after) == 1 and serialize_receipt(after[0][1]) == before
    checks.append(_check("P7", republished_cleanly and unchanged,
                         f"{republish_detail}; record_unchanged={unchanged}; entries={len(after)}"))

    # P8 / P9 — the two ways a divergent record is refused.
    fresh = witness.signer.attest(tip)
    checks.append(_case_as_check("P8", "EXTERNAL_WITNESS_DIVERGES",
                                 lambda: witness.sink.publish(tip, fresh)))
    divergent = WitnessedTip(sequence=tip.sequence, session_date=tip.session_date,
                             commit_sha256=hashlib.sha256(b"divergent").hexdigest(),
                             anchor_sha256=tip.anchor_sha256)
    checks.append(_case_as_check("P9", "EXTERNAL_WITNESS_DIVERGES",
                                 lambda: witness.sink.publish(divergent, fresh)))

    return {
        "platform": runtime.to_open_provenance(),
        "installed_key": key_evidence,
        "storage": storage,
        "operational_prefix": operational,
        "witness_evidence": witness.evidence,
        "witnessed_tip": {"sequence": tip.sequence, "session_date": tip.session_date,
                          "commit_sha256": tip.commit_sha256, "anchor_sha256": tip.anchor_sha256},
        "receipt": receipt.to_dict(),
        "readback": {"canonical_equal": canonical_equal, "records_found": len(external),
                     "prefix": prefix},
        "preflight": checks,
        "nonce": nonce,
    }


# ── negative battery ─────────────────────────────────────────────────────────────────────────────────

#: ADR 0047 (11). The three states are not interchangeable and the package must never blur them.
PROVEN_IN_4D = "PROVEN_IN_4D"                 # refused here, with the governed code
OBSERVED_UNMATCHED = "OBSERVED_UNMATCHED"     # refused here, with a DIFFERENT code — adjudicate
NOT_REFUSED = "NOT_REFUSED"                   # it went through; the control does not hold
EXPECTED_NOT_OBSERVED = "EXPECTED_NOT_OBSERVED"   # never executed; a prediction, not evidence


def _case(name: str, expected: str, fn: Any) -> dict[str, Any]:
    """Run one negative case and record what actually happened.

    A case that does NOT raise is recorded rather than crashing the battery: the package must show
    every case's real outcome, and a harness that aborted on the first surprise would hide the rest.

    The `evidence_state` is the field that matters downstream. ADR 0047 (11) forbids the
    activation-readiness report from treating a predicted refusal as observed fail-closed behaviour,
    and a state computed here — from what happened — is harder to lose than a convention applied when
    the report is written.
    """
    try:
        fn()
    except (WitnessError, WitnessEnforcementError, S3SinkError, ClientError) as exc:
        observed = getattr(exc, "code", None) or type(exc).__name__
        matched = observed == expected
        return {"case": name, "expected_code": expected, "observed_code": observed,
                "refused": True, "matched": matched, "detail": str(exc)[:400],
                "evidence_state": PROVEN_IN_4D if matched else OBSERVED_UNMATCHED}
    except Exception as exc:                          # noqa: BLE001 - an untyped failure is evidence
        return {"case": name, "expected_code": expected, "observed_code": type(exc).__name__,
                "refused": True, "matched": False, "detail": str(exc)[:400],
                "evidence_state": OBSERVED_UNMATCHED}
    return {"case": name, "expected_code": expected, "observed_code": None, "refused": False,
            "matched": False, "detail": "the operation was NOT refused",
            "evidence_state": NOT_REFUSED}


def _uncovered(name: str, expected: str, why: str) -> dict[str, Any]:
    """A required case the invocation could not reach.

    Emitted rather than omitted. A battery that silently drops the cases whose resources were not
    supplied reads, in the package, exactly like a battery that ran them — which is how a coverage gap
    becomes a claim. Step 4C's plan listed fourteen cases and its run exercised seven; the difference
    was recoverable only by reading both documents side by side.
    """
    return {"case": name, "expected_code": expected, "observed_code": None, "refused": None,
            "matched": False, "detail": why, "evidence_state": EXPECTED_NOT_OBSERVED}


def _case_as_check(name: str, expected: str, fn: Any) -> dict[str, Any]:
    outcome = _case(name, expected, fn)
    return _check(name, bool(outcome["matched"]),
                  f"expected={expected} observed={outcome['observed_code']} "
                  f"refused={outcome['refused']}")


#: Cases only an administrator can arrange, and the refusal each must produce once arranged.
OPERATOR_DRIVEN_CASES = {
    "N7 missing IAM permission": "INDEPENDENT_WITNESS_UNAVAILABLE",
    "N9 Object Lock or versioning misconfigured": "WITNESS_SINK_NOT_IMMUTABLE",
}

OPERATOR_CASE_HOWTO = {
    "N7 missing IAM permission":
        "operator-driven: narrow the role (remove one witness action), re-run with "
        "--operator-case 'N7 missing IAM permission', then restore and verify restoration",
    "N9 Object Lock or versioning misconfigured":
        "operator-driven: create a temporary bucket with neither Object Lock nor versioning, re-run "
        "with --bucket <that bucket> --operator-case 'N9 Object Lock or versioning misconfigured', "
        "then delete it",
}


def run_negatives(*, key_arn: str, bucket: str, region: str, public_key_path: Path,
                  trusted_root: Path, prefix: str = PREFLIGHT_PREFIX,
                  foreign_key_path: Path | None = None,
                  foreign_key_arn: str | None = None,
                  unreachable_endpoint: str | None = None,
                  operator_case: str | None = None) -> list[dict[str, Any]]:
    """N1–N9. Re-runnable: nothing here depends on a fresh publication succeeding.

    The cases needing infrastructure the least-privilege role cannot create — a second key, an unlocked
    bucket, a narrowed policy — take their resources as arguments, or are driven one at a time through
    `operator_case` against an environment the administrator has deliberately broken. A role able to
    manufacture its own counterexamples would be a role able to weaken its own guarantees.
    """
    nonce = _now()

    def compose(**overrides: Any) -> None:
        enforce_production_witness(
            witness_config(key_arn=overrides.get("key_arn", key_arn),
                           bucket=overrides.get("bucket", bucket),
                           prefix=overrides.get("prefix", prefix),
                           region=region,
                           public_key_path=overrides.get("public_key_path", public_key_path),
                           trusted_root=trusted_root,
                           sink_identity=overrides.get("sink_identity")),
            nonce=nonce)

    if operator_case is not None:
        # ONE case, against the environment the operator has just arranged. Deliberately exclusive: the
        # other cases would refuse for the arranged reason rather than their own, and recording those
        # as passes would be evidence of nothing.
        if operator_case not in OPERATOR_DRIVEN_CASES:
            raise PreflightError(
                f"{operator_case!r} is not an operator-driven case; expected one of "
                f"{sorted(OPERATOR_DRIVEN_CASES)}",
                code="STEP4D_UNKNOWN_OPERATOR_CASE")
        return [_case(operator_case, OPERATOR_DRIVEN_CASES[operator_case], compose)]

    cases: list[dict[str, Any]] = []

    # N1 — a trust root that is not this key's. The signer challenge is what catches it.
    if foreign_key_path is not None:
        cases.append(_case("N1 wrong installed key", "WITNESS_SIGNER_KEY_UNTRUSTED",
                           lambda: compose(public_key_path=foreign_key_path)))
    else:
        cases.append(_uncovered("N1 wrong installed key", "WITNESS_SIGNER_KEY_UNTRUSTED",
                                "no --foreign-key-path was supplied"))

    # N2 — a real, different key. Which refusal fires depends on whether the role may use it, and BOTH
    # answers are informative: denied proves the IAM scoping, untrusted proves the trust root. The
    # observed code is recorded either way rather than being forced to one expectation.
    if foreign_key_arn is not None:
        cases.append(_case("N2 wrong key ARN (real, different key)", "WITNESS_SIGNER_KEY_UNTRUSTED",
                           lambda: compose(key_arn=foreign_key_arn)))
    else:
        cases.append(_uncovered("N2 wrong key ARN (real, different key)",
                                "WITNESS_SIGNER_KEY_UNTRUSTED",
                                "no --foreign-key-arn was supplied"))

    # N3 / N4 — identities that could be repointed at a different key without the config changing.
    cases.append(_case("N3 alias ARN", "WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED",
                       lambda: compose(key_arn=key_arn.rsplit(":key/", 1)[0] + ":alias/forward")))
    cases.append(_case("N4 bare key id", "WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED",
                       lambda: compose(key_arn=key_arn.rsplit("/", 1)[1])))

    # N5 / N6 — the services unreachable. Driven by the caller through the environment so the adapters
    # are exercised unmodified; recorded as skipped rather than faked if the environment does not take.
    if unreachable_endpoint:
        cases.append(_case("N5 KMS unavailable", "INDEPENDENT_WITNESS_UNAVAILABLE",
                           lambda: _with_endpoint("KMS", unreachable_endpoint, compose)))
        cases.append(_case("N6 S3 unavailable", "WITNESS_SINK_IMMUTABILITY_UNPROVEN",
                           lambda: _with_endpoint("S3", unreachable_endpoint, compose)))
    else:
        cases.append(_uncovered("N5 KMS unavailable", "INDEPENDENT_WITNESS_UNAVAILABLE",
                                "no --unreachable-endpoint was supplied"))
        cases.append(_uncovered("N6 S3 unavailable", "WITNESS_SINK_IMMUTABILITY_UNPROVEN",
                                "no --unreachable-endpoint was supplied"))

    # N7 and N9 cannot be reached from inside a correctly-scoped runner: one needs the role narrowed,
    # the other a bucket without Object Lock, and a role able to create either could weaken its own
    # guarantees. The operator drives each with `--operator-case`, which composes against the
    # deliberately-broken environment it has just arranged. Recorded as uncovered here so a run that
    # skipped them cannot read as complete.
    for case, expected in OPERATOR_DRIVEN_CASES.items():
        cases.append(_uncovered(case, expected, OPERATOR_CASE_HOWTO[case]))

    # N8 — a declared identity the sink does not write through. The four-identity equality check.
    cases.append(_case("N8 wrong bucket declared", "WITNESS_SINK_STORAGE_MISBOUND",
                       lambda: compose(sink_identity=f"s3://{bucket}-not-this-one/{prefix}")))
    cases.append(_case("N8 wrong prefix declared", "WITNESS_SINK_STORAGE_MISBOUND",
                       lambda: compose(sink_identity=f"s3://{bucket}/{prefix}-not-this-one")))
    return cases


def _with_endpoint(service: str, endpoint: str, fn: Any) -> None:
    """Point one service's endpoint at an unroutable address for the duration of one call.

    `AWS_ENDPOINT_URL_<SERVICE>` is botocore's own per-service override, so this exercises the adapter's
    real client construction and its real failure translation rather than a patched-in exception. The
    variable is restored even if the call raises, because a leaked override would silently invalidate
    every case after it.
    """
    name = f"AWS_ENDPOINT_URL_{service}"
    previous = os.environ.get(name)
    os.environ[name] = endpoint
    try:
        fn()
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


# ── bundle ───────────────────────────────────────────────────────────────────────────────────────────

def _write_bundle(path: Path, bundle: dict[str, Any]) -> str:
    """Write the bundle and return its SHA-256 over the exact bytes written."""
    body = json.dumps(bundle, indent=2, sort_keys=True).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def _state_counts(cases: list[dict[str, Any]]) -> dict[str, int]:
    """The three ADR 0047 (11) states, counted separately and never summed.

    The activation-readiness report is required to present these apart. Emitting them apart here means
    a report that aggregates them has to do so deliberately.
    """
    counts = {PROVEN_IN_4D: 0, OBSERVED_UNMATCHED: 0, NOT_REFUSED: 0, EXPECTED_NOT_OBSERVED: 0}
    for case in cases:
        counts[case["evidence_state"]] = counts.get(case["evidence_state"], 0) + 1
    return counts


def _envelope(command: str, commit: str, started_at: str) -> dict[str, Any]:
    return {"step": STEP, "phase": command, "commit": commit, "started_at": started_at,
            "host": host_identity(), "dependencies": installed_distributions()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="step4d", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--commit", default=os.environ.get("STEP4D_COMMIT", ""))
    common.add_argument("--out", type=Path, required=True)

    a = sub.add_parser("attest", parents=[common],
                       help="record host, runtime, key and bucket state; write nothing")
    a.add_argument("--key-arn", required=True)
    a.add_argument("--bucket", required=True)
    a.add_argument("--region", required=True)
    a.add_argument("--public-key-path", type=Path, default=None)

    k = sub.add_parser("install-key", parents=[common],
                       help="export the DER SPKI and install it as the deployment trust root")
    k.add_argument("--key-arn", required=True)
    k.add_argument("--path", type=Path, required=True)
    k.add_argument("--mode", default="0444")

    for name, helptext in (("preflight", "P1-P9 against the production boundary, synthetic tip only"),
                           ("negatives", "N1-N9; re-runnable, publishes nothing new")):
        p = sub.add_parser(name, parents=[common], help=helptext)
        p.add_argument("--key-arn", required=True)
        p.add_argument("--bucket", required=True)
        p.add_argument("--region", required=True)
        p.add_argument("--prefix", default=PREFLIGHT_PREFIX)
        p.add_argument("--public-key-path", type=Path, required=True)
        p.add_argument("--trusted-root", type=Path, required=True)
        if name == "negatives":
            p.add_argument("--foreign-key-path", type=Path, default=None,
                           help="a DER SPKI for a DIFFERENT key, for the wrong-trust-root case")
            p.add_argument("--foreign-key-arn", default=None,
                           help="a real, different KMS key ARN, for the wrong-key-identity case")
            p.add_argument("--unreachable-endpoint", default=None,
                           help="an unroutable endpoint URL, for the service-unavailable cases")
            p.add_argument("--operator-case", default=None, choices=sorted(OPERATOR_DRIVEN_CASES),
                           help="run ONLY this operator-arranged case against the current environment")

    args = parser.parse_args(argv)

    # FIRST, always. Before a client is built and before anything is read or written.
    assert_supported_platform(context="the Step 4D production witness preflight")

    started_at = _now()
    bundle = _envelope(args.command, args.commit, started_at)

    if args.command == "attest":
        bundle["platform"] = capture_runtime(instance_identity=instance_identity()).to_open_provenance()
        bundle["storage"] = storage_attestation(bucket=args.bucket, region=args.region)
        bundle["operational_prefix"] = operational_prefix_is_empty(bucket=args.bucket,
                                                                   region=args.region)
        if args.public_key_path is not None:
            bundle["installed_key"] = verify_installed_key(key_arn=args.key_arn,
                                                           path=args.public_key_path)
        bundle["outcome"] = "PASS" if bundle["storage"]["matches_governed_policy"] else "FAIL"

    elif args.command == "install-key":
        bundle["installed_key"] = install_public_key(key_arn=args.key_arn, path=args.path,
                                                     mode=int(args.mode, 8))
        bundle["outcome"] = "PASS"

    elif args.command == "preflight":
        result = run_preflight(key_arn=args.key_arn, bucket=args.bucket, region=args.region,
                               public_key_path=args.public_key_path,
                               trusted_root=args.trusted_root, prefix=args.prefix)
        bundle.update(result)
        failed = [c for c in result["preflight"] if not c["passed"]]
        bundle["outcome"] = "PASS" if not failed else "FAIL"

    else:
        cases = run_negatives(key_arn=args.key_arn, bucket=args.bucket, region=args.region,
                              public_key_path=args.public_key_path,
                              trusted_root=args.trusted_root, prefix=args.prefix,
                              foreign_key_path=args.foreign_key_path,
                              foreign_key_arn=args.foreign_key_arn,
                              unreachable_endpoint=args.unreachable_endpoint,
                              operator_case=args.operator_case)
        bundle["negative_cases"] = cases
        bundle["evidence_states"] = _state_counts(cases)

        # A battery is PASS only when every case it contains was OBSERVED to refuse with the governed
        # code. An unrun case is NOT a pass — that conflation is how 4C's seven-of-fourteen coverage
        # became invisible. A case refused with a different code is reported for adjudication, and does
        # not silently become evidence either.
        bundle["outcome"] = "PASS" if all(
            c["evidence_state"] == PROVEN_IN_4D for c in cases) else "FAIL"
        bundle["unmatched_codes"] = [c["case"] for c in cases
                                     if c["evidence_state"] == OBSERVED_UNMATCHED]
        bundle["not_observed"] = [c["case"] for c in cases
                                  if c["evidence_state"] == EXPECTED_NOT_OBSERVED]

    bundle["completed_at"] = _now()
    digest = _write_bundle(args.out, bundle)
    print(f"outcome={bundle['outcome']} sha256={digest} out={args.out}")
    return 0 if bundle["outcome"] == "PASS" else 1


if __name__ == "__main__":                            # pragma: no cover - module entry point
    sys.exit(main())
