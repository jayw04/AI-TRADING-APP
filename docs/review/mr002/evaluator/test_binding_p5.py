"""MR-002 prerequisite P5 — SS4 pre-access evaluator binding qualification tests.

Exercises the binding procedure on SYNTHETIC directories: mechanical enumeration, full
classification, fail-closed detection of unbound / missing / renamed / duplicate / drifted modules,
per-leg PENDING_EVALUATOR_BIND preservation, and refusal to run on an unresolved binding.

Reads no dataset; opens no partition; releases no credentials; computes no performance.
Run: apps/backend/.venv/Scripts/python.exe -m pytest test_binding_p5.py -v
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

import mr002_valoos_binding as B

HERE = os.path.abspath(os.path.dirname(__file__))

ELEMENT_MODULES = {"benchmark_impl": "mod_bench.py", "cost_model_impl": "mod_cost.py",
                   "metric_impl": "mod_metric.py", "bootstrap_impl": "mod_boot.py",
                   "pbo_dsr_impl": "mod_dsr.py", "report_schema": "mod_report.py"}
DATA_MANIFEST = {"file": "apps/backend/data/mr002_research.duckdb", "sha256": "24e5153c" + "0" * 56}


def _dir(tmp, files):
    for name, body in files.items():
        with open(os.path.join(tmp, name), "wb") as fh:
            fh.write(body)
    return tmp


def _standard(tmp):
    files = {m: f"# {m}".encode() for m in ELEMENT_MODULES.values()}
    files.update({"test_x.py": b"t", "_gen_y.py": b"g", "notes.json": b"{}"})
    return _dir(tmp, files)


def _build(tmp, **kw):
    kwargs = {"source_commit": "c" * 40, "source_tree": "t" * 40,
              "dependency_lock": "lock.json", "dependency_lock_sha256": "d" * 64,
              "data_manifest_identity": DATA_MANIFEST,
              "expected_output_paths": ["valoos/<window>/MR002_ValOOS_<window>_Report.json"],
              "element_modules": ELEMENT_MODULES}
    kwargs.update(kw)
    return B.build_binding(tmp, **kwargs)


# =====================================================================================
# P5-01..P5-05 — mechanical enumeration and complete classification
# =====================================================================================
def test_P5_01_every_entry_is_classified():
    with tempfile.TemporaryDirectory() as d:
        _standard(d)
        os.mkdir(os.path.join(d, "__pycache__"))
        inv = B.enumerate_inventory(d)
        assert inv["entry_count"] == len(os.listdir(d))
        classes = {e["class"] for e in inv["excluded"]}
        assert classes == {B.EXCLUDED_TEST, B.EXCLUDED_GENERATOR, B.EXCLUDED_NON_EVALUATOR,
                           B.EXCLUDED_CACHE}


def test_P5_02_inclusion_rule_matches_the_registered_prefixes():
    assert B.classify("mr002_valoos_metrics.py") == B.INCLUDED_MODULE
    assert B.classify("test_increment4.py") == B.EXCLUDED_TEST
    assert B.classify("_gen_evidence_p4.py") == B.EXCLUDED_GENERATOR
    assert B.classify("MR002_Increment4_Qualification.json") == B.EXCLUDED_NON_EVALUATOR
    assert B.classify("__pycache__", is_dir=True) == B.EXCLUDED_CACHE


def test_P5_03_counts_are_derived_not_assumed():
    with tempfile.TemporaryDirectory() as d:
        _standard(d)
        inv = B.enumerate_inventory(d)
        assert inv["counts"][B.INCLUDED_MODULE] == len(ELEMENT_MODULES)
        assert sum(inv["counts"][c] for c in B.CLASSES) == inv["entry_count"]


def test_P5_04_excluded_files_are_hashed_and_accounted_for():
    with tempfile.TemporaryDirectory() as d:
        _standard(d)
        inv = B.enumerate_inventory(d)
        for e in inv["excluded"]:
            assert e["sha256"] or e["class"] == B.EXCLUDED_CACHE


def test_P5_05_empty_inventory_refuses():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(B.BindingRefused) as exc:
            B.require_qualified(d)
        assert "empty_inventory" in str(exc.value)


# =====================================================================================
# P5-06..P5-12 — fail-closed detection
# =====================================================================================
def test_P5_06_duplicate_module_content_refuses():
    with tempfile.TemporaryDirectory() as d:
        _standard(d)
        with open(os.path.join(d, "mod_copy.py"), "wb") as fh:
            fh.write(b"# mod_bench.py")
        with pytest.raises(B.BindingRefused) as exc:
            B.require_qualified(d)
        assert "duplicate_module_content" in str(exc.value)


def test_P5_07_unbound_module_refuses():
    with tempfile.TemporaryDirectory() as d:
        binding = _build(_standard(d))
        with open(os.path.join(d, "mod_new.py"), "wb") as fh:
            fh.write(b"# new")
        with pytest.raises(B.BindingRefused) as exc:
            B.require_binding(d, binding)
        assert "module_unbound" in str(exc.value)


def test_P5_08_missing_module_refuses():
    with tempfile.TemporaryDirectory() as d:
        binding = _build(_standard(d))
        os.remove(os.path.join(d, "mod_cost.py"))
        with pytest.raises(B.BindingRefused) as exc:
            B.require_binding(d, binding)
        assert "module_missing" in str(exc.value)


def test_P5_09_renamed_module_is_detected_as_a_rename_not_a_coincidence():
    with tempfile.TemporaryDirectory() as d:
        binding = _build(_standard(d))
        os.rename(os.path.join(d, "mod_cost.py"), os.path.join(d, "mod_costs.py"))
        report = B.verify_binding(d, binding)
        kinds = {p["kind"] for p in report["problems"]}
        assert "module_renamed" in kinds and "module_renamed_target" in kinds
        with pytest.raises(B.BindingRefused):
            B.require_binding(d, binding)


def test_P5_10_drifted_module_refuses():
    with tempfile.TemporaryDirectory() as d:
        binding = _build(_standard(d))
        with open(os.path.join(d, "mod_metric.py"), "wb") as fh:
            fh.write(b"# tampered")
        with pytest.raises(B.BindingRefused) as exc:
            B.require_binding(d, binding)
        assert "module_drift" in str(exc.value)


def test_P5_11_absent_or_wrong_binding_refuses():
    with tempfile.TemporaryDirectory() as d:
        _standard(d)
        for bad in (None, {}, {"record_type": "SOMETHING_ELSE"}):
            with pytest.raises(B.BindingRefused) as exc:
                B.require_binding(d, bad)
            assert "binding_absent_or_wrong_type" in str(exc.value)


@pytest.mark.parametrize("field", ["source_commit", "source_tree", "dependency_lock_sha256"])
def test_P5_12_unresolved_required_field_refuses_to_emit_a_binding(field):
    with tempfile.TemporaryDirectory() as d:
        _standard(d)
        for value in ("", B.PENDING, "TBD"):
            with pytest.raises(B.BindingRefused) as exc:
                _build(d, **{field: value})
            assert f"unresolved_required_field:{field}" in str(exc.value)


def test_P5_13_element_module_outside_the_inventory_refuses():
    with tempfile.TemporaryDirectory() as d:
        _standard(d)
        with pytest.raises(B.BindingRefused) as exc:
            _build(d, element_modules=dict(ELEMENT_MODULES, metric_impl="not_present.py"))
        assert "section4_element_module_not_in_inventory" in str(exc.value)


# =====================================================================================
# P5-14..P5-19 — PENDING_EVALUATOR_BIND preservation and SS4 completeness
# =====================================================================================
def test_P5_14_absent_container_leaves_that_leg_pending():
    with tempfile.TemporaryDirectory() as d:
        binding = _build(_standard(d))
        assert binding["binding_state"] == "PARTIALLY_RESOLVED"
        assert binding["unresolved_elements"] == ["container_image_digest"]
        assert binding["pending_evaluator_bind"] == B.PENDING
        c = binding["section4_elements"]["container_image_digest"]
        assert c["status"] == "UNRESOLVED" and c["value"] == B.PENDING


def test_P5_15_a_partially_resolved_binding_cannot_gate_a_run():
    with tempfile.TemporaryDirectory() as d:
        binding = _build(_standard(d))
        with pytest.raises(B.BindingRefused) as exc:
            B.require_binding(d, binding)  # tree is clean; the UNRESOLVED leg is what refuses
        assert "unresolved_section4_elements:container_image_digest" in str(exc.value)


def test_P5_16_a_real_image_resolves_the_leg_and_clears_pending():
    with tempfile.TemporaryDirectory() as d:
        binding = _build(_standard(d), container_image_digest="sha256:" + "a" * 64)
        assert binding["binding_state"] == "RESOLVED"
        assert binding["unresolved_elements"] == []
        assert binding["pending_evaluator_bind"] is None
        assert B.require_binding(d, binding)["matches"] is True


def test_P5_17_every_section4_element_is_accounted_for():
    with tempfile.TemporaryDirectory() as d:
        binding = _build(_standard(d))
        assert set(binding["section4_elements"]) == set(B.SECTION4_ELEMENTS)
        for element, value in binding["section4_elements"].items():
            assert value["status"] in ("RESOLVED", "UNRESOLVED",
                                       "RESOLVED_BY_REGISTERED_IDENTITY"), element


def test_P5_18_data_manifest_is_bound_by_identity_without_opening_it():
    with tempfile.TemporaryDirectory() as d:
        binding = _build(_standard(d))
        dm = binding["section4_elements"]["data_manifest_identity"]
        assert dm["status"] == "RESOLVED_BY_REGISTERED_IDENTITY"
        assert dm["sha256"] == DATA_MANIFEST["sha256"]
        assert "never opened here" in dm["note"]


def test_P5_19_inclusion_rule_disclaims_a_constant_count():
    with tempfile.TemporaryDirectory() as d:
        binding = _build(_standard(d))
        assert "NOT an adjudicated constant" in binding["inclusion_rule"]["derivation"]
        assert binding["authorizes"].startswith("NOTHING")


# =====================================================================================
# P5-20..P5-21 — the real evaluator directory
# =====================================================================================
def test_P5_20_the_real_directory_qualifies_and_accounts_for_every_entry():
    report = B.require_qualified(HERE)
    inv = report["inventory"]
    assert inv["entry_count"] == len(os.listdir(HERE))
    assert report["included_module_count"] == inv["counts"][B.INCLUDED_MODULE]
    assert inv["counts"][B.EXCLUDED_TEST] >= 4 and inv["counts"][B.EXCLUDED_GENERATOR] >= 4


def test_P5_21_emitted_binding_matches_the_real_directory_when_present():
    path = os.path.join(HERE, "MR002_EvaluatorBinding.json")
    if not os.path.exists(path):  # pragma: no cover - generated by _gen_evidence_p5
        pytest.skip("binding not yet emitted")
    with open(path, encoding="utf-8") as fh:
        binding = json.load(fh)
    report = B.verify_binding(HERE, binding)
    assert report["problems"] == [], report["problems"]
    # the container leg resolved once a qualifying image existed; before that it was PENDING,
    # and the superseded binding is preserved alongside as evidence of that state
    assert binding["binding_state"] == "RESOLVED"
    assert binding["unresolved_elements"] == []
    assert binding["section4_elements"]["container_image_digest"]["status"] == "RESOLVED"


def test_P5_22_the_superseded_partially_resolved_binding_is_preserved():
    path = os.path.join(HERE, "MR002_EvaluatorBinding_superseded_6708c59.json")
    if not os.path.exists(path):  # pragma: no cover
        pytest.skip("superseded binding absent")
    with open(path, encoding="utf-8") as fh:
        old = json.load(fh)
    assert old["binding_state"] == "PARTIALLY_RESOLVED"
    assert old["unresolved_elements"] == ["container_image_digest"]
    with open(os.path.join(HERE, "MR002_EvaluatorBinding.json"), encoding="utf-8") as fh:
        new = json.load(fh)
    assert new["supersedes"]["previous_source_commit"] == \
        old["section4_elements"]["source_commit"]["value"]
