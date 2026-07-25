"""PRODUCTION witness enforcement — the gate that makes the R5d trust boundary real (R5e).

R5d proved the record can be anchored across a separate trust boundary. It could not prove the boundary
EXISTS: the runner accepts anything satisfying the `AnchorSigner` / `ExternalAnchorSink` protocols, and
the reference implementations satisfy them while providing neither property. `Ed25519AnchorSigner` holds
its private key in the runner's own process, so the store-writer can forge any signature it likes;
`FileExternalAnchorSink` writes to a directory the store-writer can reach, so the same actor who
truncates the local anchor log can truncate the "external" witness alongside it. A run wired that way is
tamper-evident against nothing, and — worse — produces a record that LOOKS witnessed.

This module refuses that wiring. `enforce_production_witness` is the only sanctioned way to obtain the
witness triple for a governed run, and it fails closed unless every property below holds.

## What is actually checked, and why each one is checkable

  1. **The profile is PRODUCTION.** A deployment that declares REFERENCE gets a precise refusal naming
     what it declared, rather than tripping over a later check.
  2. **No signing material is reachable through the configuration** (`witness_config`, re-asserted here).
  3. **Neither factory resolves into the reference module.** A production factory that imports out of
     `app.validation.chain_witness` is, by construction, one of the implementations this gate exists to
     exclude — so the reference module is refused by name before it is imported.
  4. **Neither object is a reference implementation**, by explicit class marker and by identity against
     the known classes. The marker catches reference implementations added later, which an `isinstance`
     list would silently miss.
  5. **The signer holds no in-process private key.** Its instance attributes are walked for private-key
     objects: an adapter that "wraps" a local keypair rather than calling out to a separate service is
     structurally indistinguishable from the reference signer and is refused as such.
  6. **The signer can sign for the DEPLOYMENT-INSTALLED verifying key.** The public key is read from
     `witness.public_key_path`, never from the signer, and the signer is challenged to attest a probe tip
     that the trusted verifier must accept. This is what closes R5d's circularity: a substituted signer
     can present any identity it likes, but it cannot produce a signature that verifies under a key it
     does not hold. The probe carries `sequence = 0` and a non-date session field, so the resulting
     signature can never be replayed as a real tip (`verify_anchor_consistency` numbers tips from 1).
  7. **The sink proves its own immutability, from the storage.** A sink must report an
     `ImmutabilityAttestation` it obtained by QUERYING the storage (`source = STORAGE`); a configured
     assertion (`source = DECLARED`) is refused. "The deployment says the bucket has Object Lock" is not
     evidence that it does, and the entire truncation-resistance argument rests on it.

## What this gate does NOT claim

Stated precisely, because a governance control that is believed to do more than it does is worse than
none. From inside the process, key custody is not decidable:

  * The attribute walk in (5) catches a signer that HOLDS a private-key object — the naive wrapper, and
    the reference signer under a different class name. It cannot prove the process has no path to a key
    at all: a key parked in a module-level registry, captured in a closure, or loaded lazily on first
    `attest` would pass. Making that evasion the only way through is the point; it is not a proof.
  * The challenge in (6) proves the configured signer CAN sign for the trusted key. It does not prove
    that only the signer can — if the same key is also reachable locally, both facts hold at once.
  * (7) is the sink's own report. A sink implementation that lies about its storage is not detected here;
    what is detected is a sink that cannot answer, answers "not enforced", or answers from configuration.
  * Whether the signing service's key and the sink's credentials are beyond the reach of whoever operates
    this host is a deployment fact. A sufficiently privileged operator controls both.

What the gate does establish: the governed configuration carries no signing material, the runner verifies
against a key it did not obtain from the signer, the declared signer demonstrably holds that key, the
storage reports write-once enforcement to a query rather than an assertion, and neither reference
implementation can reach a governed session. The remainder is custody, and custody is attested by the
deployment — not by this module.

Nothing here touches Account 4 or imports the order path.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.validation.chain_witness import (
    AnchorSigner,
    AnchorVerifier,
    ExternalAnchorSink,
    WitnessedTip,
)
from app.validation.forward_window import IntegrityStop
from app.validation.witness_config import (
    REFERENCE_WITNESS_MODULE,
    WitnessComponentConfig,
    WitnessConfig,
    WitnessProfile,
    assert_no_private_key_material,
)

# The probe tip the signer is challenged with. `sequence = 0` is outside the committed numbering (real
# tips start at 1) and the session field is not a date, so a challenge signature can never be presented
# as a witness for a real observation.
CHALLENGE_SEQUENCE = 0
CHALLENGE_SESSION = "witness-key-challenge"

# Attestation sources. Only a value obtained by querying the storage is evidence.
ATTESTATION_FROM_STORAGE = "STORAGE"
ATTESTATION_DECLARED = "DECLARED"


class WitnessEnforcementError(IntegrityStop):
    """The declared witness does not provide the separation the record depends on. Fails closed."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ImmutabilityAttestation:
    """What a sink reports about the write-once enforcement of its underlying storage.

    `source` is the load-bearing field. `STORAGE` means the sink asked the storage and this is its
    answer (an Object-Lock configuration read, a WORM retention query); `DECLARED` means someone wrote it
    in a configuration file. Only the former is accepted.
    """

    enforced: bool
    mode: str                  # e.g. "COMPLIANCE", "GOVERNANCE", "WORM"
    scope: str                 # what the lock covers — bucket/prefix/volume
    source: str                # ATTESTATION_FROM_STORAGE | ATTESTATION_DECLARED
    checked_at: str            # ISO8601 UTC — when the storage was asked
    detail: str = ""

    def to_open_provenance(self) -> dict[str, Any]:
        return {"enforced": self.enforced, "mode": self.mode, "scope": self.scope,
                "source": self.source, "checked_at": self.checked_at, "detail": self.detail}


