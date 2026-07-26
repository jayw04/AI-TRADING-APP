"""The production witness signer: AWS KMS asymmetric signing (ADR 0046, Step 4A).

ADR 0045 pinned the governed production profile to `ECC_NIST_P256` with `ECDSA_SHA_256`, and R5e built
every control around a signer that does not exist yet. This is that signer. The private key lives in
KMS and is never present in this process — which is the whole point of the witness boundary, and the
reason `enforce_production_witness` refuses `Ed25519AnchorSigner`.

## What this module is NOT allowed to decide

The signer's response is EVIDENCE, never authority (ADR 0045 Decision 4). Three consequences shape the
code below, and each is easy to get wrong in a way that looks harmless:

  * **The trust root stays the deployment-installed key.** This module never reads
    `witness.public_key_path`. That file has a hardened read in `witness_enforcement`
    (`verify_and_read_public_key`, checking ownership, mode and symlink freedom from the governed
    trusted root down); a second, more casual read here would be a weaker path to the same material.
    Instead the receipt carries the fingerprint of the SPKI KMS returned, and the signer challenge in
    `enforce_production_witness` refuses it if it differs from the installed key. The comparison
    happens in the trusted verifier, not here.
  * **Identity comparison is exact string equality** (ADR 0046 Decision 10), after ARN grammar
    validation and nothing else. No alias resolution, no reconstruction from parts, no case
    normalization, no substituting a bare key id for an ARN. Anything that rewrites an identity before
    comparing it can make two different keys compare equal, which is the single thing these checks
    exist to prevent.
  * **The receipt records the ARN KMS RETURNED**, not the configured string. If the two disagree the
    call is refused outright — but recording the returned value is what makes a wrong-key wiring
    surface as a key-identity mismatch during the challenge, rather than as a signature that fails to
    verify at the first real anchor.

## The prehashed contract

`build_witness_envelope` produces the canonical bytes; `envelope_digest` reduces them to 32 bytes; KMS
signs those 32 bytes with `MessageType='DIGEST'`. The verifier
(`witness_protocol.P256PrehashedVerifier`) checks with `ECDSA(Prehashed(SHA-256))` over the same
digest. `MessageType='RAW'` would make KMS hash server-side, so the signed bytes would no longer be the
bytes the receipt names — and KMS caps raw messages at 4096 bytes anyway. The digest length is asserted
before the call rather than trusted: a digest of any other length is a refusal, never a truncation.

Nothing here touches Account 4, imports the order path, or reaches S3. Failures — credentials, network,
throttling past the retry budget, KMS service and key-state errors, malformed responses — all become a
`WitnessError` and therefore a governed refusal. There is no fallback to a local key, a cached
signature, or the reference signer.
"""

from __future__ import annotations

import base64
import re
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_der_public_key

from app.validation.witness_protocol import (
    ALGORITHM_ECDSA_SHA256_P256,
    PROTOCOL_VERSION,
    SignedReceipt,
    WitnessedTip,
    WitnessError,
    WitnessSigningIdentity,
    build_witness_envelope,
    envelope_digest,
    fingerprint_public_key,
)

#: The KMS-side names. These are AWS's identifiers, deliberately distinct from the protocol's
#: `ALGORITHM_ECDSA_SHA256_P256` — one is what we ask AWS for, the other is what the receipt declares.
KMS_SIGNING_ALGORITHM = "ECDSA_SHA_256"
KMS_KEY_SPEC = "ECC_NIST_P256"
KMS_MESSAGE_TYPE = "DIGEST"

#: SHA-256. Asserted, not assumed.
DIGEST_BYTES = 32

#: Bounded effort (ADR 0046 Decision 8). Anchoring is the production of evidence: a run that eventually
#: signs after a long outage is not obviously better than one that refuses, because a refusal is a
#: legible state an operator can act on and a silently delayed anchor is not.
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 10
MAX_ATTEMPTS = 3

