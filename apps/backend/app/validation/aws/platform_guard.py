"""Runtime attestation for the AWS witness harnesses, and the re-exported platform boundary.

## The boundary moved out of this module (ADR 0047 §7)

`assert_supported_platform`, `PlatformUnsupported` and `truststore_is_injected` now live in
`app/validation/witness_platform.py` and are re-exported here so existing callers are unaffected. The
reason is structural: `check_aws_sdk_isolation.sh` forbids any module outside `app/validation/aws/` from
importing this package, so while the boundary lived here, `session_composition` — the single production
source of a witness — could not assert it. A boundary a deployment cannot reach is documentation.

What remains here is `capture_runtime`, which belongs in this package because it reports
`boto3.__version__` and `botocore.__version__` and therefore genuinely needs the SDK.

## Where the boundary is enforced, and where it is not

In the harnesses (`integration_proof`, `production_witness`) and in
`session_composition.resolve_witness` — not inside `KmsAnchorSigner` or `S3ObjectLockAnchorSink`. The
adapters stay independently constructible and unit-testable on any platform (their Stubber suites run on
Windows today); it is the *production composition* that states where they are authorised to operate.
Putting the refusal in the adapters would break their own test suites for no gain.
"""

from __future__ import annotations

import os
import platform
import ssl
import sys
from dataclasses import dataclass, field
from typing import Any

from app.validation.witness_platform import (
    PLATFORM_UNSUPPORTED,
    SUPPORTED_OS_NAME,
    SUPPORTED_SYSTEM,
    PlatformUnsupported,
    assert_supported_platform,
    platform_is_supported,
    truststore_is_injected,
)


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
    "SUPPORTED_OS_NAME",
    "SUPPORTED_SYSTEM",
    "PlatformUnsupported",
    "RuntimeAttestation",
    "assert_supported_platform",
    "capture_runtime",
    "platform_is_supported",
    "truststore_is_injected",
]
