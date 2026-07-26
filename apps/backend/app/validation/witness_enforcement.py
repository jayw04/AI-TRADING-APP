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
import contextlib
import hashlib
import importlib
import os
import stat
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
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
from app.validation.witness_protocol import (
    ALGORITHM_ECDSA_SHA256_P256,
    ALGORITHM_ED25519,
    WitnessProtocolError,
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


# The issuance sentinel. It is attached to a witness only by `enforce_production_witness`, only after
# every property has been established, and only via `object.__setattr__` — never as a constructor
# argument, because a constructor argument is exactly what `dataclasses.replace()` would carry forward.
# Checked by identity. See `ProductionWitness` for what this does and does not establish.
_ISSUANCE_SENTINEL = object()

# The attribute the sentinel is attached under. Named once so the enforcement path, the check and the
# structural tests cannot drift apart.
_ISSUANCE_ATTR = "_issuance_marker"


def _mark_enforced(witness: ProductionWitness) -> ProductionWitness:
    """Attach the issuance sentinel to an already-verified witness.

    Deliberately a post-construction mutation on a frozen value: it is the one operation that must NOT
    be reachable through `__init__`, since everything that rebuilds the value goes through there.
    """
    object.__setattr__(witness, _ISSUANCE_ATTR, _ISSUANCE_SENTINEL)
    return witness


def assert_enforced(witness: Any) -> None:
    """Refuse anything that is not a gate-issued `ProductionWitness`. The single check every consumer
    uses, so the carrier's contract has exactly one definition.

    `type(...) is` rather than `isinstance(...)`: subclassing is refused outright, and an exact-type
    check means a future subclass created by some mechanism this module did not anticipate still cannot
    satisfy it.
    """
    if type(witness) is not ProductionWitness:
        raise WitnessEnforcementError(
            f"the witness is {type(witness).__name__}, not an enforced ProductionWitness; a governed "
            f"session's chain tips must be witnessed across the boundary enforce_production_witness() "
            f"checks", code="WITNESS_NOT_ENFORCED")
    if not witness._is_enforced():
        raise WitnessEnforcementError(
            "this ProductionWitness was not issued by enforce_production_witness() — it was constructed "
            "directly, rebuilt with dataclasses.replace(), or otherwise reconstructed, so its signer and "
            "sink have never been checked by any gate",
            code="WITNESS_NOT_ENFORCED")


@dataclass(frozen=True)
class ProductionWitness:
    """The enforced witness triple, plus the evidence that produced it. The runner receives exactly these
    objects; there is no ordinary path that reaches it with an unenforced signer or sink.

    ## Why the marker is not a field

    R5e-2's first attempt made the issuance token a dataclass FIELD checked in `__post_init__`. That was
    wrong, and the review caught it: because the token was an init field, `dataclasses.replace()` carried
    it forward automatically, so

        replace(witness, signer=some_reference_signer)

    produced a genuine, fully "enforced" `ProductionWitness` wired to a signer no gate had ever seen —
    using one idiomatic call, no private import, and a function this codebase already applies to
    `SessionRuntime`. A subclass overriding `__post_init__` got the same result just as cheaply.

    So the marker is NOT a field and NOT set by the constructor. It is attached by
    `enforce_production_witness` AFTER the value is built, via `object.__setattr__`, and it is the
    module-private sentinel checked BY IDENTITY. Every ordinary route that rebuilds or re-runs `__init__`
    — `replace()`, a subclass, a hand construction — yields an object without the marker and is refused.
    Subclassing is additionally refused outright.

    ## What survives, exactly

    The security contract distinguishes *an unchanged copy of a genuinely issued receipt* from *a
    modified or forged one*. Copying an issued witness unchanged is not an escalation; producing one the
    gate never issued is. Pinned by tests:

      * `dataclasses.replace(...)`, with or without changed fields — REFUSED (rebuilds via `__init__`)
      * subclass construction — REFUSED (`__init_subclass__`)
      * ordinary `ProductionWitness(...)` — REFUSED (no marker)
      * `copy.copy` — SURVIVES: a shallow copy carries the same sentinel object, and is an unchanged
        copy of a receipt the gate did issue
      * `copy.deepcopy` — REFUSED: deepcopy rebuilds the sentinel, so identity no longer holds
      * `pickle` round-trip — REFUSED: unpickling reconstructs the sentinel as a new object

    The last two fail CLOSED for the right reason (identity, not value) and are tested as such.

    **Stated honestly, as with the rest of this gate:** this closes the ordinary construction paths. It
    is not a defence against an actor already executing arbitrary code in this process, who can import
    the sentinel, rebind module attributes, or call `object.__setattr__` directly. In-process integrity
    is not decidable from inside the process; what is achieved is that no honest path reaches the runner
    unenforced.
    """

    signer: AnchorSigner
    verifier: AnchorVerifier
    sink: ExternalAnchorSink
    evidence: Mapping[str, Any]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        # A subclass could override __post_init__ or _is_enforced and hand the runner anything, while
        # still satisfying an isinstance check. There is no legitimate reason to specialise the carrier.
        raise TypeError(
            "ProductionWitness cannot be subclassed; a subclass could satisfy every structural check "
            "while carrying a signer and sink no gate has seen")

    def _is_enforced(self) -> bool:
        """True only for a value `enforce_production_witness` itself marked.

        Checked by IDENTITY against the module-private sentinel: an attacker-supplied attribute of the
        same name, or a value that merely compares equal, does not satisfy it.
        """
        return getattr(self, "_issuance_marker", None) is _ISSUANCE_SENTINEL


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
    """What was established about the file the verifying key was read from, component by component."""

    path: str
    trusted_root: str
    ownership_and_mode_enforced: bool     # False where the platform has no POSIX ownership semantics
    components_verified: tuple[str, ...] = ()
    owner_uid: int | None = None
    mode: str | None = None
    device: int | None = None
    inode: int | None = None
    read_from_verified_descriptor: bool = False
    detail: str = ""

    def to_open_provenance(self) -> dict[str, Any]:
        return {"path": self.path, "trusted_root": self.trusted_root,
                "ownership_and_mode_enforced": self.ownership_and_mode_enforced,
                "components_verified": list(self.components_verified),
                "owner_uid": self.owner_uid, "mode": self.mode,
                "device": self.device, "inode": self.inode,
                "read_from_verified_descriptor": self.read_from_verified_descriptor,
                "detail": self.detail}


@dataclass(frozen=True)
class VerifiedPublicKey:
    """Key bytes read from the very object that was validated, with the evidence of that validation."""

    raw: bytes
    evidence: KeyPathEvidence


# POSIX-only names, resolved through `getattr` so this module imports and type-checks identically on
# every platform. A `# type: ignore` would be wrong here in both directions: `warn_unused_ignores` makes
# it an ERROR on Linux, where the attributes genuinely exist. `_can_enforce_path_guarantees` is the one
# place that decides whether they are usable.
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_geteuid = getattr(os, "geteuid", None)


def _can_enforce_path_guarantees() -> bool:
    """Whether this platform can establish the POSIX guarantees the key path depends on.

    Needs ownership semantics, ``O_NOFOLLOW``, and ``dir_fd``-relative opens. Windows has none of them:
    ``st_uid`` is always 0, ``st_mode`` carries no group/other bits, and there is no way to pin a
    directory handle across the walk.
    """
    return (_geteuid is not None and _O_NOFOLLOW != 0
            and os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd
            # `os.stat(..., follow_symlinks=False)` is what makes each component's check a check of the
            # LINK rather than its target; without it the walk would silently follow what it must refuse.
            and os.stat in os.supports_follow_symlinks)


def _assert_component_is_safe(st: os.stat_result, *, what: str, euid: int,
                              require_dir: bool) -> None:
    """Every traversed component must be a real directory (or the final regular file), owned by root or
    this service, and not writable by anyone else.

    Ownership matters as much as mode: the owner of a directory can replace what is inside it whatever
    the permission bits say, so a component owned by a third party is as good as world-writable.
    """
    if stat.S_ISLNK(st.st_mode):
        raise WitnessEnforcementError(
            f"{what} is a symbolic link; whoever can re-point it chooses which key the signer is "
            f"challenged against", code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED")
    if require_dir and not stat.S_ISDIR(st.st_mode):
        raise WitnessEnforcementError(
            f"{what} is not a directory", code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED")
    if not require_dir and not stat.S_ISREG(st.st_mode):
        raise WitnessEnforcementError(
            f"{what} is not a regular file", code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED")
    if st.st_uid not in (0, euid):
        raise WitnessEnforcementError(
            f"{what} is owned by uid {st.st_uid}, neither root nor this service ({euid}); its owner can "
            f"replace the key the signer is challenged against",
            code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED")
    offending = stat.S_IMODE(st.st_mode) & (stat.S_IWGRP | stat.S_IWOTH)
    if offending:
        raise WitnessEnforcementError(
            f"{what} has mode {oct(stat.S_IMODE(st.st_mode))}, which is "
            f"{'group' if offending & stat.S_IWGRP else 'world'}-writable; anyone with that access can "
            f"substitute the key", code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED")


def verify_and_read_public_key(public_key_path: Path, *,
                               trusted_root: Path | None = None) -> VerifiedPublicKey:
    """Validate the path from a trusted root and read the key FROM THE SAME OBJECT that was validated.

    The deployment-installed verifying key is the root that breaks R5d's circularity: the signer is
    challenged against a key it did not supply. That argument is only as strong as this file, and an
    earlier version of this module weakened it in two ways the review named.

    **Partial ancestry.** Checking the file and its immediate parent is not enough. A world-writable
    grandparent lets an attacker replace the whole parent directory, key and all, without ever touching
    a checked object. So every component from ``trusted_root`` down to the key is verified: no symlinks
    anywhere, parents are real directories, the final component is a regular file, and each is owned by
    root or this service and not group- or world-writable.

    **Check-then-reopen.** Validating a pathname and then handing the same pathname to a separate reader
    is a time-of-check/time-of-use race: between the two syscalls the name can be pointed somewhere
    else, and the bytes that get read are not the bytes that were checked. So the walk keeps a directory
    descriptor at each step, opens the final component ``O_NOFOLLOW`` relative to the validated parent
    descriptor, ``fstat``s the descriptor, confirms it is the same (device, inode) that was validated,
    and reads the key from THAT descriptor. The caller receives bytes, never a path to reopen.

    Fails closed off POSIX. Windows cannot establish any of this. Rather than reporting an unenforced
    check and continuing, this raises: ``enforce_production_witness`` only ever runs for a PRODUCTION
    profile, and a production witness whose key path cannot be validated is not a production witness.
    Development and reference flows that want the weaker statement call
    ``describe_unenforceable_key_path`` and say so explicitly in their evidence.
    """
    raw = Path(public_key_path)
    if not raw.is_absolute():
        raise WitnessEnforcementError(
            f"the verifying key path {raw} is relative; a governed key location must be absolute so it "
            f"cannot depend on the working directory of whoever launched the run",
            code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED")
    if not _can_enforce_path_guarantees():
        raise WitnessEnforcementError(
            f"this platform cannot establish ownership, symlink and no-follow guarantees for the "
            f"verifying key at {raw}, so a production witness cannot be authorized here; POSIX is "
            f"required for a governed run", code="WITNESS_PUBLIC_KEY_PATH_UNENFORCEABLE")

    root = Path(trusted_root) if trusted_root is not None else Path(raw.anchor)
    try:
        relative = raw.relative_to(root)
    except ValueError as exc:
        raise WitnessEnforcementError(
            f"the verifying key at {raw} lies outside the trusted root {root}; the deployment must "
            f"install its key within the root it governs",
            code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED") from exc

    parts = relative.parts
    if not parts:
        raise WitnessEnforcementError(
            f"the verifying key path {raw} IS the trusted root; it must name a file within it",
            code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED")

    if _geteuid is None:                          # pragma: no cover - guarded by the check above
        raise WitnessEnforcementError(
            "ownership cannot be determined on this platform",
            code="WITNESS_PUBLIC_KEY_PATH_UNENFORCEABLE")
    euid = _geteuid()
    verified: list[str] = []
    try:
        root_st = os.lstat(root)
    except OSError as exc:
        raise WitnessEnforcementError(
            f"the trusted root {root} cannot be examined: {exc}",
            code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED") from exc
    _assert_component_is_safe(root_st, what=f"the trusted root {root}", euid=euid, require_dir=True)
    verified.append(str(root))

    fd = os.open(root, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW)
    key_fd: int | None = None
    try:
        for name in parts[:-1]:
            st = os.stat(name, dir_fd=fd, follow_symlinks=False)
            _assert_component_is_safe(st, what=f"the path component {name!r} under {root}", euid=euid,
                                      require_dir=True)
            nxt = os.open(name, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
            verified.append(name)

        final = parts[-1]
        st = os.stat(final, dir_fd=fd, follow_symlinks=False)
        _assert_component_is_safe(st, what=f"the verifying key {final!r} under {root}", euid=euid,
                                  require_dir=False)

        # Opened relative to the validated parent descriptor, refusing to follow a link that may have
        # been swapped in since the stat above.
        key_fd = os.open(final, os.O_RDONLY | _O_NOFOLLOW, dir_fd=fd)
        fst = os.fstat(key_fd)
        if (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino):
            raise WitnessEnforcementError(
                f"the verifying key at {raw} was replaced between validation and open (device/inode "
                f"changed); the bytes that would be read are not the bytes that were checked",
                code="WITNESS_PUBLIC_KEY_PATH_UNTRUSTED")
        _assert_component_is_safe(fst, what=f"the opened verifying key {raw}", euid=euid,
                                  require_dir=False)

        chunks: list[bytes] = []
        while True:
            chunk = os.read(key_fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        verified.append(final)
    except OSError as exc:
        raise WitnessEnforcementError(
            f"the deployment-installed verifying key at {raw} is unreadable: {exc}; the signer's own "
            f"key is not an acceptable substitute", code="WITNESS_PUBLIC_KEY_UNAVAILABLE") from exc
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)
        if key_fd is not None:
            with contextlib.suppress(OSError):
                os.close(key_fd)

    evidence = KeyPathEvidence(
        path=str(raw), trusted_root=str(root), ownership_and_mode_enforced=True,
        components_verified=tuple(verified), owner_uid=fst.st_uid,
        mode=oct(stat.S_IMODE(fst.st_mode)), device=fst.st_dev, inode=fst.st_ino,
        read_from_verified_descriptor=True,
        detail="every component from the trusted root verified: no symlinks, real directories, regular "
               "final file, owned by root or this service, none group- or world-writable; key read from "
               "the same descriptor that was validated")
    return VerifiedPublicKey(raw=b"".join(chunks), evidence=evidence)


def describe_unenforceable_key_path(public_key_path: Path) -> KeyPathEvidence:
    """The weaker statement, for development and reference flows only.

    Says plainly that the guarantees were NOT established. It is never used on the production path:
    ``verify_and_read_public_key`` raises there instead of returning this.
    """
    raw = Path(public_key_path)
    return KeyPathEvidence(
        path=str(raw), trusted_root="", ownership_and_mode_enforced=False,
        detail="this platform cannot establish ownership, symlink or no-follow guarantees; NO key-path "
               "check was performed and no production witness may rely on this")


def build_trusted_verifier(key_bytes: bytes, *, source: str, algorithm: str | None = None,
                           key_id: str | None = None) -> AnchorVerifier:
    """Build the verifier from bytes already read from a verified descriptor — never from a pathname,
    and never from anything the signer returned.

    Key material is interpreted according to the PINNED algorithm (ADR 0045):

      * `ECDSA_SHA_256_P256` — the installed bytes are DER SubjectPublicKeyInfo, exactly as
        `GetPublicKey` returns them, and are passed through UNCHANGED. Decoding them as text or
        trimming them would change the very bytes the fingerprint is computed over.
      * `ED25519` (reference) — 32 raw bytes, tolerating the encodings a deployment realistically
        installs: raw, 64 hex characters, or base64.

    A key of the wrong shape for the pinned algorithm is refused rather than coerced.
    """
    pinned = algorithm or ALGORITHM_ED25519
    if pinned == ALGORITHM_ECDSA_SHA256_P256:
        try:
            return AnchorVerifier(key_bytes, algorithm=pinned, key_id=key_id)
        except WitnessProtocolError as exc:
            raise WitnessEnforcementError(
                f"the verifying key at {source} is not usable for {pinned}: {exc}",
                code="WITNESS_PUBLIC_KEY_UNAVAILABLE") from exc

    public_bytes = _decode_public_key(key_bytes)
    if len(public_bytes) != 32:
        raise WitnessEnforcementError(
            f"the verifying key at {source} is {len(public_bytes)} bytes; an Ed25519 public key is 32",
            code="WITNESS_PUBLIC_KEY_UNAVAILABLE")
    try:
        return AnchorVerifier(public_bytes, algorithm=pinned, key_id=key_id)
    except Exception as exc:                      # noqa: BLE001 - any decode failure is a refusal
        raise WitnessEnforcementError(
            f"the verifying key at {source} is not a valid Ed25519 public key: {exc}",
            code="WITNESS_PUBLIC_KEY_UNAVAILABLE") from exc


def _decode_public_key(blob: bytes) -> bytes:
    """Decode an installed verifying key: raw 32 bytes, 64 hex characters, or base64.

    ## Raw keys are matched STRUCTURALLY, never by stripping

    An earlier version tolerated a trailing newline with `blob.strip(b"\\r\\n\\t ")`. `strip` removes
    ANY leading or trailing byte in that set, and a raw Ed25519 key is uniformly distributed binary —
    so whenever the key's own first or last byte happened to be `\\r`, `\\n`, `\\t` or space (4 of 256
    values), the strip ate real key material. The result was not 32 bytes, decoding fell through to the
    text paths, and a perfectly valid key was refused as "33 bytes".

    That is 1 - (252/256)^2 ~= 3.1% of keys, measured at 3.10% over 2000 generated keys, so it
    presented as a rare flake rather than a bug: it depended on which key you happened to generate.

    The terminator is therefore matched by exact shape. Space and tab are NOT accepted as terminators
    at all — they are perfectly valid key bytes and carry no reliable meaning as file endings — and
    `rstrip` is avoided for the same reason. Only an exact trailing LF or CRLF on an otherwise
    correctly-sized blob is recognised.

    A 33-byte blob ending in LF is inherently ambiguous at the byte level: it could be a 32-byte raw
    key followed by a terminator, or a 33-byte blob. Under this installation contract it is
    deterministically interpreted as a 32-byte raw key followed by an LF terminator. The decoder never
    makes that decision based on the VALUE of the key bytes themselves — which is precisely what the
    old `strip()` did, and why it corrupted roughly one key in 32.
    """
    if len(blob) == 32:
        return blob                               # raw, exactly
    # Exact-shape terminators only. Checked before the text encodings because a raw 32-byte key is
    # never valid hex (64 chars) or base64 (44 chars) of an Ed25519 key.
    if len(blob) == 33 and blob[-1:] == b"\n":
        return blob[:32]
    if len(blob) == 34 and blob[-2:] == b"\r\n":
        return blob[:32]
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
            f"{verifier.public_key_fingerprint!r}; the configured signer does not hold the trusted "
            f"key: {exc}",
            code="WITNESS_SIGNER_KEY_UNTRUSTED") from exc

    # Evidence records BOTH fingerprints so a reader can see the comparison that was made, not just
    # that one was. `verify_receipt` has already refused any disagreement — this is the record of it.
    return {"challenged": True,
            "trusted_public_key_fingerprint": verifier.public_key_fingerprint,
            "receipt_public_key_fingerprint": receipt.public_key_fingerprint,
            "receipt_algorithm": receipt.algorithm, "receipt_key_id": receipt.key_id,
            "protocol_version": receipt.protocol_version, "nonce": nonce}


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
    # nothing to challenge the signer against and no reason to reach out to it at all.
    #
    # Validation and read are ONE operation. Every component from the governed trusted root is checked,
    # and the bytes come from the same descriptor that was validated — a key read from a symlink, from
    # under a writable ancestor, or swapped between check and open would make the challenge attest to
    # whatever an attacker installed, which is worse than no attestation at all.
    verified_key = verify_and_read_public_key(config.public_key_path,
                                              trusted_root=config.trusted_root)
    key_evidence = verified_key.evidence
    # The verifier is constructed from the PINNED algorithm and key ARN (ADR 0045), never from anything
    # a signer returns. `load_witness_config` has already refused a PRODUCTION profile that does not
    # name both, so these are present by the time composition runs.
    verifier = build_trusted_verifier(verified_key.raw, source=str(config.public_key_path),
                                      algorithm=config.algorithm, key_id=config.key_id)

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

    # Marked only HERE, and only now — after every property above has been established.
    return _mark_enforced(ProductionWitness(
        signer=signer, verifier=verifier, sink=sink,
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
            "verifying_key": {"public_key_fingerprint": verifier.public_key_fingerprint,
                              "algorithm": verifier.pinned.algorithm,
                              "key_id": verifier.pinned.key_id,
                              "source_path": str(config.public_key_path),
                              "obtained_from_signer": False},
        }))


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
    "VerifiedPublicKey",
    "WitnessEnforcementError",
    "assert_enforced",
    "build_trusted_verifier",
    "describe_unenforceable_key_path",
    "enforce_production_witness",
    "new_invocation_identifier",
    "verify_and_read_public_key",
]
