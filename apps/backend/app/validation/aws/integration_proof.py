"""The Step 4C isolated AWS witness integration proof.

Run as a module, never imported — `check_aws_sdk_isolation.sh` forbids anything outside this package
from importing it, so the governed entry point stays the one CI polices:

    python -m app.validation.aws.integration_proof provision --bucket … --retention-mode … --retention-days …
    python -m app.validation.aws.integration_proof install-key --key-arn … --path …
    python -m app.validation.aws.integration_proof prove      --key-arn … --bucket … --out evidence.json

Steps 4A and 4B proved the adapters against `botocore.stub.Stubber`. Stubs prove the logic; they cannot
prove the instance-role credential chain resolves, that `GetPublicKey` returns DER the installed key
matches, that Object Lock actually refuses an overwrite, or that IAM denies what it should. That is what
this does — once, against real KMS and real S3, on the temporary EC2 Linux integration host.

## What it deliberately does NOT touch

The observation workflow. There is no `append_anchor` call, no observation store, and no chain: the
synthetic tip is handed straight to `signer.attest` and `sink.publish`. Step 4C must not be able to
write an observation even by accident, and the simplest way to guarantee that is to never construct the
machinery that could.

No Account 4, no production database, no broker, no real ACTIONS data.

## Ordering that is load-bearing

`assert_supported_platform()` runs FIRST in every subcommand — before a client is built and before
anything is provisioned. On Windows, ADR-0017's process-global truststore injection can exhaust the
recursion limit inside botocore client construction (issue #522); a run that provisioned a KMS key and
an Object-Locked bucket and *then* died there would leave real infrastructure behind, some of it
undeletable until retention expires.
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
from dataclasses import dataclass
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
from app.validation.aws.platform_guard import assert_supported_platform, capture_runtime
from app.validation.aws.s3_sink import S3SinkError
from app.validation.witness_config import load_witness_config
from app.validation.witness_enforcement import WitnessEnforcementError, enforce_production_witness
from app.validation.witness_protocol import (
    ALGORITHM_ECDSA_SHA256_P256,
    WitnessedTip,
    WitnessError,
    serialize_receipt,
)

SIGNER_FACTORY = "app.validation.aws.kms_signer:build_kms_anchor_signer"
SINK_FACTORY = "app.validation.aws.s3_sink:build_s3_object_lock_sink"

#: Retention modes S3 accepts. No default anywhere in this module — see `provision`.
RETENTION_MODES = ("COMPLIANCE", "GOVERNANCE")

#: The synthetic tip. `session_date` is deliberately not a trading date and the digests are derived from
#: a fixed marker string, so nothing here can be mistaken for a real observation in any later audit.
SYNTHETIC_MARKER = b"workbench.step4c.synthetic-witness-proof"
SYNTHETIC_SESSION = "0001-01-01"

IMDS_BASE = "http://169.254.169.254"


class ProofError(WitnessError):
    """The integration proof could not be completed. Fails closed."""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _client(service: str, region: str) -> Any:
    return boto3.client(service, region_name=region, config=Config(
        retries={"mode": "standard", "max_attempts": 3}, connect_timeout=5, read_timeout=10))


# ── EC2 instance identity ────────────────────────────────────────────────────────────────────────────

def instance_identity() -> dict[str, Any]:
    """The IMDSv2 instance identity document, or `{}` off-EC2.

    Recorded, never required: the proof states where it ran, and a reader comparing it against the
    eventual `ec2-forward-validation` host is the point. IMDSv2 (token-first) because IMDSv1 is
    disabled on hardened AMIs and a silent fallback would hide that.
    """
    try:
        token_req = urllib.request.Request(
            f"{IMDS_BASE}/latest/api/token", method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"})
        with urllib.request.urlopen(token_req, timeout=2) as response:  # noqa: S310 - link-local only
            token = response.read().decode("ascii")
        doc_req = urllib.request.Request(
            f"{IMDS_BASE}/latest/dynamic/instance-identity/document",
            headers={"X-aws-ec2-metadata-token": token})
        with urllib.request.urlopen(doc_req, timeout=2) as response:    # noqa: S310 - link-local only
            document = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return {}
    return {k: document.get(k) for k in
            ("instanceId", "imageId", "instanceType", "region", "accountId", "architecture")}


# ── provisioning ─────────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Provisioned:
    key_arn: str
    bucket: str
    region: str
    object_lock: dict[str, Any]
    versioning: str

    def to_open_provenance(self) -> dict[str, Any]:
        return {"kms_key_arn": self.key_arn, "kms_key_spec": KMS_KEY_SPEC, "s3_bucket": self.bucket,
                "s3_region": self.region, "object_lock": self.object_lock,
                "versioning": self.versioning}


def provision(*, bucket: str, region: str, retention_mode: str, retention_days: int,
              description: str) -> Provisioned:
    """Create the dedicated non-production KMS key and the Object-Lock bucket.

    `retention_mode` and `retention_days` are REQUIRED and have no default anywhere in this module.
    Under COMPLIANCE, retention cannot be shortened or bypassed by anyone including the root account:
    objects become undeletable until expiry and the bucket cannot be emptied. A default would let that
    be chosen by omission, which is the one way this decision must not be made.
    """
    if retention_mode not in RETENTION_MODES:
        raise ProofError(f"retention_mode must be one of {RETENTION_MODES}, got {retention_mode!r}",
                         code="STEP4C_RETENTION_UNSPECIFIED")
    if not isinstance(retention_days, int) or retention_days < 1:
        raise ProofError("retention_days must be a positive integer; Object Lock retention is set at "
                         "bucket creation and cannot be shortened afterwards",
                         code="STEP4C_RETENTION_UNSPECIFIED")

    kms = _client("kms", region)
    key = kms.create_key(KeySpec=KMS_KEY_SPEC, KeyUsage="SIGN_VERIFY", Description=description,
                         Tags=[{"TagKey": "workbench-purpose", "TagValue": "step4c-integration-proof"},
                               {"TagKey": "workbench-production", "TagValue": "false"}])
    key_arn = key["KeyMetadata"]["Arn"]

    s3 = _client("s3", region)
    create_args: dict[str, Any] = {"Bucket": bucket, "ObjectLockEnabledForBucket": True}
    if region != "us-east-1":
        # us-east-1 must NOT be sent as a LocationConstraint; every other region must be.
        create_args["CreateBucketConfiguration"] = {"LocationConstraint": region}
    s3.create_bucket(**create_args)

    # Object Lock requires versioning; creating with ObjectLockEnabledForBucket turns it on, and this
    # asserts rather than assumes it.
    versioning = s3.get_bucket_versioning(Bucket=bucket).get("Status", "")
    if versioning != "Enabled":
        raise ProofError(f"bucket {bucket} reports versioning {versioning!r} after creation with Object "
                         f"Lock; the write-once guarantee does not hold without it",
                         code="STEP4C_PROVISION_FAILED")

    s3.put_object_lock_configuration(
        Bucket=bucket,
        ObjectLockConfiguration={"ObjectLockEnabled": "Enabled",
                                 "Rule": {"DefaultRetention": {"Mode": retention_mode,
                                                               "Days": retention_days}}})
    lock = s3.get_object_lock_configuration(Bucket=bucket).get("ObjectLockConfiguration", {})
    return Provisioned(key_arn=key_arn, bucket=bucket, region=region, object_lock=lock,
                       versioning=versioning)


# ── the deployment-installed verifying key ───────────────────────────────────────────────────────────

def install_public_key(*, key_arn: str, path: Path, mode: int = 0o444) -> dict[str, Any]:
    """Export the KMS public key as DER SPKI and install it under production ownership/mode rules.

    Written through a fresh `O_CREAT|O_EXCL` descriptor and chmod'ed before anything reads it: the
    installed key is the trust root the signer challenge is judged against, so it must never exist
    briefly in a state something else could rewrite.
    """
    region = parse_key_arn(key_arn)
    kms = _client("kms", region)
    response = kms.get_public_key(KeyId=key_arn)

    returned = response.get("KeyId")
    if returned != key_arn:
        raise ProofError(f"GetPublicKey returned KeyId {returned!r}, not the pinned {key_arn!r}",
                         code="WITNESS_KEY_IDENTITY_MISMATCH")
    if response.get("KeySpec") != KMS_KEY_SPEC:
        raise ProofError(f"key {key_arn} is {response.get('KeySpec')!r}, not {KMS_KEY_SPEC}",
                         code="WITNESS_ALGORITHM_NOT_PINNED")
    if KMS_SIGNING_ALGORITHM not in (response.get("SigningAlgorithms") or []):
        raise ProofError(f"key {key_arn} cannot sign with {KMS_SIGNING_ALGORITHM}",
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
    return {"path": str(path), "sha256": hashlib.sha256(der).hexdigest(),
            "owner_uid": st.st_uid, "owner_gid": st.st_gid,
            "mode": oct(stat.S_IMODE(st.st_mode)), "bytes": len(der)}


# ── the proof ────────────────────────────────────────────────────────────────────────────────────────

def synthetic_tip() -> WitnessedTip:
    """A tip that cannot be mistaken for a real observation.

    `session_date` is not a trading date and both digests derive from a fixed marker, so the receipt
    this produces is self-evidently synthetic in any later audit of the witness bucket.
    """
    commit = hashlib.sha256(SYNTHETIC_MARKER).hexdigest()
    return WitnessedTip(sequence=1, session_date=SYNTHETIC_SESSION, commit_sha256=commit,
                        anchor_sha256=hashlib.sha256(commit.encode()).hexdigest())


def witness_config(*, key_arn: str, bucket: str, prefix: str, region: str, public_key_path: Path,
                   trusted_root: Path, sink_identity: str | None = None) -> Any:
    """The governed configuration a deployment would install, built here and parsed by the real loader.

    Deliberately routed through `load_witness_config` rather than constructing `WitnessConfig` directly:
    the private-key-material scan and the PRODUCTION-profile algorithm/key checks are part of what the
    proof is demonstrating.
    """
    identity = sink_identity or (f"s3://{bucket}/{prefix.strip('/')}" if prefix else f"s3://{bucket}")
    return load_witness_config({
        "profile": "PRODUCTION",
        "algorithm": ALGORITHM_ECDSA_SHA256_P256,
        "key_id": key_arn,
        "public_key_path": str(public_key_path),
        "trusted_root": str(trusted_root),
        "signer": {"factory": SIGNER_FACTORY, "identity": "step4c-kms-witness",
                   "options": {"key_arn": key_arn, "witness_identity": "step4c-kms-witness"}},
        "sink": {"factory": SINK_FACTORY, "identity": identity,
                 "options": {"bucket": bucket, "prefix": prefix, "region": region}},
    })


def run_proof(*, key_arn: str, bucket: str, prefix: str, region: str, public_key_path: Path,
              trusted_root: Path) -> dict[str, Any]:
    """Compose the real production witness, witness ONE synthetic tip, and read it back."""
    config = witness_config(key_arn=key_arn, bucket=bucket, prefix=prefix, region=region,
                            public_key_path=public_key_path, trusted_root=trusted_root)
    nonce = _now()
    witness = enforce_production_witness(config, nonce=nonce)

    tip = synthetic_tip()
    receipt = witness.signer.attest(tip)
    witness.verifier.verify(tip, receipt)         # the installed key must accept what KMS produced
    witness.sink.publish(tip, receipt)

    external = witness.sink.read_all()
    match = [(t, r) for t, r in external if t.sequence == tip.sequence]
    if not match:
        raise ProofError(f"the published tip {tip.sequence} was not readable back from {bucket}",
                         code="EXTERNAL_WITNESS_BEHIND")
    read_tip, read_receipt = match[0]
    canonical_equal = (read_tip == tip
                       and serialize_receipt(read_receipt) == serialize_receipt(receipt))
    if not canonical_equal:
        raise ProofError("the external witness record does not match what was published byte for byte",
                         code="EXTERNAL_WITNESS_DIVERGES")

    return {
        "preflight": witness.evidence,
        "witnessed_tip": {"sequence": tip.sequence, "session_date": tip.session_date,
                          "commit_sha256": tip.commit_sha256, "anchor_sha256": tip.anchor_sha256},
        "receipt": receipt.to_dict(),
        "readback": {"canonical_equal": canonical_equal, "records_found": len(external)},
        "nonce": nonce,
    }


# ── negative proofs ──────────────────────────────────────────────────────────────────────────────────

def _case(name: str, expected: str, fn: Any) -> dict[str, Any]:
    """Run one negative case and record what actually happened.

    A case that does NOT raise is recorded as `refused: false` rather than crashing the run: the bundle
    must show every case's real outcome, and a harness that aborted on the first surprise would hide
    the rest.
    """
    try:
        fn()
    except (WitnessError, WitnessEnforcementError, S3SinkError, ClientError) as exc:
        observed = getattr(exc, "code", None) or type(exc).__name__
        return {"case": name, "expected_code": expected, "observed_code": observed,
                "refused": True, "matched": observed == expected, "detail": str(exc)[:400]}
    except Exception as exc:                      # noqa: BLE001 - an untyped failure is still evidence
        return {"case": name, "expected_code": expected, "observed_code": type(exc).__name__,
                "refused": True, "matched": False, "detail": str(exc)[:400]}
    return {"case": name, "expected_code": expected, "observed_code": None, "refused": False,
            "matched": False, "detail": "the operation was NOT refused"}


def in_process_negatives(*, key_arn: str, bucket: str, prefix: str, region: str,
                         public_key_path: Path, trusted_root: Path,
                         foreign_key_path: Path | None) -> list[dict[str, Any]]:
    """The negative cases reachable without reconfiguring infrastructure.

    Cases needing a denied permission, a versioning-disabled bucket, or an absent Object Lock are driven
    separately by pointing the harness at a deliberately misconfigured resource — they cannot be created
    by a role that (correctly) lacks the permission to break its own guarantees.
    """
    nonce = _now()

    def compose(**overrides: Any) -> None:
        enforce_production_witness(
            witness_config(key_arn=overrides.get("key_arn", key_arn),
                           bucket=overrides.get("bucket", bucket), prefix=prefix, region=region,
                           public_key_path=overrides.get("public_key_path", public_key_path),
                           trusted_root=trusted_root,
                           sink_identity=overrides.get("sink_identity")),
            nonce=nonce)

    cases: list[dict[str, Any]] = []

    if foreign_key_path is not None:
        cases.append(_case("wrong installed SPKI", "WITNESS_SIGNER_KEY_UNTRUSTED",
                           lambda: compose(public_key_path=foreign_key_path)))

    cases.append(_case(
        "alias ARN instead of a key ARN", "WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED",
        lambda: compose(key_arn=key_arn.rsplit(":key/", 1)[0] + ":alias/step4c")))
    cases.append(_case(
        "bare key id instead of a key ARN", "WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED",
        lambda: compose(key_arn=key_arn.rsplit("/", 1)[1])))
    cases.append(_case(
        "sink declared as a bucket it does not write through", "WITNESS_SINK_STORAGE_MISBOUND",
        lambda: compose(sink_identity=f"s3://{bucket}-not-this-one/{prefix}")))

    # ── duplicate publication ────────────────────────────────────────────────────────────────────
    #
    # The distinction being proven, and the reason the first version of this got it wrong:
    #
    #   same tip + the SAME RECEIPT BYTES  -> idempotent no-op
    #   same tip + a FRESH attestation     -> divergent evidence, refused
    #
    # A re-attestation of an identical tip can never reproduce the stored bytes. ECDSA signing is
    # randomised (a fresh `k` per signature) and `signed_at` advances, so the receipt differs even
    # though the key, the tip and the envelope are the same. The original case here re-attested and
    # called the result "identical", so it exercised divergence twice and never tested idempotency at
    # all — the sink was right to refuse it.
    #
    # The only bytes that CAN be identical are the ones already in the sink, so the idempotency case
    # reads the stored record back and republishes exactly that. That is also the real-world shape of
    # the case: `append_anchor` publishes externally BEFORE writing the local line, so a crash between
    # the two leaves the next run republishing a receipt the sink already holds.
    config = witness_config(key_arn=key_arn, bucket=bucket, prefix=prefix, region=region,
                            public_key_path=public_key_path, trusted_root=trusted_root)
    witness = enforce_production_witness(config, nonce=_now())
    tip = synthetic_tip()

    stored = [(t, r) for t, r in witness.sink.read_all() if t.sequence == tip.sequence]
    if not stored:
        cases.append({"case": "idempotent republication of the stored receipt",
                      "expected_code": "NO_REFUSAL", "observed_code": None, "refused": False,
                      "matched": False,
                      "detail": "no record is stored at this sequence, so idempotency could not be "
                                "exercised; run `prove` against a bucket that already holds the tip"})
    else:
        stored_tip, stored_receipt = stored[0]
        before = serialize_receipt(stored_receipt)

        def republish_stored_bytes() -> None:
            witness.sink.publish(stored_tip, stored_receipt)   # must NOT raise

        idempotent = _case("idempotent republication of the stored receipt", "NO_REFUSAL",
                           republish_stored_bytes)
        # "No write occurred" is asserted, not assumed: the record must still be a single entry whose
        # canonical bytes are unchanged. A silent overwrite would show up here as a differing payload.
        after = [(t, r) for t, r in witness.sink.read_all() if t.sequence == tip.sequence]
        unchanged = len(after) == 1 and serialize_receipt(after[0][1]) == before
        cases.append({**idempotent,
                      "matched": idempotent["refused"] is False and unchanged,
                      "record_unchanged_after_republish": unchanged})

    # A fresh attestation of the SAME tip: different signature and signed_at, therefore divergent.
    fresh = witness.signer.attest(tip)
    cases.append(_case("fresh re-attestation of the same tip", "EXTERNAL_WITNESS_DIVERGES",
                       lambda: witness.sink.publish(tip, fresh)))

    # A different tip at the same sequence: divergent for a second, independent reason.
    divergent = WitnessedTip(sequence=tip.sequence, session_date=tip.session_date,
                             commit_sha256=hashlib.sha256(b"divergent").hexdigest(),
                             anchor_sha256=tip.anchor_sha256)
    cases.append(_case("divergent tip at the same sequence", "EXTERNAL_WITNESS_DIVERGES",
                       lambda: witness.sink.publish(divergent, fresh)))
    return cases


# ── CLI ──────────────────────────────────────────────────────────────────────────────────────────────

def _write_bundle(path: Path, bundle: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="step4c", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("provision", help="create the dedicated KMS key and Object-Lock bucket")
    p.add_argument("--bucket", required=True)
    p.add_argument("--region", required=True)
    p.add_argument("--retention-mode", required=True, choices=list(RETENTION_MODES),
                   help="REQUIRED. COMPLIANCE cannot be shortened or bypassed by anyone.")
    p.add_argument("--retention-days", required=True, type=int,
                   help="REQUIRED. Set at creation; objects are undeletable until it expires.")
    p.add_argument("--description", default="Trading Workbench Step 4C integration proof (non-production)")
    p.add_argument("--out", type=Path, required=True)

    k = sub.add_parser("install-key", help="export the DER SPKI and install it as the trust root")
    k.add_argument("--key-arn", required=True)
    k.add_argument("--path", type=Path, required=True)
    k.add_argument("--mode", default="0444")
    k.add_argument("--out", type=Path, required=True)

    r = sub.add_parser("prove", help="compose the real witness, witness one synthetic tip, read it back")
    r.add_argument("--key-arn", required=True)
    r.add_argument("--bucket", required=True)
    r.add_argument("--prefix", required=True)
    r.add_argument("--region", required=True)
    r.add_argument("--public-key-path", type=Path, required=True)
    r.add_argument("--trusted-root", type=Path, required=True)
    r.add_argument("--foreign-key-path", type=Path, default=None,
                   help="a DER SPKI for a DIFFERENT key, to prove the wrong-SPKI refusal")
    r.add_argument("--skip-negatives", action="store_true")
    r.add_argument("--commit", default=os.environ.get("STEP4C_COMMIT", ""))
    r.add_argument("--out", type=Path, required=True)

    args = parser.parse_args(argv)

    # FIRST, always. Before a client is built and before anything is provisioned.
    assert_supported_platform()

    started_at = _now()
    runtime = capture_runtime(instance_identity=instance_identity())

    if args.command == "provision":
        provisioned = provision(bucket=args.bucket, region=args.region,
                                retention_mode=args.retention_mode,
                                retention_days=args.retention_days, description=args.description)
        _write_bundle(args.out, {"step": "4C", "phase": "provision", "started_at": started_at,
                                 "platform": runtime.to_open_provenance(),
                                 "resources": provisioned.to_open_provenance()})
        print(f"provisioned key={provisioned.key_arn} bucket={provisioned.bucket}")
        return 0

    if args.command == "install-key":
        installed = install_public_key(key_arn=args.key_arn, path=args.path,
                                       mode=int(args.mode, 8))
        _write_bundle(args.out, {"step": "4C", "phase": "install-key", "started_at": started_at,
                                 "platform": runtime.to_open_provenance(),
                                 "installed_key": installed})
        print(f"installed {installed['path']} sha256={installed['sha256']} mode={installed['mode']}")
        return 0

    proof = run_proof(key_arn=args.key_arn, bucket=args.bucket, prefix=args.prefix,
                      region=args.region, public_key_path=args.public_key_path,
                      trusted_root=args.trusted_root)
    negatives: list[dict[str, Any]] = []
    if not args.skip_negatives:
        negatives = in_process_negatives(
            key_arn=args.key_arn, bucket=args.bucket, prefix=args.prefix, region=args.region,
            public_key_path=args.public_key_path, trusted_root=args.trusted_root,
            foreign_key_path=args.foreign_key_path)

    unmatched = [c for c in negatives if not c["matched"]]
    bundle = {
        "step": "4C", "phase": "prove", "commit": args.commit, "started_at": started_at,
        "completed_at": _now(), "platform": runtime.to_open_provenance(),
        "resources": {"kms_key_arn": args.key_arn, "s3_bucket": args.bucket,
                      "s3_prefix": args.prefix, "s3_region": args.region},
        **proof,
        "negative_cases": negatives,
        "outcome": "PASS" if not unmatched else "FAIL",
    }
    _write_bundle(args.out, bundle)
    print(f"outcome={bundle['outcome']} negatives={len(negatives)} unmatched={len(unmatched)}")
    return 0 if not unmatched else 1


if __name__ == "__main__":                        # pragma: no cover - module entry point
    sys.exit(main())