@runtime_checkable
class ImmutableAnchorSink(Protocol):
    """An `ExternalAnchorSink` that can evidence its own write-once enforcement. Production sinks must
    implement this; a sink that cannot answer the question is refused rather than assumed."""

    def immutability_attestation(self) -> ImmutabilityAttestation: ...


@dataclass(frozen=True)
class ProductionWitness:
    """The enforced witness triple, plus the evidence that produced it. The runner receives exactly these
    objects; there is no path that reaches it with an unenforced signer or sink."""

    signer: AnchorSigner
    verifier: AnchorVerifier
    sink: ExternalAnchorSink
    evidence: dict[str, Any]


# ── the deployment-installed verifying key ───────────────────────────────────────────────────────────

def load_trusted_verifier(public_key_path: Path) -> AnchorVerifier:
    """Build the verifier from the key the DEPLOYMENT installed — never from the signer.

    Accepts the three encodings a deployment realistically installs: 32 raw bytes, 64 hex characters, or
    base64. A key of the wrong length is refused rather than truncated into something that would verify
    nothing.
    """
    try:
        blob = Path(public_key_path).read_bytes()
    except OSError as exc:
        raise WitnessEnforcementError(
            f"the deployment-installed verifying key at {public_key_path} is unreadable: {exc}; the "
            f"signer's own key is not an acceptable substitute",
            code="WITNESS_PUBLIC_KEY_UNAVAILABLE") from exc

    public_bytes = _decode_public_key(blob)
    if len(public_bytes) != 32:
        raise WitnessEnforcementError(
            f"the verifying key at {public_key_path} is {len(public_bytes)} bytes; an Ed25519 public key "
            f"is 32", code="WITNESS_PUBLIC_KEY_UNAVAILABLE")
    try:
        return AnchorVerifier(public_bytes)
    except Exception as exc:                      # noqa: BLE001 - any decode failure is a refusal
        raise WitnessEnforcementError(
            f"the verifying key at {public_key_path} is not a valid Ed25519 public key: {exc}",
            code="WITNESS_PUBLIC_KEY_UNAVAILABLE") from exc


