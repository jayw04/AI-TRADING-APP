"""The Step 4C platform boundary (issue #522, owner ruling 2026-07-26).

One of these tests is unusual and worth naming: on the developer's Windows laptop
`test_a_non_linux_invocation_is_refused` exercises the REAL refusal, not a simulated one — this is the
platform the guard exists to stop. On Linux CI the same guarantee is reached by forcing the platform
values, so the property is proven on both.
"""

from __future__ import annotations

import os
import platform
import ssl

import pytest

from app.validation.aws.platform_guard import (
    PLATFORM_UNSUPPORTED,
    PlatformUnsupported,
    assert_supported_platform,
    capture_runtime,
    truststore_is_injected,
)

LINUX = platform.system() == "Linux" and os.name == "posix"


def test_a_non_linux_invocation_is_refused(monkeypatch):
    """The gate: Windows, macOS, or anything whose OS and API family disagree."""
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(os, "name", "nt")
    with pytest.raises(PlatformUnsupported) as exc:
        assert_supported_platform()
    assert exc.value.code == PLATFORM_UNSUPPORTED
    assert "Linux/posix only" in str(exc.value) or "Linux/posix" in str(exc.value)


@pytest.mark.skipif(LINUX, reason="this assertion is about the unsupported host, which Linux is not")
def test_the_refusal_is_real_on_this_machine():
    """No monkeypatching: the developer's Windows box must actually be refused.

    A guard that only refuses a faked platform is a guard nobody has run.
    """
    with pytest.raises(PlatformUnsupported) as exc:
        assert_supported_platform()
    assert exc.value.code == PLATFORM_UNSUPPORTED


@pytest.mark.skipif(not LINUX, reason="only the supported platform may pass the gate")
def test_linux_passes_the_gate():
    assert_supported_platform()                   # raises if the boundary is wrong on the real host


def test_a_platform_whose_os_family_disagrees_is_refused(monkeypatch):
    """`platform.system()` says Linux but `os.name` does not — not an environment this understands."""
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(os, "name", "nt")
    with pytest.raises(PlatformUnsupported) as exc:
        assert_supported_platform()
    assert exc.value.code == PLATFORM_UNSUPPORTED


def test_the_refusal_names_why_it_refused():
    """An operator hitting this must learn it is a boundary, not a bug."""
    if LINUX:
        pytest.skip("the message is asserted on the platform that is actually refused")
    with pytest.raises(PlatformUnsupported) as exc:
        assert_supported_platform()
    message = str(exc.value)
    assert "instance-role" in message              # what the EC2 host proves that this one cannot
    assert "#522" in message                       # where the Windows interaction is tracked


# ── the runtime attestation ──────────────────────────────────────────────────────────────────────────

def test_the_runtime_attestation_records_observed_values():
    attestation = capture_runtime()
    provenance = attestation.to_open_provenance()

    assert provenance["system"] == platform.system()
    assert provenance["os_name"] == os.name
    assert provenance["openssl_version"] == ssl.OPENSSL_VERSION
    assert provenance["python_version"].count(".") >= 2
    assert provenance["boto3_version"] and provenance["botocore_version"]
    assert provenance["instance_identity"] == {}


def test_the_attestation_records_the_tls_injection_state():
    """Issue #522's diagnostic: whether ADR-0017's process-global injection was active."""
    attestation = capture_runtime()
    assert attestation.truststore_injected is truststore_is_injected()
    assert attestation.ssl_context_module == getattr(ssl.SSLContext, "__module__", "unknown")


def test_the_attestation_carries_instance_identity_when_supplied():
    attestation = capture_runtime(
        instance_identity={"instanceId": "i-0abc", "imageId": "ami-0def", "region": "us-east-1"})
    assert attestation.to_open_provenance()["instance_identity"]["imageId"] == "ami-0def"


def test_capturing_the_runtime_is_not_gated_by_the_platform(monkeypatch):
    """An operator diagnosing a refusal needs the attestation OF the refused machine."""
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(os, "name", "nt")
    attestation = capture_runtime()               # must not raise
    assert attestation.system == "Windows"
