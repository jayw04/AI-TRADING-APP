"""SPQ-1 Phase 3A — Validation Authorization Package tests (specifications; no data access).

Proves the 15 required Phase 3A properties against the generated specification artifacts. These verify
that the immutable contract ENCODES the required behavior before any validation/OOS data is opened; the
executable enforcement is bound at evaluator qualification. No test opens validation/OOS data or computes
performance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
P3A = REPO / "docs" / "review" / "mr002" / "phase3a"
PREREG = REPO / "docs" / "review" / "mr002" / "MR002_ValidationOOS_Preregistration_v1.0.4.json"
PREREG_SHA = "b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c"

pytestmark = pytest.mark.skipif(not P3A.exists(), reason="Phase 3A package absent")


def load(name):  # noqa: ANN001
    return json.load(open(P3A / name))


def test_1_preregistration_facts_reproduce_exactly():
    assert PREREG.exists()
    assert hashlib.sha256(PREREG.read_bytes()).hexdigest() == PREREG_SHA
    dp = load("MR002_Phase3A_PregistrationDiffProof_v1.0.json")
    assert dp["content_sha256_reproduces"] is True
    assert dp["all_reproduce"] is True
    assert dp["moving_block_absent"] is True
    for k, v in dp["facts"].items():
        assert v["reproduces"] is True, f"fact {k} does not reproduce"


def test_2_no_post_prereg_trial_affecting_change():
    a = load("MR002_Phase3A_MultiplicityAndDegreesOfFreedomAttestation_v1.0.json")
    assert a["gate"]["signal_or_trial_affecting_count"] == 0
    assert a["gate"]["signal_or_trial_affecting_count_is_zero"] is True
    assert not [c for c in a["changes"] if c["classification"] == "SIGNAL_OR_TRIAL_AFFECTING"]
    assert all(c["affects_trial_count"] is False for c in a["changes"])
    assert all(c["performance_observed"] is False for c in a["changes"])


def test_3_dsr_N_remains_5():
    a = load("MR002_Phase3A_MultiplicityAndDegreesOfFreedomAttestation_v1.0.json")
    assert a["gate"]["dsr_multiplicity_N"] == 5 and a["gate"]["dsr_N_remains_5"] is True
    nm = load("ValidationNullModelSpecification_v1.0.json")
    assert nm["dsr_multiplicity_N"] == 5
    assert nm["trial_ledger_sha256"] == \
        "deda5cec0bbb72dd845633e99682849e6cf0db949e252dba956a432fcb383e9b"
    assert len(nm["trial_set"]) == 5


def test_4_ordinary_dev_credentials_cannot_read_sealed():
    s = load("MR002_Phase3A_SealedPartitionControlSpecification_v1.0.json")
    props = " ".join(s["required_properties"]).lower()
    assert "unavailable to ordinary development execution" in props
    assert s["storage_boundaries"]["credential_custody"].lower().startswith("dedicated iam principal")


def test_5_access_history_detects_unauthorized_read():
    h = load("SealedPartitionAccessHistory_v1.0.json")
    assert "authorized (bool)" in h["record_fields"]
    assert h["required_runtime_gate_values"]["validation_access_events_before_authorization"] == 0
    assert h["required_runtime_gate_values"]["oos_access_events_before_validation"] == 0
    # two-record distinction (per-run ledger vs program-history access log)
    s = load("MR002_Phase3A_SealedPartitionControlSpecification_v1.0.json")
    assert set(s["two_required_records"]) == {"OpenedObjectLedger", "SealedStoreAccessLog"}


def test_6_and_13_structural_preflight_does_not_query_sealed_rows_or_run_metrics():
    p = load("ValidationPartitionStructuralPreflight_v1.0.json")
    assert p["authorized_mode_preauthorization"] == "STRUCTURAL_PREFLIGHT"
    assert p["preauthorization_direct_validation_reads"] == 0
    mustnot = " ".join(p["must_not"]).lower()
    assert "query sealed rows directly" in mustnot
    assert "calculate returns" in mustnot and "calculate performance" in mustnot


def test_7_content_commitments_are_stable():
    c = load("SealedPartitionContentCommitment_v1.0.json")
    assert c["commitment_scheme"]["algorithm"].startswith("SHA-256")
    assert "custodian" in c["commitment_scheme"]["custodian_binding"].lower()
    # value-blind: only metadata, no row values
    assert "row counts" in c["commitment_scheme"]["value_blind_metadata"]


def test_8_and_10_enrichment_edge_cases_are_fail_closed():
    e = load("MR002_Phase3A_ExecutionEnrichmentEdgeCaseSpecification_v1.0.json")
    assert e["default"].startswith("FAIL CLOSED")
    assert "no silent price substitution" in e["default"].lower()
    reg = e["registered_edge_cases"]
    # every listed edge case terminates as a registered stop/disposition (no silent success/fallback)
    for case in ("no_official_open", "trading_halt", "delisting", "symbol_or_permsec_transition",
                 "split_close_t_to_open_t1", "missing_or_conflicting_open", "future_information"):
        assert case in reg
        assert reg[case].startswith(("EXECUTION_ENRICHMENT_STOP", "INTEGRITY_STOP",
                                     "registered adjusted open OR"))
    assert e["each_outcome"] == {"one_terminal_treatment": True, "no_silent_fallback": True,
                                 "one_census_category": True, "one_reconciliation_path": True}
    # separate code namespace
    reg_codes = load("ExecutionEnrichmentCodeRegistry_v1.0.json")
    assert "SEPARATE from signal-production" in reg_codes["namespace"]


def test_9_decision_records_never_mutated():
    s = load("ExecutionEnrichmentSchema_v1.0.json")
    assert s["signal_decision_record_ref"]["immutable"] is True
    assert s["signal_decision_record_ref"]["never_mutated_by_enrichment"] is True
    assert "decision_record_sha256" in s["enriched_candidate_record_fields"]


def test_11_short_unavailable_behavior_matches_registered_model():
    sp = load("ShortBorrowLocateModelSpecification_v1.0.json")
    ans = sp["governed_answers"]
    assert "refused" in ans["short_cannot_be_located"].lower()
    assert "prohibited" in ans["failed_entry_one_sided_or_ghost_position"].lower()
    assert sp["views"]["PRIMARY_GATE"]["borrow_bps_per_year"] == 50
    assert "MUST NOT" in sp["relation_to_primary_gate"] or "does not redefine" in sp["relation_to_primary_gate"]
    # no manufactured locate data
    classes = {r["class"] for r in sp["rules"]}
    assert "UNOBSERVABLE_LIMITATION" in classes and "CONSERVATIVE_PROXY" in classes


def test_12_metric_roles_cannot_change_after_publication():
    m = load("MR002_Phase3A_MetricRoleRegistry_v1.0.json")
    roles = {k: v["metric_role"] for k, v in m["metrics"].items()}
    assert set(roles.values()) <= set(m["role_domain"])
    assert roles["net_oos_sharpe_ge_0.70"] == "PRIMARY_GATE"
    assert roles["conservative_availability_borrow_ssr_economic_operability"] == "SECONDARY_GATE"
    assert roles["frictionless_short_attribution"] == "DIAGNOSTIC_ONLY"
    assert "cannot change after publication" in m["immutability"]
    # every metric carries a valid sample_stage
    assert all(e["sample_stage"] in m["sample_stage_domain"] for e in m["metrics"].values())
    pub = load("MR002_Phase3A_PublicationManifest_v1.0.json")
    got = hashlib.sha256((P3A / "MR002_Phase3A_MetricRoleRegistry_v1.0.json").read_bytes()).hexdigest()
    assert pub["artifact_sha256"]["MetricRoleRegistry"] == got


def test_16_oos_only_gates_cannot_execute_during_validation():
    v = load("MR002_Phase3A_ValidationStageDecisionSpecification_v1.0.json")
    prohibited = set(v["oos_only_metrics_prohibited_during_validation"])
    # the three OOS primary gates must be prohibited during validation
    assert "net_oos_sharpe_ge_0.70" in prohibited
    assert "one_sided_95pct_bootstrap_lower_bound_daily_mean_net_return_gt_0" in prohibited
    assert "dsr_significance_ge_0.95_N5" in prohibited
    # validation stage does not compute OOS primary gates
    computed = set(v["metrics_computed_during_validation"])
    assert not (computed & {"net_oos_sharpe_ge_0.70", "dsr_significance_ge_0.95_N5"})
    assert set(v["allowed_verdicts"]) == {"VALIDATION_ADVANCE_REQUEST", "VALIDATION_DO_NOT_ADVANCE",
                                          "VALIDATION_INCONCLUSIVE", "INTEGRITY_FAILURE"}
    # every metric in the role registry has a sample_stage (role alone can't misroute a metric)
    m = load("MR002_Phase3A_MetricRoleRegistry_v1.0.json")
    assert all("sample_stage" in e for e in m["metrics"].values())


def test_16b_validation_metrics_list_is_canonical_and_unique():
    v = load("MR002_Phase3A_ValidationStageDecisionSpecification_v1.0.json")
    mc = v["metrics_computed_during_validation"]
    assert len(mc) == len(set(mc))          # correction A: no duplicate entry
    assert mc == sorted(mc)                  # canonical order


def test_16c_advancement_conditions_deterministic_diagnostics_not_gating():
    v = load("MR002_Phase3A_ValidationStageDecisionSpecification_v1.0.json")
    conds = v["oos_authorization_request_conditions"]
    # correction B: only the four deterministic conditions; no discretionary red-flag / coherence test
    joined = " ".join(conds).lower()
    assert "red flag" not in joined and "directionally coherent" not in joined
    assert v["advancement_conditions_are_binding_and_deterministic"] is True
    assert set(conds) == {"every validation integrity gate passes",
                          "Config B >= 3 of 5 folds net-positive", "Configs A and C both net-profitable",
                          "no post-validation tuning requested"}
    # PBO / concentration / directional coherence are diagnostics, reported-not-gating
    diag = v["validation_diagnostics_reported_not_gating"]
    for d in ("pbo_cscv", "directional_coherence_A_B_C",
              "single_year_sector_side_issuer_concentration"):
        assert "NEVER changes the advance verdict" in diag[d] or "NOT a validation pass/fail" in diag[d]


def test_17_validation_advancement_rule_is_hash_bound():
    r = load("ValidationRunSpecification_v1.0.json")
    got = hashlib.sha256(
        (P3A / "MR002_Phase3A_ValidationStageDecisionSpecification_v1.0.json").read_bytes()).hexdigest()
    assert r["validation_stage_decision_sha256"] == got
    assert r["bound_specifications"]["ValidationStageDecisionSpecification"] == got


def test_18_both_decision_and_enrichment_schemas_are_run_bound():
    r = load("ValidationRunSpecification_v1.0.json")
    bs = r["bound_schemas"]
    assert bs["SignalDecisionRecord_schema_sha256"] == \
        "49c0e550f78127e04fcf92a649645aef23560173ccf89ef630dab30d4892497f"
    enrich = hashlib.sha256((P3A / "ExecutionEnrichmentSchema_v1.0.json").read_bytes()).hexdigest()
    assert bs["ExecutionEnrichmentSchema_sha256"] == enrich
    assert "fail closed" in bs["fail_closed"].lower()
    assert "ExecutionEnrichmentSchema" in r["bound_specifications"]


def test_19_seal_templates_not_mistaken_for_runtime_evidence():
    for name in ("SealedPartitionAccessHistory_v1.0.json", "SealVerificationReport_v1.0.json",
                 "SealedPartitionContentCommitment_v1.0.json"):
        a = load(name)
        assert a["artifact_kind"] == "SPECIFICATION_TEMPLATE"
        assert a["contains_runtime_evidence"] is False
        assert a["runtime_instance_required_before_authorization"] is True
    ctrl = load("MR002_Phase3A_SealedPartitionControlSpecification_v1.0.json")
    assert ctrl["artifact_kind"] == "SPECIFICATION_TEMPLATE"
    assert "REQUIRED RUNTIME GATE VALUES" in ctrl["required_runtime_gate_values"]["note"]
    # reserved runtime-evidence names exist
    assert "ValidationPartitionAccessHistory_v1.0.json" in ctrl["reserved_runtime_evidence_names"]


def test_20_package_and_manifest_counts_reconcile():
    pub = load("MR002_Phase3A_PublicationManifest_v1.0.json")
    assert pub["publication_manifest_self_excluded"] is True
    assert pub["manifest_bound_artifact_count"] == len(pub["artifact_sha256"])
    assert pub["package_file_count"] == pub["manifest_bound_artifact_count"] + 1
    # actual files on disk == package_file_count (json + md), excluding the generator
    files = [f for f in P3A.iterdir() if f.suffix in (".json", ".md")]
    assert len(files) == pub["package_file_count"]


def test_14_oos_stages_O1_O2_cannot_materialize_performance():
    o = load("MR002_Phase3A_OOSConsumptionProtocol_v1.0.json")
    assert set(o["stages"]) == {"O1", "O2", "O3", "O4", "O5"}
    assert "may qualify as non-consumptive" in o["stage_rule"]["O1_O2"]
    assert "presumptively CONSUMES" in o["stage_rule"]["O3_or_later"]
    assert "no portfolio return series was materialized" in o["non_consumptive_requires_all"]


def test_15_numeric_runtime_mismatch_fail_stops():
    r = load("NumericRuntimeIdentityManifest_v1.0.json")
    assert "FAIL-STOPS" in r["mismatch_policy"]
    req = " ".join(r["required_bindings"]).lower()
    for token in ("numpy version", "blas", "lapack", "thread-count", "lockfile", "seed", "timezone"):
        assert token in req
    assert r["registered_seeds"]["bootstrap_seed"] == 20260711


def test_publication_manifest_binds_every_artifact_and_holds_boundary():
    pub = load("MR002_Phase3A_PublicationManifest_v1.0.json")
    assert pub["diff_proof_all_reproduce"] is True
    assert pub["dof_gate_signal_or_trial_affecting_zero"] is True
    assert pub["dsr_N"] == 5
    assert "validation_authorization=false" in pub["boundary"]
    assert pub["manifest_bound_artifact_count"] == len(pub["artifact_sha256"]) >= 24
    auth = load("ValidationAuthorization_v1.0.json")
    assert auth["validation_authorization"] is False
    assert auth["state"].startswith("REQUEST")