def _decode_public_key(blob: bytes) -> bytes:
    if len(blob) == 32:
        return blob                               # raw, exactly — checked before any stripping
    # A raw key written by a tool that appends a newline. Checked before the text encodings because a
    # 32-byte key is never valid hex (64 chars) or base64 (44 chars) of an Ed25519 key.
    stripped = blob.strip(b"\r\n\t ")
    if len(stripped) == 32:
        return stripped
    text = blob.decode("utf-8", errors="ignore").strip()
    if len(text) == 64:
        try:
            return bytes.fromhex(text)
        except ValueError:
            pass
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return blob


# ── factory resolution ───────────────────────────────────────────────────────────────────────────────

def _resolve_factory(component: WitnessComponentConfig, *, name: str) -> Any:
    """Import and call the deployment's factory. The reference module is refused BEFORE it is imported."""
    module_name, _, attr = component.factory.partition(":")
    if module_name == REFERENCE_WITNESS_MODULE or module_name.startswith(
            REFERENCE_WITNESS_MODULE + "."):
        raise WitnessEnforcementError(
            f"witness.{name}.factory resolves into {REFERENCE_WITNESS_MODULE}, which holds the reference "
            f"implementations; production requires a separately controlled {name}",
            code=_refusal_code(name))
    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, attr)
    except (ImportError, AttributeError) as exc:
        raise WitnessEnforcementError(
            f"witness.{name}.factory {component.factory!r} could not be resolved: {exc}",
            code=_refusal_code(name)) from exc

    assert_no_private_key_material(component.options, where=f"witness.{name}.options")
    try:
        return factory(**component.options)
    except WitnessEnforcementError:
        raise
    except Exception as exc:                      # noqa: BLE001 - a factory that cannot build is a refusal
        raise WitnessEnforcementError(
            f"witness.{name}.factory {component.factory!r} failed to construct the {name}: "
            f"{type(exc).__name__}: {exc}", code=_refusal_code(name)) from exc


def _refusal_code(name: str) -> str:
    return ("WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED" if name == "signer"
            else "WITNESS_SINK_NOT_IMMUTABLE")


# ── the individual properties ────────────────────────────────────────────────────────────────────────

def _assert_not_reference(obj: Any, *, name: str, reference_types: tuple[type, ...]) -> None:
    """Refuse R5d's reference implementations, by declared marker and by type.

    The marker is checked first and is the general rule: any implementation that declares itself
    reference-only is refused, including ones added after this gate was written. The type check is the
    backstop for a marker that is removed or shadowed.
    """
    if bool(getattr(type(obj), "IS_REFERENCE_IMPLEMENTATION", False)) or isinstance(
            obj, reference_types):
        raise WitnessEnforcementError(
            f"witness.{name} resolved to {type(obj).__name__}, a reference implementation: it provides "
            f"the interface but not the separation — production requires a "
            f"{'separately controlled signer' if name == 'signer' else 'genuinely immutable sink'}",
            code=_refusal_code(name))


