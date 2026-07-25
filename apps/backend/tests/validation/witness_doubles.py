"""Production-SHAPED witness doubles for the R5e enforcement tests.

These exist because the gate must be exercised against something it accepts — otherwise the tests only
prove it refuses, and a gate that refuses everything is indistinguishable from a broken one.

They are doubles, not production adapters. `_RemoteSignerDouble` models a signing-service client: the
object the runner holds carries only a handle, and the key material lives in this module's registry
standing in for the separate service. That is enough to satisfy the gate's attribute walk and to answer
the key challenge, and it is exactly the evasion the enforcement docstring names as undetectable from
inside the process — stated here so nobody mistakes "the double passes" for "the check is airtight".

Real production adapters (a signing-service client, an Object-Lock sink) are installed by the deployment
and live outside this repository, so that adding one does not add an external dependency to the image.
"""

from __future__ import annotations

import base64
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.validation.chain_witness import SignedReceipt, WitnessedTip, public_key_id
from app.validation.witness_enforcement import (
    ATTESTATION_DECLARED,
    ATTESTATION_FROM_STORAGE,
    ImmutabilityAttestation,
)

# The "separate signing service": key material lives here, never on the object the runner holds.
_SERVICE_KEYS: dict[str, Ed25519PrivateKey] = {}


def provision_service_key(handle: str) -> bytes:
    """Create a key inside the stand-in service and return ONLY its public bytes — what a deployment
    installs at `witness.public_key_path`."""
    key = Ed25519PrivateKey.generate()
    _SERVICE_KEYS[handle] = key
    return key.public_key().public_bytes_raw()


def public_bytes_for(handle: str) -> bytes:
    return _SERVICE_KEYS[handle].public_key().public_bytes_raw()


class _RemoteSignerDouble:
    """An `AnchorSigner` that calls out to the stand-in service. Holds a handle, not a key."""

    def __init__(self, handle: str, endpoint: str) -> None:
        self.handle = handle                      # a string; the attribute walk finds no key object
        self.endpoint = endpoint

    def attest(self, tip: WitnessedTip) -> SignedReceipt:
        key = _SERVICE_KEYS[self.handle]
        signature = key.sign(tip.signing_bytes())
        return SignedReceipt(
            signature_b64=base64.b64encode(signature).decode("ascii"),
            public_key_id=public_key_id(key.public_key().public_bytes_raw()),
            witness_identity=self.endpoint)

    def identity(self) -> str:
        return f"remote-signer://{self.endpoint}#{self.handle}"


class _UnreachableSignerDouble(_RemoteSignerDouble):
    """A configured signer whose service cannot be reached."""

    def attest(self, tip: WitnessedTip) -> SignedReceipt:
        raise ConnectionError("signing service unreachable")


class _WrapperSignerDouble:
    """The shape the gate must refuse: a differently-named class that keeps the key in this process."""

    def __init__(self) -> None:
        self._key = Ed25519PrivateKey.generate()

    def attest(self, tip: WitnessedTip) -> SignedReceipt:      # pragma: no cover - refused first
        signature = self._key.sign(tip.signing_bytes())
        return SignedReceipt(signature_b64=base64.b64encode(signature).decode("ascii"),
                             public_key_id=public_key_id(self._key.public_key().public_bytes_raw()),
                             witness_identity="wrapper")

    def identity(self) -> str:
        return "wrapper-signer"


class _NestedWrapperSignerDouble(_WrapperSignerDouble):
    """The same evasion one container deep — a key hidden in a dict of "clients"."""

    def __init__(self) -> None:
        self.clients = {"primary": Ed25519PrivateKey.generate()}


class _ObjectLockSinkDouble:
    """An `ExternalAnchorSink` that reports write-once enforcement queried from its storage."""

    def __init__(self, *, scope: str, mode: str = "COMPLIANCE",
                 source: str = ATTESTATION_FROM_STORAGE, enforced: bool = True) -> None:
        self._scope = scope
        self._mode = mode
        self._source = source
        self._enforced = enforced
        self.records: list[tuple[WitnessedTip, SignedReceipt]] = []

    def publish(self, tip: WitnessedTip, receipt: SignedReceipt) -> None:
        self.records.append((tip, receipt))

    def read_all(self) -> list[tuple[WitnessedTip, SignedReceipt]]:
        return sorted(self.records, key=lambda r: r[0].sequence)

    def identity(self) -> str:
        return f"object-lock://{self._scope}"

    def immutability_attestation(self) -> ImmutabilityAttestation:
        return ImmutabilityAttestation(
            enforced=self._enforced, mode=self._mode, scope=self._scope, source=self._source,
            checked_at="2026-07-25T00:00:00Z", detail="GetObjectLockConfiguration")


class _SilentSinkDouble(_ObjectLockSinkDouble):
    """A sink that cannot answer the immutability question at all."""

    immutability_attestation = None               # type: ignore[assignment]


class _UnreachableSinkDouble(_ObjectLockSinkDouble):
    """A sink whose storage cannot be queried."""

    def immutability_attestation(self) -> ImmutabilityAttestation:
        raise TimeoutError("object-lock configuration query timed out")


# ── factories the governed configuration names ───────────────────────────────────────────────────────

def build_signer(*, handle: str = "svc-1", endpoint: str = "signer.internal") -> Any:
    return _RemoteSignerDouble(handle, endpoint)


def build_unreachable_signer(**kwargs: Any) -> Any:
    return _UnreachableSignerDouble(kwargs.get("handle", "svc-1"), kwargs.get("endpoint", "down"))


def build_wrapper_signer(**_: Any) -> Any:
    return _WrapperSignerDouble()


def build_nested_wrapper_signer(**_: Any) -> Any:
    return _NestedWrapperSignerDouble()


def build_reference_signer(**_: Any) -> Any:
    """A factory OUTSIDE the reference module that hands back the reference implementation — the
    module-name check alone would miss this, so the marker must catch it."""
    from app.validation.chain_witness import Ed25519AnchorSigner

    return Ed25519AnchorSigner.generate(witness_identity="smuggled")


def build_not_a_signer(**_: Any) -> Any:
    return object()


def build_exploding_signer(**_: Any) -> Any:
    raise RuntimeError("the signing client could not be constructed")


def build_sink(*, scope: str = "s3://anchors/prod", mode: str = "COMPLIANCE") -> Any:
    return _ObjectLockSinkDouble(scope=scope, mode=mode)


def build_declared_sink(**_: Any) -> Any:
    return _ObjectLockSinkDouble(scope="s3://anchors/prod", source=ATTESTATION_DECLARED)


def build_unenforced_sink(**_: Any) -> Any:
    return _ObjectLockSinkDouble(scope="s3://anchors/prod", enforced=False)


def build_unscoped_sink(**_: Any) -> Any:
    return _ObjectLockSinkDouble(scope="   ", mode="   ")


def build_silent_sink(**_: Any) -> Any:
    return _SilentSinkDouble(scope="s3://anchors/prod")


def build_unreachable_sink(**_: Any) -> Any:
    return _UnreachableSinkDouble(scope="s3://anchors/prod")


def build_reference_sink(*, root: str = ".", **_: Any) -> Any:
    from pathlib import Path

    from app.validation.chain_witness import FileExternalAnchorSink

    return FileExternalAnchorSink(Path(root), identity="smuggled")


def build_wrong_attestation_sink(**_: Any) -> Any:
    class _Bad(_ObjectLockSinkDouble):
        def immutability_attestation(self):       # type: ignore[override]
            return {"enforced": True}             # not an ImmutabilityAttestation

    return _Bad(scope="s3://anchors/prod")
