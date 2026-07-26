"""Independent anchor WITNESS — the separate trust boundary the chain tip is recorded across (R5d).

The local anchor log (`chain_anchor`) lives in the same store, written by the same process, as the
observations it witnesses. A local attacker who can rewrite `observations/7..N` can ordinarily rewrite
`chain_anchors.jsonl` lines 7..N too and recompute every digest — so the local log alone is defence in
depth, not an independent witness (the #494 threat model, restated by the R5d review).

This module supplies the separate trust boundary, in two complementary parts:

  * **A signer whose private key the observation-store writer does NOT hold** (`AnchorSigner`). Each tip
    is signed; the runner keeps only the PUBLIC verifying key. An attacker with local write access can
    alter the tip bytes but cannot forge a signature for the altered tip — rewrite protection. In
    production the signer is an out-of-process signing service / KMS / HSM; here `Ed25519AnchorSigner`
    is the reference implementation and the tests construct it with a throwaway key.
  * **An external, append-only sink with separately governed write authority** (`ExternalAnchorSink`).
    Each signed tip is also persisted there (WORM / Object-Lock / a different account in production). An
    attacker who truncates the local log to hide the latest sessions cannot remove the externally
    recorded tip — truncation/rollback protection. `FileExternalAnchorSink` is the reference
    implementation; it writes one no-overwrite file per tip under a root OUTSIDE the observation store.

Verification (in `chain_anchor.verify_anchor_consistency`) uses BOTH: every local anchor's signature must
verify against the public key, and the external sink's recorded tips must match the local log — a local
tip the sink never saw, or a sink tip the local log dropped, fails closed.

Nothing here touches Account 4 or imports the order path.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.validation.witness_protocol import (
    ALGORITHM_ED25519,
    PROTOCOL_VERSION,
    SignedReceipt,
    WitnessedTip,
    WitnessError,
    WitnessSigningIdentity,
    build_verifier,
    build_witness_envelope,
    envelope_digest,
    fingerprint_public_key,
    verify_receipt,
)

# `WitnessError` is defined by the protocol module and re-exported here, so the hierarchy has one root
# and the dependency direction stays protocol <- chain_witness.


# `WitnessedTip` and `SignedReceipt` now live in `witness_protocol` — the protocol owns its own schema,
# and this module owns signer custody and sinks. Re-exported so existing importers keep working.
#
# The old `public_key_id()` (sha256 truncated to 16 hex characters) is GONE. A receipt carries the FULL
# `public_key_fingerprint`; truncating a mismatch detector to 64 bits bought nothing.


def reference_key_id(public_bytes: bytes) -> str:
    """The key identity of the Ed25519 REFERENCE signer, derived from its own key.

    Production key identity is the pinned KMS key ARN and comes from governed configuration. This is the
    reference implementation naming itself, not a value synthesized to fill a required field — and the
    `reference:` prefix means it can never be mistaken for a production ARN.
    """
    return f"reference:ed25519:{fingerprint_public_key(public_bytes)[:16]}"


@runtime_checkable
class AnchorSigner(Protocol):
    """Signs a chain tip across a trust boundary the observation-store writer cannot reach. The runner
    holds a reference to this (a client), never the private key."""

    def attest(self, tip: WitnessedTip) -> SignedReceipt: ...

    def identity(self) -> str: ...


class AnchorVerifier:
    """Verifies tip receipts using ONLY public material — safe to hold locally.

    A facade over the protocol's typed verifier strategies. It holds the deployment's PINNED identity
    and delegates to `verify_receipt`, which checks protocol version, algorithm, key identity and
    envelope digest BEFORE any cryptography runs.

    The reference default is Ed25519 with the key naming itself. A production caller constructs this
    explicitly with the pinned algorithm and key ARN from governed configuration — the verifier never
    infers either from a receipt.
    """

    def __init__(self, installed_key_bytes: bytes, *, algorithm: str = ALGORITHM_ED25519,
                 key_id: str | None = None) -> None:
        self._installed = installed_key_bytes
        self.pinned = WitnessSigningIdentity(
            protocol_version=PROTOCOL_VERSION, algorithm=algorithm,
            key_id=key_id if key_id is not None else reference_key_id(installed_key_bytes),
            public_key_fingerprint=fingerprint_public_key(installed_key_bytes))
        self._verifier = build_verifier(algorithm, installed_key_bytes)

    @property
    def public_key_fingerprint(self) -> str:
        return self.pinned.public_key_fingerprint

    def verify(self, tip: WitnessedTip, receipt: SignedReceipt) -> None:
        verify_receipt(tip, receipt, pinned=self.pinned, verifier=self._verifier)


class Ed25519AnchorSigner:
    """Reference `AnchorSigner`: an Ed25519 keypair. In production this object lives in the separate
    signing service and only its `attest` is reachable; the runner is given the public key (via
    `verifier()`) and a client, never these private-key bytes.

    DEVELOPMENT AND TESTS ONLY. Held in the runner's own process, this key gives the observation-store
    writer the ability to forge any signature, so it is not a separate trust boundary at all. R5e's
    `witness_enforcement.enforce_production_witness` refuses it — via the marker below — for any governed
    session."""

    IS_REFERENCE_IMPLEMENTATION = True

    def __init__(self, private_key: Ed25519PrivateKey, *, witness_identity: str) -> None:
        self._private = private_key
        self._witness_identity = witness_identity
        self._public_bytes = private_key.public_key().public_bytes_raw()
        self.public_key_fingerprint = fingerprint_public_key(self._public_bytes)
        self._identity = WitnessSigningIdentity(
            protocol_version=PROTOCOL_VERSION, algorithm=ALGORITHM_ED25519,
            key_id=reference_key_id(self._public_bytes),
            public_key_fingerprint=self.public_key_fingerprint)

    @classmethod
    def generate(cls, *, witness_identity: str) -> Ed25519AnchorSigner:
        return cls(Ed25519PrivateKey.generate(), witness_identity=witness_identity)

    def attest(self, tip: WitnessedTip) -> SignedReceipt:
        """Emit a COMPLETE protocol-v2 receipt.

        Ed25519 is not a prehashed scheme, so the signature covers the envelope bytes directly. The
        digest is still recorded — it is what lets a reader prove the envelope reconstructs, which is a
        separate question from whether the signature is valid.
        """
        envelope = build_witness_envelope(tip, self._identity)
        signature = self._private.sign(envelope)
        return SignedReceipt(
            protocol_version=PROTOCOL_VERSION,
            algorithm=ALGORITHM_ED25519,
            key_id=self._identity.key_id,
            public_key_fingerprint=self.public_key_fingerprint,
            message_digest=envelope_digest(envelope).hex(),
            signature=base64.b64encode(signature).decode("ascii"),
            signed_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            witness_identity=self._witness_identity)

    def identity(self) -> str:
        return f"{self._witness_identity}@{self.public_key_fingerprint[:16]}"

    def public_bytes(self) -> bytes:
        return self._public_bytes

    def verifier(self) -> AnchorVerifier:
        """The public-key-only verifier the runner holds (the private key stays here)."""
        return AnchorVerifier(self._public_bytes, algorithm=ALGORITHM_ED25519,
                              key_id=self._identity.key_id)


@runtime_checkable
class ExternalAnchorSink(Protocol):
    """An append-only record of signed tips with SEPARATELY GOVERNED write authority — WORM / Object-Lock
    / a different account in production. Cross-checked against the local log so a local truncation (the
    latest tips deleted) is caught by the sink still holding them."""

    def publish(self, tip: WitnessedTip, receipt: SignedReceipt) -> None: ...

    def read_all(self) -> list[tuple[WitnessedTip, SignedReceipt]]: ...

    def identity(self) -> str: ...


class FileExternalAnchorSink:
    """Reference `ExternalAnchorSink`: one no-overwrite JSON file per tip under a root that MUST be
    outside the observation store and, in production, on write-once storage with separate credentials
    (the class cannot enforce that here — deployment does). No-overwrite publish models the append-only,
    never-rewrite property; a second publish of the same sequence fails closed.

    DEVELOPMENT AND TESTS ONLY. A directory the store-writer can reach is not separately governed: the
    same actor who truncates the local anchor log truncates this alongside it. R5e's
    `witness_enforcement.enforce_production_witness` refuses it — via the marker below — for any governed
    session."""

    IS_REFERENCE_IMPLEMENTATION = True

    def __init__(self, root: Path, *, identity: str) -> None:
        self._root = root
        self._identity = identity

    def publish(self, tip: WitnessedTip, receipt: SignedReceipt) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{tip.sequence:06d}.json"
        payload = json.dumps({"tip": {"sequence": tip.sequence, "session_date": tip.session_date,
                                      "commit_sha256": tip.commit_sha256,
                                      "anchor_sha256": tip.anchor_sha256},
                              "receipt": receipt.to_dict()}, sort_keys=True, indent=2)
        try:
            # O_EXCL: the sink is append-only; it never rewrites a recorded tip. (Write-once enforcement
            # in production comes from the storage layer — WORM / Object-Lock — not the file mode.)
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("tip", {}).get("commit_sha256") == tip.commit_sha256:
                return                                  # idempotent: the same tip is already witnessed
            raise WitnessError(
                f"the external sink already holds a DIFFERENT tip at sequence {tip.sequence} — refusing "
                f"to overwrite an immutable witness", code="EXTERNAL_WITNESS_DIVERGES") from None
        try:
            os.write(fd, payload.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)

    def read_all(self) -> list[tuple[WitnessedTip, SignedReceipt]]:
        if not self._root.is_dir():
            return []
        out: list[tuple[int, WitnessedTip, SignedReceipt]] = []
        for path in self._root.iterdir():
            if not (path.is_file() and path.name.endswith(".json")):
                continue
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
                t = obj["tip"]
                tip = WitnessedTip(sequence=int(t["sequence"]), session_date=str(t["session_date"]),
                                   commit_sha256=str(t["commit_sha256"]),
                                   anchor_sha256=str(t["anchor_sha256"]))
                receipt = SignedReceipt.from_dict(obj["receipt"])
            except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
                raise WitnessError(f"external witness record {path.name} is unreadable/corrupt: {exc}",
                                   code="EXTERNAL_WITNESS_INVALID") from exc
            out.append((tip.sequence, tip, receipt))
        out.sort(key=lambda r: r[0])
        return [(tip, receipt) for _, tip, receipt in out]

    def identity(self) -> str:
        return self._identity
