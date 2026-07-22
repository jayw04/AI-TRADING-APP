"""MR-002 P5 continuation — container-image leg tests (synthetic; no build, no partition access).

Exercises the image-identity rules directly: content-addressed references only, source
commit/tree agreement, byte-identical bound modules inside the image with none omitted and no
extra included module, and dependency-lock agreement. Also checks the emitted artifacts when present.

Run: apps/backend/.venv/Scripts/python.exe -m pytest test_image_p5.py -v
"""

from __future__ import annotations

import json
import os

import pytest

import mr002_valoos_binding as B
import mr002_valoos_image as IMG

HERE = os.path.abspath(os.path.dirname(__file__))
DIGEST = "sha256:" + "a" * 64
BASE = "python@sha256:" + "b" * 64
COMMIT, TREE, LOCK_SHA = "c" * 40, "t" * 40, "d" * 64


def _binding(modules):
    return {"record_type": "MR002_EvaluatorBinding", "included_modules": dict(modules),
            "section4_elements": {
                "source_commit": {"status": "RESOLVED", "value": COMMIT},
                "source_tree": {"status": "RESOLVED", "value": TREE},
                "dependency_lock": {"status": "RESOLVED", "sha256": LOCK_SHA}}}


def _manifest(modules, **kw):
    kwargs = {"image_digest": DIGEST, "base_image_digest": BASE, "platform": "linux/amd64",
              "builder": "docker/29", "build_definition": "Dockerfile",
              "build_definition_sha256": "e" * 64, "source_commit": COMMIT, "source_tree": TREE,
              "dependency_lock": "lock.json", "dependency_lock_sha256": LOCK_SHA,
              "evaluator_path_in_image": "/opt/mr002/evaluator",
              "module_digests": dict(modules), "build_inputs": {}}
    kwargs.update(kw)
    return IMG.build_image_manifest(**kwargs)


MODULES = {"mod_a.py": "1" * 64, "mod_b.py": "2" * 64}


# =====================================================================================
# content addressing
# =====================================================================================
@pytest.mark.parametrize("ref,ok", [
    ("sha256:" + "a" * 64, True),
    ("python@sha256:" + "a" * 64, True),
    ("mr002-evaluator-p5:qualify", False),
    ("latest", False),
    ("sha256:short", False),
    ("sha256:" + "A" * 64, False),
    (None, False),
])
def test_I1_only_content_addressed_references_are_identities(ref, ok):
    assert IMG.is_content_addressed(ref) is ok


def test_I2_manifest_refuses_a_mutable_tag():
    with pytest.raises(IMG.ImageRefused) as exc:
        _manifest(MODULES, image_digest="mr002-evaluator-p5:qualify")
    assert "not_content_addressed" in str(exc.value)


def test_I3_manifest_refuses_a_tag_only_base():
    with pytest.raises(IMG.ImageRefused):
        _manifest(MODULES, base_image_digest="python:3.13-slim")


def test_I4_manifest_refuses_if_sealed_data_was_mounted():
    with pytest.raises(IMG.ImageRefused) as exc:
        _manifest(MODULES, sealed_data_mounted=True)
    assert "sealed_data_mounted_during_build" in str(exc.value)


def test_I5_manifest_refuses_an_empty_module_set():
    with pytest.raises(IMG.ImageRefused) as exc:
        _manifest({})
    assert "empty_module_set" in str(exc.value)


# =====================================================================================
# verification against the source binding
# =====================================================================================
def test_I6_matching_image_passes():
    rep = IMG.require_image(_manifest(MODULES), _binding(MODULES), observed_image_digest=DIGEST)
    assert rep["matches"] is True and rep["bound_module_count"] == 2


def test_I7_module_drift_in_image_refuses():
    drifted = dict(MODULES, **{"mod_a.py": "9" * 64})
    with pytest.raises(IMG.ImageRefused) as exc:
        IMG.require_image(_manifest(drifted), _binding(MODULES))
    assert "module_drift_in_image" in str(exc.value)


