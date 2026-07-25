"""Governed WITNESS configuration — how the deployment declares its anchor trust boundary (R5e).

R5d built the independent chain-tip witness: a signer whose private key the observation-store writer does
not hold, and an external append-only sink with separately governed write authority. It shipped two
REFERENCE implementations — `Ed25519AnchorSigner` (an in-process keypair) and `FileExternalAnchorSink` (a
directory of no-overwrite files) — which make the interfaces testable but provide neither property in
production: an in-process key IS held by the writer, and a directory the writer can reach is not
separately governed.

This module is where the deployment declares what it actually uses. Two things matter about the shape:

  * **The declaration lives in the governed configuration, not in caller arguments.** An operator who
    could pass `--anchor-sink /tmp/mine` on the command line could witness the record against storage
    they control, and the anchor would faithfully attest to it. The witness block is read from the same
    deployment-owned file as every other binding (`forward_deployment_config`).
  * **The verifying key is configured SEPARATELY from the signer.** In R5d's reference wiring the
    verifier is obtained from the signer (`Ed25519AnchorSigner.verifier()`), which is circular — a
    substituted signer supplies the very key its signatures are checked against, and every forged
    signature verifies. In production the public key is installed by the deployment at
    `public_key_path`, and `witness_enforcement` challenges the signer to prove it can sign for THAT
    key. A signer that cannot is refused.

What this module does NOT do is decide whether the declaration is acceptable — it parses, validates
shape, and refuses private key material. The production gate is `witness_enforcement`.

Nothing here touches Account 4 or imports the order path.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.validation.forward_window import IntegrityStop

# The module holding R5d's reference implementations. A production factory may never resolve into it.
REFERENCE_WITNESS_MODULE = "app.validation.chain_witness"

_FACTORY_RE = re.compile(r"^[A-Za-z_][\w.]*:[A-Za-z_]\w*$")

# Key NAMES that carry signing material. A reference to externally-held credentials is fine — a KMS key
# ARN, an IAM role, a Secrets Manager ARN, a profile name — because naming where a secret lives is not
# the same as handing the runner the secret. Naming the material itself is refused.
_PRIVATE_KEY_NAME_RE = re.compile(
    r"(private|passphrase|password|seed|secret[_-]?(key|access[_-]?key)|key[_-]?material)", re.I)

# Field names that ARE the material rather than a pointer to it, matched exactly (case-insensitively) so
# that `secret_arn` and `credentials_profile` — which name where custody lives — stay configurable.
# The short ones are JWK/COSE private components: `d` (EC/OKP private scalar), `p`/`q`/`dp`/`dq`/`qi`
# (RSA primes and CRT parameters), `k` (symmetric octet key).
_SECRET_EXACT_NAMES = frozenset({
    "secret", "secrets", "access_key", "accesskey", "credential", "credentials",
    "private_bytes", "privatebytes", "signing_key", "signingkey", "key_bytes", "keybytes",
    "d", "p", "q", "dp", "dq", "qi", "k",
})

# PEM/OpenSSH private-key headers, in any of the encodings that appear in real configuration files.
# `BEGIN OPENSSH PRIVATE KEY`, `BEGIN RSA PRIVATE KEY` and `BEGIN PRIVATE KEY` all match.
_PRIVATE_PEM_RE = re.compile(r"-{2,}\s*BEGIN[ \w]*PRIVATE KEY", re.I)

# Raw key material carried as text. Ed25519/AES-256 seeds are 32 bytes, P-384 48, Ed448/SHA-512 64 —
# the lengths a signing key realistically takes.
_KEY_MATERIAL_LENGTHS = (32, 48, 64)
_HEX_KEY_RE = re.compile(r"[0-9a-fA-F]+")
_BASE64_CANDIDATE_RE = re.compile(r"[A-Za-z0-9+/_-]{40,512}={0,2}")

# The one narrow escape: content-addressed identifiers are 64 hex characters and are legitimately
# configurable (an image digest, an artifact checksum). Matched on the FIELD NAME's final token, so a
# digest must be named as one. This closes accidental placement, not a deployer determined to hide a key
# in a field called `x_digest` — which the module's stated limits already cover.
_DIGEST_NAME_RE = re.compile(r"(^|[_-])(sha256|sha512|digest|fingerprint|checksum|etag)$", re.I)


class WitnessConfigError(IntegrityStop):
    """The deployment's witness declaration is absent, malformed, or carries signing material the runner
    must never hold. Fails closed."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class WitnessProfile(StrEnum):
    """What the deployment claims its witness is.

    PRODUCTION — a separately controlled signer and an immutable external sink, subject to every check in
    `witness_enforcement`. REFERENCE — R5d's in-process signer and filesystem sink: usable for
    development and tests, and REFUSED by the production gate. The profile exists so a misconfigured
    deployment gets a precise refusal naming what it declared, rather than an opaque type error deep in
    the enforcement path.
    """

    PRODUCTION = "PRODUCTION"
    REFERENCE = "REFERENCE"


