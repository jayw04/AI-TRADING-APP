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

  8. **The verifying key is read from a file the deployment controls** (R5e-2). The path must be a real
     regular file — not a symlink, and not reached through one — owned by this process's user or root,
     and neither it nor its directory group- or world-writable. Without this, (6) is circular in a
     second way: an attacker who can swap the key file installs one whose private half they hold, and
     the challenge then verifies perfectly against it.

Issuance is token-guarded (R5e-2): the gate is not merely the sanctioned way to obtain the witness
triple, it is the only ordinary way — `ProductionWitness` refuses to be constructed without a private
sentinel that only this module holds. See its docstring for the precise claim.

## What this gate does NOT claim

Stated precisely, because a governance control that is believed to do more than it does is worse than
none. From inside the process, key custody is not decidable:

  * The attribute walk in (5) catches a signer that HOLDS a private-key object — the naive wrapper, and
    the reference signer under a different class name. It cannot prove the process has no path to a key
    at all: a key parked in a module-level registry, captured in a closure, or loaded lazily on first
    `attest` would pass. Making that evasion the only way through is the point; it is not a proof.
  * The challenge in (6) proves the configured signer CAN sign for the trusted key. It does not prove
    that only the signer can — if the same key is also reachable locally, both facts hold at once.
  * (7) is the sink's own report. A sink implementation that lies about its storage — fabricating all
    four identities consistently — is not detected here; what is detected is a sink that cannot answer,
    answers "not enforced", answers from configuration, or answers about storage OTHER than the one it
    publishes through. That last one is a wiring error rather than an attack, and it is the failure this
    gate most realistically prevents.
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
import os
import stat
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
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

    Two fields are load-bearing.

    `source` — `STORAGE` means the sink asked the storage and this is its answer (an Object-Lock
    configuration read, a WORM retention query); `DECLARED` means someone wrote it in a configuration
    file. Only the former is accepted.

    `storage_identity` — the canonical identity of the storage that was ASKED, derived from the query
    response rather than copied from configuration. Without it the attestation floats free of the object
    it describes: an adapter that queries an immutable bucket A while publishing to a mutable bucket B
    satisfies every other field here, and the record's truncation resistance quietly rests on B. It must
    equal the identity the sink publishes and reads through — see `_assert_sink_is_immutable`.
    """

    enforced: bool
    mode: str                  # e.g. "COMPLIANCE", "GOVERNANCE", "WORM"
    scope: str                 # what the lock covers — bucket/prefix/volume
    source: str                # ATTESTATION_FROM_STORAGE | ATTESTATION_DECLARED
    checked_at: str            # ISO8601 UTC — when the storage was asked
    storage_identity: str = ""  # the canonical identity of the storage that answered
    detail: str = ""

    def to_open_provenance(self) -> dict[str, Any]:
        return {"enforced": self.enforced, "mode": self.mode, "scope": self.scope,
                "source": self.source, "checked_at": self.checked_at,
                "storage_identity": self.storage_identity, "detail": self.detail}


@runtime_checkable
class ImmutableAnchorSink(Protocol):
    """An `ExternalAnchorSink` that can evidence its own write-once enforcement AND bind that evidence to
    the storage it actually writes through. Production sinks must implement both; a sink that cannot
    answer either question is refused rather than assumed.

    `publication_storage_identity` must be derived from the client `publish`/`read_all` use — not from
    configuration — so that a mis-wired adapter cannot attest one bucket and publish to another.
    """

    def immutability_attestation(self) -> ImmutabilityAttestation: ...

    def publication_storage_identity(self) -> str: ...


# The issuance token. `ProductionWitness` refuses to exist without it, and only `enforce_production_
# witness` holds it — so the carrier a `SessionRuntime` accepts cannot be assembled by ordinary
# construction. See `ProductionWitness` for what this does and does not establish.
_ISSUANCE_TOKEN = object()


@dataclass(frozen=True)
class ProductionWitness:
    """The enforced witness triple, plus the evidence that produced it. The runner receives exactly these
    objects; there is no path that reaches it with an unenforced signer or sink.

    ## Why this cannot simply be constructed

    R5e-1 made `enforce_production_witness` the sanctioned way to obtain the triple, but a plain frozen
    dataclass is constructible by anyone: `ProductionWitness(signer=Ed25519AnchorSigner(...), ...)` would
    have produced a carrier the runner accepts, wired to exactly the reference implementations the gate
    exists to exclude — and it would have looked deliberate in review. So issuance is token-guarded: the
    constructor refuses unless handed a module-private sentinel that only the gate holds.

    This makes the enforced path the ONLY ordinary way to obtain a witness. A caller who wants to bypass
    it must import a private name (`_ISSUANCE_TOKEN`) — which is visible in review and cannot happen by
    accident, by refactor, or by a future `run-session` variant wiring the triple itself.

    **Stated honestly, as with the rest of this gate:** this prevents the ordinary bypass and the wiring
    error. It is not a defence against an actor already executing arbitrary code in this process — such
    an actor can import the private token, rebind module attributes, or construct the object through
    `object.__new__`. In-process integrity is not decidable from inside the process; what is achieved
    here is that no honest path reaches the runner unenforced.
    """

    signer: AnchorSigner
    verifier: AnchorVerifier
    sink: ExternalAnchorSink
    evidence: dict[str, Any]
    # Positioned last with a default so the field never appears in evidence, comparisons or reprs; it
    # carries no information beyond "the gate issued this".
    issued_by: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.issued_by is not _ISSUANCE_TOKEN:
            raise WitnessEnforcementError(
                "a ProductionWitness may only be issued by enforce_production_witness(); constructing "
                "the triple directly would hand the runner a signer and sink that no gate has checked, "
                "which is precisely the wiring this control exists to exclude",
                code="WITNESS_NOT_ENFORCED")


# ── the fresh invocation identifier ──────────────────────────────────────────────────────────────────

def new_invocation_identifier() -> str:
    """A canonical UTC identifier, unique to this invocation, used as the signer challenge nonce.

    The challenge is only meaningful if it is FRESH. A nonce derived from the wall clock alone repeats
    whenever two invocations land in the same second — and a repeated nonce means a signature captured
    from an earlier challenge satisfies a later one, so a signer that has lost access to the trusted key
    (a revoked KMS grant, a rotated credential, a substituted endpoint replaying a recorded response)
    would still appear to hold it. The random component makes the probe unrepeatable in practice.

    Format: `YYYYMMDDTHHMMSSZ-<32 hex>` — sorts chronologically, carries the invocation time for
    evidence, and is unambiguous about being UTC. Freshness is a SEPARATE property from the
    `sequence = 0` / non-date-session probe construction, which is what stops a challenge signature from
    ever being replayed as a real tip; this stops it being replayed as another CHALLENGE.
    """
    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{now}-{uuid.uuid4().hex}"


# ── the deployment-installed verifying key ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class KeyPathEvidence:
    """What was established about the file the verifying key was read from."""

    path: str
    resolved_path: str
    ownership_and_mode_enforced: bool     # False where the platform has no POSIX ownership semantics
    owner_uid: int | None = None
    mode: str | None = None
    detail: str = ""

    def to_open_provenance(self) -> dict[str, Any]:
        return {"path": self.path, "resolved_path": self.resolved_path,
                "ownership_and_mode_enforced": self.ownership_and_mode_enforced,
                "owner_uid": self.owner_uid, "mode": self.mode, "detail": self.detail}


def verify_key_path(public_key_path: Path) -> KeyPathEvidence:
    """Establish that the verifying key is read from a file the deployment controls.

    The whole trust argument rests on `witness.public_key_path` holding the key the DEPLOYMENT installed.
    That argument is only as strong as the file: if the path is a symlink, whoever controls the link
    chooses which key is read; if the file or its directory is group- or world-writable, whoever holds
    that access can replace the key with one whose private half they hold, and a substituted signer then
    passes the challenge in `_challenge_signer` perfectly. Either way the gate would report a verified
    trust boundary while verifying against an attacker's key — a false attestation, which is worse than
    no attestation.

    Refused: a symlink (at the final component or anywhere above it), a non-regular file, a file not
    owned by this process's user or root, and group- or world-writable permissions on the file or on the
    directory holding it (a writable directory permits replacement regardless of the file's own mode).

    ⚠ Ownership and mode are POSIX properties. On platforms without them — Windows, where `st_uid` is
    always 0 and `st_mode` carries no group/other bits — those checks CANNOT be performed and are
    reported as unenforced rather than silently passed. The symlink and regular-file checks still apply.
    A production deployment is POSIX; a Windows run is a development convenience, and its evidence says
    so rather than claiming a check it did not make.
    """
    raw = Path(public_key_path)
    try:
        link_status = raw.lstat()
    except OSError as exc:
        raise WitnessEnforcementError(
            f"the deployment-installed verifying key at {raw} is unreadable: {exc}; the signer's own "
            f"key is not an acceptable substitute", code="WITNESS_PUBLIC_KEY_UNAVAILABLE") from exc

    if stat.S_ISLNK(link_status.st_mode):
        raise WitnessEnforcementError(
            f"the verifying key path {raw} is a symbolic link; whoever can re-point the link chooses "
            f"which key the signer is challenged against, so the key must be a real file installed by "
            f"the deployment", code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED")

    resolved = raw.resolve()
    if resolved != raw.absolute():
        raise WitnessEnforcementError(
            f"the verifying key path {raw} resolves to {resolved} through a symbolic link in one of its "
            f"parent directories; the path the deployment governs must be the path that is read",
            code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED")
    if not stat.S_ISREG(link_status.st_mode):
        raise WitnessEnforcementError(
            f"the verifying key path {raw} is not a regular file",
            code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED")

    if not hasattr(os, "geteuid"):                # Windows and any non-POSIX platform
        return KeyPathEvidence(
            path=str(raw), resolved_path=str(resolved), ownership_and_mode_enforced=False,
            detail="not a POSIX platform: ownership and permission checks were NOT performed; the "
                   "symlink and regular-file checks were")

    euid = os.geteuid()
    if link_status.st_uid not in (euid, 0):
        raise WitnessEnforcementError(
            f"the verifying key at {raw} is owned by uid {link_status.st_uid}, neither this process's "
            f"user ({euid}) nor root; a key another account can rewrite is not a deployment-installed "
            f"key", code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED")

    _assert_not_writable_by_others(raw, link_status.st_mode, what="verifying key")
    parent = raw.parent
    try:
        parent_status = parent.stat()
    except OSError as exc:
        raise WitnessEnforcementError(
            f"the directory holding the verifying key ({parent}) cannot be examined: {exc}",
            code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED") from exc
    if parent_status.st_uid not in (euid, 0):
        raise WitnessEnforcementError(
            f"the directory holding the verifying key ({parent}) is owned by uid {parent_status.st_uid}, "
            f"neither this process's user ({euid}) nor root; its owner can replace the key file",
            code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED")
    _assert_not_writable_by_others(parent, parent_status.st_mode, what="directory holding the key")

    return KeyPathEvidence(
        path=str(raw), resolved_path=str(resolved), ownership_and_mode_enforced=True,
        owner_uid=link_status.st_uid, mode=oct(stat.S_IMODE(link_status.st_mode)),
        detail="regular file, not a symlink, owned by this user or root, not group- or world-writable, "
               "in a directory with the same properties")


def _assert_not_writable_by_others(path: Path, mode: int, *, what: str) -> None:
    """Refuse group- or world-writable key material. Read access is not the concern — a PUBLIC key is
    meant to be readable; write access is, because it permits substitution."""
    offending = stat.S_IMODE(mode) & (stat.S_IWGRP | stat.S_IWOTH)
    if offending:
        raise WitnessEnforcementError(
            f"the {what} at {path} has mode {oct(stat.S_IMODE(mode))}, which is "
            f"{'group' if offending & stat.S_IWGRP else 'world'}-writable; anyone with that access can "
            f"substitute the key the signer is challenged against",
            code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED")


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


def _assert_sink_is_immutable(sink: Any, *, configured_identity: str) -> ImmutabilityAttestation:
    """Require the sink to evidence write-once enforcement from the storage itself, AND to bind that
    evidence to the storage it publishes through."""
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

    _assert_attestation_binds_the_publication_storage(
        sink, attestation, configured_identity=configured_identity)
    return attestation


def _assert_attestation_binds_the_publication_storage(
        sink: Any, attestation: ImmutabilityAttestation, *, configured_identity: str) -> None:
    """Require one storage identity across the declaration, the object, the lock query and the writer.

    An attestation that is not bound to the publication path proves nothing about where tips land. The
    ordinary way this goes wrong is not malice but wiring: an adapter that reads its Object-Lock
    configuration from one bucket and publishes to another — a copy-paste in a deployment manifest, a
    prefix that drifted, a client constructed twice from different settings — reports `enforced=True`
    from storage while the record accumulates in a bucket anyone can truncate.

    So all four must be exactly equal:

        the identity the deployment DECLARED   (witness.sink.identity)
        the identity the object REPORTS        (ExternalAnchorSink.identity)
        the identity the LOCK QUERY answered   (ImmutabilityAttestation.storage_identity)
        the identity the WRITER uses           (publication_storage_identity)

    This cannot detect an implementation that fabricates all four — that is the stated "a sink can lie"
    limit. It does structurally exclude the mis-wired adapter, which is an ordinary configuration error
    rather than an attack, and which no other check in this gate would catch.
    """
    attested = str(attestation.storage_identity or "").strip()
    if not attested:
        raise WitnessEnforcementError(
            "witness.sink attested write-once enforcement without naming WHICH storage answered; an "
            "attestation that is not bound to the publication path proves nothing about where tips land",
            code="WITNESS_SINK_STORAGE_MISBOUND")

    publisher = getattr(sink, "publication_storage_identity", None)
    if not callable(publisher):
        raise WitnessEnforcementError(
            f"witness.sink {type(sink).__name__} cannot report the storage its publish/read path uses, "
            f"so its immutability attestation cannot be bound to where tips are actually written",
            code="WITNESS_SINK_STORAGE_MISBOUND")
    try:
        publication_identity = str(publisher() or "").strip()
    except Exception as exc:                      # noqa: BLE001 - unreachable writer is a refusal
        raise WitnessEnforcementError(
            f"witness.sink could not report its publication storage: {type(exc).__name__}: {exc}",
            code="WITNESS_SINK_STORAGE_MISBOUND") from exc

    reported = _safe_identity(sink).strip()
    declared = str(configured_identity or "").strip()
    identities = {"declared": declared, "reported": reported,
                  "attested": attested, "publication": publication_identity}
    if len(set(identities.values())) != 1:
        raise WitnessEnforcementError(
            f"witness.sink storage identities disagree: {identities}; the storage whose write-once "
            f"enforcement was verified must be exactly the storage the sink publishes and reads through",
            code="WITNESS_SINK_STORAGE_MISBOUND")


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
    # nothing to challenge the signer against and no reason to reach out to it at all. The PATH is
    # established before the bytes are read — a key read from a symlink or a world-writable file would
    # make the challenge attest to whatever an attacker installed.
    key_evidence = verify_key_path(config.public_key_path)
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
    attestation = _assert_sink_is_immutable(sink, configured_identity=config.sink.identity)

    return ProductionWitness(
        signer=signer, verifier=verifier, sink=sink,
        issued_by=_ISSUANCE_TOKEN,
        evidence={
            "profile": config.profile.value,
            "invocation": nonce,
            "verifying_key_path": key_evidence.to_open_provenance(),
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
    "KeyPathEvidence",
    "ProductionWitness",
    "WitnessEnforcementError",
    "enforce_production_witness",
    "load_trusted_verifier",
    "new_invocation_identifier",
    "verify_key_path",
]
