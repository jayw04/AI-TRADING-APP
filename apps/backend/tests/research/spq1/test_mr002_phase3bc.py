"""SPQ-1 Phase 3B/C — Execution Authorization Request tests (request only; no data access).

Proves the request package (a) recomputes the Phase-3A lineage rather than asserting it, (b) reports
grant readiness honestly, and (c) holds the authorization boundary. No test opens validation/OOS data
or computes performance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
RVW = REPO / "docs" / "review" / "mr002"
P3A = RVW / "phase3a"
P3BC = RVW / "phase3bc"
PREREG_SHA = "b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c"
DSR_LEDGER_SHA = "deda5cec0bbb72dd845633e99682849e6cf0db949e252dba956a432fcb383e9b"

pytestmark = pytest.mark.skipif(not P3BC.exists(), reason="Phase 3B/C request package absent")


def load(name):  # noqa: ANN001
    return json.load(open(P3BC / name))


def test_1_phase3a_lineage_recomputes_with_zero_drift():
    lin = load("MR002_Phase3BC_Phase3ALineageProof_v1.0.json")
    assert lin["verdict"] == "PHASE_3A_LINEAGE_INTACT"
    assert lin["governing_preregistration"]["reproduces"] is True
    assert lin["governing_preregistration"]["bound_sha256"] == PREREG_SHA
    arts = lin["phase3a_artifacts"]
    assert arts["all_reproduce"] is True and arts["counts_reconcile"] is True
    assert arts["manifest_bound_artifact_count"] == len(arts["artifacts"]) == 25
    # every recorded hash is a genuine recomputation of the file on disk, not a copied constant
    for name, rec in arts["artifacts"].items():
        p = P3A / rec["file"]
        assert p.exists(), name
        assert hashlib.sha256(p.read_bytes()).hexdigest() == rec["recomputed_sha256"] == \
            rec["bound_sha256"]


def test_2_run_specification_schema_binding_still_holds():
    lin = load("MR002_Phase3BC_Phase3ALineageProof_v1.0.json")
    b = lin["run_specification_schema_bindings"]["SignalDecisionRecord_model_module"]
    mod = REPO / b["path"]
    assert hashlib.sha256(mod.read_bytes()).hexdigest() == b["bound_sha256"]
    assert b["reproduces"] is True
    assert "fail closed" in lin["run_specification_schema_bindings"]["fail_closed_rule"].lower()


def test_3_evaluator_modules_bound_and_undrifted():
    lin = load("MR002_Phase3BC_Phase3ALineageProof_v1.0.json")
    ev = lin["evaluator_module_reference_identities"]
    assert ev["zero_drift"] is True and ev["drift"] == []
    assert ev["modules_present_but_unbound"] == []
    assert ev["bound_module_count"] >= 21
    # binding the modules is NOT qualification, and the artifact must say so
    assert "does NOT constitute evaluator qualification" in ev["note"]


def test_4_dsr_binding_unchanged_N5():
    lin = load("MR002_Phase3BC_Phase3ALineageProof_v1.0.json")
    o = lin["other_governing_identities"]
    assert o["dsr_trial_ledger_sha256"] == DSR_LEDGER_SHA
    assert o["dsr_trial_ledger_matches_prereg"] is True and o["dsr_trials_N"] == 5
    g = load("MR002_Phase3BC_ExecutionGateTable_v1.0.json")
    assert g["null_model_binding"]["trials_N"] == 5
    assert len(g["null_model_binding"]["trial_set"]) == 5
    assert "no new null models" in g["null_model_binding"]["rule"]


def test_5_prerequisite_register_is_complete_and_honest():
    reg = load("MR002_Phase3BC_RuntimePrerequisiteRegister_v1.0.json")
    ids = [p["id"] for p in reg["prerequisites"]]
    assert ids == [f"P{i}" for i in range(1, len(ids) + 1)], "prerequisite ids must be dense"
    assert reg["counts"]["total"] == len(ids)
    blocking = [p for p in reg["prerequisites"] if p["blocks_grant"]]
    assert reg["counts"]["blocking"] == len(blocking)
    assert reg["counts"]["blocking_unsatisfied"] == len(reg["blocking_unsatisfied_ids"])
    assert reg["counts"]["blocking_satisfied"] + reg["counts"]["blocking_unsatisfied"] == len(blocking)
    for p in reg["prerequisites"]:
        assert p["producer"] and p["evidence"] and p["satisfaction_criterion"]
        assert p["status"] in reg["status_domain"]


def test_6_custodian_seal_evidence_is_not_claimed_as_satisfied():
    reg = load("MR002_Phase3BC_RuntimePrerequisiteRegister_v1.0.json")
    seal = {p["id"]: p for p in reg["prerequisites"] if p["producer"].startswith("CUSTODIAN")}
    assert seal, "custodian prerequisites must be enumerated"
    for p in seal.values():
        assert p["status"] != "SATISFIED"
        assert p["blocks_grant"] is True
    # the three reserved runtime evidence names all appear as prerequisites
    titles = " ".join(p["title"] for p in reg["prerequisites"])
    for nm in ("ValidationPartitionContentCommitment", "ValidationPartitionAccessHistory",
               "ValidationSealVerificationReport"):
        assert nm in titles


def test_7_request_grants_nothing_and_excludes_oos():
    req = load("MR002_Phase3BC_ExecutionAuthorizationRequest_v1.0.json")
    assert req["validation_authorization"] is False
    assert req["sealed_data_read"] is False
    assert req["state"].startswith("REQUEST")
    assert req["grants"].startswith("NOTHING")
    assert req["requested_scope_if_granted"]["executions"] == 1
    assert req["requested_scope_if_granted"]["configs"] == ["A", "B", "C"]
    assert "EXCLUDED" in req["requested_scope_if_granted"]["oos"]
    assert "OOS partition access" in req["explicitly_not_requested"]
    assert "SEALED AND UNREAD" in req["boundary"]


def test_8_grant_readiness_reflects_the_register():
    reg = load("MR002_Phase3BC_RuntimePrerequisiteRegister_v1.0.json")
    req = load("MR002_Phase3BC_ExecutionAuthorizationRequest_v1.0.json")
    pub = load("MR002_Phase3BC_PublicationManifest_v1.0.json")
    expected = "READY" if not reg["blocking_unsatisfied_ids"] else "NOT_READY"
    assert reg["grant_readiness"] == req["grant_readiness"] == pub["grant_readiness"] == expected
    assert req["prerequisite_summary"]["blocking_unsatisfied_ids"] == reg["blocking_unsatisfied_ids"]
    assert pub["blocking_unsatisfied_ids"] == reg["blocking_unsatisfied_ids"]


def test_9_three_decisions_are_ordered_and_separable():
    req = load("MR002_Phase3BC_ExecutionAuthorizationRequest_v1.0.json")
    d = {x["id"]: x for x in req["decisions_requested_of_the_owner"]}
    assert set(d) == {"D1", "D2", "D3"}
    assert "Authorizes nothing" in d["D1"]["consequence"] or \
        "authorizes nothing" in d["D1"]["consequence"]
    assert "NO performance" in d["D2"]["consequence"]
    assert "consumes the single" in d["D3"]["consequence"]
    assert "D1 -> D2" in req["sequencing_rule"] and "D3" in req["sequencing_rule"]
    reg = load("MR002_Phase3BC_RuntimePrerequisiteRegister_v1.0.json")
    assert "two separate decisions" in reg["authorization_note"]


def test_10_phase3b_integrity_gates_all_require_zero():
    g = load("MR002_Phase3BC_ExecutionGateTable_v1.0.json")
    gates = g["phase_3b_integrity_gates"]
    assert len(gates) == 8
    for gate in gates:
        assert gate["required"] == 0 and gate["evidenced_by"]
    names = {x["gate"] for x in gates}
    assert "oos_reads_run_ledger_and_store_access_log" in names
    assert "validation_access_events_before_authorization" in names


def test_11_primary_gate_and_stage_separation_preserved():
    g = load("MR002_Phase3BC_ExecutionGateTable_v1.0.json")
    m = g["metric_roles"]
    assert "0.70" in m["primary_validation_gate"]
    assert "conservative-borrow" in m["primary_validation_gate"]
    assert "PROHIBITED" in m["stage_separation"]
    assert "must never become substitute success criteria" in m["diagnostics_are_not_gates"]
    assert set(g["verdict_domain"]) == {"VALIDATION_ADVANCE_REQUEST", "DO_NOT_ADVANCE",
                                        "INCONCLUSIVE", "INTEGRITY_FAILURE"}


def test_12_deliverables_are_runtime_only_and_census_is_not_a_count_gate():
    d = load("MR002_Phase3BC_DeliverableRegister_v1.0.json")
    assert len(d["phase_3b"]) == 6 and len(d["phase_3c"]) == 8
    assert "none exists now" in d["note"] and "pre-populated" in d["note"]
    assert "must NOT become a fixed" in d["census_rule"]
    assert d["enrichment_default"].startswith("FAIL CLOSED")


def test_13_stop_conditions_cover_the_identity_and_seal_failures():
    req = load("MR002_Phase3BC_ExecutionAuthorizationRequest_v1.0.json")
    stops = " ".join(req["stop_conditions"]).lower()
    for token in ("numeric-runtime identity mismatch", "executionenrichmentschema",
                  "oos access event", "pending_evaluator_bind", "integrity gate"):
        assert token in stops


def test_14_publication_manifest_binds_every_artifact_and_holds_boundary():
    pub = load("MR002_Phase3BC_PublicationManifest_v1.0.json")
    assert pub["publication_manifest_self_excluded"] is True
    assert pub["validation_authorization"] is False
    assert "SEALED AND UNREAD" in pub["boundary"]
    assert pub["manifest_bound_artifact_count"] == len(pub["artifact_sha256"])
    assert pub["package_file_count"] == pub["manifest_bound_artifact_count"] + 1
    files = [f for f in P3BC.iterdir() if f.suffix in (".json", ".md")]
    assert len(files) == pub["package_file_count"]
    for name, want in pub["artifact_sha256"].items():
        cands = [f for f in files if f.name.startswith(f"MR002_Phase3BC_{name}_v1.0.")]
        assert len(cands) == 1, name
        assert hashlib.sha256(cands[0].read_bytes()).hexdigest() == want
