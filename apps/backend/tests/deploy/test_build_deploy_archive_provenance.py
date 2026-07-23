"""build-deploy-archive.sh — path-scoped ADR-0043 provenance model (2026-07-22).

The build guard was advanced from "no apps/** delta from the frozen PR8 baseline" to a path-scoped
model: the GOVERNED ADR-0043 executable/checker/governing paths must be byte-identical to the
implementation baseline, while the complete deployed tree is an explicit reviewed SHA whose
remaining application delta is enumerated and classified as non-ADR-0043.

The tests are HERMETIC — they build a synthetic git repo with a governed path and a non-governed
path and run the real script against it. They deliberately do NOT depend on the live repo's
history: GitHub Actions checks out shallow (fetch-depth 1), so real historical SHAs are absent on
the runner. Testing the LOGIC in a synthetic repo is both CI-safe and a stronger test.

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

# One governed ADR-0043 path and one ordinary application path (both must exist for the script's
# hardcoded GOVERNED_PATHS list to have something to compare).
GOVERNED_FILE = "apps/backend/app/orders/settlement.py"
OTHER_FILE = "apps/backend/app/strategies/backtest_context.py"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="needs bash + git (the provenance proof is produced where .git exists)",
)


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return r.stdout.strip()


def _write(repo: Path, rel: str, content: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _commit(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path) -> Path:
    """A synthetic repo: BASELINE commit has the governed file + an ordinary file."""
    r = tmp_path / "syn"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "commit.gpgsign", "false")
    _write(r, GOVERNED_FILE, "SETTLEMENT V1\n")
    _write(r, OTHER_FILE, "other v1\n")
    return r


def _run(repo: Path, source_ref: str, impl_sha: str, out_sub: str = "dist"):
    import os
    env = {**os.environ, "ADR0043_IMPLEMENTATION_SHA": impl_sha}
    return subprocess.run(
        [BASH, str(SCRIPT), source_ref, out_sub],
        cwd=repo, capture_output=True, text=True, env=env, timeout=120,
    )


def _marker(repo: Path, out_sub: str = "dist") -> dict:
    return json.loads((repo / out_sub / "DEPLOYED_BUILD_INFO.json").read_text(encoding="utf-8"))


# (1) accepts the deployed SHA when governed paths match the implementation baseline -------------

def test_accepts_when_governed_paths_match_the_implementation_baseline(repo):
    base = _commit(repo, "baseline")
    _write(repo, OTHER_FILE, "other v2\n")        # non-governed change only
    deployed = _commit(repo, "reviewed non-adr0043 superset")

    r = _run(repo, deployed, impl_sha=base)
    assert r.returncode == 0, r.stdout + r.stderr
    m = _marker(repo)
    assert m["adr0043_governed_paths_match"] is True
    assert m["implementation_ancestry_verified"] is True
    assert m["reviewed_superset_delta_classification"] == "reviewed_non_adr0043_superset"
    assert OTHER_FILE in m["application_delta_after_adr0043_baseline"]
    assert GOVERNED_FILE not in m["application_delta_after_adr0043_baseline"]


# (1b) a baseline file EXCLUDED from the deploy is recorded as excluded, never as present ---------

def test_excluded_baseline_file_is_recorded_distinctly_not_as_present(repo):
    """A validation-box deploy may intentionally EXCLUDE reviewed work merged after the accepted
    superset. Such a file (present in the baseline, absent from the deploy) must be recorded under
    baseline_paths_excluded_from_deploy, and must NOT appear in the present-in-deploy delta — else
    the marker would imply the box carries a file it does not."""
    EXTRA = "apps/backend/app/strategies/extra_feature.py"
    _write(repo, EXTRA, "extra v1\n")
    base = _commit(repo, "baseline with an extra non-governed file")
    (repo / EXTRA).unlink()                       # deploy reverts/excludes the extra file
    _write(repo, OTHER_FILE, "other v2\n")        # and modifies another (present) non-governed file
    deployed = _commit(repo, "deploy excludes the extra file, modifies another")

    r = _run(repo, deployed, impl_sha=base)
    assert r.returncode == 0, r.stdout + r.stderr
    m = _marker(repo)
    assert m["adr0043_governed_paths_match"] is True
    assert EXTRA in m["baseline_paths_excluded_from_deploy"]
    assert EXTRA not in m["application_delta_after_adr0043_baseline"]
    assert OTHER_FILE in m["application_delta_after_adr0043_baseline"]   # modified & present
    assert OTHER_FILE not in m["baseline_paths_excluded_from_deploy"]


# (2) rejects a target that changes a governed file after the baseline --------------------------

def test_rejects_a_target_that_changes_a_governed_path_after_the_baseline(repo):
    base = _commit(repo, "baseline")
    _write(repo, GOVERNED_FILE, "SETTLEMENT V2 — unreviewed change\n")
    deployed = _commit(repo, "governed path changed after baseline")

    r = _run(repo, deployed, impl_sha=base)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "governed ADR-0043 path" in (r.stdout + r.stderr)
    assert "settlement.py" in (r.stdout + r.stderr)
    assert not (repo / "dist" / "DEPLOYED_BUILD_INFO.json").exists()


# (3) a governed path is never classified into the non-ADR-0043 superset ------------------------

def test_a_governed_path_is_never_classified_into_the_non_adr0043_superset(repo):
    base = _commit(repo, "baseline")
    _write(repo, GOVERNED_FILE, "SETTLEMENT V2\n")
    _write(repo, OTHER_FILE, "other v2\n")
    deployed = _commit(repo, "both governed and non-governed changed")

    r = _run(repo, deployed, impl_sha=base)
    # the governed-path invariant fires first — no manifest, no misclassification
    assert r.returncode == 3
    assert not (repo / "dist" / "DEPLOYED_BUILD_INFO.json").exists()


# (4) rejects a target where the implementation baseline is not an ancestor ----------------------

def test_rejects_when_the_implementation_baseline_is_not_an_ancestor(repo):
    earlier = _commit(repo, "earlier")
    _write(repo, OTHER_FILE, "other v2\n")
    later = _commit(repo, "later — becomes the baseline")
    # deploy the EARLIER commit with the LATER commit as the baseline: later is not an ancestor.
    r = _run(repo, earlier, impl_sha=later)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "NOT an ancestor" in (r.stdout + r.stderr)


# (5) rejects a moving ref, and rejects an omitted explicit SHA ----------------------------------

def test_rejects_a_moving_branch_ref(repo):
    base = _commit(repo, "baseline")
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")   # the current branch name
    r = _run(repo, branch, impl_sha=base)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "moving ref" in (r.stdout + r.stderr)


def test_rejects_an_omitted_source_sha(repo):
    _commit(repo, "baseline")
    r = subprocess.run([BASH, str(SCRIPT)], cwd=repo, capture_output=True, text=True, timeout=60)
    assert r.returncode == 1
    assert "EXPLICIT approved commit SHA" in (r.stdout + r.stderr)


# (6) the marker records BOTH identities, distinctly -------------------------------------------

def test_marker_records_both_implementation_and_deployed_identities(repo):
    base = _commit(repo, "baseline")
    _write(repo, OTHER_FILE, "other v2\n")
    deployed = _commit(repo, "superset")

    r = _run(repo, deployed, impl_sha=base)
    assert r.returncode == 0, r.stdout + r.stderr
    m = _marker(repo)
    assert m["deployed_repository_commit"] == deployed
    assert m["adr0043_implementation_commit"] == base
    # the historical PR8 baseline is recorded as a third, distinct identity
    assert "adr0043_original_baseline_commit" in m
    assert m["deployed_repository_commit"] != m["adr0043_implementation_commit"]
