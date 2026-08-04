"""Run the factor-data readiness watchdog's bash harness under pytest so CI exercises it.

The harness (``deploy/aws/tests/test_factor_freshness.sh``) fakes systemd, Docker and AWS
and drives the real watchdog through every producer-liveness, sealed-generation, freshness,
calendar and interlock path. It is POSIX bash + python3 + coreutils; it runs in CI (Linux)
and is skipped on Windows/where bash is absent. When it runs, a non-zero exit fails this
test with the harness output attached.

The property the harness pins is the 2026-08-03/04 defect: a fresh store must not be able
to hide a dead producer. Every producer-liveness case runs with a clean store report.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
HARNESS = REPO_ROOT / "deploy" / "aws" / "tests" / "test_factor_freshness.sh"
WATCHDOG = REPO_ROOT / "deploy" / "aws" / "factor-freshness.sh"


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="bash harness runs on POSIX/CI, not Windows"
)
@pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")
@pytest.mark.skipif(shutil.which("python3") is None, reason="python3 unavailable to the harness")
def test_factor_freshness_bash_harness_passes():
    assert HARNESS.exists(), f"harness missing at {HARNESS}"
    result = subprocess.run(["bash", str(HARNESS)], capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, f"watchdog harness failed:\n{result.stdout}\n{result.stderr}"
    assert "0 failed" in result.stdout


# Skipped on Windows for the same reason as the harness: `shutil.which("bash")` resolves
# to the WSL stub, which cannot execute. Shell syntax is checked on POSIX/CI.
@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="bash harness runs on POSIX/CI, not Windows"
)
@pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")
def test_watchdog_shell_syntax_is_clean():
    result = subprocess.run(
        ["bash", "-n", str(WATCHDOG)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr


def test_watchdog_does_not_depend_on_factor_refresh_py():
    """The production image predates ``scripts/factor_refresh.py`` and bakes ``scripts/``
    in rather than bind-mounting it. This watchdog must never become the reason that file
    gets deployed, so it may name the module in a comment but never invoke it."""
    text = WATCHDOG.read_text(encoding="utf-8")
    code = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    assert not [ln for ln in code if "factor_refresh.py" in ln]
    # Nor may it deploy, restart, or otherwise mutate the stack as a side effect.
    assert not [ln for ln in code if "docker compose" in ln or "docker-compose" in ln]


def test_watchdog_uses_the_exact_sealed_artifact_name():
    assert "_factor_refresh_universe_sealed.json" in WATCHDOG.read_text(encoding="utf-8")


def test_embedded_python_blocks_compile():
    """The in-container freshness query only runs against a real DuckDB store on the box —
    the harness fakes ``docker``, so a syntax error in it would ship unnoticed and the
    watchdog would degrade to reporting the store as unreadable. Compile every embedded
    heredoc so that cannot happen."""
    blocks = re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY\n", WATCHDOG.read_text(encoding="utf-8"), re.S)
    assert len(blocks) >= 3, f"expected the embedded python heredocs, found {len(blocks)}"
    for index, block in enumerate(blocks):
        compile(block, f"factor-freshness.sh:<python block {index}>", "exec")


def test_readiness_failure_exit_code_survives_the_unit_success_exit_status():
    """``workbench-factor-freshness.service`` declares ``SuccessExitStatus=0 1``, so an
    exit of 1 is recorded by systemd as a SUCCESS. A readiness failure must exit with a
    code the unit does NOT absorb, or the interlock signal dies at the unit boundary."""
    unit = REPO_ROOT / "deploy" / "aws" / "systemd" / "workbench-factor-freshness.service"
    declared = [
        ln.split("=", 1)[1].split()
        for ln in unit.read_text(encoding="utf-8").splitlines()
        if ln.startswith("SuccessExitStatus=")
    ]
    absorbed = {code for line in declared for code in line}
    assert "2" not in absorbed, f"the unit absorbs exit 2: {absorbed}"

    text = WATCHDOG.read_text(encoding="utf-8")
    assert "EXIT_NOT_READY=2" in text
    assert "EXIT_READY=0" in text
