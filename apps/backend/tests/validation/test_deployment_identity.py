"""Deployed-tree identity (R5c-2b) — three identities, kept distinct, required to agree.

A `deployed_tree_identity` that is whatever string the caller passed evidences nothing. These tests pin
that the value is derived from the deployment's own sources, that missing evidence and mismatched
evidence are DIFFERENT stops, and that a dirty build tree is refused outright.
"""

from __future__ import annotations

import json

import pytest

from app.validation.deployment_identity import (
    DeploymentEvidenceMismatch,
    DeploymentEvidenceMissing,
    DeploymentModel,
    verify_deployment_identity,
)

COMMIT = "b0058bf335628f8dbde09a93915314f3a1f7743b"
OTHER_COMMIT = "a" * 40
DIGEST = "sha256:" + "b" * 64
OTHER_DIGEST = "sha256:" + "c" * 64


def _write(path, payload) -> str:
    path.write_text(json.dumps(payload) if isinstance(payload, dict) else str(payload),
                    encoding="utf-8")
    return str(path)


@pytest.fixture
def deployment(tmp_path):
    """A clean container deployment: build stamp, runtime digest and manifest all agreeing."""
    build = tmp_path / "build_info.json"
    _write(build, {"commit": COMMIT, "tree_clean": True, "image_digest": DIGEST,
                   "built_at": "2026-07-24T18:00:00Z"})
    runtime = tmp_path / "image_digest"
    _write(runtime, DIGEST)
    manifest = tmp_path / "deployment_manifest.json"
    _write(manifest, {"commit": COMMIT, "image_digest": DIGEST,
                      "deployed_at": "2026-07-24T18:05:00Z"})
    return {"build": build, "runtime": runtime, "manifest": manifest, "root": tmp_path}


def _verify(deployment, **kw):
    kw.setdefault("model", DeploymentModel.CONTAINER)
    kw.setdefault("build_info_path", deployment["build"])
    kw.setdefault("deployment_manifest_path", deployment["manifest"])
    kw.setdefault("runtime_digest_path", deployment["runtime"])
    return verify_deployment_identity(**kw)


# ---- the agreeing deployment -----------------------------------------------------------------------

def test_three_agreeing_identities_verify(deployment):
    ev = _verify(deployment)
    assert ev.agreed_commit == COMMIT
    assert ev.agreed_artifact_digest == DIGEST
    assert ev.embedded_build_commit == COMMIT
    assert ev.runtime_artifact_digest == DIGEST
    assert ev.manifest_commit == COMMIT
    assert len(ev.identity_digest) == 64


def test_the_identities_are_kept_distinct_in_the_evidence(deployment):
    d = _verify(deployment).to_open_provenance()
    # three separately-sourced identities, not one collapsed string
    assert d["embedded_build_commit"] and d["runtime_artifact_digest"] and d["manifest_commit"]
    assert d["build_info_source"] != d["manifest_source"] != d["runtime_digest_source"]
    assert d["model"] == "CONTAINER"


def test_the_runtime_digest_may_come_from_the_environment(deployment, monkeypatch):
    monkeypatch.setenv("WORKBENCH_IMAGE_DIGEST", DIGEST)
    ev = _verify(deployment, runtime_digest_path=deployment["root"] / "absent",
                 runtime_digest_env="WORKBENCH_IMAGE_DIGEST")
    assert ev.runtime_artifact_digest == DIGEST
    assert ev.runtime_digest_source == "env:WORKBENCH_IMAGE_DIGEST"


def test_a_source_checkout_deployment_needs_no_artifact_digest(tmp_path):
    build = tmp_path / "build_info.json"
    _write(build, {"commit": COMMIT, "tree_clean": True})
    manifest = tmp_path / "manifest.json"
    _write(manifest, {"commit": COMMIT})
    ev = verify_deployment_identity(model=DeploymentModel.SOURCE_CHECKOUT, build_info_path=build,
                                    deployment_manifest_path=manifest)
    assert ev.agreed_commit == COMMIT and ev.agreed_artifact_digest is None


