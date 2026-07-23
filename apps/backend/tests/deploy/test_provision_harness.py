"""Run the ADR-0043 validation-provisioner bash harness under pytest so CI exercises it.

The harness (``deploy/aws/tests/test_provision_adr0043_validation.sh``) fakes aws/docker/curl and
drives the real provisioner through every refusal, staging, migration-gate, and rollback path. It is
POSIX bash + python3 + coreutils; it runs in CI (Linux) and is skipped on Windows/where bash is
absent. When it runs, a non-zero exit fails this test with the harness output attached.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
HARNESS = REPO_ROOT / "deploy" / "aws" / "tests" / "test_provision_adr0043_validation.sh"


@pytest.mark.skipif(sys.platform.startswith("win"), reason="bash harness runs on POSIX/CI, not Windows")
@pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")
@pytest.mark.skipif(shutil.which("python3") is None, reason="python3 unavailable to the harness")
def test_validation_provisioner_bash_harness_passes():
    assert HARNESS.exists(), f"harness missing at {HARNESS}"
    result = subprocess.run(["bash", str(HARNESS)], capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, f"provisioner harness failed:\n{result.stdout}\n{result.stderr}"
    assert "0 failed" in result.stdout