# A FULL, IMMUTABLE key ARN and nothing else. Aliases are refused because an alias can be repointed at
# a different key without the configuration changing; bare key ids because they name no region or
# account. Multi-Region key ids (`mrk-…`) are refused too: the same key material exists in several
# regions, so such an ARN does not name exactly one key in one place, which is what "immutable identity"
# has to mean here.
_KEY_ARN_RE = re.compile(
    r"^arn:(?P<partition>aws|aws-cn|aws-us-gov):kms:"
    r"(?P<region>[a-z]{2}(?:-[a-z]+)+-\d):"
    r"(?P<account>\d{12}):key/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


class KmsWitnessError(WitnessError):
    """AWS KMS could not produce a witness signature, or returned one that does not match the pinned
    identity. Fails closed.

    The base already stores `code`; no override is defined, so the two cannot drift.
    """


def parse_key_arn(key_arn: str) -> str:
    """Validate a full immutable KMS key ARN and return the region it names.

    Grammar validation ONLY — the string is never rewritten. The region is read out of the ARN rather
    than configured separately so the two cannot disagree: a deployment pinning a `us-east-1` key while
    configuring `us-west-2` would build a client that cannot see the key, and the failure would look
    like a missing key rather than the configuration contradiction it is.
    """
    if not isinstance(key_arn, str) or not key_arn.strip():
        raise KmsWitnessError(
            "witness.signer.options.key_arn is required; the governed key identity is the full "
            "immutable KMS key ARN", code="WITNESS_KMS_KEY_ARN_INVALID")
    match = _KEY_ARN_RE.match(key_arn)
    if match is None:
        raise KmsWitnessError(
            f"key_arn {key_arn!r} is not a full immutable KMS key ARN "
            f"(arn:<partition>:kms:<region>:<account>:key/<uuid>). Aliases, bare key ids, "
            f"multi-Region key ids and ARNs naming another resource type are refused: the pinned "
            f"identity must name exactly one key that cannot be repointed",
            code="WITNESS_KMS_KEY_ARN_INVALID")
    return match.group("region")


def _require_exact(*, returned: Any, pinned: str, what: str, code: str) -> None:
    """Exact string equality, with no normalization of either side (ADR 0046 Decision 10)."""
    if not isinstance(returned, str) or returned != pinned:
        raise KmsWitnessError(
            f"KMS returned {what} {returned!r}; this deployment pins {pinned!r}. Comparison is exact: "
            f"a semantically equivalent value that differs in text — a bare key id, a different case — "
            f"is refused rather than normalized",
            code=code)


class KmsAnchorSigner:
    """Production `AnchorSigner` backed by AWS KMS.

    Holds a boto3 client and nothing else. It has no private-key object to hold, so
    `witness_enforcement._assert_no_in_process_private_key` passes on the merits rather than by
    accident — the observation-store writer genuinely cannot produce a signature.

    Constructed only by `build_kms_anchor_signer`, which is reached only through the
    `witness.signer.factory` string in the governed configuration.
    """

    def __init__(self, *, client: Any, key_arn: str, witness_identity: str) -> None:
        self._client = client
        self._key_arn = key_arn
        self._witness_identity = witness_identity
        # Construction-time cross-check. Doing it here turns "this ARN is wrong", "this key is the
        # wrong spec" and "this key cannot sign with the pinned algorithm" into refusals before any
        # session runs, instead of signature failures at the first anchor.
        self._public_key_der = self._fetch_and_check_public_key()
        self.public_key_fingerprint = fingerprint_public_key(self._public_key_der)
        self._identity = WitnessSigningIdentity(
            protocol_version=PROTOCOL_VERSION,
            algorithm=ALGORITHM_ECDSA_SHA256_P256,
            key_id=self._key_arn,
            public_key_fingerprint=self.public_key_fingerprint)

    # ── construction-time cross-check ────────────────────────────────────────────────────────────────

    def _fetch_and_check_public_key(self) -> bytes:
        """Call `GetPublicKey` ONCE and check the key is what the deployment pinned.

        This is a cross-check, not a trust root: the DER returned here is never installed anywhere and
        never used to build a verifier. Whoever controls the ARN controls this response, so treating it
        as authority would restore exactly the circularity R5e removed when it stopped obtaining the
        verifier from the signer.
        """
        response = self._call(self._client.get_public_key, KeyId=self._key_arn, what="GetPublicKey")

        _require_exact(returned=response.get("KeyId"), pinned=self._key_arn, what="a KeyId",
                       code="WITNESS_KEY_IDENTITY_MISMATCH")

        key_spec = response.get("KeySpec") or response.get("CustomerMasterKeySpec")
        if key_spec != KMS_KEY_SPEC:
            raise KmsWitnessError(
                f"the pinned key has KeySpec {key_spec!r}; the governed production profile requires "
                f"{KMS_KEY_SPEC} (ADR 0045)", code="WITNESS_ALGORITHM_NOT_PINNED")

        advertised = response.get("SigningAlgorithms") or []
        if KMS_SIGNING_ALGORITHM not in advertised:
            raise KmsWitnessError(
                f"the pinned key advertises signing algorithms {sorted(advertised)!r}, which does not "
                f"include {KMS_SIGNING_ALGORITHM}", code="WITNESS_ALGORITHM_NOT_PINNED")

        der = response.get("PublicKey")
        if not isinstance(der, (bytes, bytearray)) or not der:
            raise KmsWitnessError(
                f"GetPublicKey returned {type(der).__name__} rather than DER SubjectPublicKeyInfo bytes",
                code="WITNESS_PUBLIC_KEY_UNUSABLE")
        der = bytes(der)

        # Parsed for self-consistency only. Equality with the DEPLOYMENT-INSTALLED key is enforced by
        # the signer challenge, which compares this fingerprint against the trusted verifier's.
        try:
            key = load_der_public_key(der)
        except Exception as exc:                  # noqa: BLE001 - any parse failure is a refusal
            raise KmsWitnessError(
                f"GetPublicKey returned bytes that are not parseable DER SubjectPublicKeyInfo: {exc}",
                code="WITNESS_PUBLIC_KEY_UNUSABLE") from exc
        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
            raise KmsWitnessError(
                f"GetPublicKey returned a {type(key).__name__} that is not a P-256 EC public key",
                code="WITNESS_PUBLIC_KEY_UNUSABLE")
        return der

    # ── the AnchorSigner interface ───────────────────────────────────────────────────────────────────

    def attest(self, tip: WitnessedTip) -> SignedReceipt:
        """Sign one chain tip in KMS and return a complete protocol-v2 receipt."""
        envelope = build_witness_envelope(tip, self._identity)
        digest = envelope_digest(envelope)
        if len(digest) != DIGEST_BYTES:
            raise KmsWitnessError(
                f"the envelope digest is {len(digest)} bytes; MessageType={KMS_MESSAGE_TYPE} requires "
                f"exactly {DIGEST_BYTES}", code="WITNESS_MESSAGE_DIGEST_MISMATCH")

        response = self._call(
            self._client.sign, what="Sign",
            KeyId=self._key_arn, Message=digest, MessageType=KMS_MESSAGE_TYPE,
            SigningAlgorithm=KMS_SIGNING_ALGORITHM)

        _require_exact(returned=response.get("SigningAlgorithm"), pinned=KMS_SIGNING_ALGORITHM,
                       what="a SigningAlgorithm", code="WITNESS_ALGORITHM_NOT_PINNED")
        _require_exact(returned=response.get("KeyId"), pinned=self._key_arn, what="a KeyId",
                       code="WITNESS_KEY_IDENTITY_MISMATCH")

        signature = response.get("Signature")
        if not isinstance(signature, (bytes, bytearray)) or not signature:
            raise KmsWitnessError(
                f"Sign returned {type(signature).__name__} rather than signature bytes",
                code="ANCHOR_SIGNATURE_INVALID")

        return SignedReceipt(
            protocol_version=PROTOCOL_VERSION,
            algorithm=ALGORITHM_ECDSA_SHA256_P256,
            # The ARN KMS RETURNED. Identical to the pinned one by the check above — recording the
            # returned value is what makes a wrong-key wiring a key-identity finding rather than a
            # signature failure.
            key_id=response["KeyId"],
            public_key_fingerprint=self.public_key_fingerprint,
            message_digest=digest.hex(),
            # ASN.1 DER, exactly as KMS produced it. Never normalized to raw r||s: the protocol stores
            # what the signer emitted, and a re-encoding step is one more place for the stored bytes
            # and the verified bytes to diverge.
            signature=base64.b64encode(bytes(signature)).decode("ascii"),
            signed_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            witness_identity=self._witness_identity)

    def identity(self) -> str:
        return f"{self._witness_identity}@{self._key_arn}"

    # ── failure translation ──────────────────────────────────────────────────────────────────────────

    def _call(self, operation: Any, *, what: str, **kwargs: Any) -> dict[str, Any]:
        """Invoke one KMS operation, turning EVERY failure into a governed refusal.

        `ClientError` covers the service-side conditions an operator needs named — a disabled or
        pending-deletion key, access denied, throttling that survived the retry budget. `BotoCoreError`
        covers the client-side ones: no credentials, endpoint resolution, connection and read timeouts.
        The bare `Exception` arm is the backstop, because an SDK exception escaping this boundary
        un-translated would surface somewhere that does not know it means "stop".
        """
        try:
            response = operation(**kwargs)
        except ClientError as exc:
            error = exc.response.get("Error", {}) if isinstance(exc.response, dict) else {}
            raise KmsWitnessError(
                f"KMS {what} was refused for {self._key_arn}: "
                f"{error.get('Code', 'Unknown')}: {error.get('Message', exc)}",
                code="INDEPENDENT_WITNESS_UNAVAILABLE") from exc
        except BotoCoreError as exc:
            raise KmsWitnessError(
                f"KMS {what} could not be completed for {self._key_arn} "
                f"({type(exc).__name__}: {exc}); credentials, connectivity or the retry budget",
                code="INDEPENDENT_WITNESS_UNAVAILABLE") from exc
        except Exception as exc:                  # noqa: BLE001 - no SDK failure escapes untranslated
            raise KmsWitnessError(
                f"KMS {what} failed unexpectedly for {self._key_arn}: {type(exc).__name__}: {exc}",
                code="INDEPENDENT_WITNESS_UNAVAILABLE") from exc

        if not isinstance(response, dict):
            raise KmsWitnessError(
                f"KMS {what} returned {type(response).__name__} rather than a response mapping",
                code="INDEPENDENT_WITNESS_UNAVAILABLE")
        return response


def build_kms_anchor_signer(*, key_arn: str, witness_identity: str,
                            client: Any = None) -> KmsAnchorSigner:
    """The factory named by `witness.signer.factory` in the governed configuration.

    Credentials are NOT accepted here and never will be: they come from the ambient provider chain (the
    instance role on `ec2-forward-validation`). `witness_config.assert_no_private_key_material` already
    refuses `access_key`, `credential(s)` and `secret*` option names before this module is imported, and
    the region is derived from the ARN rather than configured, so there is no option through which an
    operator could point the witness at a different endpoint.

    `client` is a test seam. It cannot be supplied by a deployment: `options` comes from JSON and a
    boto3 client is not expressible there, so configuration can only ever take the `None` path.
    """
    region = parse_key_arn(key_arn)
    if not isinstance(witness_identity, str) or not witness_identity.strip():
        raise KmsWitnessError(
            "witness.signer.options.witness_identity is required; an unnamed signer cannot be "
            "attributed in the record", code="WITNESS_CONFIG_INCOMPLETE")

    if client is None:
        client = boto3.client(
            "kms",
            region_name=region,
            config=Config(
                retries={"mode": "standard", "max_attempts": MAX_ATTEMPTS},
                connect_timeout=CONNECT_TIMEOUT_SECONDS,
                read_timeout=READ_TIMEOUT_SECONDS,
            ),
        )
    return KmsAnchorSigner(client=client, key_arn=key_arn, witness_identity=witness_identity)


__all__ = [
    "DIGEST_BYTES",
    "KMS_KEY_SPEC",
    "KMS_MESSAGE_TYPE",
    "KMS_SIGNING_ALGORITHM",
    "KmsAnchorSigner",
    "KmsWitnessError",
    "build_kms_anchor_signer",
    "parse_key_arn",
]
