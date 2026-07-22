"""build-deploy-archive.sh — path-scoped ADR-0043 provenance model (2026-07-22).

The build guard was advanced from "no apps/** delta from the frozen PR8 baseline c8b3ac24" to a
path-scoped model: the GOVERNED ADR-0043 executable/checker/governing paths must be byte-identical
to the implementation baseline ea6db6e (#463 settlement barrier), while the complete deployed tree
is an explicit reviewed SHA whose remaining application delta is enumerated and classified as
non-ADR-0043. These tests pin that model against the real repository history.

Run with bash (the script is POSIX sh); CI is Linux, local dev has Git Bash.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "deploy/aws/build-deploy-archive.sh"
BASH = shutil.which("bash") or "bash"

# The three governing identities (owner ruling 2026-07-22).
DEPLOYED = "b0058bf335628f8dbde09a93915314f3a1f7743b"   # reviewed superset tip (#467)
ADR0043_IMPL = "ea6db6e6d5dc338196ffca9919a7a2e2643e1f6c"   # #463 settlement barrier
PR8_BASELINE = "c8b3ac24b839d7b19c40979a9e4be859151dbab7"   # historical, recorded only
PRE_463 = "d03af06e611a4e17b3d18b2b1f4f00bd365a42c0"   # #461 tip — parent of ea6db6e

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or not (REPO_ROOT / ".git").exists(),
    reason="needs bash + a git checkout (the provenance proof is produced where .git exists)",
)


def _bash_path(pth: Path) -> str:
    """A path bash's tar accepts. On Git Bash a Windows drive path is misread as a remote host
    (the drive-letter colon looks like host:path) — convert C:/x to /c/x. Linux str() is fine."""
    s = str(pth)
    if len(s) > 2 and s[1] == ":" and s[2] in ("\\", "/"):
        return "/" + s[0].lower() + s[2:].replace("\\", "/")
    return s


def _run(args: list[str], out_dir: Path, env_extra: dict | None = None):
    env = None
    if env_extra:
        import os
        env = {**os.environ, **env_extra}
    return subprocess.run(
        [BASH, str(SCRIPT), *args, _bash_path(out_dir)],
        cwd=REPO_ROOT, capture_output=True, text=True, env=env, timeout=180,
    )


def _marker(out_dir: Path) -> dict:
    return json.loads((out_dir / "DEPLOYED_BUILD_INFO.json").read_text(encoding="utf-8"))


# (1) accepts the reviewed superset tip when governed ADR-0043 files match the baseline ----------

def test_accepts_deployed_sha_when_governed_paths_match_the_implementation_baseline(tmp_path):
    r = _run([DEPLOYED], tmp_path)
    assert r.returncode == 0, r.stderr + r.stdout
    m = _marker(tmp_path)
    assert m["adr0043_governed_paths_match"] is True
    assert m["implementation_ancestry_verified"] is True
    assert m["reviewed_superset_delta_classification"] == "reviewed_non_adr0043_superset"
    # the enumerated delta is exactly #467's application files, none of them governed
    assert "apps/backend/app/strategies/backtest_context.py" in \
        m["application_delta_after_adr0043_baseline"]


# (2) rejects a target that changes a governed file after the baseline --------------------------

def test_rejects_a_target_that_changes_a_governed_path_after_the_baseline(tmp_path):
    # Move the baseline BEFORE #463: then settlement.py (a governed path, introduced by #463) differs
    # between the baseline and the deployed tree — a governed-path change that must be refused.
    r = _run([DEPLOYED], tmp_path, env_extra={"ADR0043_IMPLEMENTATION_SHA": PRE_463})
    assert r.returncode == 3, r.stdout + r.stderr
    assert "governed ADR-0043 path" in (r.stdout + r.stderr)
    assert "settlement.py" in (r.stdout + r.stderr)
    assert not (tmp_path / "DEPLOYED_BUILD_INFO.json").exists()   # nothing written on refusal


# (3) an application change inside the governed set cannot be classified as non-ADR-0043 ---------
#     (the "unenumerated / misclassified delta" guard). Same mechanism as (2): with the baseline
#     before #463, settlement.py appears in the apps/scripts delta AND is governed → refused, so it
#     can never be silently enumerated as reviewed_non_adr0043_superset.

def test_a_governed_path_is_never_classified_into_the_non_adr0043_superset(tmp_path):
    r = _run([DEPLOYED], tmp_path, env_extra={"ADR0043_IMPLEMENTATION_SHA": PRE_463})
    assert r.returncode == 3
    # the refusal fires on the governed-path invariant, before any manifest is written
    assert not (tmp_path / "DEPLOYED_BUILD_INFO.json").exists()


# (4) rejects a target where the implementation baseline is not an ancestor ----------------------

def test_rejects_when_the_implementation_baseline_is_not_an_ancestor(tmp_path):
    # ea6db6e (#463) is NOT an ancestor of PR8 (c8b3ac24, which predates it).
    r = _run([PR8_BASELINE], tmp_path)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "NOT an ancestor" in (r.stdout + r.stderr)


# (5) rejects a moving ref, and rejects an omitted explicit SHA ----------------------------------

def test_rejects_a_moving_branch_ref(tmp_path):
    r = _run(["main"], tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "moving ref" in (r.stdout + r.stderr)


def test_rejects_an_omitted_source_sha(tmp_path):
    # No SHA arg: the only positional is the out-dir, which the script sees as SOURCE_REF and then
    # fails to resolve to a commit (or, if empty, prints the explicit-SHA FATAL).
    r = subprocess.run([BASH, str(SCRIPT)], cwd=REPO_ROOT, capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 1
    assert "EXPLICIT approved commit SHA" in (r.stdout + r.stderr)


# (6) the marker records BOTH identities, distinctly -------------------------------------------

def test_marker_records_both_implementation_and_deployed_identities(tmp_path):
    r = _run([DEPLOYED], tmp_path)
    assert r.returncode == 0, r.stderr + r.stdout
    m = _marker(tmp_path)
    assert m["deployed_repository_commit"] == DEPLOYED
    assert m["adr0043_implementation_commit"] == ADR0043_IMPL
    assert m["adr0043_original_baseline_commit"] == PR8_BASELINE
    # the three are distinct — never conflated
    assert len({m["deployed_repository_commit"], m["adr0043_implementation_commit"],
                m["adr0043_original_baseline_commit"]}) == 3
