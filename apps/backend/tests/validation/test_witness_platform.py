"""The SDK-free platform boundary (ADR 0047 §7).

The point of this module existing at all is that `session_composition` can import it and cannot import
`app/validation/aws/`. So the load-bearing test here is not the predicate — it is the structural one at
the bottom, which proves reaching the boundary does not reach the SDK.
"""

from __future__ import annotations

import os
import platform
import ssl
import subprocess
import sys
from pathlib import Path

import pytest

from app.validation.witness_platform import (
    PLATFORM_UNSUPPORTED,
    PlatformUnsupported,
    assert_supported_platform,
    platform_is_supported,
    truststore_is_injected,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]

ON_SUPPORTED = platform_is_supported()


def test_the_predicate_agrees_with_the_interpreter_it_is_asked_about():
    assert platform_is_supported() is (platform.system() == "Linux" and os.name == "posix")


@pytest.mark.skipif(not ON_SUPPORTED, reason="the supported-platform path")
def test_a_supported_platform_is_not_refused():
    assert_supported_platform()                    # raises if the boundary is wrong on the real host


@pytest.mark.skipif(ON_SUPPORTED, reason="the unsupported-platform refusal")
def test_an_unsupported_platform_is_refused_with_the_governed_code():
    """Exercised for real on the Windows developer machine.

    A guard that only ever refuses a *simulated* platform is a guard nobody has run. Linux CI skips
    this one and runs the pair above instead; between them every platform runs one arm honestly.
    """
    with pytest.raises(PlatformUnsupported) as exc:
        assert_supported_platform()
    assert exc.value.code == PLATFORM_UNSUPPORTED
    assert "issue #522" in str(exc.value)


@pytest.mark.skipif(ON_SUPPORTED, reason="the unsupported-platform refusal")
def test_the_refusal_names_the_caller_context():
    """The same boundary is asserted from the composition root and from the 4D harness; an operator
    reading the refusal needs to know which one refused."""
    with pytest.raises(PlatformUnsupported) as exc:
        assert_supported_platform(context="the Step 4D production witness preflight")
    assert "the Step 4D production witness preflight" in str(exc.value)


def test_injection_detection_reads_the_live_ssl_context_rather_than_a_captured_baseline(monkeypatch):
    """ADR-0017 injection is process-global and can happen after import, so the check must look at
    `ssl.SSLContext` now — a value captured at import time would already be the truststore class in
    exactly the runs where the answer matters."""
    assert truststore_is_injected() is ssl.SSLContext.__module__.startswith("truststore")

    class _Injected(ssl.SSLContext):
        pass

    _Injected.__module__ = "truststore._api"
    monkeypatch.setattr(ssl, "SSLContext", _Injected)
    assert truststore_is_injected() is True


def test_reaching_the_boundary_does_not_reach_the_aws_sdk():
    """The structural reason this module exists.

    `check_aws_sdk_isolation.sh` forbids `session_composition` from importing `app.validation.aws`, so
    the boundary it asserts must be importable without pulling in that package — or the SDK. Asserted
    in a fresh interpreter because this one has already imported everything.
    """
    probe = (
        "import sys; import app.validation.witness_platform; "
        "print(sorted(m for m in sys.modules "
        "if m == 'boto3' or m == 'botocore' or m.startswith('app.validation.aws')))"
    )
    result = subprocess.run([sys.executable, "-c", probe], cwd=BACKEND_ROOT,
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]", result.stdout
