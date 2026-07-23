"""ADR-0043 deploy-provenance guard — proven against curated and contaminated trees.

A gate that only ever passes is a gate that checks nothing, so every rule here is exercised in both
directions: a synthetic CURATED history (implementation baseline -> prior deploy -> curated commit
that adds exactly the approved delta) yields zero violations, and a matching CONTAMINATED history —
an extra apps/** path, a changed migration, a swapped blob, a wrong source, a broken ancestor —
yields the specific violation. Two real-repo tests close the loop against the actual reviewed tree
(07d3b82) and the actual full-main squash commit (ea6db6e) the guard exists to refuse.

The synthetic cases build real git repositories (deterministic authorship) rather than mocking git,
because the whole value of the guard is that it agrees with git's own notion of blobs and ancestry.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

# The guard lives in deploy/aws, outside the package tree — load it by path.
REPO_ROOT = Path(__file__).resolve().parents[4]
GUARD_PATH = REPO_ROOT / "deploy" / "aws" / "verify_deploy_provenance.py"
REAL_MANIFEST = REPO_ROOT / "deploy" / "aws" / "adr0043_deploy_manifest.json"

_spec = importlib.util.spec_from_file_location("verify_deploy_provenance", GUARD_PATH)
guard = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
# Register before exec so the module's frozen-annotation dataclass can resolve its own module.
sys.modules["verify_deploy_provenance"] = guard
_spec.loader.exec_module(guard)


# ---------------------------------------------------------------------------- synthetic git repos

_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
}


def _run(repo: Path, *args: str) -> str:
    import os

    env = {**os.environ, **_ENV}
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env)
    assert out.returncode == 0, f"git {args} failed: {out.stderr}"
    return out.stdout.strip()


def _write(repo: Path, rel: str, content: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _commit(repo: Path, msg: str) -> str:
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", msg)
    return _run(repo, "rev-parse", "HEAD")


def _blob(repo: Path, ref: str, path: str) -> str:
    return _run(repo, "rev-parse", f"{ref}:{path}")


# The approved delta the curated commit introduces on top of the prior deploy.
APP_FILES = {
    "apps/backend/app/orders/settlement.py": "# settlement barrier\n",
    "apps/backend/scripts/check_settlement_barrier.sh": "#!/usr/bin/env bash\n",
    "apps/backend/tests/orders/test_settlement.py": "# tests\n",
}
OP_FILES = {
    "CLAUDE.md": "# conventions\n",
    "scripts/reconcile_stuck_orders.py": "# reconcile\n",
}


@pytest.fixture
def curated(tmp_path: Path) -> dict:
    """A CURATED history: impl baseline -> prior deploy (0 apps delta) -> curated (adds the approved
    delta and nothing else). Returns the repo path, the three SHAs, and a matching manifest."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init", "-q")
    _run(repo, "config", "commit.gpgsign", "false")

    # impl baseline — the pre-existing risk-path tree + a migration that must NEVER change.
    _write(repo, "apps/backend/app/risk/engine.py", "# engine\n")
    _write(repo, "apps/backend/alembic/versions/0001_init.py", "# init migration\n")
    _write(repo, "README.md", "base\n")
    impl = _commit(repo, "impl baseline")

    # prior deploy — a doc-only change (0 apps delta), mirroring 80a6c043 vs c8b3ac24.
    _write(repo, "docs/deploy.md", "prior\n")
    prior = _commit(repo, "prior deploy")

    # curated — adds exactly the approved application + operational delta.
    for rel, content in {**APP_FILES, **OP_FILES}.items():
        _write(repo, rel, content)
    validation = _commit(repo, "curated settlement-barrier baseline")

    manifest = {
        "implementation_baseline": impl,
        "prior_deploy_baseline": prior,
        "validation_executable_baseline": validation,
        "migration_delta_allowed": False,
        "migration_path_globs": ["apps/backend/alembic/versions/"],
        "approved_application_paths": {p: _blob(repo, validation, p) for p in APP_FILES},
        "approved_operational_paths": {p: _blob(repo, validation, p) for p in OP_FILES},
    }
    return {"repo": repo, "impl": impl, "prior": prior, "validation": validation,
            "manifest": manifest}


# ---------------------------------------------------------------------------- the happy path


