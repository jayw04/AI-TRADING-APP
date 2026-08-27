"""End-to-end: build producer -> deploy evidence -> runtime derivation -> verifier.

The unit suite proves each source refuses when mutated. This one proves the legs actually *connect* —
that the value the build stamps is the value the runtime derives, over the same scope, through the same
canonicalization.

That connection is the part that was missing on 2026-08-26. Every declaration in
`DEPLOYED_BUILD_INFO.json` was internally consistent; nothing computed anything from the code that was
actually running, so nothing could disagree.

⚠ These tests drive the REAL producer (`scripts/compute_deploy_code_digest.py`) against a real git
repository and a real `git archive` extraction, because the whole property under test is agreement
between two independently written collectors. A fixture that called only one of them would prove
nothing.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from app.validation.deployment_identity import (
    DeploymentEvidenceMismatch,
    DeploymentEvidenceMissing,
    DeploymentModel,
    derive_runtime_code_digest,
    verify_deployment_identity,
)

PRODUCER = Path(__file__).resolve().parents[2] / "scripts" / "compute_deploy_code_digest.py"
IMAGE_DIGEST = "sha256:" + "3" * 64


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(("git", *args), cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout.strip()


@pytest.fixture
def deployed(tmp_path):
    """A real repo with `apps/backend/app`, archived and extracted the way the box does it."""
    repo = tmp_path / "repo"
    (repo / "apps/backend/app/validation").mkdir(parents=True)
    # ⚠ Mirrors the real repository's DEPLOY-EOL DETERMINISM rule. Without it, a Windows build host
    # with core.autocrlf=true makes `git archive` emit CRLF while the blobs hold LF, and the two sides
    # disagree for a reason that has nothing to do with the code. Production pins eol=lf; a fixture
    # that omitted it would be testing a repository unlike the one that ships.
    (repo / ".gitattributes").write_text("* text=auto eol=lf\n", encoding="utf-8")
    (repo / "apps/backend/app/main.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "apps/backend/app/validation/thing.py").write_text("def f():\n    return 1\n",
                                                               encoding="utf-8")
    # Present in the repo but outside the digest scope: must not perturb either side.
    (repo / "apps/backend/app/notes.md").write_text("not code\n", encoding="utf-8")

    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "t@example.com", cwd=repo)
    _git("config", "user.name", "T", cwd=repo)
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "deployed tree", cwd=repo)
    sha = _git("rev-parse", "HEAD", cwd=repo)

    # The producer, run exactly as build-deploy-archive.sh runs it.
    produced = subprocess.run(
        (sys.executable, str(PRODUCER), "--repo", str(repo), "--ref", sha),
        capture_output=True, text=True)
    assert produced.returncode == 0, produced.stderr
    code_digest = produced.stdout.strip()

    # `git archive` + extract — the box's actual delivery path.
    archive = tmp_path / "source.tar"
    with archive.open("wb") as handle:
        subprocess.run(("git", "archive", "--format=tar", sha), cwd=repo, stdout=handle, check=True)
    extracted = tmp_path / "opt"
    extracted.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(extracted)          # noqa: S202 - fixture-controlled archive
    runtime_root = extracted / "apps/backend/app"

    build = tmp_path / "build_info.json"
    build.write_text(json.dumps({
        "commit": sha, "tree_clean": True,
        "image_digest": IMAGE_DIGEST, "code_digest": code_digest,
    }), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"commit": sha, "image_digest": IMAGE_DIGEST}), encoding="utf-8")
    runtime_digest = tmp_path / "runtime_digest"
    runtime_digest.write_text(IMAGE_DIGEST, encoding="utf-8")

    return {"repo": repo, "sha": sha, "code_digest": code_digest, "runtime_root": runtime_root,
            "build": build, "manifest": manifest, "runtime_digest": runtime_digest}


def _verify(deployed, **overrides):
    kw = {
        "model": DeploymentModel.CONTAINER_ATTESTED,
        "build_info_path": deployed["build"],
        "deployment_manifest_path": deployed["manifest"],
        "runtime_digest_path": deployed["runtime_digest"],
        "runtime_tree_root": deployed["runtime_root"],
    }
    kw.update(overrides)
    return verify_deployment_identity(**kw)


def test_the_producer_and_the_runtime_derive_the_same_value(deployed):
    """★ The parity property. Build-time reads git blobs; runtime reads the extracted archive."""
    assert derive_runtime_code_digest(deployed["runtime_root"]) == deployed["code_digest"]


def test_the_full_chain_verifies(deployed):
    evidence = _verify(deployed)
    assert evidence.agreed_commit == deployed["sha"]
    assert evidence.runtime_code_digest == deployed["code_digest"]
    assert evidence.runtime_code_source.startswith("derived:")


def test_a_non_code_file_does_not_affect_either_side(deployed):
    """`notes.md` is inside the deployed tree but outside the scope. Both collectors must ignore it,
    or the two sides would disagree for a reason unrelated to the code."""
    (deployed["runtime_root"] / "notes.md").write_text("edited after deploy\n", encoding="utf-8")
    assert _verify(deployed).runtime_code_digest == deployed["code_digest"]


def test_mutating_the_runtime_after_the_stamp_refuses(deployed):
    """★ REQUIRED: the 2026-08-26 shape, end to end. The stamp was produced honestly; the runtime then
    moved. Every declaration still agrees. The derivation must be what catches it."""
    (deployed["runtime_root"] / "main.py").write_text("VALUE = 999\n", encoding="utf-8")
    with pytest.raises(DeploymentEvidenceMismatch, match="not the built code"):
        _verify(deployed)


def test_adding_a_file_to_the_deployed_runtime_refuses(deployed):
    (deployed["runtime_root"] / "validation" / "injected.py").write_text("X = 1\n", encoding="utf-8")
    with pytest.raises(DeploymentEvidenceMismatch, match="not the built code"):
        _verify(deployed)


def test_a_marker_without_code_digest_refuses_rather_than_skipping_the_check(deployed):
    """A pre-Amendment-8 marker must not silently verify under the attested model."""
    payload = json.loads(deployed["build"].read_text(encoding="utf-8"))
    payload.pop("code_digest")
    deployed["build"].write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DeploymentEvidenceMissing, match="no code_digest"):
        _verify(deployed)


def test_the_producer_refuses_an_empty_scope(deployed):
    """Fail closed rather than stamping the digest of nothing."""
    produced = subprocess.run(
        (sys.executable, str(PRODUCER), "--repo", str(deployed["repo"]),
         "--ref", deployed["sha"], "--prefix", "apps/backend/does_not_exist"),
        capture_output=True, text=True)
    assert produced.returncode == 1
    assert "empty tree" in produced.stderr


def test_the_producer_is_stable_across_runs(deployed):
    again = subprocess.run(
        (sys.executable, str(PRODUCER), "--repo", str(deployed["repo"]), "--ref", deployed["sha"]),
        capture_output=True, text=True)
    assert again.returncode == 0
    assert again.stdout.strip() == deployed["code_digest"]


def test_a_different_commit_stamps_a_different_identity(deployed):
    (deployed["repo"] / "apps/backend/app/main.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git("add", "-A", cwd=deployed["repo"])
    _git("commit", "-q", "-m", "second", cwd=deployed["repo"])
    second = _git("rev-parse", "HEAD", cwd=deployed["repo"])
    produced = subprocess.run(
        (sys.executable, str(PRODUCER), "--repo", str(deployed["repo"]), "--ref", second),
        capture_output=True, text=True)
    assert produced.returncode == 0
    assert produced.stdout.strip() != deployed["code_digest"]
