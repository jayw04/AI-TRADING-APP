"""MR-002 Stage-3 — signed launch-attestation PRODUCER (launcher-side tooling).

Closes the OPEN_IN_LAUNCH_ATTESTATION class (execution package v1.9, findings 8-15:
observed command/mount + signed attestation production): this tool is run by the
LAUNCHER on the launch host, derives every bound hash by OBSERVING the actual artifact
bytes (never by trusting operator-supplied hashes), signs the canonical payload with an
Ed25519 key held outside the repository, and self-verifies its output against the frozen
loader `load_launch_attestation` before reporting success.

The canonical-payload rule is FROZEN by the loader (population runner, cycle-7 finding 4):
every field except {signature, canonical_signed_payload_sha256}, serialized
json.dumps(sort_keys=True, separators=(",", ":")) utf-8. This producer implements the
same rule; the frozen loader remains the authority.

Launch-command grammar (owner review 2026-07-18, blockers 2-5) — CLOSED, not best-effort.
`validate_launch_argv` is the single shared parser used by BOTH `produce` and `exec`; an
argv that fails it is refused BEFORE attestation production and AGAIN before execution,
even if its signature verifies. The only accepted shape is:

    docker run [--rm] --network=none [--name=<n>] [--workdir=<abs>|-w <abs>]
        (--mount type=bind,src=<abs>,dst=<abs>,(ro|readonly|ro=false) | --mount=<same-spec>)...
        (--env=KEY=VALUE | -e KEY=VALUE)...
        <image ID sha256:<64hex> equal to image_digest, or <name>@<that digest>>
        (python|python3) <args>...

with: exactly ONE dst=/out bind mount whose mode token is EXACTLY `ro=false` (the one
Docker-valid explicit read-write declaration — exec-refusal ruling 2026-07-19: Docker's
real --mount grammar has no bare `rw` token, so bare `rw`, mode omission, `ro=true`,
`readonly=true`, and `readonly=false` are ALL refused for /out), absolute host src — its
derived NORMALIZED identity "<src>:/out:rw" (a logical identity, deliberately distinct
from the CLI token) must equal the signed output_mount_identity; every OTHER mount
explicitly ro (governed inputs are read-only); no duplicate mount destination; a FINITE
environment set (blocker 6 — no MR002_* wildcard: the four numerical vars pinned exactly,
PYTHONPATH required and pinned to /work/apps/backend, the nine governed MR002_* keys
pinned to their fixed /inputs paths, the 64-hex countersign hash channel, and NOTHING
else — MR002_OUT is deliberately absent so the runner uses its default under the governed
/out, and MR002_EXECUTION_BINDING_SHA256 is FORBIDDEN in the attested template: it is the
one LAUNCHER-DERIVED field, injected at exec from the actual binding bytes — blocker 8);
the container command CLOSED to exactly `(python|python3) scripts/
mr002_stage3_population_runner.py` with no arguments (blocker 7 — the runner is
environment-driven; -c/-m, other scripts, extra options, and validation/OOS window
arguments are refused by construction); no -v/--volume (ambiguous with --mount), no
--privileged, no host networking, no docker.sock mount, no mutable image tag, no shell
wrapper as the container command, and ANY unrecognized option refused (closed grammar).

Canonical governed-input binding (blocker 5): the four authority artifacts whose bytes
this tool hashes MUST be the same bytes the attested command consumes. GOVERNED_INPUTS
fixes, one-to-one: the signed hash field ↔ a read-only bind mount at a FIXED container
destination ↔ the exact MR002_* environment value the runner reads (the authorization key
is MR002_EXECUTION_COUNTERSIGN — the variable the registered runner actually consumes):

    authorization_sha256      /inputs/authorization.json      MR002_EXECUTION_COUNTERSIGN
    expected_pins_sha256      /inputs/expected_pins.json      MR002_EXPECTED_PINS
    source_manifest_sha256    /inputs/source_manifest.json    MR002_SOURCE_MANIFEST
    execution_package_sha256  /inputs/execution_package.json  MR002_EXECUTION_PACKAGE

The five runner-required artifact paths (execution binding, launch attestation,
verification receipt, realism PASS, final test report) are likewise pinned to fixed
/inputs paths with mandatory read-only mounts; their integrity is enforced IN-CONTAINER
by the runner's fail-closed loaders against the countersigned Phase-B binding chain (an
attestation cannot bind its own hash, nor the receipt's, which is produced after it).
The countersign hash channel must equal the observed authorization hash (produce AND
exec — no cycle, the authorization pre-exists the attestation).

Blocker-8 phase-ordering resolution: the Phase-B binding contains the attestation and
receipt hashes, so the binding's own hash cannot appear inside the signed command
(attestation → binding hash → binding → attestation hash is a fixed-point cycle). The
attestation therefore signs an attested_command_template WITHOUT the binding hash; after
Phase B is assembled the launcher's `exec` receives the binding path explicitly
(--binding), DERIVES its sha256 from the actual bytes, verifies it through the frozen
`load_execution_binding`, cross-validates it against the attestation + receipt, proves
the attested /inputs mount source carries the same bytes, and injects exactly one
derived field:  executed argv = attested_command_template +
--env=MR002_EXECUTION_BINDING_SHA256=<observed>.  No other field may be added, removed,
or rewritten (the executed argv is re-validated in executed mode, where the derived key
is REQUIRED; in template mode it is refused).

`validate_launch_argv` structurally requires all four mounts (ro, fixed destinations, no
duplicates, no mount shadowing /inputs, sources not under the writable /out source).
`produce` additionally requires realpath(mount src) == realpath(hashed host path) with
symlink sources refused for these four; `exec` RE-HASHES each mount source and requires
equality with the signed hash — a signed hash of file A with a command consuming file B
is refused at both boundaries.

Persistence (blocker 4): all immutable evidence goes through `publish_immutable`,
imported FROM the frozen verification tool (one primitive, owned by the trust root). It
uses hard-link create-if-absent publication — never os.replace() — so a destination that
appears at any instant, including after every pre-check, refuses the publication and the
competing bytes stay untouched. Keys are Ed25519 ONLY (enforced by type, not by what
happens to load); the private key is created 0600 and never overwritten.

Subcommands
    generate-key  create an Ed25519 keypair (private key OUTSIDE the repo; refuses overwrite)
    produce       validate the exact argv + governed-input binding, build + sign + publish
                  the attestation, then self-verify via the frozen loader (exit 2 on any
                  validation/publication refusal)
    exec          verify the attestation + receipt via the frozen loaders, RE-VALIDATE the
                  attested argv against the closed grammar, RE-HASH every governed input
                  from its attested mount source, then exec the argv EXACTLY

Trust anchors: the trusted public key (committed) and the frozen verification tool
`scripts/mr002_stage3_attestation_verify.py` (its sha256 is bound INSIDE the attestation).
⚠ The attestation and its verification must run on the SAME host/checkout — a CRLF
re-checkout changes the verification tool's bytes and its bound hash.

This tool authorizes nothing. It produces evidence for Phase B; the owner's execution
countersignature remains the only authority for a Stage-3 run.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys

ATTESTATION_RECORD_TYPE = "MR002_STAGE3_LAUNCH_ATTESTATION"
SIGNATURE_ALGORITHM = "ed25519"
DEFAULT_VERIFICATION_TOOL = "scripts/mr002_stage3_attestation_verify.py"

REQUIRED_LAUNCH_ENV = {
    "OPENBLAS_CORETYPE": "HASWELL",
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
}
# The environment grammar is a FINITE SET (owner review 2026-07-18, blocker 6) — no
# MR002_* wildcard. Every key below is demonstrably read by the registered entrypoint
# (`run_clean_successor` in scripts/mr002_stage3_population_runner.py) and carries a
# defined validation rule; any other key, including any other MR002_* key, is refused.
# PYTHONPATH is REQUIRED and pinned: the runner imports app.research.mr002.* with no
# sys.path bootstrap, so the registered command cannot import without exactly this value.
PYTHONPATH_APPROVED = "/work/apps/backend"
REGISTERED_ENTRYPOINT = "scripts/mr002_stage3_population_runner.py"
OUTPUT_MOUNT_DST = "/out"
GOVERNED_INPUTS_DIR = "/inputs"
# (attestation hash field, env key consumed by the runner, fixed container destination,
#  build_attestation keyword whose host bytes are hashed) — one-to-one by construction.
# ⚠ The authorization env key is MR002_EXECUTION_COUNTERSIGN because that is the variable
# the registered runner actually reads (population_runner run_clean_successor) — binding
# the consumer's real name, not a decorative alias.
GOVERNED_INPUTS = (
    ("authorization_sha256", "MR002_EXECUTION_COUNTERSIGN",
     "/inputs/authorization.json", "authorization_path"),
    ("expected_pins_sha256", "MR002_EXPECTED_PINS",
     "/inputs/expected_pins.json", "expected_pins_path"),
    ("source_manifest_sha256", "MR002_SOURCE_MANIFEST",
     "/inputs/source_manifest.json", "source_manifest_path"),
    ("execution_package_sha256", "MR002_EXECUTION_PACKAGE",
     "/inputs/execution_package.json", "execution_package_path"),
)
# Runner-required artifact paths whose HASHES are carried by the countersigned Phase-B
# binding chain and verified fail-closed IN-CONTAINER by the runner's loaders (the
# attestation cannot bind its own hash, nor the receipt's, which is produced after it).
# Grammar rule: exact fixed path + exactly one read-only bind mount at that destination.
GOVERNED_ARTIFACT_ENV = {
    "MR002_EXECUTION_BINDING": "/inputs/execution_binding.json",
    "MR002_LAUNCH_ATTESTATION": "/inputs/launch_attestation.json",
    "MR002_LAUNCH_VERIFICATION_RECEIPT": "/inputs/launch_verification_receipt.json",
    "MR002_REALISM_PASS": "/inputs/realism_pass.json",
    "MR002_FINAL_TEST_REPORT": "/inputs/final_test_report.json",
}
# Hash channel the runner reads from env AND that the attested template may carry:
# MR002_EXECUTION_COUNTERSIGN_SHA256 — 64-hex, and must equal the OBSERVED authorization
# hash (checked at produce AND exec). No cycle: the authorization exists before the
# attestation is produced.
HEX64_ENV_KEYS = ("MR002_EXECUTION_COUNTERSIGN_SHA256",)
# MR002_EXECUTION_BINDING_SHA256 is the ONE LAUNCHER-DERIVED field (owner review
# 2026-07-18, blocker 8): the Phase-B binding must contain the attestation and receipt
# hashes, so its own hash CANNOT appear inside the signed command (a fixed-point/preimage
# cycle). The attested exact_command is therefore a TEMPLATE that must NOT contain this
# key (operator-supplied values are refused as unknown keys); at exec time the launcher
# derives it from the ACTUAL binding bytes, cross-validates the binding through the
# frozen loader against the attestation + receipt, proves the bytes match the attested
# /inputs mount source, and injects EXACTLY ONE `--env=` token:
#     executed argv = attested_command_template + this one derived field
# No other field may be added, removed, or rewritten (enforced by re-validating the
# executed argv in executed mode, where the key is REQUIRED).
DERIVED_BINDING_ENV_KEY = "MR002_EXECUTION_BINDING_SHA256"
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
# NOT allowed (deliberately): MR002_OUT — the runner then uses its default /out/cleanrun
# inside the governed rw /out mount; alternate output/checkpoint locations are refused.
_ABS_PATH_RE = re.compile(r"^(/|[A-Za-z]:[/\\])")
_IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_MOUNT_SPEC_KEYS = {"type", "src", "source", "dst", "destination", "target"}
# Docker's real --mount grammar has NO bare `rw` token (exec-refusal ruling 2026-07-19):
# read-only is the bare `ro`/`readonly` flag; the ONLY approved explicit read-write
# declaration is the exact Docker-valid token `ro=false` (mode omission NOT approved).
# Internally the parser normalizes `ro=false` to the marker flag "rw" — the normalized
# output identity stays "<src>:/out:rw", which is a LOGICAL identity, distinct from the
# Docker CLI token `ro=false` that the command itself must carry.
_MOUNT_SPEC_FLAGS = {"ro", "readonly"}
_MOUNT_EXPLICIT_RW_TOKEN = "ro=false"


class LaunchValidationError(Exception):
    """A launch-integrity refusal: the operation must not proceed."""


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def canonical_payload(doc: dict) -> bytes:
    """The FROZEN canonical unsigned payload (must match the frozen loader exactly)."""
    unsigned = {k: v for k, v in doc.items()
                if k not in ("signature", "canonical_signed_payload_sha256")}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _parse_mount_spec(spec: str) -> dict:
    """Strictly parse one --mount spec; unknown keys/flags are refused (closed grammar)."""
    mount: dict = {"flags": set()}
    for part in spec.split(","):
        if not part:
            raise LaunchValidationError(f"MOUNT_SPEC_EMPTY_SEGMENT:{spec}")
        if part == _MOUNT_EXPLICIT_RW_TOKEN:
            # the ONE approved explicit read-write declaration (Docker-valid)
            mount["flags"].add("rw")
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            if k in ("ro", "readonly"):
                # ro=true / readonly=true / readonly=false are NOT in the closed grammar —
                # only bare ro|readonly (read-only) and exactly `ro=false` (read-write)
                raise LaunchValidationError(f"MOUNT_MODE_TOKEN_NOT_APPROVED:{part}")
            if k not in _MOUNT_SPEC_KEYS:
                raise LaunchValidationError(f"MOUNT_SPEC_UNKNOWN_KEY:{k}")
            if k in ("src", "source"):
                k = "src"
            elif k in ("dst", "destination", "target"):
                k = "dst"
            if k in mount:
                raise LaunchValidationError(f"MOUNT_SPEC_DUPLICATE_KEY:{k}")
            mount[k] = v
        elif part in _MOUNT_SPEC_FLAGS:
            mount["flags"].add("ro" if part == "readonly" else part)
        else:
            raise LaunchValidationError(f"MOUNT_SPEC_UNKNOWN_FLAG:{part}")
    if mount.get("type") != "bind":
        raise LaunchValidationError(f"MOUNT_NOT_BIND:{mount.get('type')}")
    src, dst = mount.get("src", ""), mount.get("dst", "")
    if not _ABS_PATH_RE.match(src):
        raise LaunchValidationError(f"MOUNT_SRC_NOT_ABSOLUTE:{src}")
    if not dst.startswith("/"):
        raise LaunchValidationError(f"MOUNT_DST_NOT_ABSOLUTE:{dst}")
    if "docker.sock" in src or "docker.sock" in dst:
        raise LaunchValidationError("MOUNT_DOCKER_SOCKET_FORBIDDEN")
    if {"ro", "rw"} <= mount["flags"]:
        raise LaunchValidationError(f"MOUNT_MODE_CONTRADICTORY:{spec}")
    return mount


def _parse_launch_argv(argv, *, image_digest: str, executed: bool = False) -> dict:
    """Parse + fully validate the closed launch grammar (blockers 2-3 + the structural
    half of blocker 5 + the blocker-8 template/executed distinction).

    executed=False validates the ATTESTED TEMPLATE, in which the launcher-derived
    DERIVED_BINDING_ENV_KEY must be ABSENT (an operator-supplied value is refused as an
    unknown key). executed=True validates the EXECUTED argv, in which that key is
    REQUIRED and 64-hex — so template + exactly the one derived field is the only shape
    that passes both modes. Returns {"output_identity", "mounts", "env", "governed_srcs",
    "artifact_srcs", "image_index"}."""
    if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
        raise LaunchValidationError("LAUNCH_ARGV_NOT_STRING_LIST")
    if not _IMAGE_DIGEST_RE.match(str(image_digest)):
        raise LaunchValidationError(f"IMAGE_DIGEST_NOT_FULL_SHA256:{image_digest}")
    if argv[:2] != ["docker", "run"]:
        raise LaunchValidationError(f"LAUNCH_NOT_DOCKER_RUN:{argv[:2]}")

    mounts: list[dict] = []
    env: dict[str, str] = {}
    network_none = False
    image = None
    image_index = -1
    command: list[str] = []

    def _env_kv(kv: str) -> None:
        if "=" not in kv:
            raise LaunchValidationError(f"ENV_NOT_KEY_VALUE:{kv}")
        k, v = kv.split("=", 1)
        if k in env:
            raise LaunchValidationError(f"ENV_KEY_DUPLICATE:{k}")
        env[k] = v

    i = 2
    while i < len(argv):
        tok = argv[i]
        if tok == "--rm":
            i += 1
        elif tok == "--network=none":
            network_none = True
            i += 1
        elif tok == "--network" or tok.startswith("--network=") or tok.startswith("--net"):
            raise LaunchValidationError(f"NETWORK_NOT_NONE:{tok}")
        elif tok == "--privileged":
            raise LaunchValidationError("PRIVILEGED_FORBIDDEN")
        elif tok in ("-v", "--volume") or tok.startswith("--volume="):
            raise LaunchValidationError("VOLUME_STYLE_MOUNT_FORBIDDEN_USE_CANONICAL_MOUNT")
        elif tok == "--mount":
            if i + 1 >= len(argv):
                raise LaunchValidationError("MOUNT_MISSING_SPEC")
            mounts.append(_parse_mount_spec(argv[i + 1]))
            i += 2
        elif tok.startswith("--mount="):
            mounts.append(_parse_mount_spec(tok[len("--mount="):]))
            i += 1
        elif tok.startswith("--env="):
            _env_kv(tok[len("--env="):])
            i += 1
        elif tok == "-e":
            if i + 1 >= len(argv):
                raise LaunchValidationError("ENV_MISSING_VALUE")
            _env_kv(argv[i + 1])
            i += 2
        elif tok.startswith("--name="):
            if not _NAME_RE.match(tok[len("--name="):]):
                raise LaunchValidationError(f"NAME_INVALID:{tok}")
            i += 1
        elif tok.startswith("--workdir="):
            if not tok[len("--workdir="):].startswith("/"):
                raise LaunchValidationError(f"WORKDIR_NOT_ABSOLUTE:{tok}")
            i += 1
        elif tok == "-w":
            if i + 1 >= len(argv) or not argv[i + 1].startswith("/"):
                raise LaunchValidationError("WORKDIR_NOT_ABSOLUTE")
            i += 2
        elif tok.startswith("-"):
            # the grammar is CLOSED: anything not explicitly allowed is refused
            raise LaunchValidationError(f"OPTION_NOT_IN_CLOSED_GRAMMAR:{tok}")
        else:
            image = tok
            image_index = i
            command = argv[i + 1:]
            break
    else:
        raise LaunchValidationError("IMAGE_MISSING")

    if not network_none:
        raise LaunchValidationError("NETWORK_NONE_REQUIRED")
    # immutable image identity: the bare image ID, or <name>@<digest> — never a mutable tag
    if image != image_digest and not image.endswith("@" + image_digest):
        raise LaunchValidationError(f"IMAGE_NOT_PINNED_TO_DIGEST:{image}")
    # blocker 6: FINITE environment set — every key has a defined rule, everything else
    # (including any other MR002_* key) is refused
    governed_env_exact = {k: dst for _, k, dst, _ in GOVERNED_INPUTS} | GOVERNED_ARTIFACT_ENV
    allowed_keys = (set(REQUIRED_LAUNCH_ENV) | {"PYTHONPATH"} | set(governed_env_exact)
                    | set(HEX64_ENV_KEYS))
    if executed:
        # blocker 8: the executed argv carries exactly the one launcher-derived field
        allowed_keys.add(DERIVED_BINDING_ENV_KEY)
        if not _HEX64_RE.match(env.get(DERIVED_BINDING_ENV_KEY, "")):
            raise LaunchValidationError(
                f"ENV_NOT_HEX64:{DERIVED_BINDING_ENV_KEY}={env.get(DERIVED_BINDING_ENV_KEY)}")
    for k in sorted(set(env) - allowed_keys):
        raise LaunchValidationError(f"ENV_KEY_NOT_ALLOWED:{k}")
    for k, v in REQUIRED_LAUNCH_ENV.items():
        if env.get(k) != v:
            raise LaunchValidationError(f"REQUIRED_ENV_MISSING_OR_WRONG:{k}={env.get(k)}")
    if env.get("PYTHONPATH") != PYTHONPATH_APPROVED:
        raise LaunchValidationError(
            f"REQUIRED_ENV_MISSING_OR_WRONG:PYTHONPATH={env.get('PYTHONPATH')}")
    for k, dst in governed_env_exact.items():
        if env.get(k) != dst:
            raise LaunchValidationError(f"GOVERNED_ENV_MISSING_OR_WRONG:{k}={env.get(k)}")
    for k in HEX64_ENV_KEYS:
        if not _HEX64_RE.match(env.get(k, "")):
            raise LaunchValidationError(f"ENV_NOT_HEX64:{k}={env.get(k)}")
    # blocker 7: the container command is CLOSED to the exact registered entrypoint with
    # no arguments (the runner is environment-driven) — -c/-m, other scripts, extra
    # options, and validation/OOS window arguments are all refused by construction
    if not command:
        raise LaunchValidationError("CONTAINER_COMMAND_MISSING")
    if command[0] not in ("python", "python3"):
        raise LaunchValidationError(f"CONTAINER_COMMAND_NOT_ALLOWED:{command[0]}")
    if command[1:] != [REGISTERED_ENTRYPOINT]:
        raise LaunchValidationError(f"CONTAINER_COMMAND_NOT_REGISTERED:{command[:4]}")

    out_mounts = [m for m in mounts if m["dst"] == OUTPUT_MOUNT_DST]
    if len(out_mounts) != 1:
        raise LaunchValidationError(f"OUTPUT_MOUNT_COUNT_NOT_ONE:{len(out_mounts)}")
    out = out_mounts[0]
    if "rw" not in out["flags"] or "ro" in out["flags"]:
        raise LaunchValidationError("OUTPUT_MOUNT_NOT_EXPLICITLY_RW")
    for m in mounts:
        if m is out:
            continue
        if "ro" not in m["flags"] or "rw" in m["flags"]:
            raise LaunchValidationError(f"INPUT_MOUNT_NOT_READONLY:{m.get('src')}")

    # blocker 5 (structural): no duplicate destination anywhere
    dsts = [m["dst"] for m in mounts]
    for dst in dsts:
        if dsts.count(dst) > 1:
            raise LaunchValidationError(f"MOUNT_DST_DUPLICATE:{dst}")
    # each governed input: exactly one ro bind mount at its FIXED destination, and the
    # runner's env var must point at exactly that destination
    governed_dsts = ({dst for _, _, dst, _ in GOVERNED_INPUTS}
                     | set(GOVERNED_ARTIFACT_ENV.values()))
    governed_srcs: dict[str, str] = {}
    for _, env_key, dst, _ in GOVERNED_INPUTS:
        matches = [m for m in mounts if m["dst"] == dst]
        if len(matches) != 1:
            raise LaunchValidationError(f"GOVERNED_INPUT_MOUNT_MISSING:{dst}")
        governed_srcs[env_key] = matches[0]["src"]
    artifact_srcs: dict[str, str] = {}
    for env_key, dst in GOVERNED_ARTIFACT_ENV.items():
        matches = [m for m in mounts if m["dst"] == dst]
        if len(matches) != 1:
            raise LaunchValidationError(f"GOVERNED_INPUT_MOUNT_MISSING:{dst}")
        artifact_srcs[env_key] = matches[0]["src"]
    # no mount may shadow the governed-inputs tree (any mode — Docker mount ordering
    # could otherwise mask an /inputs file with different bytes)
    for m in mounts:
        d = m["dst"]
        if d in governed_dsts:
            continue
        if d == "/" or d == GOVERNED_INPUTS_DIR or d.startswith(GOVERNED_INPUTS_DIR + "/"):
            raise LaunchValidationError(f"INPUTS_SHADOW_MOUNT_FORBIDDEN:{d}")
    # governed sources must not live under the writable output-mount source
    out_root = os.path.realpath(out["src"])
    for src in governed_srcs.values():
        src_real = os.path.realpath(src)
        if src_real == out_root or src_real.startswith(out_root + os.sep):
            raise LaunchValidationError(f"GOVERNED_INPUT_UNDER_OUTPUT_MOUNT:{src}")

    return {"output_identity": f"{out['src']}:{OUTPUT_MOUNT_DST}:rw",
            "mounts": mounts, "env": env, "governed_srcs": governed_srcs,
            "artifact_srcs": artifact_srcs, "image_index": image_index}


def validate_launch_argv(argv, *, image_digest: str) -> str:
    """The SHARED closed-grammar launch-command validator (blockers 2-5, structural).

    Accepts only the canonical `docker run` form documented in the module docstring,
    including the four governed-input mounts and their exact env bindings. Returns the
    DERIVED output-mount identity "<src>:/out:rw" — the caller must require equality
    with the signed output_mount_identity. Raises LaunchValidationError on any
    deviation; there is no best-effort acceptance path.
    """
    return _parse_launch_argv(argv, image_digest=image_digest)["output_identity"]


def governed_input_sources(argv, *, image_digest: str) -> dict[str, str]:
    """Validate the argv and return {env_key: mount src} for the four governed inputs."""
    return _parse_launch_argv(argv, image_digest=image_digest)["governed_srcs"]


def key_id_for_public_pem(public_pem: bytes) -> str:
    """Stable key identity: 'ed25519:' + sha256 of the RAW 32-byte public key.

    Refuses any PEM that is not an Ed25519 public key — an identity is never assigned to
    a key type that merely happens to load.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    pub = serialization.load_pem_public_key(public_pem)
    if not isinstance(pub, Ed25519PublicKey):
        raise LaunchValidationError(f"PUBLIC_KEY_NOT_ED25519:{type(pub).__name__}")
    raw = pub.public_bytes(encoding=serialization.Encoding.Raw,
                           format=serialization.PublicFormat.Raw)
    return f"{SIGNATURE_ALGORITHM}:{hashlib.sha256(raw).hexdigest()}"


