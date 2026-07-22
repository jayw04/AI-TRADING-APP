"""MR-002 prerequisite P4 — SS5 acceptance submission tests.

Verifies that the P4 products (a) re-derive rather than restate, (b) do not apply a status change or
make the CAS anchor grant-capable, and (c) hold the P4 boundary. Reads no dataset; opens no partition.
Run: apps/backend/.venv/Scripts/python.exe -m pytest test_p4_acceptance.py -v
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess

import pytest

import mr002_valoos_code_identity as CI
import mr002_valoos_registry as REG

HERE = os.path.abspath(os.path.dirname(__file__))
RVW = os.path.abspath(os.path.join(HERE, ".."))
ACCEPTANCE = "MR002_P3_AcceptanceRecord.json"
SUBMISSION = "MR002_EvaluatorAcceptanceSubmission.json"

pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(HERE, ACCEPTANCE)),
                                reason="P4 package absent")


def load(name):  # noqa: ANN001
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return json.load(fh)


def test_P4_01_every_verification_check_passes():
    a = load(ACCEPTANCE)
    assert a["verification_all_pass"] is True
    assert a["verdict"] == "ACCEPT_AS_COMPLIANT"
    assert len(a["verification_findings"]) >= 15
    assert all(f["result"] == "PASS" for f in a["verification_findings"])


def test_P4_02_verification_is_independent_not_restated():
    a = load(ACCEPTANCE)
    assert "INDEPENDENT RE-DERIVATION" in a["verification_method"]
    assert "not taken as evidence of themselves" in a["verification_method"]
    assert a["zero_read_denial_chain"]["re_derived"] is True


def test_P4_03_bound_module_digests_recompute_from_disk():
    a = load(ACCEPTANCE)
    for name, want in a["bound_evidence_digests"].items():
        path = os.path.join(HERE, name)
        assert os.path.exists(path), name
        with open(path, "rb") as fh:
            assert hashlib.sha256(fh.read()).hexdigest() == want, name


def test_P4_04_the_eight_required_binding_items_are_present():
    a = load(ACCEPTANCE)
    assert set(a["bound_commits"]) == {"increment", "finding"}
    for key in ("bound_evidence_digests", "operational_modules", "test_inventory",
                "zero_read_denial_chain", "explicit_exclusions_and_unresolved_fields",
                "phase3a_registry_finding"):
        assert a[key], key
    assert len(a["operational_modules"]) == 4


def test_P4_05_status_transition_is_proposed_not_applied():
    a = load(ACCEPTANCE)
    t = a["status_transition"]
    assert t["from"] == "PRODUCED" and t["to"] == "SATISFIED"
    assert t["applied_here"] is False
    assert "ON OWNER ADJUDICATION" in t["effective"]


def test_P4_06_cas_anchor_is_untouched_and_not_grant_capable():
    a = load(ACCEPTANCE)
    c = a["cas_anchor_effect"]
    assert c["anchor_modified"] is False and c["grant_capable_field_present"] is False
    assert c["adjudicated_prerequisite_digest"] != \
        c["prospective_prerequisite_digest_if_only_P3_transitions"]
    assert "must recompute the digest from the THEN-current register" in c["note"]
    # the record itself must contain no true authorization flag anywhere
    blob = json.dumps(a)
    assert '"validation_authorization": true' not in blob.lower()


def test_P4_07_state_file_still_reads_false_at_rev_zero():
    path = os.path.join(RVW, "phase3bc", "MR002_Phase3BC_ValidationAuthorizationState_v1.0.json")
    with open(path, encoding="utf-8") as fh:
        state = json.load(fh)
    assert state["validation_authorization"] is False and state["_rev"] == 0


def test_P4_08_p10_and_evaluator_bind_remain_open():
    a = load(ACCEPTANCE)
    ex = a["explicit_exclusions_and_unresolved_fields"]
    assert ex["P10_runtime_instance"].startswith("UNSATISFIED")
    assert ex["PENDING_EVALUATOR_BIND"].startswith("UNRESOLVED")
    s = load(SUBMISSION)
    ident = s["section5_elements"]["evaluator_code_identities"]
    assert ident["commit_tree_container"].startswith("PENDING_EVALUATOR_BIND")
    assert s["section5_elements"]["container_and_dependency_identity"][
        "container_image_digest"].startswith("ABSENT")


def _inventory_at_record_commit():
    """The evaluator .py inventory at the commit that last wrote the acceptance record.

    The P4 record is a SNAPSHOT bound to its own commit, so it is verified against history, not
    against a live tree that legitimately moves on as later prerequisites are produced.
    """
    rel = "docs/review/mr002/evaluator"
    root = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))

    def git(*args):
        return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                              check=True).stdout
    commit = git("log", "-1", "--format=%H", "--", f"{rel}/{ACCEPTANCE}").strip()
    names = [line.split("\t")[-1].rsplit("/", 1)[-1]
             for line in git("ls-tree", "--name-only", f"{commit}:{rel}").splitlines()]
    py = [n for n in names if n.endswith(".py")]
    modules = [n for n in py if not n.startswith(("test_", "_gen_"))]
    return commit, py, modules


def test_P4_09_inventory_counts_are_derived_and_true_at_the_record_commit():
    a = load(ACCEPTANCE)
    f = a["phase3a_registry_finding"]
    commit, py_at_commit, modules_at_commit = _inventory_at_record_commit()
    assert commit, "acceptance record must be committed"
    assert f["section4_inventory_now"] == len(modules_at_commit)
    assert f["current_all_py_file_count"] == len(py_at_commit)
    assert f["phase3a_bound_files_drifted"] == 0
    # and the live tree may only have GROWN since; nothing bound may have vanished
    assert len(CI.module_digests(HERE)) >= f["section4_inventory_now"]


def test_P4_10_the_p3_submission_numeral_is_corrected_not_silently_dropped():
    a = load(ACCEPTANCE)
    c = a["phase3a_registry_finding"]["CORRECTION_to_P3_submission_section6"]
    assert "21 -> 25" in c["p3_submission_asserted"]
    assert "not like-for-like" in c["defect"]
    _, _, modules_at_commit = _inventory_at_record_commit()
    assert c["mechanically_derived_truth"]["section4_modules_now"] == len(modules_at_commit)
    assert "UNMODIFIED" in c["status"]
    assert "SUBSTANCE" in c["unchanged_conclusions"]


def test_P4_11_every_required_gate_has_a_synthetic_result():
    s = load(SUBMISSION)
    g = s["section5_elements"]["gate_fixture_results"]
    assert g["required_gate_count"] == len(REG.REQUIRED_GATES)
    assert g["gates_with_synthetic_result"] == g["required_gate_count"]
    assert g["missing"] == []
    assert set(g["results"]) == set(REG.REQUIRED_GATES)


def test_P4_12_diagnostics_are_present_and_non_gating():
    s = load(SUBMISSION)
    d = s["section5_elements"]["diagnostics_non_gating"]
    assert sorted(d["required"]) == sorted(REG.REQUIRED_DIAGNOSTICS)
    assert d["all_classified_non_gating"] is True


def test_P4_13_trials_N_is_read_from_the_ledger_and_tampering_fails_closed():
    s = load(SUBMISSION)
    t = s["section5_elements"]["trials_N_read_from_bound_identity"]
    assert t["N"] == 5
    assert t["no_code_constant_fallback"] is True
    assert t["tampered_N_fails_closed"] is True


def test_P4_14_zero_performance_confirmed():
    s = load(SUBMISSION)
    z = s["section5_elements"]["zero_performance_confirmation"]
    assert z["validation_data_read"] is False and z["oos_data_read"] is False
    assert z["development_performance_computed"] is False
    assert z["synthetic_fixture_only"] is True and z["sealed_reads"] == 0


def test_P4_15_acceptance_standard_unchanged_and_downstream_work_not_begun():
    s = load(SUBMISSION)
    assert s["acceptance_standard_unchanged"]["asserted"] is True
    outstanding = " ".join(s["outstanding_prerequisites_not_addressed_here"])
    for token in ("P5", "P6-P9", "P10", "P11", "P13"):
        assert token in outstanding
    assert "SEALED AND UNREAD" in s["boundary"]