def test_curated_source_passes_clean(curated):
    v = guard.verify(curated["validation"], curated["manifest"], curated["repo"])
    assert v == [], [x.detail for x in v]


# ---------------------------------------------------------------------------- rule 1: exact source


def test_source_that_is_not_the_curated_commit_is_refused(curated):
    # The prior-deploy commit is a real, valid commit — but it is NOT the curated baseline.
    v = guard.verify(curated["prior"], curated["manifest"], curated["repo"])
    assert [x.rule for x in v] == ["source-not-curated-commit"]


def test_unresolvable_source_is_refused(curated):
    v = guard.verify("does-not-exist", curated["manifest"], curated["repo"])
    assert [x.rule for x in v] == ["source-unresolved"]


def test_building_from_a_branch_ref_that_is_not_the_baseline_is_refused(curated):
    # Simulate "build from main": a branch whose tip is a DIFFERENT commit than the baseline.
    _write(curated["repo"], "apps/backend/app/extra.py", "# drifted\n")
    _run(curated["repo"], "checkout", "-q", "-b", "main")
    _commit(curated["repo"], "main advances")
    v = guard.verify("main", curated["manifest"], curated["repo"])
    assert [x.rule for x in v] == ["source-not-curated-commit"]


# ---------------------------------------------------------------------------- rule 2: lineage


def test_broken_implementation_ancestry_is_refused(curated):
    # Point the impl baseline at an unrelated root commit (not an ancestor of the baseline).
    orphan = curated["repo"] / "orphan"
    orphan.mkdir()
    _run(orphan, "init", "-q")
    _run(orphan, "config", "commit.gpgsign", "false")
    _write(orphan, "x", "y")
    unrelated = _commit(orphan, "unrelated")
    # Fetch the orphan commit into the main repo so it resolves but is not an ancestor.
    _run(curated["repo"], "fetch", "-q", str(orphan), unrelated)
    m = {**curated["manifest"], "implementation_baseline": unrelated}
    v = guard.verify(curated["validation"], m, curated["repo"])
    assert any(x.rule == "lineage-broken" for x in v)


# ---------------------------------------------------------------------------- rules 3/4: delta


def test_an_extra_apps_path_in_the_delta_is_refused(curated):
    # A curated tree that ALSO changed an unrelated risk-path file — the ea6db6e failure mode.
    repo, prior = curated["repo"], curated["prior"]
    _run(repo, "checkout", "-q", prior)
    for rel, content in {**APP_FILES, **OP_FILES}.items():
        _write(repo, rel, content)
    _write(repo, "apps/backend/app/risk/decision_service.py", "# UNRELATED risk change\n")
    contaminated = _commit(repo, "curated + unrelated risk-path change")
    m = {**curated["manifest"], "validation_executable_baseline": contaminated}
    m["approved_application_paths"] = {p: _blob(repo, contaminated, p) for p in APP_FILES}
    m["approved_operational_paths"] = {p: _blob(repo, contaminated, p) for p in OP_FILES}
    v = guard.verify(contaminated, m, repo)
    assert any(x.rule == "unapproved-application-path"
               and "decision_service.py" in x.detail for x in v)


def test_a_changed_migration_is_refused(curated):
    repo, prior = curated["repo"], curated["prior"]
    _run(repo, "checkout", "-q", prior)
    for rel, content in {**APP_FILES, **OP_FILES}.items():
        _write(repo, rel, content)
    _write(repo, "apps/backend/alembic/versions/0002_new.py", "# NEW migration rides in\n")
    contaminated = _commit(repo, "curated + a new migration")
    m = {**curated["manifest"], "validation_executable_baseline": contaminated}
    m["approved_application_paths"] = {p: _blob(repo, contaminated, p) for p in APP_FILES}
    m["approved_operational_paths"] = {p: _blob(repo, contaminated, p) for p in OP_FILES}
    v = guard.verify(contaminated, m, repo)
    assert any(x.rule == "migration-changed" and "0002_new.py" in x.detail for x in v)