@dataclass(frozen=True)
class WitnessComponentConfig:
    """One witness component (the signer or the sink) as the deployment declares it.

    `factory` is a `module:callable` the DEPLOYMENT installs — the production adapters (a signing-service
    client, an Object-Lock sink) live outside this repository so that adding one does not add an external
    dependency to the order-path image. `options` is passed to the factory verbatim and is scanned for
    key material before anything is imported.
    """

    factory: str
    identity: str
    options: dict[str, Any] = field(default_factory=dict)

    def to_open_provenance(self) -> dict[str, Any]:
        # `options` is deliberately summarised by key, not value: the enforcement evidence is published
        # into the readiness report, and a value that merely LOOKS harmless today should not be copied
        # into an operator-visible artifact.
        return {"factory": self.factory, "identity": self.identity,
                "option_keys": sorted(str(k) for k in self.options)}


@dataclass(frozen=True)
class WitnessConfig:
    """The deployment's complete anchor trust-boundary declaration."""

    profile: WitnessProfile
    signer: WitnessComponentConfig
    sink: WitnessComponentConfig
    public_key_path: Path        # the DEPLOYMENT-installed verifying key — never obtained from the signer
    # The boundary the key-path walk starts from (R5e-2). Every component from here down to the key is
    # verified for ownership, mode and symlink freedom. Optional: when absent the walk starts at the
    # filesystem root, which is correct but stricter than some deployments need — OS-managed ancestors
    # are root-owned and pass, yet naming the root the deployment actually governs states the intent and
    # avoids depending on assumptions about ancestors it does not control.
    trusted_root: Path | None = None

    def to_open_provenance(self) -> dict[str, Any]:
        return {"profile": self.profile.value, "signer": self.signer.to_open_provenance(),
                "sink": self.sink.to_open_provenance(), "public_key_path": str(self.public_key_path),
                "trusted_root": str(self.trusted_root) if self.trusted_root else None}


def _decoded_key_material(text: str, *, digest_named: bool) -> str | None:
    """Describe `text` if it is raw key material carried as a string, else None.

    Name-based detection alone is not a control: a 32-byte Ed25519 seed base64-encoded under
    `credential_blob` carries exactly as much signing power as one under `private_key`. This closes the
    concrete encodings — hex and base64 of the lengths a signing key actually takes — so that hiding one
    requires deliberately disguising it rather than merely not calling it a key.
    """
    compact = "".join(text.split())
    if not compact:
        return None

    if _HEX_KEY_RE.fullmatch(compact) and len(compact) // 2 in _KEY_MATERIAL_LENGTHS \
            and len(compact) % 2 == 0:
        if digest_named and len(compact) in (64, 128):
            return None                           # a content address, named as one
        return f"{len(compact) // 2} bytes of hex-encoded key material"

    if _BASE64_CANDIDATE_RE.fullmatch(compact):
        for decoder in (base64.b64decode, base64.urlsafe_b64decode):
            try:
                raw = decoder(compact + "=" * (-len(compact) % 4))
            except (binascii.Error, ValueError):
                continue
            if len(raw) in _KEY_MATERIAL_LENGTHS:
                return f"{len(raw)} bytes of base64-encoded key material"
    return None


def _int_array_key_material(values: Any) -> str | None:
    """Describe `values` if it is a byte array of a private-key length — the JSON form a key takes when
    it is serialised as a list of octets rather than a string."""
    items = list(values)
    if len(items) not in _KEY_MATERIAL_LENGTHS:
        return None
    if all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255 for v in items):
        return f"a {len(items)}-byte array of key material"
    return None


