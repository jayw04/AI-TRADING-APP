"""Falsification suite for the three-source deployment identity (CONTAINER_ATTESTED).

The existing suite covers the declared sources. This one exists because production falsified them: on
2026-08-26 the backend image was rebuilt at 20:23:02Z while `.deploy_src_sha` and
`DEPLOYED_BUILD_INFO.json` went on declaring the previous commit. Every source in that picture was an
*assertion*, and assertions survive the thing they describe.

So the tests below are written against one property: **an identity that can be satisfied by writing a
file is not an identity.** Each mutation is applied to exactly one source, and each must refuse.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.validation.deployment_identity import (
    CODE_DIGEST_SCHEMA,
    DeploymentEvidenceMismatch,
    DeploymentEvidenceMissing,
    DeploymentModel,
    derive_runtime_code_digest,
    verify_deployment_identity,
)

COMMIT_A = "a" * 40
COMMIT_B = "b" * 40
DIGEST_A = "sha256:" + "1" * 64
DIGEST_B = "sha256:" + "2" * 64


def _tree(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for relative, body in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return root


@pytest.fixture
def deployment(tmp_path):
    """A complete, self-consistent CONTAINER_ATTESTED deployment: A / A / A."""
    code = _tree(tmp_path / "app", {
        "main.py": "VALUE = 1\n",
        "pkg/mod.py": "def f():\n    return 1\n",
        "pkg/__init__.py": "",
    })
    code_digest = derive_runtime_code_digest(code)

    build = tmp_path / "build_info.json"
    build.write_text(json.dumps({
        "commit": COMMIT_A, "tree_clean": True,
        "image_digest": DIGEST_A, "code_digest": code_digest,
    }), encoding="utf-8")

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"commit": COMMIT_A, "image_digest": DIGEST_A}), encoding="utf-8")

    runtime = tmp_path / "runtime_digest"
    runtime.write_text(DIGEST_A, encoding="utf-8")

    return {"root": tmp_path, "code": code, "build": build,
            "manifest": manifest, "runtime": runtime, "code_digest": code_digest}


def _verify(deployment, **overrides):
    kw = {
        "model": DeploymentModel.CONTAINER_ATTESTED,
        "build_info_path": deployment["build"],
        "deployment_manifest_path": deployment["manifest"],
        "runtime_digest_path": deployment["runtime"],
        "runtime_tree_root": deployment["code"],
    }
    kw.update(overrides)
    return verify_deployment_identity(**kw)


# ── A / A / A ────────────────────────────────────────────────────────────────────────────────────

def test_three_agreeing_sources_verify(deployment):
    evidence = _verify(deployment)
    assert evidence.agreed_commit == COMMIT_A
    assert evidence.runtime_code_digest == deployment["code_digest"]
    assert evidence.embedded_code_digest == deployment["code_digest"]


def test_the_derived_digest_is_marked_as_derived_not_declared(deployment):
    evidence = _verify(deployment)
    assert evidence.runtime_code_source.startswith("derived:")
    # The declared and derived runtime sources stay separate fields; collapsing them would let the
    # declaration stand in for the derivation.
    assert evidence.runtime_digest_source != evidence.runtime_code_source


# ── single-source mutation: each must refuse ─────────────────────────────────────────────────────

def test_mutating_the_embedded_build_stamp_refuses(deployment):
    deployment["build"].write_text(json.dumps({
        "commit": COMMIT_B, "tree_clean": True,
        "image_digest": DIGEST_A, "code_digest": deployment["code_digest"],
    }), encoding="utf-8")
    with pytest.raises(DeploymentEvidenceMismatch):
        _verify(deployment)


def test_mutating_the_running_artifact_refuses(deployment):
    (deployment["code"] / "pkg" / "mod.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    with pytest.raises(DeploymentEvidenceMismatch, match="not the built code"):
        _verify(deployment)


def test_adding_a_file_to_the_running_tree_refuses(deployment):
    (deployment["code"] / "pkg" / "extra.py").write_text("BACKDOOR = True\n", encoding="utf-8")
    with pytest.raises(DeploymentEvidenceMismatch, match="not the built code"):
        _verify(deployment)


def test_removing_a_file_from_the_running_tree_refuses(deployment):
    (deployment["code"] / "pkg" / "mod.py").unlink()
    with pytest.raises(DeploymentEvidenceMismatch, match="not the built code"):
        _verify(deployment)


def test_mutating_the_deployment_manifest_refuses(deployment):
    deployment["manifest"].write_text(
        json.dumps({"commit": COMMIT_B, "image_digest": DIGEST_A}), encoding="utf-8")
    with pytest.raises(DeploymentEvidenceMismatch):
        _verify(deployment)


def test_mutating_the_declared_runtime_digest_refuses(deployment):
    deployment["runtime"].write_text(DIGEST_B, encoding="utf-8")
    with pytest.raises(DeploymentEvidenceMismatch):
        _verify(deployment)


# ── removing each source independently: missing, not mismatched ──────────────────────────────────

def test_removing_the_build_stamp_is_missing_evidence(deployment):
    deployment["build"].unlink()
    with pytest.raises(DeploymentEvidenceMissing):
        _verify(deployment)


def test_removing_the_manifest_is_missing_evidence(deployment):
    deployment["manifest"].unlink()
    with pytest.raises(DeploymentEvidenceMissing):
        _verify(deployment)


def test_removing_the_declared_runtime_digest_is_missing_evidence(deployment):
    deployment["runtime"].unlink()
    with pytest.raises(DeploymentEvidenceMissing):
        _verify(deployment, runtime_digest_env="A_VARIABLE_THAT_IS_NOT_SET")


def test_removing_the_running_code_tree_is_missing_evidence(deployment):
    with pytest.raises(DeploymentEvidenceMissing):
        _verify(deployment, runtime_tree_root=deployment["root"] / "absent")


def test_supplying_no_code_tree_at_all_is_missing_evidence(deployment):
    with pytest.raises(DeploymentEvidenceMissing, match="DECLARED digest alone"):
        _verify(deployment, runtime_tree_root=None)


def test_a_build_stamp_without_a_code_digest_is_missing_evidence(deployment):
    deployment["build"].write_text(json.dumps({
        "commit": COMMIT_A, "tree_clean": True, "image_digest": DIGEST_A,
    }), encoding="utf-8")
    with pytest.raises(DeploymentEvidenceMissing, match="no code_digest"):
        _verify(deployment)


def test_an_empty_code_tree_is_refused_rather_than_hashed(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(DeploymentEvidenceMissing, match="empty traversal"):
        derive_runtime_code_digest(empty)


# ── runtime A vs runtime B ───────────────────────────────────────────────────────────────────────

def test_two_complete_runtimes_derive_different_identities(tmp_path):
    a = _tree(tmp_path / "a", {"main.py": "VALUE = 1\n"})
    b = _tree(tmp_path / "b", {"main.py": "VALUE = 2\n"})
    assert derive_runtime_code_digest(a) != derive_runtime_code_digest(b)


def test_identical_content_at_a_different_root_derives_the_same_identity(tmp_path):
    a = _tree(tmp_path / "a", {"main.py": "VALUE = 1\n", "pkg/mod.py": "X = 0\n"})
    b = _tree(tmp_path / "b", {"main.py": "VALUE = 1\n", "pkg/mod.py": "X = 0\n"})
    # The identity is of the CODE, not of where it happens to be mounted.
    assert derive_runtime_code_digest(a) == derive_runtime_code_digest(b)


def test_a_moved_file_changes_the_identity(tmp_path):
    a = _tree(tmp_path / "a", {"pkg/mod.py": "X = 0\n"})
    b = _tree(tmp_path / "b", {"other/mod.py": "X = 0\n"})
    # Same bytes, different path: the framing must not let one masquerade as the other.
    assert derive_runtime_code_digest(a) != derive_runtime_code_digest(b)


def test_pycache_does_not_affect_the_identity(deployment):
    before = derive_runtime_code_digest(deployment["code"])
    cache = deployment["code"] / "pkg" / "__pycache__"
    cache.mkdir()
    (cache / "mod.cpython-312.pyc").write_bytes(b"\x00\x01compiled")
    assert derive_runtime_code_digest(deployment["code"]) == before


def test_the_digest_is_stable_across_repeated_derivation(deployment):
    assert derive_runtime_code_digest(deployment["code"]) == deployment["code_digest"]


def test_the_schema_is_bound_into_the_digest():
    assert CODE_DIGEST_SCHEMA == "workbench-code-digest/1"


# ── the operator pin may narrow, never substitute ────────────────────────────────────────────────

def test_a_matching_pin_is_accepted(deployment):
    assert _verify(deployment, expected_commit=COMMIT_A).agreed_commit == COMMIT_A


def test_a_conflicting_pin_is_a_mismatch(deployment):
    with pytest.raises(DeploymentEvidenceMismatch):
        _verify(deployment, expected_commit=COMMIT_B)


def test_a_pin_cannot_substitute_for_a_missing_source(deployment):
    """The pin is not evidence. Removing a source and pinning the 'right' commit must still refuse."""
    deployment["build"].unlink()
    with pytest.raises(DeploymentEvidenceMissing):
        _verify(deployment, expected_commit=COMMIT_A)


def test_a_pin_cannot_rescue_a_mutated_runtime(deployment):
    (deployment["code"] / "main.py").write_text("VALUE = 999\n", encoding="utf-8")
    with pytest.raises(DeploymentEvidenceMismatch):
        _verify(deployment, expected_commit=COMMIT_A)


# ── the 2026-08-26 production failure shape ──────────────────────────────────────────────────────

def test_the_2026_08_26_shape_fails_closed_and_is_never_read_as_unchanged(tmp_path):
    """Regression: manifest/pin declares the OLD commit; the runtime is a rebuilt artifact.

    This is what actually happened on the box. The sampler ran on one image; the backend was rebuilt
    at 20:23:02Z; `.deploy_src_sha` and `DEPLOYED_BUILD_INFO.json` both continued to declare
    `07a9233`. Under a pin-only check the deployment reads as *unchanged*, which is the single most
    dangerous possible answer. Here it must refuse.
    """
    running = _tree(tmp_path / "app", {"main.py": "REBUILT = True\n"})
    rebuilt_code_digest = derive_runtime_code_digest(running)

    # The artifact honestly stamps what it is: the NEW commit, and the rebuilt tree.
    build = tmp_path / "build_info.json"
    build.write_text(json.dumps({
        "commit": COMMIT_B, "tree_clean": True,
        "image_digest": DIGEST_B, "code_digest": rebuilt_code_digest,
    }), encoding="utf-8")

    # The deploy-written manifest was never updated: it still declares the OLD deployment.
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"commit": COMMIT_A, "image_digest": DIGEST_A}), encoding="utf-8")

    runtime = tmp_path / "runtime_digest"
    runtime.write_text(DIGEST_B, encoding="utf-8")

    with pytest.raises(DeploymentEvidenceMismatch) as stop:
        verify_deployment_identity(
            model=DeploymentModel.CONTAINER_ATTESTED,
            build_info_path=build,
            deployment_manifest_path=manifest,
            runtime_digest_path=runtime,
            runtime_tree_root=running,
        )
    assert "was not deployed" in str(stop.value)


def test_the_2026_08_26_shape_still_fails_when_the_stale_pin_is_supplied_as_expected(tmp_path):
    """The operator 'knows' the box is on the old commit and pins it. That must not manufacture a PASS."""
    running = _tree(tmp_path / "app", {"main.py": "REBUILT = True\n"})
    build = tmp_path / "build_info.json"
    build.write_text(json.dumps({
        "commit": COMMIT_B, "tree_clean": True, "image_digest": DIGEST_B,
        "code_digest": derive_runtime_code_digest(running),
    }), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"commit": COMMIT_A, "image_digest": DIGEST_A}), encoding="utf-8")
    runtime = tmp_path / "runtime_digest"
    runtime.write_text(DIGEST_B, encoding="utf-8")

    with pytest.raises(DeploymentEvidenceMismatch):
        verify_deployment_identity(
            model=DeploymentModel.CONTAINER_ATTESTED,
            build_info_path=build,
            deployment_manifest_path=manifest,
            runtime_digest_path=runtime,
            runtime_tree_root=running,
            expected_commit=COMMIT_A,
        )


def test_a_hand_repaired_manifest_still_cannot_hide_a_changed_runtime(tmp_path):
    """Close the obvious workaround: someone 'fixes' the manifest to match the stamp, but the running
    tree has drifted from what was built. The derived source is the only thing left that can tell."""
    running = _tree(tmp_path / "app", {"main.py": "VALUE = 1\n"})
    built_digest = derive_runtime_code_digest(running)
    (running / "main.py").write_text("VALUE = 1  # hotfixed in place\n", encoding="utf-8")

    build = tmp_path / "build_info.json"
    build.write_text(json.dumps({
        "commit": COMMIT_A, "tree_clean": True,
        "image_digest": DIGEST_A, "code_digest": built_digest,
    }), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"commit": COMMIT_A, "image_digest": DIGEST_A}), encoding="utf-8")
    runtime = tmp_path / "runtime_digest"
    runtime.write_text(DIGEST_A, encoding="utf-8")

    # Every declared source agrees with every other declared source. Only the derivation disagrees.
    with pytest.raises(DeploymentEvidenceMismatch, match="not the built code"):
        verify_deployment_identity(
            model=DeploymentModel.CONTAINER_ATTESTED,
            build_info_path=build,
            deployment_manifest_path=manifest,
            runtime_digest_path=runtime,
            runtime_tree_root=running,
        )


# ── no environment-supplied identity ─────────────────────────────────────────────────────────────

def test_no_environment_variable_can_supply_the_code_identity(deployment, monkeypatch):
    """There is deliberately no env path for the derived source. Setting plausible variables must not
    change the outcome for a mutated runtime."""
    (deployment["code"] / "main.py").write_text("VALUE = 42\n", encoding="utf-8")
    for name in ("WORKBENCH_CODE_VERSION", "WORKBENCH_CODE_DIGEST", "DEPLOY_SRC_SHA"):
        monkeypatch.setenv(name, deployment["code_digest"])
    with pytest.raises(DeploymentEvidenceMismatch, match="not the built code"):
        _verify(deployment)


def test_the_declared_runtime_digest_cannot_stand_in_for_the_derivation(deployment):
    """A correct declared image digest must not rescue a runtime whose code has changed."""
    (deployment["code"] / "main.py").write_text("VALUE = 7\n", encoding="utf-8")
    assert deployment["runtime"].read_text(encoding="utf-8").strip() == DIGEST_A
    with pytest.raises(DeploymentEvidenceMismatch, match="not the built code"):
        _verify(deployment)


# ── the pre-existing models keep their behaviour ─────────────────────────────────────────────────

def test_the_container_model_is_unchanged_and_needs_no_code_tree(deployment):
    evidence = verify_deployment_identity(
        model=DeploymentModel.CONTAINER,
        build_info_path=deployment["build"],
        deployment_manifest_path=deployment["manifest"],
        runtime_digest_path=deployment["runtime"],
    )
    assert evidence.agreed_commit == COMMIT_A
    assert evidence.runtime_code_digest is None
