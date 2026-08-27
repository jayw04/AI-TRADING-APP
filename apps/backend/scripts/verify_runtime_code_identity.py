"""Startup enforcement: refuse to boot if the running code is not the code this image was built with.

Runs BEFORE `alembic upgrade head`, not merely before serving traffic. Migrations and seeding are
side effects on durable state; a container whose code cannot be identified must not reach them.

## What this proves, and what it does not

⛔ This is **runtime integrity enforcement, not deployment provenance.** It proves exactly one thing:

    the code executing now equals the code this image claims it was built with.

It CANNOT prove the correct approved image was deployed. A wrong or hostile image carries wrong code
*and* a matching self-description, and passes this gate perfectly. That question is answered only by
the host-side attestation (MDQ preflight Gate 6), which reads the container from outside via the Docker
daemon. Neither check substitutes for the other.

## Why the expected value is baked, not passed

`/app/BUILD_CODE_IDENTITY.json` is written INTO the image at build time, derived from the very bytes
`COPY app ./app` placed there. It is deliberately not an environment variable: an operator facing a
mismatch at 09:20 on a capture morning could otherwise "fix" it by changing the asserted value, which
converts a fail-closed integrity gate into a formality.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.validation.deployment_identity import (  # noqa: E402
    CODE_DIGEST_SCHEMA,
    DeploymentIdentityError,
    derive_runtime_code_digest,
)

BUILD_IDENTITY_PATH = Path("/app/BUILD_CODE_IDENTITY.json")
RUNTIME_CODE_ROOT = Path("/app/app")


def verify(identity_path: Path = BUILD_IDENTITY_PATH,
           code_root: Path = RUNTIME_CODE_ROOT) -> str:
    """Return the agreed digest, or raise. Every failure mode is a refusal."""
    if not identity_path.is_file():
        raise DeploymentIdentityError(
            f"the image carries no baked code identity at {identity_path}; an image that cannot say "
            f"what it was built with cannot be verified, and is refused rather than trusted")
    try:
        payload = json.loads(identity_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentIdentityError(
            f"the baked code identity at {identity_path} is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise DeploymentIdentityError(f"the baked code identity at {identity_path} is not an object")

    schema = payload.get("schema")
    if schema != CODE_DIGEST_SCHEMA:
        raise DeploymentIdentityError(
            f"the baked code identity declares schema {schema!r}, but this runtime canonicalizes as "
            f"{CODE_DIGEST_SCHEMA!r}; comparing digests across algorithms would be meaningless")

    expected = str(payload.get("code_digest", "")).strip().lower()
    if not expected.startswith("sha256:") or len(expected) != 71:
        raise DeploymentIdentityError(
            f"the baked code identity records no usable code_digest ({payload.get('code_digest')!r})")

    actual = derive_runtime_code_digest(code_root)
    if actual != expected:
        raise DeploymentIdentityError(
            f"RUNTIME CODE MISMATCH: {code_root} hashes to {actual}, but this image was built with "
            f"{expected}. The code executing now is not the code this image was built from — refusing "
            f"to run migrations or serve.")
    return actual


def main() -> int:
    try:
        digest = verify()
    except DeploymentIdentityError as exc:
        print(f"STARTUP REFUSED - runtime code identity: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - unknown failure is still a refusal
        print(f"STARTUP REFUSED - runtime code identity could not be established: {exc}",
              file=sys.stderr)
        return 1
    print(f"runtime code identity verified: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