# ---- MISSING evidence ------------------------------------------------------------------------------

def test_an_absent_build_stamp_is_missing_evidence(deployment):
    with pytest.raises(DeploymentEvidenceMissing, match="embedded build stamp is absent"):
        _verify(deployment, build_info_path=deployment["root"] / "nope.json")


def test_an_unreadable_build_stamp_is_missing_evidence(deployment):
    deployment["build"].write_text("{not json", encoding="utf-8")
    with pytest.raises(DeploymentEvidenceMissing, match="unreadable"):
        _verify(deployment)


def test_a_build_stamp_without_a_commit_is_missing_evidence(deployment):
    _write(deployment["build"], {"tree_clean": True, "image_digest": DIGEST})
    with pytest.raises(DeploymentEvidenceMissing, match="no valid commit"):
        _verify(deployment)


def test_a_build_stamp_without_cleanliness_is_missing_evidence(deployment):
    _write(deployment["build"], {"commit": COMMIT, "image_digest": DIGEST})
    with pytest.raises(DeploymentEvidenceMissing, match="must be the JSON boolean"):
        _verify(deployment)


def test_an_absent_runtime_digest_is_missing_evidence(deployment):
    with pytest.raises(DeploymentEvidenceMissing, match="reports no running artifact digest"):
        _verify(deployment, runtime_digest_path=deployment["root"] / "absent",
                runtime_digest_env="A_VARIABLE_THAT_IS_NOT_SET")


def test_an_absent_manifest_is_missing_evidence(deployment):
    with pytest.raises(DeploymentEvidenceMissing, match="deployment manifest is absent"):
        _verify(deployment, deployment_manifest_path=deployment["root"] / "gone.json")


def test_a_manifest_without_an_artifact_digest_is_missing_evidence(deployment):
    _write(deployment["manifest"], {"commit": COMMIT})
    with pytest.raises(DeploymentEvidenceMissing, match="records no artifact digest"):
        _verify(deployment)


# ---- MISMATCHED evidence (a different stop, deliberately) -------------------------------------------

def test_a_dirty_build_tree_is_refused(deployment):
    _write(deployment["build"], {"commit": COMMIT, "tree_clean": False, "image_digest": DIGEST})
    with pytest.raises(DeploymentEvidenceMismatch, match="DIRTY working tree"):
        _verify(deployment)


def test_a_manifest_commit_disagreement_is_a_mismatch(deployment):
    _write(deployment["manifest"], {"commit": OTHER_COMMIT, "image_digest": DIGEST})
    with pytest.raises(DeploymentEvidenceMismatch, match="was not deployed"):
        _verify(deployment)


def test_a_runtime_digest_disagreement_is_a_mismatch(deployment):
    _write(deployment["runtime"], OTHER_DIGEST)
    with pytest.raises(DeploymentEvidenceMismatch, match="artifact digests disagree"):
        _verify(deployment)


def test_a_build_stamp_digest_disagreement_is_a_mismatch(deployment):
    _write(deployment["build"], {"commit": COMMIT, "tree_clean": True, "image_digest": OTHER_DIGEST})
    with pytest.raises(DeploymentEvidenceMismatch, match="artifact digests disagree"):
        _verify(deployment)


@pytest.mark.parametrize("bad", ["not-a-digest", "sha256:zz", "", "sha256:" + "b" * 63])
def test_a_malformed_runtime_digest_is_a_mismatch(bad, deployment):
    _write(deployment["runtime"], bad)
    with pytest.raises((DeploymentEvidenceMismatch, DeploymentEvidenceMissing)):
        _verify(deployment)


# ---- an operator pin can only narrow, never supply --------------------------------------------------

def test_a_matching_operator_pin_is_accepted(deployment):
    assert _verify(deployment, expected_commit=COMMIT).agreed_commit == COMMIT


