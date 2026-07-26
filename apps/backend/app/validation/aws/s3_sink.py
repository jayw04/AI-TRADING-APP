"""The production external witness: an S3 Object-Lock append-only sink (ADR 0046, Step 4B).

The signer (`kms_signer`) gives the chain tip a signature the observation-store writer cannot forge —
rewrite protection. It does nothing about TRUNCATION: an attacker who deletes the latest anchors hides
the sessions entirely, and every remaining signature still verifies. That is what the external sink is
for. Tips land in storage with separately governed write authority, and
`chain_anchor._assert_witnessed` cross-checks it against the local log, so a local truncation shows up
as `EXTERNAL_WITNESS_AHEAD`.

`FileExternalAnchorSink` models the shape but provides none of the property — a directory the
store-writer can reach is truncated by the same actor, in the same breath — so R5e refuses it. This
adapter is the real one.

## What makes the sink trustworthy is not the code here

An `ImmutabilityAttestation` is only worth anything if it was ASKED of the storage and BOUND to the
storage that is actually written through. Both are enforced by `witness_enforcement`, and this module is
written to satisfy them honestly:

  * `immutability_attestation()` reports what `GetBucketVersioning` and `GetObjectLockConfiguration`
    answered, with `source=STORAGE`. A configured assertion that the bucket is immutable would be
    `DECLARED` and would be refused.
  * `publication_storage_identity()` is built from the SAME bucket and prefix attributes that
    `publish()` and `read_all()` use. The failure this defends against is not malice but wiring: an
    adapter that reads Object-Lock configuration from bucket A while publishing to bucket B reports
    `enforced=True` while the record accumulates somewhere anyone can truncate.

## Append-only, structurally

There is no delete, no overwrite and no rewrite path on this class — not a guarded one, none. `publish`
writes with `IfNoneMatch='*'`, so S3 itself refuses to replace an existing object, and a second publish
of the same tip is resolved by READING what is already there:

  * byte-identical payload → the tip is already witnessed, and the publish is an idempotent no-op;
  * anything else → `EXTERNAL_WITNESS_DIVERGES`, refused.

That distinction is why the payload is canonical JSON with the receipt stored as the protocol's own
canonical string: "identical" has to mean identical bytes, or idempotency quietly becomes "close
enough".

Object identity is deterministic and derived from the governed tip — sequence and session date — so the
same tip always addresses the same object and two writers cannot race into two different keys for one
sequence. On read, the key is recomputed from the parsed content and required to match, so an object
filed under a key that disagrees with what it contains is refused rather than silently accepted.

## Least-privilege IAM (Step 4B; provisioned later, in the isolated integration proof)

    s3:PutObject, s3:GetObject, s3:ListBucket,
    s3:GetBucketVersioning, s3:GetBucketObjectLockConfiguration

scoped to the one bucket and prefix. Deliberately no `s3:DeleteObject`, no
`s3:PutBucketObjectLockConfiguration`, no `s3:BypassGovernanceRetention`: the writer must not be able to
remove a tip, weaken the lock, or override retention.

Nothing here touches Account 4, imports the order path, or signs anything.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.validation.witness_enforcement import (
    ATTESTATION_FROM_STORAGE,
    ImmutabilityAttestation,
)
from app.validation.witness_protocol import (
    SignedReceipt,
    WitnessedTip,
    WitnessError,
    deserialize_receipt,
    serialize_receipt,
)

#: Bounded effort, matching the signer. A witness that hangs is a session that hangs.
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 10
MAX_ATTEMPTS = 3

#: A guard on `read_all` pagination. The forward window is 1700 sessions; a sink holding orders of
#: magnitude more objects than tips is a condition to stop on, not to page through.
MAX_LIST_PAGES = 100

#: Object Lock retention modes S3 can enforce. `GOVERNANCE` is accepted because the least-privilege
#: policy withholds `s3:BypassGovernanceRetention` — the mode is recorded in the attestation either way,
#: so an auditor can see which one protected the record.
LOCK_MODES = ("COMPLIANCE", "GOVERNANCE")

_TIP_FIELDS = ("sequence", "session_date", "commit_sha256", "anchor_sha256")


class S3SinkError(WitnessError):
    """The external witness could not be written, read, or proven immutable. Fails closed."""


def _canonical_prefix(prefix: str) -> str:
    """A prefix with no leading or trailing separator, so identity and keys are unambiguous."""
    return str(prefix or "").strip().strip("/")


class S3ObjectLockAnchorSink:
    """Production `ExternalAnchorSink` over an S3 bucket with Object Lock and versioning enabled.

    Constructed only by `build_s3_object_lock_sink`, reached only through the `witness.sink.factory`
    string in the governed configuration.
    """

    def __init__(self, *, client: Any, bucket: str, prefix: str) -> None:
        self._client = client
        self._bucket = str(bucket)
        self._prefix = _canonical_prefix(prefix)

    # ── identity ─────────────────────────────────────────────────────────────────────────────────────

    def _storage_identity(self) -> str:
        """The one canonical identity, derived from the attributes publish/read_all actually use."""
        return f"s3://{self._bucket}/{self._prefix}" if self._prefix else f"s3://{self._bucket}"

    def identity(self) -> str:
        return self._storage_identity()

    def publication_storage_identity(self) -> str:
        """Required by `ImmutableAnchorSink`, and required to EQUAL the attested identity.

        Both come from `self._bucket`/`self._prefix`, which are the same values every `put_object`,
        `get_object` and `list_objects_v2` below is issued against. There is deliberately no second
        source of bucket configuration in this class for them to drift from.
        """
        return self._storage_identity()

    def _key_for(self, sequence: int, session_date: str) -> str:
        """Deterministic object identity from the governed tip.

        Zero-padded so lexicographic listing order is sequence order, and carrying the session date so
        an object names the session it witnesses without being opened.
        """
        name = f"{int(sequence):06d}-{session_date}.json"
        return f"{self._prefix}/{name}" if self._prefix else name

    # ── the canonical payload ────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _canonical_payload(tip: WitnessedTip, receipt: SignedReceipt) -> bytes:
        """The exact bytes stored for one tip.

        The receipt is embedded as the PROTOCOL's canonical string rather than a nested object this
        module assembles: a layer that builds its own mapping can bypass the strict parse on the way
        back in, and byte-level idempotency needs a byte-level canonical form.
        """
        payload = {
            "tip": {"sequence": int(tip.sequence), "session_date": tip.session_date,
                    "commit_sha256": tip.commit_sha256, "anchor_sha256": tip.anchor_sha256},
            "receipt": serialize_receipt(receipt),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    # ── publish ──────────────────────────────────────────────────────────────────────────────────────

    def publish(self, tip: WitnessedTip, receipt: SignedReceipt) -> None:
        """Record one signed tip. Append-only: never overwrites, never deletes.

        `IfNoneMatch='*'` makes S3 itself refuse to replace an existing object, so the no-overwrite
        property is enforced by the storage rather than by this code remembering to check first.
        """
        key = self._key_for(tip.sequence, tip.session_date)
        body = self._canonical_payload(tip, receipt)
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=body,
                ContentType="application/json", IfNoneMatch="*")
            return
        except ClientError as exc:
            if _error_code(exc) not in ("PreconditionFailed", "ConditionalRequestConflict"):
                raise self._translate(exc, "PutObject") from exc
        except BotoCoreError as exc:
            raise self._translate(exc, "PutObject") from exc
        except Exception as exc:                  # noqa: BLE001 - no SDK failure escapes untranslated
            raise self._translate(exc, "PutObject") from exc

        # The object already exists. Idempotent ONLY if what is there is byte-identical.
        existing = self._get_object_bytes(key)
        if existing == body:
            return
        raise S3SinkError(
            f"the external sink already holds a DIFFERENT record at {key} — refusing to overwrite an "
            f"immutable witness. The stored bytes and the bytes for this tip differ, so one of them "
            f"does not describe the tip being anchored",
            code="EXTERNAL_WITNESS_DIVERGES")

    # ── read ─────────────────────────────────────────────────────────────────────────────────────────

    def read_all(self) -> list[tuple[WitnessedTip, SignedReceipt]]:
        """Every recorded tip, in sequence order, parsed through the protocol's strict schema."""
        records: list[tuple[int, WitnessedTip, SignedReceipt]] = []
        for key in self._list_keys():
            tip, receipt = self._parse(key, self._get_object_bytes(key))
            records.append((tip.sequence, tip, receipt))
        records.sort(key=lambda r: r[0])
        return [(tip, receipt) for _, tip, receipt in records]

    def _list_keys(self) -> list[str]:
        keys: list[str] = []
        token: str | None = None
        for _ in range(MAX_LIST_PAGES):
            kwargs: dict[str, Any] = {"Bucket": self._bucket}
            if self._prefix:
                kwargs["Prefix"] = f"{self._prefix}/"
            if token:
                kwargs["ContinuationToken"] = token
            response = self._call(self._client.list_objects_v2, what="ListObjectsV2", **kwargs)
            for item in response.get("Contents") or []:
                key = item.get("Key")
                if isinstance(key, str) and key.endswith(".json"):
                    keys.append(key)
            if not response.get("IsTruncated"):
                return keys
            token = response.get("NextContinuationToken")
            if not token:
                return keys
        raise S3SinkError(
            f"the external witness listing exceeded {MAX_LIST_PAGES} pages; a sink holding far more "
            f"objects than there are committed tips is a condition to stop on",
            code="EXTERNAL_WITNESS_INVALID")

    def _get_object_bytes(self, key: str) -> bytes:
        response = self._call(self._client.get_object, what="GetObject",
                              Bucket=self._bucket, Key=key)
        body = response.get("Body")
        # `getattr` rather than `body.read()`: a response with no Body at all must become a refusal
        # here, not an AttributeError on the way out of the witness boundary.
        reader = getattr(body, "read", None)
        try:
            raw = reader() if callable(reader) else body
        except Exception as exc:                  # noqa: BLE001 - an unreadable body is a refusal
            raise S3SinkError(f"the external witness record {key} could not be read: {exc}",
                              code="EXTERNAL_WITNESS_INVALID") from exc
        if not isinstance(raw, (bytes, bytearray)):
            raise S3SinkError(
                f"the external witness record {key} returned {type(raw).__name__} rather than bytes",
                code="EXTERNAL_WITNESS_INVALID")
        return bytes(raw)

    def _parse(self, key: str, raw: bytes) -> tuple[WitnessedTip, SignedReceipt]:
        """Strict parse. Unknown fields, a missing receipt, or a key that disagrees with the content are
        all refusals — an object filed under the wrong key is not evidence about the tip it claims."""
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise S3SinkError(f"the external witness record {key} is not valid JSON: {exc}",
                              code="EXTERNAL_WITNESS_INVALID") from exc
        if not isinstance(payload, dict) or set(payload) != {"tip", "receipt"}:
            raise S3SinkError(
                f"the external witness record {key} does not carry exactly a tip and a receipt",
                code="EXTERNAL_WITNESS_INVALID")
        tip_obj = payload["tip"]
        if not isinstance(tip_obj, dict) or set(tip_obj) != set(_TIP_FIELDS):
            raise S3SinkError(
                f"the external witness record {key} has an unexpected tip field set",
                code="EXTERNAL_WITNESS_INVALID")
        try:
            tip = WitnessedTip(sequence=int(tip_obj["sequence"]),
                               session_date=str(tip_obj["session_date"]),
                               commit_sha256=str(tip_obj["commit_sha256"]),
                               anchor_sha256=str(tip_obj["anchor_sha256"]))
        except (TypeError, ValueError) as exc:
            raise S3SinkError(f"the external witness record {key} has an unreadable tip: {exc}",
                              code="EXTERNAL_WITNESS_INVALID") from exc

        receipt_text = payload["receipt"]
        if not isinstance(receipt_text, str):
            raise S3SinkError(
                f"the external witness record {key} stores its receipt as "
                f"{type(receipt_text).__name__}, not the protocol's canonical string",
                code="EXTERNAL_WITNESS_INVALID")
        try:
            receipt = deserialize_receipt(receipt_text)
        except WitnessError as exc:
            raise S3SinkError(f"the external witness record {key} has an invalid receipt: {exc}",
                              code="EXTERNAL_WITNESS_INVALID") from exc

        expected = self._key_for(tip.sequence, tip.session_date)
        if key != expected:
            raise S3SinkError(
                f"the external witness record at {key} describes sequence {tip.sequence} / session "
                f"{tip.session_date}, which belongs at {expected}; an object filed under a key that "
                f"disagrees with its content is not evidence about the tip it names",
                code="EXTERNAL_WITNESS_INVALID")
        return tip, receipt

    # ── the immutability attestation ─────────────────────────────────────────────────────────────────

    def immutability_attestation(self) -> ImmutabilityAttestation:
        """Ask the STORAGE whether it enforces write-once, and report exactly what it answered.

        Two questions, because either alone is insufficient: Object Lock cannot be enabled without
        versioning, and versioning alone permits deletion of the current version. A bucket missing
        either is reported `enforced=False`, which the gate turns into a refusal — as distinct from a
        query that FAILS, which raises and becomes `WITNESS_SINK_IMMUTABILITY_UNPROVEN`.
        """
        versioning = self._call(self._client.get_bucket_versioning, what="GetBucketVersioning",
                                Bucket=self._bucket)
        lock = self._call(self._client.get_object_lock_configuration,
                          what="GetObjectLockConfiguration", Bucket=self._bucket)

        versioning_status = str(versioning.get("Status") or "")
        configuration = lock.get("ObjectLockConfiguration") or {}
        lock_enabled = str(configuration.get("ObjectLockEnabled") or "")
        retention = (configuration.get("Rule") or {}).get("DefaultRetention") or {}
        mode = str(retention.get("Mode") or "")
        days, years = retention.get("Days"), retention.get("Years")

        period = (f"{days} day(s)" if days else f"{years} year(s)" if years else "none")
        enforced = (versioning_status == "Enabled" and lock_enabled == "Enabled"
                    and mode in LOCK_MODES and bool(days or years))

        detail = (f"GetBucketVersioning.Status={versioning_status or 'absent'}; "
                  f"GetObjectLockConfiguration.ObjectLockEnabled={lock_enabled or 'absent'}; "
                  f"DefaultRetention.Mode={mode or 'absent'}; retention={period}")
        return ImmutabilityAttestation(
            enforced=enforced,
            mode=mode or "NONE",
            scope=self._storage_identity(),
            source=ATTESTATION_FROM_STORAGE,
            checked_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            storage_identity=self._storage_identity(),
            detail=detail)

    # ── failure translation ──────────────────────────────────────────────────────────────────────────

    def _translate(self, exc: Exception, what: str) -> S3SinkError:
        if isinstance(exc, ClientError):
            error = exc.response.get("Error", {}) if isinstance(exc.response, dict) else {}
            return S3SinkError(
                f"S3 {what} was refused for {self._storage_identity()}: "
                f"{error.get('Code', 'Unknown')}: {error.get('Message', exc)}",
                code="INDEPENDENT_WITNESS_UNAVAILABLE")
        if isinstance(exc, BotoCoreError):
            return S3SinkError(
                f"S3 {what} could not be completed for {self._storage_identity()} "
                f"({type(exc).__name__}: {exc}); credentials, connectivity or the retry budget",
                code="INDEPENDENT_WITNESS_UNAVAILABLE")
        return S3SinkError(
            f"S3 {what} failed unexpectedly for {self._storage_identity()}: "
            f"{type(exc).__name__}: {exc}", code="INDEPENDENT_WITNESS_UNAVAILABLE")

    def _call(self, operation: Any, *, what: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = operation(**kwargs)
        except Exception as exc:                  # noqa: BLE001 - every SDK failure becomes a stop
            raise self._translate(exc, what) from exc
        if not isinstance(response, dict):
            raise S3SinkError(
                f"S3 {what} returned {type(response).__name__} rather than a response mapping",
                code="INDEPENDENT_WITNESS_UNAVAILABLE")
        return response


def _error_code(exc: ClientError) -> str:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return ""
    return str((response.get("Error") or {}).get("Code") or "")


def build_s3_object_lock_sink(*, bucket: str, prefix: str, region: str,
                              client: Any = None) -> S3ObjectLockAnchorSink:
    """The factory named by `witness.sink.factory` in the governed configuration.

    Credentials are not accepted here: they come from the ambient provider chain, and
    `witness_config.assert_no_private_key_material` refuses credential-shaped option names before this
    module is imported.

    `region` must be stated because, unlike the signer's key ARN, a bucket name carries none. It is
    verified against `GetBucketLocation` at construction, so a deployment that names the wrong region
    is refused rather than silently talking to an endpoint that redirects.

    `client` is a test seam and cannot be supplied by a deployment: `options` comes from JSON.
    """
    for name, value in (("bucket", bucket), ("prefix", prefix), ("region", region)):
        if not isinstance(value, str) or not value.strip():
            raise S3SinkError(
                f"witness.sink.options.{name} is required; an external witness that cannot name its "
                f"storage cannot be bound to it", code="WITNESS_CONFIG_INCOMPLETE")

    if client is None:
        client = boto3.client(
            "s3",
            region_name=region,
            config=Config(
                retries={"mode": "standard", "max_attempts": MAX_ATTEMPTS},
                connect_timeout=CONNECT_TIMEOUT_SECONDS,
                read_timeout=READ_TIMEOUT_SECONDS,
            ),
        )

    sink = S3ObjectLockAnchorSink(client=client, bucket=bucket, prefix=prefix)
    actual = sink._call(client.get_bucket_location, what="GetBucketLocation", Bucket=bucket)
    # S3 reports us-east-1 as an absent/empty LocationConstraint, for historical reasons.
    located = str(actual.get("LocationConstraint") or "us-east-1")
    if located != region:
        raise S3SinkError(
            f"witness.sink.options.region is {region!r} but bucket {bucket!r} is in {located!r}; the "
            f"region a deployment pins and the region the bucket is in must be the same",
            code="WITNESS_SINK_NOT_IMMUTABLE")
    return sink


__all__ = [
    "LOCK_MODES",
    "MAX_LIST_PAGES",
    "S3ObjectLockAnchorSink",
    "S3SinkError",
    "build_s3_object_lock_sink",
]