def generate_keypair(private_path: str, public_path: str) -> str:
    """Create an Ed25519 keypair; refuses to overwrite either file (symlinks included).
    The private key is created with mode 0600 at creation time, not post-hoc."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    for p in (private_path, public_path):
        if os.path.lexists(p):
            raise SystemExit(f"REFUSED: key file already exists: {p}")
    key = Ed25519PrivateKey.generate()
    priv = key.private_bytes(encoding=serialization.Encoding.PEM,
                             format=serialization.PrivateFormat.PKCS8,
                             encryption_algorithm=serialization.NoEncryption())
    pub = key.public_key().public_bytes(encoding=serialization.Encoding.PEM,
                                        format=serialization.PublicFormat.SubjectPublicKeyInfo)
    os.makedirs(os.path.dirname(os.path.abspath(private_path)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(public_path)), exist_ok=True)
    fd = os.open(private_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(priv)
    with open(public_path, "xb") as fh:
        fh.write(pub)
    return key_id_for_public_pem(pub)


def _validate_governed_binding(srcs: dict[str, str], *,
                               host_paths: dict[str, str]) -> None:
    """Blocker 5 (host half, produce-time): the mount source of each governed input must
    resolve (realpath) to EXACTLY the host file whose bytes are hashed into the signed
    payload; symlink sources and symlink host paths are refused for these four."""
    for _, env_key, _, kwarg in GOVERNED_INPUTS:
        src, host = srcs[env_key], host_paths[kwarg]
        if os.path.islink(src):
            raise LaunchValidationError(f"GOVERNED_INPUT_SYMLINK_SOURCE:{env_key}:{src}")
        if os.path.islink(host):
            raise LaunchValidationError(f"GOVERNED_INPUT_SYMLINK_HOST:{env_key}:{host}")
        if os.path.realpath(src) != os.path.realpath(host):
            raise LaunchValidationError(
                f"GOVERNED_INPUT_SOURCE_MISMATCH:{env_key}:mounted={src}:hashed={host}")


def build_attestation(*, authorization_path: str, expected_pins_path: str,
                      source_manifest_path: str, execution_package_path: str,
                      bound_commit: str, bound_tree: str, image_digest: str,
                      oci_config_digest: str, exact_command_argv: list[str],
                      output_mount_identity: str, private_key_path: str,
                      verification_tool_path: str, launcher_identity: str | None = None,
                      run_nonce: str | None = None) -> dict:
    """Assemble + sign the attestation. Every artifact hash is OBSERVED from file bytes;
    the exact argv must pass the closed launch grammar; the DERIVED output-mount identity
    must equal the claimed one (blocker 2); and every governed input's mount source must
    be the very file being hashed (blocker 5) — contradictory assertions refuse."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    parsed = _parse_launch_argv(exact_command_argv, image_digest=image_digest)
    derived_mount = parsed["output_identity"]
    if output_mount_identity != derived_mount:
        raise LaunchValidationError(
            f"OUTPUT_MOUNT_IDENTITY_MISMATCH:claimed={output_mount_identity}:derived={derived_mount}")
    _validate_governed_binding(
        parsed["governed_srcs"],
        host_paths={"authorization_path": authorization_path,
                    "expected_pins_path": expected_pins_path,
                    "source_manifest_path": source_manifest_path,
                    "execution_package_path": execution_package_path})
    auth_sha = _sha256_file(authorization_path)
    # blocker 6 rule: the runner's root-of-chain hash channel must equal the OBSERVED
    # authorization hash — a mismatched channel is refused before it can be signed
    if parsed["env"]["MR002_EXECUTION_COUNTERSIGN_SHA256"] != auth_sha:
        raise LaunchValidationError(
            f"ENV_COUNTERSIGN_SHA_MISMATCH:env="
            f"{parsed['env']['MR002_EXECUTION_COUNTERSIGN_SHA256']}:observed={auth_sha}")
    doc = {
        "record_type": ATTESTATION_RECORD_TYPE,
        "version": "1.0",
        "record_status": "IMMUTABLE",
        "authorization_sha256": auth_sha,
        "expected_pins_sha256": _sha256_file(expected_pins_path),
        "source_manifest_sha256": _sha256_file(source_manifest_path),
        "execution_package_sha256": _sha256_file(execution_package_path),
        "bound_commit": bound_commit,
        "bound_tree": bound_tree,
        "image_digest": image_digest,
        "oci_config_digest": oci_config_digest,
        "launcher_identity": launcher_identity or
            f"{getpass.getuser()}@{socket.gethostname()} mr002_stage3_launch_attestation.py",
        "exact_command": json.dumps(exact_command_argv),
        "output_mount_identity": derived_mount,
        "run_nonce": run_nonce or secrets.token_hex(32),
        "signature_algorithm": SIGNATURE_ALGORITHM,
        "verification_tool": verification_tool_path.replace("\\", "/"),
        "verification_tool_sha256": _sha256_file(verification_tool_path),
    }
    with open(private_key_path, "rb") as fh:
        key = serialization.load_pem_private_key(fh.read(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise LaunchValidationError(f"PRIVATE_KEY_NOT_ED25519:{type(key).__name__}")
    pub_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)
    doc["signing_key_id"] = key_id_for_public_pem(pub_pem)
    payload = canonical_payload(doc)
    doc["canonical_signed_payload_sha256"] = hashlib.sha256(payload).hexdigest()
    doc["signature"] = base64.b64encode(key.sign(payload)).decode("ascii")
    return doc


def produce(args: argparse.Namespace) -> int:
    # the publication primitive is owned by the FROZEN verification tool (blocker 4)
    from scripts.mr002_stage3_attestation_verify import PublicationRefused, publish_immutable
    try:
        doc = build_attestation(
            authorization_path=args.authorization, expected_pins_path=args.expected_pins,
            source_manifest_path=args.source_manifest, execution_package_path=args.execution_package,
            bound_commit=args.bound_commit, bound_tree=args.bound_tree,
            image_digest=args.image_digest, oci_config_digest=args.oci_config_digest,
            exact_command_argv=json.loads(args.exact_command_argv),
            output_mount_identity=args.output_mount, private_key_path=args.private_key,
            verification_tool_path=args.verification_tool, launcher_identity=args.launcher_identity,
            run_nonce=args.run_nonce)
        data = (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode("utf-8")
        got = publish_immutable(args.out, data)
    except (LaunchValidationError, PublicationRefused) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    # self-verify through the FROZEN loader before reporting success
    from scripts.mr002_stage3_population_runner import load_launch_attestation
    load_launch_attestation(args.out, got)
    print(json.dumps({"attestation_path": args.out, "attestation_sha256": got,
                      "byte_length": len(data), "signing_key_id": doc["signing_key_id"],
                      "run_nonce": doc["run_nonce"]}, indent=1))
    return 0


def exec_attested(args: argparse.Namespace) -> int:
    """Verify attestation + receipt via the FROZEN loaders, RE-VALIDATE the attested
    template against the closed launch grammar, RE-HASH every governed input from its
    attested mount source (blockers 3 + 5), then resolve the blocker-8 cycle: derive the
    Phase-B binding hash from the ACTUAL bytes at --binding (assembled AFTER attestation
    + receipt), verify the binding through the frozen loader, cross-validate it against
    the attestation and receipt, prove the attested /inputs mount source carries the same
    bytes, inject EXACTLY ONE derived env field, and exec:

        executed argv = attested_command_template + one launcher-derived binding-hash field

    A signed but operationally unsafe or substituted-input command is refused here even
    though its signature verifies."""
    from scripts.mr002_stage3_population_runner import (
        Stage3RunRefused,
        load_execution_binding,
        load_launch_attestation,
        load_verification_receipt,
    )
    att_sha = _sha256_file(args.attestation)
    attestation = load_launch_attestation(args.attestation, att_sha)
    load_verification_receipt(args.receipt, _sha256_file(args.receipt), att_sha,
                              attestation=attestation)
    template = json.loads(attestation["exact_command"])
    try:
        parsed = _parse_launch_argv(template, image_digest=attestation["image_digest"])
        if parsed["output_identity"] != attestation["output_mount_identity"]:
            raise LaunchValidationError(
                f"OUTPUT_MOUNT_IDENTITY_MISMATCH:signed={attestation['output_mount_identity']}"
                f":derived={parsed['output_identity']}")
        for hash_field, env_key, _, _ in GOVERNED_INPUTS:
            src = parsed["governed_srcs"][env_key]
            if os.path.islink(src):
                raise LaunchValidationError(f"GOVERNED_INPUT_SYMLINK_SOURCE:{env_key}:{src}")
            try:
                got = _sha256_file(src)
            except OSError as exc:
                raise LaunchValidationError(
                    f"GOVERNED_INPUT_UNREADABLE:{env_key}:{src}") from exc
            if got != attestation[hash_field]:
                raise LaunchValidationError(
                    f"GOVERNED_INPUT_BYTES_MISMATCH:{env_key}:signed="
                    f"{attestation[hash_field]}:observed={got}")
        # blocker 6 at the exec boundary: the countersign env channel must agree with the
        # attested authorization hash
        if parsed["env"]["MR002_EXECUTION_COUNTERSIGN_SHA256"] != attestation["authorization_sha256"]:
            raise LaunchValidationError(
                f"ENV_COUNTERSIGN_SHA_MISMATCH:env="
                f"{parsed['env']['MR002_EXECUTION_COUNTERSIGN_SHA256']}"
                f":signed={attestation['authorization_sha256']}")
        # blocker 8: derive the binding hash from ACTUAL bytes — never operator-supplied
        try:
            derived_binding_sha = _sha256_file(args.binding)
        except OSError as exc:
            raise LaunchValidationError(f"BINDING_UNREADABLE:{args.binding}") from exc
        binding = load_execution_binding(args.binding, derived_binding_sha)
        cross = {
            "launch_attestation_sha256": att_sha,
            "launch_verification_receipt_sha256": _sha256_file(args.receipt),
            "authorization_sha256": attestation["authorization_sha256"],
            "expected_pins_sha256": attestation["expected_pins_sha256"],
            "implementation_manifest_sha256": attestation["source_manifest_sha256"],
            "execution_package_sha256": attestation["execution_package_sha256"],
            "bound_commit": attestation["bound_commit"],
            "bound_tree": attestation["bound_tree"],
            "image_digest": attestation["image_digest"],
            "oci_config_digest": attestation["oci_config_digest"],
        }
        mism = [k for k, v in cross.items() if binding.get(k) != v]
        if mism:
            raise LaunchValidationError(f"BINDING_CROSS_VALIDATION_MISMATCH:{mism}")
        # the injected hash must correspond to the bytes mounted at the attested source
        binding_src = parsed["artifact_srcs"]["MR002_EXECUTION_BINDING"]
        try:
            mounted_sha = _sha256_file(binding_src)
        except OSError as exc:
            raise LaunchValidationError(
                f"GOVERNED_INPUT_UNREADABLE:MR002_EXECUTION_BINDING:{binding_src}") from exc
        if mounted_sha != derived_binding_sha:
            raise LaunchValidationError(
                f"BINDING_MOUNT_BYTES_MISMATCH:mounted={mounted_sha}"
                f":derived={derived_binding_sha}")
        # inject exactly the one derived field, then re-validate in executed mode: the
        # executed argv may differ from the template ONLY by this token
        idx = parsed["image_index"]
        executed = (template[:idx]
                    + [f"--env={DERIVED_BINDING_ENV_KEY}={derived_binding_sha}"]
                    + template[idx:])
        executed_parsed = _parse_launch_argv(
            executed, image_digest=attestation["image_digest"], executed=True)
        if executed_parsed["env"][DERIVED_BINDING_ENV_KEY] != derived_binding_sha:
            raise LaunchValidationError("DERIVED_FIELD_INJECTION_INCONSISTENT")
    except (LaunchValidationError, Stage3RunRefused) as exc:
        print(f"REFUSED: attested command failed launch validation: {exc}", file=sys.stderr)
        return 2
    print(f"exec (attested, receipt-verified, grammar-validated, inputs re-hashed, "
          f"binding-derived): {executed}")
    return subprocess.run(executed, check=False).returncode  # noqa: S603 - template + derived field


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate-key", help="create an Ed25519 keypair (refuses overwrite)")
    g.add_argument("--private-key", required=True, help="output path OUTSIDE the repository")
    g.add_argument("--public-key", required=True)

    p = sub.add_parser("produce", help="validate argv + input binding, build + sign + publish")
    p.add_argument("--authorization", required=True)
    p.add_argument("--expected-pins", required=True)
    p.add_argument("--source-manifest", required=True)
    p.add_argument("--execution-package", required=True)
    p.add_argument("--bound-commit", required=True)
    p.add_argument("--bound-tree", required=True)
    p.add_argument("--image-digest", required=True)
    p.add_argument("--oci-config-digest", required=True)
    p.add_argument("--exact-command-argv", required=True,
                   help="JSON array of argv strings — the EXACT command to be launched; "
                        "must satisfy the closed launch grammar incl. governed-input mounts")
    p.add_argument("--output-mount", required=True,
                   help="claimed output-mount identity '<abs-src>:/out:rw' — must equal the "
                        "identity DERIVED from the argv, or production is refused")
    p.add_argument("--private-key", required=True)
    p.add_argument("--verification-tool", default=DEFAULT_VERIFICATION_TOOL)
    p.add_argument("--launcher-identity", default=None)
    p.add_argument("--run-nonce", default=None)
    p.add_argument("--out", required=True)

    e = sub.add_parser("exec", help="verify attestation + receipt + grammar + input bytes, "
                                    "derive the binding hash, inject it, exec")
    e.add_argument("--attestation", required=True)
    e.add_argument("--receipt", required=True)
    e.add_argument("--binding", required=True,
                   help="the assembled Phase-B execution binding (produced AFTER the "
                        "attestation and receipt); its hash is DERIVED from these bytes "
                        "and injected as the one launcher-derived env field")

    args = ap.parse_args()
    if args.cmd == "generate-key":
        kid = generate_keypair(args.private_key, args.public_key)
        print(json.dumps({"signing_key_id": kid, "public_key": args.public_key}))
        return 0
    if args.cmd == "produce":
        return produce(args)
    return exec_attested(args)


if __name__ == "__main__":
    raise SystemExit(main())