def test_I8_omitted_module_refuses():
    with pytest.raises(IMG.ImageRefused) as exc:
        IMG.require_image(_manifest({"mod_a.py": MODULES["mod_a.py"]}), _binding(MODULES))
    assert "module_omitted_from_image" in str(exc.value)


def test_I9_additional_unbound_module_refuses():
    extra = dict(MODULES, **{"mod_c.py": "3" * 64})
    with pytest.raises(IMG.ImageRefused) as exc:
        IMG.require_image(_manifest(extra), _binding(MODULES))
    assert "additional_unbound_module_in_image" in str(exc.value)


@pytest.mark.parametrize("field", ["source_commit", "source_tree"])
def test_I10_wrong_source_identity_refuses(field):
    with pytest.raises(IMG.ImageRefused) as exc:
        IMG.require_image(_manifest(MODULES, **{field: "0" * 40}), _binding(MODULES))
    assert "source_identity_mismatch" in str(exc.value)


def test_I11_changed_dependency_lock_refuses():
    with pytest.raises(IMG.ImageRefused) as exc:
        IMG.require_image(_manifest(MODULES, dependency_lock_sha256="0" * 64), _binding(MODULES))
    assert "dependency_lock_mismatch" in str(exc.value)


def test_I12_altered_observed_digest_refuses():
    with pytest.raises(IMG.ImageRefused) as exc:
        IMG.require_image(_manifest(MODULES), _binding(MODULES),
                          observed_image_digest="sha256:" + "f" * 64)
    assert "image_digest_mismatch" in str(exc.value)


def test_I13_absent_manifest_or_binding_refuses():
    with pytest.raises(IMG.ImageRefused):
        IMG.require_image({}, _binding(MODULES))
    with pytest.raises(IMG.ImageRefused):
        IMG.require_image(_manifest(MODULES), {"record_type": "OTHER"})


# =====================================================================================
# the emitted artifacts
# =====================================================================================
def _emitted(name):
    path = os.path.join(HERE, name)
    if not os.path.exists(path):  # pragma: no cover
        pytest.skip(f"{name} not emitted")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_I14_emitted_manifest_is_content_addressed_and_clean():
    m = _emitted("MR002_EvaluatorImageManifest.json")
    assert IMG.is_content_addressed(m["image_digest"])
    assert IMG.is_content_addressed(m["base_image_digest"])
    assert m["sealed_data_mounted"] is False
    assert m["build_inputs"]["network"] == "none"
    assert m["build_inputs"]["mounts"] == "none"
    assert "NOT a P10" in m["scope"]


def test_I15_emitted_binding_is_resolved_and_matches_the_image():
    b = _emitted("MR002_EvaluatorBinding.json")
    m = _emitted("MR002_EvaluatorImageManifest.json")
    assert b["binding_state"] == "RESOLVED" and b["unresolved_elements"] == []
    assert b["section4_elements"]["container_image_digest"]["value"] == m["image_digest"]
    assert IMG.require_image(m, b)["matches"] is True
    assert b["supersedes"]["previous_source_commit"] != \
        b["section4_elements"]["source_commit"]["value"]


def test_I16_resolved_binding_now_gates_the_live_tree():
    b = _emitted("MR002_EvaluatorBinding.json")
    assert B.require_binding(HERE, b)["matches"] is True


def test_I17_container_qualification_refused_every_defect_class():
    q = _emitted("MR002_P5_ContainerQualification.json")
    assert q["all_defect_classes_refused"] is True
    labels = {r["label"] for r in q["refusal_demonstrations"]}
    assert labels >= {"module_drift_in_image", "module_omitted_from_image",
                      "additional_unbound_module_in_image", "altered_image_digest",
                      "wrong_source_commit", "wrong_source_tree", "changed_dependency_lock",
                      "mutable_tag_only_identity"}
    in_image = [r for r in q["refusal_demonstrations"] if r["where"] == "inside the produced image"]
    assert len(in_image) >= 3 and all(r["refused"] for r in in_image)
    assert q["section4_gate_inside_image"]["passed"] is True
    assert q["image_contents"]["byte_identical_to_bound_set"] is True
    assert q["image"]["sealed_data_mounted"] is False
    assert "NOT P10" in q["scope_boundary"]