def assert_no_private_key_material(payload: Any, *, where: str = "witness") -> None:
    """Refuse a configuration that hands the runner signing material.

    The whole point of the separate signer is that this process CANNOT produce a signature on its own. A
    private key reachable through the governed configuration defeats that completely, however carefully
    the rest of the wiring is done, so the check runs before any factory is imported.

    The scan is by NAME and by VALUE, because either alone is trivially avoided:

      * by name — fields that are the material (`private_key`, `passphrase`, `signing_key`, the JWK
        private components `d`/`p`/`q`/`dp`/`dq`/`qi`/`k`) rather than a pointer to where custody lives
        (`key_arn`, `role_arn`, `secret_arn`, `credentials_profile`, which stay configurable);
      * by value — PEM and OpenSSH private-key headers, hex or base64 decoding to 32/48/64 bytes, and
        integer arrays of those lengths, WHEREVER they appear, including under an innocuous field name.

    It is not a general secret detector and does not claim to be: a key split across two fields, or
    compressed, or named `x_digest`, passes. It closes the forms a key actually takes in a configuration
    file, which is what makes "the configuration carries no signing material" a checked property rather
    than a stated intention.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            name = str(key)
            if _PRIVATE_KEY_NAME_RE.search(name) or name.strip().lower() in _SECRET_EXACT_NAMES:
                raise WitnessConfigError(
                    f"{where}.{name} names private signing material; the runner must never hold a key it "
                    f"can sign with — configure a reference to the separately controlled signer instead",
                    code="WITNESS_PRIVATE_KEY_IN_CONFIG")
            assert_no_private_key_material(value, where=f"{where}.{name}")
    elif isinstance(payload, (list, tuple)):
        found = _int_array_key_material(payload)
        if found:
            raise WitnessConfigError(
                f"{where} is {found}; the runner must never hold a key it can sign with",
                code="WITNESS_PRIVATE_KEY_IN_CONFIG")
        for index, value in enumerate(payload):
            assert_no_private_key_material(value, where=f"{where}[{index}]")
    elif isinstance(payload, str):
        if _PRIVATE_PEM_RE.search(payload):
            raise WitnessConfigError(
                f"{where} contains an inline PEM private key; the runner must never hold a key it can "
                f"sign with", code="WITNESS_PRIVATE_KEY_IN_CONFIG")
        # The field's own name decides whether 64 hex characters are a content address or a key.
        leaf = where.rsplit(".", 1)[-1].split("[", 1)[0]
        found = _decoded_key_material(payload, digest_named=bool(_DIGEST_NAME_RE.search(leaf)))
        if found:
            raise WitnessConfigError(
                f"{where} carries {found} under an innocuous name; the runner must never hold a key it "
                f"can sign with — configure a reference to the separately controlled signer instead",
                code="WITNESS_PRIVATE_KEY_IN_CONFIG")


def _component(payload: Any, *, name: str) -> WitnessComponentConfig:
    if not isinstance(payload, dict):
        raise WitnessConfigError(f"witness.{name} must be an object describing the {name}",
                                 code="WITNESS_CONFIG_INCOMPLETE")
    factory = str(payload.get("factory") or "").strip()
    identity = str(payload.get("identity") or "").strip()
    if not factory or not identity:
        raise WitnessConfigError(
            f"witness.{name} must declare both `factory` and `identity`; an unnamed {name} cannot be "
            f"attributed in the record", code="WITNESS_CONFIG_INCOMPLETE")
    if not _FACTORY_RE.match(factory):
        raise WitnessConfigError(
            f"witness.{name}.factory {factory!r} is not a `module:callable` reference",
            code="WITNESS_CONFIG_INCOMPLETE")
    options = payload.get("options") or {}
    if not isinstance(options, dict):
        raise WitnessConfigError(f"witness.{name}.options must be an object",
                                 code="WITNESS_CONFIG_INCOMPLETE")
    return WitnessComponentConfig(factory=factory, identity=identity, options=dict(options))


def load_witness_config(payload: Any) -> WitnessConfig:
    """Parse and validate the `witness` block of the governed configuration.

    Shape and key material only. Whether the declaration is ACCEPTABLE FOR PRODUCTION — a non-reference
    signer that can sign for the deployment-installed key, a sink that proves its own immutability — is
    `witness_enforcement.enforce_production_witness`.
    """
    if payload in (None, ""):
        raise WitnessConfigError(
            "the configuration declares no `witness` block; a deployment that cannot independently "
            "witness its chain tips cannot run a governed session",
            code="WITNESS_CONFIG_INCOMPLETE")
    if not isinstance(payload, dict):
        raise WitnessConfigError("the `witness` block must be an object",
                                 code="WITNESS_CONFIG_INCOMPLETE")

    # BEFORE anything else, and before any factory module is imported.
    assert_no_private_key_material(payload)

    raw_profile = str(payload.get("profile") or "").strip()
    try:
        profile = WitnessProfile(raw_profile)
    except ValueError as exc:
        known = ", ".join(p.value for p in WitnessProfile)
        raise WitnessConfigError(
            f"unknown witness.profile {raw_profile!r}; expected one of {known}",
            code="WITNESS_CONFIG_INCOMPLETE") from exc

    public_key_path = str(payload.get("public_key_path") or "").strip()
    if not public_key_path:
        raise WitnessConfigError(
            "witness.public_key_path is required; the verifying key must be installed by the deployment "
            "rather than obtained from the signer, or a substituted signer would supply the very key its "
            "signatures are checked against", code="WITNESS_CONFIG_INCOMPLETE")

    trusted_root = str(payload.get("trusted_root") or "").strip()
    if trusted_root and not Path(trusted_root).is_absolute():
        raise WitnessConfigError(
            f"witness.trusted_root {trusted_root!r} must be absolute; a relative root would depend on "
            f"the working directory of whoever launched the run",
            code="WITNESS_CONFIG_INCOMPLETE")

    return WitnessConfig(
        profile=profile,
        signer=_component(payload.get("signer"), name="signer"),
        sink=_component(payload.get("sink"), name="sink"),
        public_key_path=Path(public_key_path),
        trusted_root=Path(trusted_root) if trusted_root else None,
    )


__all__ = [
    "REFERENCE_WITNESS_MODULE",
    "WitnessComponentConfig",
    "WitnessConfig",
    "WitnessConfigError",
    "WitnessProfile",
    "assert_no_private_key_material",
    "load_witness_config",
]