def test_a_conflicting_operator_pin_is_a_mismatch(deployment):
    with pytest.raises(DeploymentEvidenceMismatch, match="operator pinned"):
        _verify(deployment, expected_commit=OTHER_COMMIT)


def test_the_pin_never_becomes_the_identity(deployment):
    """Even a correct pin is checked against the derived identity rather than replacing it."""
    _write(deployment["build"], {"commit": OTHER_COMMIT, "tree_clean": True, "image_digest": DIGEST})
    _write(deployment["manifest"], {"commit": OTHER_COMMIT, "image_digest": DIGEST})
    ev = _verify(deployment, expected_commit=OTHER_COMMIT)
    assert ev.agreed_commit == OTHER_COMMIT            # derived from the sources, which agree
    with pytest.raises(DeploymentEvidenceMismatch):
        _verify(deployment, expected_commit=COMMIT)    # the pin cannot override the sources


# ---- tree_clean must be the JSON boolean, not merely truthy -----------------------------------------

@pytest.mark.parametrize("value", ["false", "true", "dirty", 0, 1, [], {}, "", None])
def test_a_non_boolean_tree_clean_is_malformed_evidence(value, deployment):
    """"false" and 1 are truthy; "" and 0 are falsy. None of them is a recorded fact, so all are
    missing/malformed evidence rather than a clean or dirty verdict."""
    _write(deployment["build"], {"commit": COMMIT, "tree_clean": value, "image_digest": DIGEST})
    with pytest.raises(DeploymentEvidenceMissing, match="must be the JSON boolean"):
        _verify(deployment)


def test_tree_clean_false_is_a_dirty_artifact_mismatch(deployment):
    _write(deployment["build"], {"commit": COMMIT, "tree_clean": False, "image_digest": DIGEST})
    with pytest.raises(DeploymentEvidenceMismatch, match="DIRTY working tree"):
        _verify(deployment)


def test_tree_clean_true_is_accepted(deployment):
    _write(deployment["build"], {"commit": COMMIT, "tree_clean": True, "image_digest": DIGEST})
    assert _verify(deployment).embedded_build_tree_clean is True


# ---- runtime-digest I/O failures stay inside the governed error model --------------------------------

def test_a_runtime_digest_path_that_is_a_directory_is_missing_evidence(deployment, tmp_path):
    """It exists, so it is the configured evidence — and it cannot be read. That is broken deployment
    evidence, not a reason to fall back to the environment."""
    as_dir = tmp_path / "digest_dir"
    as_dir.mkdir()
    with pytest.raises(DeploymentEvidenceMissing, match="not a regular file"):
        _verify(deployment, runtime_digest_path=as_dir, runtime_digest_env="WORKBENCH_IMAGE_DIGEST")


def test_an_unreadable_runtime_digest_does_not_fall_back_to_the_environment(deployment, monkeypatch):
    monkeypatch.setenv("WORKBENCH_IMAGE_DIGEST", DIGEST)

    real_read_text = type(deployment["runtime"]).read_text

    def boom(self, *args, **kwargs):
        if self == deployment["runtime"]:
            raise PermissionError("permission denied")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(type(deployment["runtime"]), "read_text", boom)
    with pytest.raises(DeploymentEvidenceMissing, match="unreadable"):
        _verify(deployment, runtime_digest_env="WORKBENCH_IMAGE_DIGEST")


def test_the_environment_is_used_only_when_no_runtime_file_exists(deployment, monkeypatch):
    monkeypatch.setenv("WORKBENCH_IMAGE_DIGEST", DIGEST)
    ev = _verify(deployment, runtime_digest_path=deployment["root"] / "never_written",
                 runtime_digest_env="WORKBENCH_IMAGE_DIGEST")
    assert ev.runtime_digest_source == "env:WORKBENCH_IMAGE_DIGEST"