def _assert_no_in_process_private_key(signer: Any) -> None:
    """Refuse a signer that holds a private key in this process.

    An adapter wrapping a local keypair is structurally the reference signer with a different class name:
    the store-writer can sign anything, so the signature proves nothing about who authorised the tip. The
    check walks the signer's own attributes (and one level of container nesting, which is where a wrapped
    key actually hides) for private-key objects.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_types: tuple[type, ...] = (Ed25519PrivateKey,)
    try:
        from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

        private_types = (Ed25519PrivateKey, RSAPrivateKey, EllipticCurvePrivateKey)
    except ImportError:                           # pragma: no cover - cryptography always ships these
        pass

    def offending(value: Any, depth: int = 0) -> str | None:
        if isinstance(value, private_types):
            return type(value).__name__
        if depth >= 1:
            return None
        if isinstance(value, dict):
            values: Any = value.values()
        elif isinstance(value, (list, tuple, set, frozenset)):
            values = value
        else:
            return None
        for item in values:
            found = offending(item, depth + 1)
            if found:
                return found
        return None

    # `getattr(..., "__dict__", {})` rather than `vars()`: a `__slots__` signer has no instance dict and
    # must not crash the gate — it simply exposes no attributes to walk.
    for attr, value in dict(getattr(signer, "__dict__", {}) or {}).items():
        found = offending(value)
        if found:
            raise WitnessEnforcementError(
                f"witness.signer holds a {found} in this process (attribute {attr!r}); a signer the "
                f"observation-store writer can sign with is not a separate trust boundary",
                code="WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED")


def _challenge_signer(signer: AnchorSigner, verifier: AnchorVerifier, *, nonce: str) -> dict[str, Any]:
    """Prove the signer can sign for the deployment-installed key.

    Without this, `witness.public_key_path` is decoration: a substituted signer would present its own
    identity, its signatures would fail only later — at the first `verify_anchor_consistency`, AFTER a
    session had been evaluated — and the failure would look like corruption rather than substitution.
    Challenging up front turns it into a refusal before anything runs.
    """
    digest = hashlib.sha256(f"{CHALLENGE_SESSION}|{nonce}".encode()).hexdigest()
    probe = WitnessedTip(sequence=CHALLENGE_SEQUENCE, session_date=CHALLENGE_SESSION,
                         commit_sha256=digest,
                         anchor_sha256=hashlib.sha256(digest.encode()).hexdigest())
    try:
        receipt = signer.attest(probe)
    except Exception as exc:                      # noqa: BLE001 - unreachable signer is a refusal
        raise WitnessEnforcementError(
            f"the separately controlled signer could not be reached to prove it holds the "
            f"deployment-installed key: {type(exc).__name__}: {exc}",
            code="WITNESS_SIGNER_KEY_UNTRUSTED") from exc

    try:
        verifier.verify(probe, receipt)
    except Exception as exc:                      # noqa: BLE001 - any verification failure is a refusal
        raise WitnessEnforcementError(
            f"the signer's attestation does not verify under the deployment-installed key "
            f"{verifier.public_key_id!r}; the configured signer does not hold the trusted key: {exc}",
            code="WITNESS_SIGNER_KEY_UNTRUSTED") from exc

    return {"challenged": True, "public_key_id": verifier.public_key_id,
            "receipt_public_key_id": receipt.public_key_id, "nonce": nonce}


def _assert_sink_is_immutable(sink: Any) -> ImmutabilityAttestation:
    """Require the sink to evidence write-once enforcement, from the storage itself."""
    # Checked by callability rather than `isinstance(sink, ImmutableAnchorSink)`: a runtime_checkable
    # Protocol passes on an attribute that merely EXISTS, so a sink with the name bound to None — or to
    # anything uncallable — would satisfy the isinstance and fail at the call. `ImmutableAnchorSink`
    # remains the declared contract a deployment's sink implements against.
    attest = getattr(sink, "immutability_attestation", None)
    if not callable(attest):
        raise WitnessEnforcementError(
            f"witness.sink {type(sink).__name__} cannot attest its own immutability; a sink whose "
            f"write-once enforcement is unknown cannot carry the record's truncation resistance",
            code="WITNESS_SINK_IMMUTABILITY_UNPROVEN")
    try:
        attestation = attest()
    except Exception as exc:                      # noqa: BLE001 - unreachable storage is a refusal
        raise WitnessEnforcementError(
            f"witness.sink could not be asked whether its storage enforces write-once: "
            f"{type(exc).__name__}: {exc}", code="WITNESS_SINK_IMMUTABILITY_UNPROVEN") from exc

    if not isinstance(attestation, ImmutabilityAttestation):
        raise WitnessEnforcementError(
            f"witness.sink returned {type(attestation).__name__} rather than an ImmutabilityAttestation",
            code="WITNESS_SINK_IMMUTABILITY_UNPROVEN")
    if not attestation.enforced:
        raise WitnessEnforcementError(
            f"witness.sink reports that its storage does NOT enforce write-once "
            f"(mode={attestation.mode!r}, scope={attestation.scope!r}); a sink the store-writer can "
            f"rewrite or truncate is not an independent witness",
            code="WITNESS_SINK_NOT_IMMUTABLE")
    if attestation.source != ATTESTATION_FROM_STORAGE:
        raise WitnessEnforcementError(
            f"witness.sink's immutability is {attestation.source!r}, not queried from the storage; a "
            f"configured assertion that the storage is write-once is not evidence that it is",
            code="WITNESS_SINK_IMMUTABILITY_UNPROVEN")
    if not str(attestation.mode).strip() or not str(attestation.scope).strip():
        raise WitnessEnforcementError(
            "witness.sink attested write-once enforcement without naming the mode and scope it covers",
            code="WITNESS_SINK_IMMUTABILITY_UNPROVEN")
    return attestation


# ── the gate ─────────────────────────────────────────────────────────────────────────────────────────

def enforce_production_witness(config: WitnessConfig, *, nonce: str) -> ProductionWitness:
    """Resolve and enforce the deployment's witness. The ONLY sanctioned source of a governed run's
    witness triple.

    `nonce` is caller-supplied (the run timestamp) so the challenge is deterministic under test and
    distinct per invocation in production.
    """
    if config.profile is not WitnessProfile.PRODUCTION:
        raise WitnessEnforcementError(
            f"the deployment declares witness.profile={config.profile.value}; the reference signer and "
            f"filesystem sink are development implementations and can never witness a governed session",
            code="WITNESS_PROFILE_NOT_PRODUCTION")

    from app.validation.chain_witness import Ed25519AnchorSigner, FileExternalAnchorSink

    # The trusted key FIRST: if the deployment cannot produce the verifying key it installed, there is
    # nothing to challenge the signer against and no reason to reach out to it at all.
    verifier = load_trusted_verifier(config.public_key_path)

    signer = _resolve_factory(config.signer, name="signer")
    _assert_not_reference(signer, name="signer", reference_types=(Ed25519AnchorSigner,))
    if not isinstance(signer, AnchorSigner):
        raise WitnessEnforcementError(
            f"witness.signer {type(signer).__name__} does not satisfy the AnchorSigner interface",
            code="WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED")
    _assert_no_in_process_private_key(signer)
    challenge = _challenge_signer(signer, verifier, nonce=nonce)

    sink = _resolve_factory(config.sink, name="sink")
    _assert_not_reference(sink, name="sink", reference_types=(FileExternalAnchorSink,))
    if not isinstance(sink, ExternalAnchorSink):
        raise WitnessEnforcementError(
            f"witness.sink {type(sink).__name__} does not satisfy the ExternalAnchorSink interface",
            code="WITNESS_SINK_NOT_IMMUTABLE")
    attestation = _assert_sink_is_immutable(sink)

    return ProductionWitness(
        signer=signer, verifier=verifier, sink=sink,
        evidence={
            "profile": config.profile.value,
            "signer": {**config.signer.to_open_provenance(),
                       "resolved_type": type(signer).__name__,
                       "reported_identity": _safe_identity(signer),
                       "key_challenge": challenge},
            "sink": {**config.sink.to_open_provenance(),
                     "resolved_type": type(sink).__name__,
                     "reported_identity": _safe_identity(sink),
                     "immutability": attestation.to_open_provenance()},
            "verifying_key": {"public_key_id": verifier.public_key_id,
                              "source_path": str(config.public_key_path),
                              "obtained_from_signer": False},
        })


def _safe_identity(obj: Any) -> str:
    try:
        return str(obj.identity())
    except Exception as exc:                      # noqa: BLE001 - evidence, never a failure path
        return f"<identity unavailable: {type(exc).__name__}: {exc}>"


__all__ = [
    "ATTESTATION_DECLARED",
    "ATTESTATION_FROM_STORAGE",
    "CHALLENGE_SEQUENCE",
    "CHALLENGE_SESSION",
    "ImmutabilityAttestation",
    "ImmutableAnchorSink",
    "ProductionWitness",
    "WitnessEnforcementError",
    "enforce_production_witness",
    "load_trusted_verifier",
]
