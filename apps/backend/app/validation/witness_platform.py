"""The platform boundary for a production witness (ADR 0047 §7).

A production witness talks to AWS. Where it is authorised to do that is a property of the *deployment*,
not of the adapters, and it has to be enforced somewhere the production composition root can reach.

## Why this module exists separately from `app/validation/aws/platform_guard.py`

Step 4C put the boundary in the AWS package, which was correct for a harness and wrong for a
deployment: `check_aws_sdk_isolation.sh` forbids any module outside `app/validation/aws/` from importing
that package *at all*, so `session_composition` — the single production source of a witness — could not
assert the boundary it depends on. Duplicating the predicate would leave two definitions to drift;
relaxing the invariant would trade a structural property for a convenience.

So the predicate lives here, SDK-free, and `platform_guard` imports it. What stays in the AWS package is
`capture_runtime`, which genuinely needs the SDK because it reports `boto3.__version__`.

## What the boundary is, and what it is not

Linux/POSIX only. Two reasons, and the second is the one people forget:

- **The guarantees.** The installed trust root is protected by POSIX ownership, mode and `O_NOFOLLOW`
  checks (`verify_and_read_public_key`). A platform that cannot establish them refuses a PRODUCTION
  witness anyway; asserting the platform first turns a late, oblique refusal into an early, accurate one.
- **Issue #522.** ADR 0017's `enable_os_trust_store()` calls `truststore.inject_into_ssl()`, which
  replaces `ssl.SSLContext` process-wide, and constructing a botocore client under the resulting process
  state can exhaust the recursion limit on Windows. An unenforced boundary would let a run get as far as
  building AWS clients — and, in a provisioning context, as far as creating real resources — before
  failing somewhere inside botocore with an unreadable error.

This is a boundary drawn around #522, **not** a finding that the Windows behaviour is acceptable, and
not a fix. The defect stays open.
"""

from __future__ import annotations

import os
import platform
import ssl

from app.validation.witness_protocol import WitnessError

#: The refusal code an invocation on an unsupported platform produces.
PLATFORM_UNSUPPORTED = "AWS_WITNESS_PLATFORM_UNSUPPORTED"

SUPPORTED_SYSTEM = "Linux"
SUPPORTED_OS_NAME = "posix"


class PlatformUnsupported(WitnessError):
    """A production witness was reached somewhere it is not authorised to operate. Fails closed."""


def truststore_is_injected() -> bool:
    """Whether ADR-0017's process-global TLS injection is currently active.

    Recorded rather than acted upon. If issue #522 ever reproduces on Linux, this field is what tells an
    investigator whether the injection was in play at the moment clients were constructed.
    """
    return getattr(ssl.SSLContext, "__module__", "").startswith("truststore")


def platform_is_supported() -> bool:
    """The predicate, without the refusal — for callers that must report rather than raise."""
    return platform.system() == SUPPORTED_SYSTEM and os.name == SUPPORTED_OS_NAME


def assert_supported_platform(*, context: str = "a production witness") -> None:
    """Refuse to continue unless this is Linux/POSIX. Called BEFORE any AWS client is constructed.

    Both `platform.system()` and `os.name` are checked: the first names the OS, the second the API
    family, and a runtime where they disagree is not an environment this boundary understands.
    """
    system = platform.system()
    if not platform_is_supported():
        raise PlatformUnsupported(
            f"{context} runs on {SUPPORTED_SYSTEM}/{SUPPORTED_OS_NAME} only; this is "
            f"{system or 'unknown'}/{os.name}. The witness requires POSIX ownership and no-follow "
            f"guarantees on the installed trust root, and on Windows ADR-0017's process-global "
            f"truststore injection can exhaust the recursion limit during botocore client construction "
            f"(issue #522) — so this refuses now rather than failing late, after clients are built",
            code=PLATFORM_UNSUPPORTED)


__all__ = [
    "PLATFORM_UNSUPPORTED",
    "SUPPORTED_OS_NAME",
    "SUPPORTED_SYSTEM",
    "PlatformUnsupported",
    "assert_supported_platform",
    "platform_is_supported",
    "truststore_is_injected",
]
