"""Run the ADR-0043 DB backup/restore recovery harness under pytest so CI exercises it.

The harness (``deploy/aws/tests/test_db_backup_restore.sh``) builds a synthetic WAL-mode SQLite DB,
backs it up, simulates the a4c7e1b93d20 migration, whole-file restores, and proves the restore is
byte-identical to the pre-migration snapshot with the migration undone. POSIX bash + python3; run in
CI (Linux), skipped on Windows / where bash is absent.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
HARNESS = REPO_ROOT / "deploy" / "aws" / "tests" / "test_db_backup_restore.sh"


@pytest.mark.skipif(sys.platform.startswith("win"), reason="bash harness runs on POSIX/CI, not Windows")
@pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")
def test_db_backup_restore_harness_passes():
    assert HARNESS.exists(), f"harness missing at {HARNESS}"
    result = subprocess.run(["bash", str(HARNESS)], capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, f"DB recovery harness failed:\n{result.stdout}\n{result.stderr}"
    assert "0 failed" in result.stdout