def test_an_extra_operational_path_in_the_delta_is_refused(curated):
    repo, prior = curated["repo"], curated["prior"]
    _run(repo, "checkout", "-q", prior)
    for rel, content in {**APP_FILES, **OP_FILES}.items():
        _write(repo, rel, content)
    _write(repo, "deploy/aws/some_other_tool.sh", "# not in the inventory\n")
    contaminated = _commit(repo, "curated + extra operational file")
    m = {**curated["manifest"], "validation_executable_baseline": contaminated}
    m["approved_application_paths"] = {p: _blob(repo, contaminated, p) for p in APP_FILES}
    m["approved_operational_paths"] = {p: _blob(repo, contaminated, p) for p in OP_FILES}
    v = guard.verify(contaminated, m, repo)
    assert any(x.rule == "unapproved-operational-path" for x in v)


# ---------------------------------------------------------------------------- rule 5: blob-exact


def test_an_approved_path_at_the_wrong_revision_is_refused(curated):
    # Path membership is fine; the CONTENT is a different revision than the frozen manifest blob.
    m = {**curated["manifest"],
         "approved_application_paths": {**curated["manifest"]["approved_application_paths"]}}
    victim = "apps/backend/app/orders/settlement.py"
    m["approved_application_paths"][victim] = "0" * 40  # frozen blob that does not match the tree
    v = guard.verify(curated["validation"], m, curated["repo"])
    assert any(x.rule == "blob-mismatch" and victim in x.detail for x in v)


def test_a_missing_approved_path_is_refused(curated):
    m = {**curated["manifest"],
         "approved_application_paths": {**curated["manifest"]["approved_application_paths"],
                                        "apps/backend/app/orders/not_present.py": "0" * 40}}
    v = guard.verify(curated["validation"], m, curated["repo"])
    assert any(x.rule == "approved-path-missing" for x in v)


# ---------------------------------------------------------------------------- rule 6: manifest


def test_missing_manifest_file_is_a_refusal(tmp_path):
    with pytest.raises(guard.ManifestError, match="not found"):
        guard.load_manifest(tmp_path / "nope.json")


def test_malformed_manifest_json_is_a_refusal(tmp_path):
    p = tmp_path / "m.json"
    p.write_text("{ not json", encoding="utf-8")
    with pytest.raises(guard.ManifestError, match="not valid JSON"):
        guard.load_manifest(p)


def test_manifest_missing_a_required_field_is_a_refusal(tmp_path, curated):
    p = tmp_path / "m.json"
    incomplete = {k: v for k, v in curated["manifest"].items()
                  if k != "validation_executable_baseline"}
    p.write_text(json.dumps(incomplete), encoding="utf-8")
    with pytest.raises(guard.ManifestError, match="missing required field"):
        guard.load_manifest(p)


def test_empty_application_inventory_is_a_refusal(tmp_path, curated):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({**curated["manifest"], "approved_application_paths": {}}),
                 encoding="utf-8")
    with pytest.raises(guard.ManifestError, match="non-empty"):
        guard.load_manifest(p)


# ---------------------------------------------------------------------------- real repo, both ways


@pytest.mark.skipif(not REAL_MANIFEST.exists(), reason="real manifest absent")
def test_the_real_curated_baseline_passes_the_real_manifest():
    """The actual reviewed tree (07d3b82) against the committed manifest — zero violations."""
    manifest = guard.load_manifest(REAL_MANIFEST)
    baseline = manifest["validation_executable_baseline"]
    if guard.resolve_commit(REPO_ROOT, baseline) is None:
        pytest.skip("validation executable baseline not present in this checkout")
    v = guard.verify(baseline, manifest, REPO_ROOT)
    assert v == [], [x.detail for x in v]


@pytest.mark.skipif(not REAL_MANIFEST.exists(), reason="real manifest absent")
def test_the_full_main_squash_commit_is_refused():
    """ea6db6e — the full origin/main tip carrying ADR-0044, a new migration, momentum-daily and
    risk-path deltas — must be refused as a source. This is the exact contamination the amendment
    exists to keep out of the ENFORCE box."""
    manifest = guard.load_manifest(REAL_MANIFEST)
    ea6db6e = "ea6db6e6d5dc338196ffca9919a7a2e2643e1f6c"
    if guard.resolve_commit(REPO_ROOT, ea6db6e) is None:
        pytest.skip("governance merge commit not present in this checkout")
    v = guard.verify(ea6db6e, manifest, REPO_ROOT)
    assert any(x.rule == "source-not-curated-commit" for x in v)
