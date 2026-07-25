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
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.validation.forward_window import IntegrityStop


class WitnessError(IntegrityStop):
    """The independent witness could not be produced or verified. Fails closed."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class WitnessedTip:
    """The compact identity of a committed chain tip that is signed and externally recorded. It binds the
    observation tip (`commit_sha256`) and the LOCAL anchor line (`anchor_sha256`), so the external witness
    and the local log cannot silently disagree about which tip was witnessed."""
    sequence: int
    session_date: str
    commit_sha256: str
    anchor_sha256: str

    def signing_bytes(self) -> bytes:
        return json.dumps(
            {"sequence": self.sequence, "session_date": self.session_date,
             "commit_sha256": self.commit_sha256, "anchor_sha256": self.anchor_sha256},
            sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class SignedReceipt:
    """A signature over a `WitnessedTip`, plus the identity of the key that produced it."""
    signature_b64: str
    public_key_id: str
    witness_identity: str

    def to_dict(self) -> dict:
        return {"signature_b64": self.signature_b64, "public_key_id": self.public_key_id,
                "witness_identity": self.witness_identity}

    @classmethod
    def from_dict(cls, d: dict) -> SignedReceipt:
        return cls(signature_b64=str(d["signature_b64"]), public_key_id=str(d["public_key_id"]),
                   witness_identity=str(d["witness_identity"]))


def public_key_id(public_bytes: bytes) -> str:
    """A stable fingerprint of a public verifying key."""
    return hashlib.sha256(public_bytes).hexdigest()[:16]


@runtime_checkable
class AnchorSigner(Protocol):
    """Signs a chain tip across a trust boundary the observation-store writer cannot reach. The runner
    holds a reference to this (a client), never the private key."""

    def attest(self, tip: WitnessedTip) -> SignedReceipt: ...

    def identity(self) -> str: ...


class AnchorVerifier:
    """Verifies tip signatures using ONLY the public key — safe to hold locally. A mismatch between the
    receipt's `public_key_id` and this verifier's key, or a bad signature, fails closed."""

    def __init__(self, public_bytes: bytes) -> None:
        self._public = Ed25519PublicKey.from_public_bytes(public_bytes)
        self._public_bytes = public_bytes
        self.public_key_id = public_key_id(public_bytes)

    def verify(self, tip: WitnessedTip, receipt: SignedReceipt) -> None:
        if receipt.public_key_id != self.public_key_id:
            raise WitnessError(
                f"the receipt was signed by key {receipt.public_key_id!r}, not the trusted witness key "
                f"{self.public_key_id!r}", code="ANCHOR_SIGNATURE_INVALID")
        try:
            self._public.verify(base64.b64decode(receipt.signature_b64), tip.signing_bytes())
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise WitnessError(
                f"the witness signature for tip {tip.sequence} does not verify — the tip was altered "
                f"after it was signed", code="ANCHOR_SIGNATURE_INVALID") from exc


class Ed25519AnchorSigner:
    """Reference `AnchorSigner`: an Ed25519 keypair. In production this object lives in the separate
    signing service and only its `attest` is reachable; the runner is given the public key (via
    `verifier()`) and a client, never these private-key bytes."""

    def __init__(self, private_key: Ed25519PrivateKey, *, witness_identity: str) -> None:
        self._private = private_key
        self._witness_identity = witness_identity
        self._public_bytes = private_key.public_key().public_bytes_raw()
        self.public_key_id = public_key_id(self._public_bytes)

    @classmethod
    def generate(cls, *, witness_identity: str) -> Ed25519AnchorSigner:
        return cls(Ed25519PrivateKey.generate(), witness_identity=witness_identity)

    def attest(self, tip: WitnessedTip) -> SignedReceipt:
        signature = self._private.sign(tip.signing_bytes())
        return SignedReceipt(signature_b64=base64.b64encode(signature).decode("ascii"),
                             public_key_id=self.public_key_id, witness_identity=self._witness_identity)

    def identity(self) -> str:
        return f"{self._witness_identity}@{self.public_key_id}"

    def public_bytes(self) -> bytes:
        return self._public_bytes

    def verifier(self) -> AnchorVerifier:
        """The public-key-only verifier the runner holds (the private key stays here)."""
        return AnchorVerifier(self._public_bytes)


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
    never-rewrite property; a second publish of the same sequence fails closed."""

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
