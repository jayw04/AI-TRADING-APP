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

# PEM private-key headers, in any of the encodings that appear in real configuration files.
_PRIVATE_PEM_RE = re.compile(r"-{2,}\s*BEGIN[ \w]*PRIVATE KEY", re.I)


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

    def to_open_provenance(self) -> dict[str, Any]:
        return {"profile": self.profile.value, "signer": self.signer.to_open_provenance(),
                "sink": self.sink.to_open_provenance(), "public_key_path": str(self.public_key_path)}


def assert_no_private_key_material(payload: Any, *, where: str = "witness") -> None:
    """Refuse a configuration that hands the runner signing material.

    The whole point of the separate signer is that this process CANNOT produce a signature on its own. A
    private key reachable through the governed configuration defeats that completely, however carefully
    the rest of the wiring is done, so the check runs before any factory is imported.

    Walks the structure by key name and by value: a PEM private-key header is refused wherever it
    appears, including under an innocuous key name.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            name = str(key)
            if _PRIVATE_KEY_NAME_RE.search(name):
                raise WitnessConfigError(
                    f"{where}.{name} names private signing material; the runner must never hold a key it "
                    f"can sign with — configure a reference to the separately controlled signer instead",
                    code="WITNESS_PRIVATE_KEY_IN_CONFIG")
            assert_no_private_key_material(value, where=f"{where}.{name}")
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            assert_no_private_key_material(value, where=f"{where}[{index}]")
    elif isinstance(payload, str) and _PRIVATE_PEM_RE.search(payload):
        raise WitnessConfigError(
            f"{where} contains an inline PEM private key; the runner must never hold a key it can sign "
            f"with", code="WITNESS_PRIVATE_KEY_IN_CONFIG")


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

    return WitnessConfig(
        profile=profile,
        signer=_component(payload.get("signer"), name="signer"),
        sink=_component(payload.get("sink"), name="sink"),
        public_key_path=Path(public_key_path),
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
