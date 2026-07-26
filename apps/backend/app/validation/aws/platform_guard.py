"""The Step 4C platform boundary and runtime attestation (ADR 0046 follow-on).

Step 4C is an isolated AWS integration proof. It runs on a temporary EC2 Linux host — deliberately not
`ec2-paper`, and deliberately not the developer's laptop — because what it must prove is the real
execution conditions: the instance-role credential chain, POSIX ownership and mode on the installed
verifying key, VPC/DNS/TLS behaviour, real KMS and S3 endpoints, and IAM scoping. A Linux kernel hosted
on the laptop would prove only that the Python runs.

## Why the refusal is a hard gate rather than documentation

Issue #522: ADR 0017's `enable_os_trust_store()` calls `truststore.inject_into_ssl()`, which replaces
`ssl.SSLContext` process-wide, and constructing a botocore client under the resulting process state can
exhaust the recursion limit on Windows. The owner's ruling is that Step 4C proceeds Linux-only as an
explicit platform boundary — NOT a finding that the Windows behaviour is acceptable, and not a reason to
patch around the interaction a second time.

A documented boundary that is not enforced fails in the worst way: a Windows invocation would run,
provision real AWS resources, and only then hit `RecursionError` somewhere inside botocore — leaving
half-created infrastructure and an unreadable failure. So the guard refuses FIRST, before any client is
constructed and before anything is provisioned, with `AWS_WITNESS_PLATFORM_UNSUPPORTED`.

## Where this lives, and where it does not

Here, in the 4C harness path — not inside `KmsAnchorSigner` or `S3ObjectLockAnchorSink`. The adapters
stay independently constructible and unit-testable on any platform (their tests run on Windows today);
it is the *production composition* that states where they are authorised to operate. Putting the
refusal in the adapters would break their own Stubber-based test suites for no gain.
"""

from __future__ import annotations

import os
import platform
import ssl
import sys
from dataclasses import dataclass, field
from typing import Any

from app.validation.witness_protocol import WitnessError

#: The refusal code a non-Linux invocation produces.
PLATFORM_UNSUPPORTED = "AWS_WITNESS_PLATFORM_UNSUPPORTED"

SUPPORTED_SYSTEM = "Linux"
SUPPORTED_OS_NAME = "posix"


class PlatformUnsupported(WitnessError):
    """Step 4C was invoked somewhere it is not authorised to run. Fails closed, before any AWS call."""


@dataclass(frozen=True)
class RuntimeAttestation:
    """What the proof records about the environment that produced it.

    Every field is observed, never configured. An evidence bundle that merely asserted "this ran on
    Linux" would be worth nothing; these are the values a reader can compare against the deployment they
    care about.
    """

    system: str
    release: str
    machine: str
    os_name: str
    python_version: str
    openssl_version: str
    ssl_context_module: str          # 'ssl' normally; 'truststore._api' if ADR-0017 injection is active
    truststore_injected: bool
    boto3_version: str
    botocore_version: str
    instance_identity: dict[str, Any] = field(default_factory=dict)

    def to_open_provenance(self) -> dict[str, Any]:
        return {
            "system": self.system, "release": self.release, "machine": self.machine,
            "os_name": self.os_name, "python_version": self.python_version,
            "openssl_version": self.openssl_version,
            "ssl_context_module": self.ssl_context_module,
            "truststore_injected": self.truststore_injected,
            "boto3_version": self.boto3_version, "botocore_version": self.botocore_version,
            "instance_identity": self.instance_identity,
        }


def truststore_is_injected() -> bool:
    """Whether ADR-0017's process-global TLS injection is currently active.

    Recorded rather than acted upon. If a future run reproduces issue #522 on Linux, this field is what
    tells an investigator whether the injection was in play.
    """
    return getattr(ssl.SSLContext, "__module__", "").startswith("truststore")


def assert_supported_platform() -> None:
    """Refuse to continue unless this is Linux/POSIX. Called BEFORE anything is provisioned.

    Both `platform.system()` and `os.name` are checked: the first names the OS, the second the API
    family, and a runtime where they disagree is not an environment this proof understands.
    """
    system = platform.system()
    if system != SUPPORTED_SYSTEM or os.name != SUPPORTED_OS_NAME:
        raise PlatformUnsupported(
            f"Step 4C runs on {SUPPORTED_SYSTEM}/{SUPPORTED_OS_NAME} only; this is "
            f"{system or 'unknown'}/{os.name}. The AWS witness integration proof must execute on the "
            f"temporary EC2 Linux integration host so it exercises the instance-role credential chain, "
            f"POSIX key-file ownership, and real KMS/S3 endpoints. On Windows, ADR-0017's process-global "
            f"truststore injection can also exhaust the recursion limit during botocore client "
            f"construction (issue #522) — so a run here would fail late, after provisioning real "
            f"resources, rather than refusing now",
            code=PLATFORM_UNSUPPORTED)


def capture_runtime(*, instance_identity: dict[str, Any] | None = None) -> RuntimeAttestation:
    """Observe the runtime. Safe to call on any platform — recording is not gated.

    Deliberately separate from `assert_supported_platform`: an operator diagnosing a refusal wants the
    attestation of the machine that WAS refused, and coupling the two would deny them that.
    """
    import boto3
    import botocore

    return RuntimeAttestation(
        system=platform.system(),
        release=platform.release(),
        machine=platform.machine(),
        os_name=os.name,
        python_version=sys.version.split()[0],
        openssl_version=ssl.OPENSSL_VERSION,
        ssl_context_module=getattr(ssl.SSLContext, "__module__", "unknown"),
        truststore_injected=truststore_is_injected(),
        boto3_version=boto3.__version__,
        botocore_version=botocore.__version__,
        instance_identity=dict(instance_identity or {}),
    )


__all__ = [
    "PLATFORM_UNSUPPORTED",
    "PlatformUnsupported",
    "RuntimeAttestation",
    "assert_supported_platform",
    "capture_runtime",
    "truststore_is_injected",
]
