"""SPQ-1 Phase 3A — Validation Authorization Package generator (specifications only).

Produces the complete Phase 3A package: governing-source registry + diff-proof, degrees-of-freedom
attestation, sealed-partition control specs, short borrow/locate model, execution-enrichment contract,
metric-role registry + OOS-consumption protocol + null-model spec, numeric-runtime + structural-preflight
specs, and the consolidated validation authorization submission + publication manifest.

DRAFTING ONLY. Binds governing preregistration v1.0.4 and the evaluator identities by full SHA-256.
Opens NO validation or OOS data, computes NO returns/performance, grants NO authorization
(validation_authorization stays false). Reads only committed, non-sealed governing sources to bind them.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[4])
OUT = os.path.dirname(os.path.abspath(__file__))
RVW = os.path.join(ROOT, "docs", "review", "mr002")
EVAL = os.path.join(RVW, "evaluator")

# ---- governing preregistration v1.0.4 (owner-adjudicated governing source) ----
PREREG = "MR002_ValidationOOS_Preregistration_v1.0.4.json"
PREREG_COMMIT = "4385ec7728a81c0db965e2f44d6017e6116d027c"
PREREG_SHA = "b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c"
SUPERSEDED_PREREG_COMMIT = "c7a2e4b7ec5bb5012413bd385c78dee3e80d50cb"  # v1.0.3


def sha_file(p):  # noqa: ANN001
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def dump(obj, name):  # noqa: ANN001
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    open(p, "w", encoding="utf-8", newline="\n").write(
        json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n")
    return sha_file(p)


def dump_md(text, name):  # noqa: ANN001
    p = os.path.join(OUT, name)
    open(p, "w", encoding="utf-8", newline="\n").write(text)
    return sha_file(p)


def load(rel):  # noqa: ANN001
    return json.load(open(os.path.join(RVW, rel)))


# ---- bind governing-source identities ----
PREREG_JSON = load(PREREG)
assert sha_file(os.path.join(RVW, PREREG)) == PREREG_SHA, "prereg v1.0.4 content SHA mismatch -> STOP"
assert PREREG_JSON["version"] == "1.0.4"
CORRECTION_SHA = sha_file(os.path.join(RVW, "MR002_ValidationOOS_CorrectionRecord_v1.0.4.json"))
DSR_LEDGER_SHA = sha_file(os.path.join(RVW, "MR002_DSR_TrialLedger_v1.0.json"))
SEALED_MANIFEST_SHA = sha_file(os.path.join(
    ROOT, "docs", "implementation", "evidence", "mr_002", "MR002_SealedManifest_v1.0.json"))
EVALUATOR_IDENTITIES = {os.path.basename(f): sha_file(os.path.join(EVAL, f))
                        for f in sorted(os.listdir(EVAL)) if f.endswith(".py")}

DSR_LEDGER_BOUND = PREREG_JSON["dsr"]["trial_ledger_sha256"]
assert DSR_LEDGER_BOUND == "deda5cec0bbb72dd845633e99682849e6cf0db949e252dba956a432fcb383e9b"

# governing SignalDecisionRecord schema identity (Phase 2B producer; enrichment consumes it immutably)
SIGNAL_DECISION_RECORD_SCHEMA_SHA = "49c0e550f78127e04fcf92a649645aef23560173ccf89ef630dab30d4892497f"
SIGNAL_DECISION_RECORD_MODEL_SHA = sha_file(os.path.join(
    ROOT, "apps", "backend", "app", "research", "mr002", "spq1", "models.py"))
SAMPLE_STAGE = {"VALIDATION", "OOS", "VALIDATION_AND_OOS_COMBINED", "POST_RESEARCH_OPERABILITY"}

H = {}  # artifact -> sha256


# =====================================================================================
# WP 3A-1 — Governing-source extraction
# =====================================================================================
gsr = {
    "record_type": "MR002_Phase3A_GoverningSourceRegistry", "version": "1.0",
    "scope": "binds the governing Validation/OOS contract by full SHA-256; NO data opened; NO performance",
    "governing_preregistration": {
        "file": f"docs/review/mr002/{PREREG}", "version": "1.0.4",
        "commit": PREREG_COMMIT, "content_sha256": PREREG_SHA,
        "supersedes_v1_0_3_commit": SUPERSEDED_PREREG_COMMIT,
        "correction_record": "MR002_ValidationOOS_CorrectionRecord_v1.0.4.json",
        "correction_record_sha256": CORRECTION_SHA,
        "correction_classification": "INTEGRITY/GOVERNANCE (bootstrap transcription repair; not a trial)"},
    "bound_facts": {
        "windows": PREREG_JSON["windows_literal"],
        "validation_folds": PREREG_JSON["validation_folds_literal_governing"],
        "seam_rule": PREREG_JSON["seam_rule"],
        "gates_frozen": PREREG_JSON["gates_frozen"],
        "cost_model_frozen_values": PREREG_JSON["cost_model_frozen_values"],
        "exposure_limits_frozen": PREREG_JSON["exposure_limits_frozen"],
        "coverage_gates": PREREG_JSON["coverage_gates"],
        "bootstrap": PREREG_JSON["bootstrap"],
        "dsr": PREREG_JSON["dsr"],
        "sharpe_estimator": PREREG_JSON["sharpe_estimator"],
        "sealed_access_protocol": PREREG_JSON["sealed_access_protocol"],
        "sequencing": PREREG_JSON["sequencing"],
        "governing_frozen_sources": PREREG_JSON["governing_frozen_sources"],
        "governing_gate_source": PREREG_JSON["governing_gate_source"],
        "terminal_dispositions": PREREG_JSON["terminal_dispositions"]},
    "bound_artifact_identities": {
        "dsr_trial_ledger": {"file": "MR002_DSR_TrialLedger_v1.0.json", "sha256": DSR_LEDGER_SHA,
                             "bound_in_prereg": DSR_LEDGER_BOUND, "N": PREREG_JSON["dsr"]["trials_N"]},
        "sealed_manifest": {"file": "docs/implementation/evidence/mr_002/MR002_SealedManifest_v1.0.json",
                            "sha256": SEALED_MANIFEST_SHA},
        "authoritative_calendar_snapshot": PREREG_JSON["governing_frozen_sources"][
            "authoritative_calendar_snapshot"]},
    "evaluator_code_identities": {
        "status": "PREREQUISITE (full evaluator qualification binds file+blob+sha256+version+commit+tree"
                  "+container+lock+synthetic evidence; Phase 3A binds the current module SHA-256 as the "
                  "reference to be re-verified at evaluator qualification)",
        "modules": EVALUATOR_IDENTITIES},
    "authorization_state": {"validation_authorization": PREREG_JSON["sequencing"]["validation_authorization"],
                            "sealed_data_read": PREREG_JSON["sealed_data_read"]},
}
H["GoverningSourceRegistry"] = dump(gsr, "MR002_Phase3A_GoverningSourceRegistry_v1.0.json")

# diff-proof: every roadmap-bound value reproduces from the governing prereg v1.0.4
expected = {
    "validation_window": ("2020-01-13", "2023-02-08"),
    "oos_window": ("2023-05-30", "2026-07-01"),
    "folds": 5, "s_min": 0.70,
    "cost_side_bps": 10, "borrow_bps_per_year": 50, "adv_cap": 0.02, "nav_usd": 10_000_000,
    "bootstrap_name": "stationary (Politis-Romano, circular) bootstrap of daily net returns",
    "bootstrap_L_primary": 5, "bootstrap_L_sensitivity": 10, "bootstrap_reps": 10000,
    "bootstrap_seed": 20260711, "bootstrap_rng": "numpy_PCG64",
    "dsr_N": 5, "dsr_ledger": DSR_LEDGER_BOUND, "realization_horizon": 6,
    "validation_authorization": False,
}
actual = {
    "validation_window": (PREREG_JSON["windows_literal"]["validation"]["scoring_eligible_first"],
                          PREREG_JSON["windows_literal"]["validation"]["scoring_eligible_last"]),
    "oos_window": (PREREG_JSON["windows_literal"]["oos"]["scoring_eligible_first"],
                   PREREG_JSON["windows_literal"]["oos"]["scoring_eligible_last"]),
    "folds": len(PREREG_JSON["validation_folds_literal_governing"]),
    "s_min": float(PREREG_JSON["gates_frozen"]["oos_pass_requires_BOTH"][0].split(">=")[1]),
    "cost_side_bps": PREREG_JSON["cost_model_frozen_values"]["commission_slippage_bps_per_side"],
    "borrow_bps_per_year": PREREG_JSON["cost_model_frozen_values"]["borrow_bps_per_year"],
    "adv_cap": PREREG_JSON["cost_model_frozen_values"]["adv_participation_cap"],
    "nav_usd": PREREG_JSON["cost_model_frozen_values"]["nav_usd"],
    "bootstrap_name": PREREG_JSON["bootstrap"]["name"],
    "bootstrap_L_primary": PREREG_JSON["bootstrap"]["expected_block_length_primary_sessions"],
    "bootstrap_L_sensitivity": PREREG_JSON["bootstrap"]["expected_block_length_sensitivity_sessions"],
    "bootstrap_reps": PREREG_JSON["bootstrap"]["replications_each"],
    "bootstrap_seed": PREREG_JSON["bootstrap"]["seed"], "bootstrap_rng": PREREG_JSON["bootstrap"]["rng"],
    "dsr_N": PREREG_JSON["dsr"]["trials_N"], "dsr_ledger": PREREG_JSON["dsr"]["trial_ledger_sha256"],
    "realization_horizon": PREREG_JSON["seam_rule"]["realization_horizon_governing"],
    "validation_authorization": PREREG_JSON["sequencing"]["validation_authorization"],
}
diff = {k: {"expected": expected[k], "actual": actual[k], "reproduces": expected[k] == actual[k]}
        for k in expected}
all_reproduce = all(v["reproduces"] for v in diff.values())
assert all_reproduce, f"WP3A-1 diff-proof FAILED (a bound value does not reproduce) -> STOP: {diff}"
diffproof = {"record_type": "MR002_Phase3A_PregistrationDiffProof", "version": "1.0",
    "governing_preregistration_sha256": PREREG_SHA, "governing_commit": PREREG_COMMIT,
    "content_sha256_reproduces": sha_file(os.path.join(RVW, PREREG)) == PREREG_SHA,
    "facts": diff, "all_reproduce": all_reproduce,
    "stationary_bootstrap_not_moving_block": "the ACTIVE bootstrap block is stationary; moving-block keys "
        "absent (the correction narrative names the superseded values but they are not the active rule)",
    "moving_block_absent": ("block_length_sessions" not in PREREG_JSON["bootstrap"]
        and "resamples" not in PREREG_JSON["bootstrap"]
        and "stationary" in PREREG_JSON["bootstrap"]["name"])}
H["PregistrationDiffProof"] = dump(diffproof, "MR002_Phase3A_PregistrationDiffProof_v1.0.json")


# =====================================================================================
# WP 3A-2 — Degrees-of-freedom / multiplicity attestation
# =====================================================================================
CHANGES = [
    {"change": "v1.0.3 -> v1.0.4 bootstrap transcription correction (moving-block -> frozen v0.3 "
        "stationary Politis-Romano)", "classification": "GOVERNANCE_ONLY",
     "evidence": "MR002_ValidationOOS_CorrectionRecord_v1.0.4.json", "sha256": CORRECTION_SHA,
     "affects_trial_count": False, "performance_observed": False},
    {"change": "Phase 2B calendar verification-harness correction (dev_calendar_sha256 vs "
        "RegisteredCalendar.identity false-stop)", "classification": "INTEGRITY_ONLY",
     "evidence": "tests/research/spq1/test_spq1_phase2b_2.py + runner cal_sha check",
     "affects_trial_count": False, "performance_observed": False},
    {"change": "Non-injective request-identity collision amendment (run-spec v1.0 -> v1.1)",
     "classification": "GOVERNANCE_ONLY",
     "evidence": "RunSpecification_v1.1 (fd19aef5) + CollisionRuleAmendment_v1.1",
     "affects_trial_count": False, "performance_observed": False},
    {"change": "Runner-side collision detection (collision_rule.py; frozen bb029a96 unchanged)",
     "classification": "INTEGRITY_ONLY", "evidence": "collision_rule.py + CollisionCensus",
     "affects_trial_count": False, "performance_observed": False},
    {"change": "Terminal-key clarification (distinct_terminal_keys vs accepted-resolved)",
     "classification": "EVIDENCE_ONLY", "evidence": "MR002_SPQ1_Phase2B_2B3_TerminalKeyClarification_v1.0",
     "affects_trial_count": False, "performance_observed": False},
    {"change": "Phase 2B artifact / schema corrections + 2B-2 full run + 2B-3 governance closeout",
     "classification": "EVIDENCE_ONLY", "evidence": "Phase 2B evidence commit 1cc98f5 + closeout 4c358ac",
     "affects_trial_count": False, "performance_observed": False},
    {"change": "Post-Phase-2B roadmap v1.1 + v1.1.1 erratum (planning documents)",
     "classification": "GOVERNANCE_ONLY", "evidence": "MR002_Development_Plan_Next_Phases_v1.1{,.1}.md",
     "affects_trial_count": False, "performance_observed": False},
]
signal_affecting = [c for c in CHANGES if c["classification"] == "SIGNAL_OR_TRIAL_AFFECTING"]
attest = {"record_type": "MR002_Phase3A_MultiplicityAndDegreesOfFreedomAttestation", "version": "1.0",
    "scope": "every governed change from preregistration v1.0.3 through Phase 2B closure + the v1.0.4 "
             "bootstrap correction",
    "classification_domain": ["INTEGRITY_ONLY", "EVIDENCE_ONLY", "GOVERNANCE_ONLY",
                              "SIGNAL_OR_TRIAL_AFFECTING"],
    "changes": CHANGES,
    "conclusions": {"no_signal_threshold_changed": True, "no_holding_period_changed": True,
        "no_universe_selection_rule_changed": True, "no_portfolio_or_execution_rule_changed": True,
        "no_metric_gate_changed": True, "no_config_ABC_definition_changed": True,
        "no_performance_result_observed": True, "no_additional_trial_introduced": True},
    "gate": {"signal_or_trial_affecting_count": len(signal_affecting),
             "signal_or_trial_affecting_count_is_zero": len(signal_affecting) == 0,
             "dsr_multiplicity_N": PREREG_JSON["dsr"]["trials_N"], "dsr_N_remains_5": PREREG_JSON["dsr"]["trials_N"] == 5},
    "dsr_trial_ledger_sha256": DSR_LEDGER_BOUND}
assert len(signal_affecting) == 0 and PREREG_JSON["dsr"]["trials_N"] == 5, "WP3A-2 gate FAILED -> STOP"
H["MultiplicityAndDegreesOfFreedomAttestation"] = dump(
    attest, "MR002_Phase3A_MultiplicityAndDegreesOfFreedomAttestation_v1.0.json")


# =====================================================================================
# WP 3A-3 — Sealed-partition control (design specs + zero-access proof structure)
# =====================================================================================
seal_ctrl = {"record_type": "MR002_Phase3A_SealedPartitionControlSpecification", "version": "1.0",
    "extends": "prereg v1.0.4 sealed_access_protocol (CloudTrail S3 data events; dedicated IAM principal)",
    "required_properties": ["separate validation and OOS storage boundaries",
        "read credentials unavailable to ordinary development execution",
        "append-only access audit", "content commitments for sealed partitions",
        "hash-chained or otherwise tamper-evident access events",
        "explicit authorization event before credentials are released",
        "opened-object ledger for the authorized run",
        "post-run reconciliation against the store-level access log"],
    "two_required_records": {
        "OpenedObjectLedger": "what the AUTHORIZED PROGRAM opened (per-run)",
        "SealedStoreAccessLog": "whether ANYTHING opened the partition across program history"},
    "storage_boundaries": {"validation_partition": "separate bucket/prefix; validation-only IAM policy",
        "oos_partition": "separate bucket/prefix; explicit DENY during validation",
        "credential_custody": "dedicated IAM principal; keys not in developer env; released only on the "
            "explicit authorization event", "release_mechanism": "owner-signed authorization event -> "
            "time-bounded credential release -> access recorded"},
    "commitment_and_tamper_evidence": {"content_commitment": "custodian-produced value-blind content "
        "commitment (SHA-256 over canonical partition metadata + row-level content hash) committed BEFORE "
        "the research team receives the Phase 3A package",
        "access_events": "CloudTrail S3 GetObject data events; hash-chained export; policy-state snapshots "
            "before and after each execution"},
    "required_runtime_gate_values": {"note": "these are REQUIRED RUNTIME GATE VALUES to be evidenced by "
        "custodian-produced runtime instances BEFORE authorization; Phase 3A does NOT evidence them",
        "validation_access_events_before_authorization": 0, "oos_access_events_before_validation": 0,
        "oos_access_events_before_oos_authorization": 0},
    "artifact_kind": "SPECIFICATION_TEMPLATE", "contains_runtime_evidence": False,
    "runtime_instance_required_before_authorization": True,
    "reserved_runtime_evidence_names": ["ValidationPartitionAccessHistory_v1.0.json",
        "ValidationPartitionContentCommitment_v1.0.json", "ValidationSealVerificationReport_v1.0.json",
        "OOSPartitionAccessHistory_v1.0.json", "OOSPartitionContentCommitment_v1.0.json",
        "OOSSealVerificationReport_v1.0.json"],
    "governing_binding": {"prereg_sha256": PREREG_SHA,
        "sealed_manifest_sha256": SEALED_MANIFEST_SHA}}
H["SealedPartitionControlSpecification"] = dump(
    seal_ctrl, "MR002_Phase3A_SealedPartitionControlSpecification_v1.0.json")
H["SealedPartitionContentCommitment"] = dump({
    "record_type": "SealedPartitionContentCommitment", "version": "1.0",
    "artifact_kind": "SPECIFICATION_TEMPLATE", "contains_runtime_evidence": False,
    "runtime_instance_required_before_authorization": True,
    "runtime_evidence_names": ["ValidationPartitionContentCommitment_v1.0.json",
        "OOSPartitionContentCommitment_v1.0.json"],
    "purpose": "custodian-produced, value-blind content commitment of the sealed validation & OOS "
        "partitions, committed before the research team receives Phase 3A; enables post-authorization "
        "structural verification without pre-authorization row access",
    "commitment_scheme": {"algorithm": "SHA-256 over canonical (sorted) partition content",
        "value_blind_metadata": ["schema identity", "table names", "row counts", "date bounds",
            "session count", "symbol/security counts", "factor-series coverage", "null-count summaries",
            "latest source date"],
        "custodian_binding": "custodian process identity + access event MUST be audit-bound"},
    "status": "SPECIFICATION (actual commitments produced by the custodian before authorization; values "
        "not present in this drafting artifact)"},
    "SealedPartitionContentCommitment_v1.0.json")
H["SealedPartitionAccessHistory"] = dump({
    "record_type": "SealedPartitionAccessHistory", "version": "1.0",
    "artifact_kind": "SPECIFICATION_TEMPLATE", "contains_runtime_evidence": False,
    "runtime_instance_required_before_authorization": True,
    "runtime_evidence_names": ["ValidationPartitionAccessHistory_v1.0.json",
        "OOSPartitionAccessHistory_v1.0.json"],
    "content": "METADATA ONLY + proof of zero unauthorized access (NO partition values)",
    "record_fields": ["partition", "event_time_utc", "principal", "operation", "object_key_prefix",
        "authorized (bool)", "authorization_event_ref", "hash_chain_prev", "hash_chain_row"],
    "required_runtime_gate_values": {"note": "required at runtime; NOT evidenced by this template",
        "validation_access_events_before_authorization": 0,
        "oos_access_events_before_validation": 0, "oos_access_events_before_oos_authorization": 0}},
    "SealedPartitionAccessHistory_v1.0.json")
H["SealVerificationReport"] = dump({
    "record_type": "SealVerificationReport", "version": "1.0",
    "artifact_kind": "SPECIFICATION_TEMPLATE", "contains_runtime_evidence": False,
    "runtime_instance_required_before_authorization": True,
    "runtime_evidence_names": ["ValidationSealVerificationReport_v1.0.json",
        "OOSSealVerificationReport_v1.0.json"],
    "verifies": ["content commitment stable", "no access-before-authorization events",
        "OpenedObjectLedger reconciles against SealedStoreAccessLog",
        "OOS partition DENY in force during validation"],
    "distinction": {"OpenedObjectLedger": "per-run opened objects",
        "SealedStoreAccessLog": "program-history access to the partition"}},
    "SealVerificationReport_v1.0.json")


# =====================================================================================
# WP 3A-4 — Short borrow/locate/SSR model
# =====================================================================================
FACT = ["OBSERVED_PIT_FACT", "RECONSTRUCTED_PIT_FACT", "CONSERVATIVE_PROXY", "UNOBSERVABLE_LIMITATION"]
short_rules = [
    {"rule": "borrow financing cost", "value": "50 bps/yr (day-count 360); 300 bps/yr stress",
     "class": "OBSERVED_PIT_FACT", "data_source": "prereg v1.0.4 cost_model_frozen_values.borrow_bps_per_year",
     "effective_date": "frozen", "fallback": "n/a", "economic_effect": "reduces net short return",
     "primary_gate_input": True, "diagnostic": False},
    {"rule": "borrow availability / locate", "value": "PIT borrow availability is generally not "
        "reconstructable for this data tier", "class": "UNOBSERVABLE_LIMITATION",
     "data_source": "none (no historical locate feed)", "effective_date": "n/a",
     "fallback": "CONSERVATIVE_PROXY (below)", "economic_effect": "may prevent or resize a short",
     "primary_gate_input": False, "diagnostic": True},
    {"rule": "conservative availability proxy", "value": "shortability proxy = a security is shortable "
        "only if it satisfies a preregistered liquidity/size floor at close t (exact floor bound in the "
        "conservative-view spec); otherwise REFUSED_SHORT_UNAVAILABLE",
     "class": "CONSERVATIVE_PROXY", "data_source": "PIT price/ADV/market-cap already in the frozen "
        "universe", "effective_date": "close t", "fallback": "refuse the short (no synthetic locate)",
     "economic_effect": "reduces short breadth in the conservative view", "primary_gate_input": False,
     "diagnostic": True},
    {"rule": "Regulation SHO / SSR", "value": "if reconstructable from PIT price (>=10% intraday decline "
        "trigger), apply uptick restriction to short entries the following session; else disclose as "
        "UNOBSERVABLE_LIMITATION", "class": "RECONSTRUCTED_PIT_FACT",
     "data_source": "PIT prior-close vs low (approx)", "effective_date": "t+1", "fallback": "disclose",
     "economic_effect": "delays/blocks some short entries in the conservative view",
     "primary_gate_input": False, "diagnostic": True},
]
short_answers = {
    "short_cannot_be_located": "conservative view: the candidate short is REFUSED (REFUSED_SHORT_UNAVAILABLE) "
        "- not synthetically located; primary view: borrow available by assumption (borrow COST applied)",
    "refused_delayed_or_resized": "REFUSED (fail-closed) in the conservative view; never silently resized "
        "to fabricate neutrality",
    "cost_applied_to_accepted_shorts": "50 bps/yr borrow financing (primary); 300 bps/yr stress; 1000 bps/yr "
        "severe diagnostic",
    "ssr_active": "conservative view applies an uptick restriction to the next-session short entry where "
        "reconstructable; otherwise disclosed as a limitation",
    "pending_short_exits": "buy-to-cover at next-open t+1 per the frozen execution rule; a pending exit is "
        "never dropped",
    "buy_to_cover_failure": "treated as a fail-closed INTEGRITY_STOP; no silent carry",
    "failed_entry_one_sided_or_ghost_position": "PROHIBITED - a refused short does not create a naked long; "
        "portfolio is reconstructed under the preregistered rule below (no ghost/one-sided position)",
    "unavailable_short_alters_dollar_neutrality": "conservative view: the paired long gross is reduced to "
        "preserve dollar-neutrality (long_gross == short_gross) under a preregistered reconstruction rule; "
        "it does NOT run one-sided",
    "portfolio_fails_or_reconstructed": "reconstructed under a preregistered conservative rule (scale the "
        "book to the achievable neutral gross), NOT a post-hoc discretionary fix; the exact rule is frozen "
        "in the conservative-view spec before validation",
}
short_spec = {"record_type": "ShortBorrowLocateModelSpecification", "version": "1.0",
    "views": {
        "PRIMARY_GATE": {"name": "preregistered net model", "borrow_financing_included": True,
            "borrow_bps_per_year": 50, "borrow_availability": "assumed (frictionless availability)",
            "note": "this is the frozen preregistered research test; net_oos_sharpe >= 0.70 is computed "
                "on THIS series and MUST NOT move to the conservative view"},
        "SECONDARY_GATE_ECONOMIC_OPERABILITY": {"name": "conservative availability/locate/SSR model",
            "role": "may BLOCK product promotion; does NOT replace the primary statistical test",
            "no_manufactured_locate_data": True},
        "DIAGNOSTIC_ONLY": {"name": "zero-borrow-cost frictionless short attribution",
            "label": "FRICTIONLESS_SHORT_RESEARCH_DIAGNOSTIC / NOT AN IMPLEMENTABLE PERFORMANCE ESTIMATE"}},
    "rule_classification_domain": FACT,
    "rules": short_rules, "governed_answers": short_answers,
    "relation_to_primary_gate": "the conservative view is a SECONDARY/ECONOMIC_OPERABILITY_GATE; it changes "
        "NO preregistered value and does not redefine net_oos_sharpe >= 0.70",
    "prohibition": "do NOT manufacture historical locate data that does not exist; unobservable facts are "
        "labeled UNOBSERVABLE_LIMITATION and disclosed",
    "governing_binding": {"prereg_sha256": PREREG_SHA}}
H["ShortBorrowLocateModelSpecification"] = dump(
    short_spec, "ShortBorrowLocateModelSpecification_v1.0.json")


# =====================================================================================
# WP 3A-5 — Execution-enrichment contract (t+1)
# =====================================================================================
ENRICH_CODES = {
    "EXECUTION_ENRICHMENT_SUCCESS": "official next-open t+1 attached; decision record bound; no future info",
    "EXECUTION_ENRICHMENT_STOP:NO_OFFICIAL_OPEN": "no official open at t+1 (fail closed; no fallback price)",
    "EXECUTION_ENRICHMENT_STOP:TRADING_HALT": "t+1 halt / no execution session (fail closed)",
    "EXECUTION_ENRICHMENT_STOP:DELISTING": "delisted at/before t+1 (fail closed)",
    "EXECUTION_ENRICHMENT_STOP:IDENTITY_CONFLICT": "symbol/permanent-security transition or non-injective "
        "identity at execution (fail closed; no post-hoc winner)",
    "EXECUTION_ENRICHMENT_STOP:CORPORATE_ACTION_UNRESOLVED": "split/dividend/merger/cash+stock/"
        "cash-acquisition not resolvable to a registered adjusted open (fail closed)",
    "EXECUTION_ENRICHMENT_STOP:SOURCE_MISSING": "official-open source/identity missing or changed",
    "EXECUTION_ENRICHMENT_STOP:PRICE_CONFLICT": "missing or conflicting open prices; adjusted-vs-unadjusted "
        "identity mismatch; calendar mismatch (execution session != registered next session)",
    "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED": "any t+1 fact that would inject information after close t",
}
enrich_edge = {"record_type": "MR002_Phase3A_ExecutionEnrichmentEdgeCaseSpecification", "version": "1.0",
    "default": "FAIL CLOSED. No silent price substitution, previous-close fallback, later-open fallback, "
        "or post-hoc security winner.",
    "registered_edge_cases": {
        "no_official_open": "EXECUTION_ENRICHMENT_STOP:NO_OFFICIAL_OPEN",
        "trading_halt": "EXECUTION_ENRICHMENT_STOP:TRADING_HALT",
        "delisting": "EXECUTION_ENRICHMENT_STOP:DELISTING",
        "symbol_or_permsec_transition": "EXECUTION_ENRICHMENT_STOP:IDENTITY_CONFLICT",
        "split_close_t_to_open_t1": "EXECUTION_ENRICHMENT_STOP:CORPORATE_ACTION_UNRESOLVED (unless a "
            "registered adjusted open resolves it)",
        "dividend_or_distribution": "registered adjusted open OR CORPORATE_ACTION_UNRESOLVED",
        "merger_consideration": "EXECUTION_ENRICHMENT_STOP:CORPORATE_ACTION_UNRESOLVED",
        "cash_only_acquisition": "EXECUTION_ENRICHMENT_STOP:CORPORATE_ACTION_UNRESOLVED",
        "stock_and_cash_acquisition": "EXECUTION_ENRICHMENT_STOP:CORPORATE_ACTION_UNRESOLVED",
        "missing_or_conflicting_open": "EXECUTION_ENRICHMENT_STOP:PRICE_CONFLICT",
        "adjusted_vs_unadjusted_open_identity": "EXECUTION_ENRICHMENT_STOP:PRICE_CONFLICT",
        "calendar_mismatch": "EXECUTION_ENRICHMENT_STOP:PRICE_CONFLICT",
        "execution_session_ne_registered_next": "EXECUTION_ENRICHMENT_STOP:PRICE_CONFLICT",
        "future_information": "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED"},
    "per_record_bindings": ["ExecutionEnrichmentDisposition", "ExecutionEnrichmentCode",
        "decision_record_sha256", "requested_execution_session", "actual_source_session",
        "corporate_action_identity", "official_open_source_identity", "terminal_treatment"],
    "census_categories": ["successful enrichment", "no-open", "halt", "delisting",
        "corporate-action transition", "identity conflict", "missing source", "future-information stop",
        "other registered disposition"],
    "census_note": "recomputed from the authorized partition; known cases may be registered in advance but "
        "are NOT a fixed expected-count gate",
    "each_outcome": {"one_terminal_treatment": True, "no_silent_fallback": True, "one_census_category": True,
        "one_reconciliation_path": True},
    "execution_rule_binding": {"execution": PREREG_JSON["cost_model_frozen_values"]["execution"],
        "realization_horizon": PREREG_JSON["seam_rule"]["realization_horizon_governing"],
        "forward_fill": PREREG_JSON["cost_model_frozen_values"]["forward_fill"]}}
H["ExecutionEnrichmentEdgeCaseSpecification"] = dump(
    enrich_edge, "MR002_Phase3A_ExecutionEnrichmentEdgeCaseSpecification_v1.0.json")
H["ExecutionEnrichmentCodeRegistry"] = dump({
    "record_type": "ExecutionEnrichmentCodeRegistry", "version": "1.0",
    "namespace": "EXECUTION_ENRICHMENT_* (SEPARATE from signal-production refusal codes)",
    "codes": ENRICH_CODES,
    "invariant": "each code has exactly one terminal treatment, no silent fallback, one census category, "
        "one reconciliation path; enrichment codes are never reused for signal-production failures"},
    "ExecutionEnrichmentCodeRegistry_v1.0.json")
H["ExecutionEnrichmentSchema"] = dump({
    "record_type": "ExecutionEnrichmentSchema", "version": "1.0",
    "binding": "immutable SignalDecisionRecord -> ExecutionEnrichedCandidateRecord",
    "signal_decision_record_ref": {"bound_by": "decision_record_sha256 (Phase 2B publication)",
        "immutable": True, "never_mutated_by_enrichment": True},
    "enriched_candidate_record_fields": ["decision_record_sha256", "decision_session_t",
        "execution_session_t_plus_1", "official_open_source_identity", "official_open_price_ref",
        "realization_horizon", "ExecutionEnrichmentDisposition", "ExecutionEnrichmentCode",
        "corporate_action_identity", "conservative_short_flag"],
    "future_information_guard": "any t+1 fact bearing on close-t decision -> INTEGRITY_STOP:"
        "FUTURE_INFORMATION_DETECTED",
    "execution": PREREG_JSON["cost_model_frozen_values"]["execution"],
    "realization_horizon": PREREG_JSON["seam_rule"]["realization_horizon_governing"]},
    "ExecutionEnrichmentSchema_v1.0.json")


# =====================================================================================
# WP 3A-6 — Metric roles, OOS-consumption, null-model
# =====================================================================================
ROLE = {"PRIMARY_GATE", "SECONDARY_GATE", "DIAGNOSTIC_ONLY", "INTEGRITY_ONLY"}
# metric -> (role, sample_stage) ; sample_stage bound from prereg v1.0.4 gates_frozen "sample" fields
metric_roles = {
    "net_oos_sharpe_ge_0.70": ("PRIMARY_GATE", "OOS"),
    "one_sided_95pct_bootstrap_lower_bound_daily_mean_net_return_gt_0": ("PRIMARY_GATE", "OOS"),
    "dsr_significance_ge_0.95_N5": ("PRIMARY_GATE", "OOS"),
    "net_annualized_return_ge_0.03": ("SECONDARY_GATE", "OOS"),
    "net_max_drawdown_le_0.15": ("SECONDARY_GATE", "VALIDATION_AND_OOS_COMBINED"),
    "net_oos_calmar_ge_0.75": ("SECONDARY_GATE", "OOS"),
    "cost_stress_profitable_20bps_300bps": ("SECONDARY_GATE", "OOS"),
    "breadth_trades_ge_500_entrydates_ge_100_long_ge_100_short_ge_100": ("SECONDARY_GATE", "OOS"),
    "trade_concentration_single_le_0.10_top10_le_0.20": ("SECONDARY_GATE", "OOS"),
    "annual_profile_min_3_positive_years_largest_le_0.50": ("SECONDARY_GATE", "VALIDATION_AND_OOS_COMBINED"),
    "regime_gates_2of3_trend_positive_no_vol_sharpe_lt_-0.5": ("SECONDARY_GATE", "VALIDATION_AND_OOS_COMBINED"),
    "validation_positive_folds_ge_3_of_5": ("SECONDARY_GATE", "VALIDATION"),
    "parameter_stability_A_and_C_net_profitable": ("SECONDARY_GATE", "VALIDATION"),
    "conservative_availability_borrow_ssr_economic_operability": ("SECONDARY_GATE", "POST_RESEARCH_OPERABILITY"),
    "pbo_cscv": ("DIAGNOSTIC_ONLY", "VALIDATION"),
    "positive_pnl_regime_concentration": ("DIAGNOSTIC_ONLY", "VALIDATION_AND_OOS_COMBINED"),
    "annual_herfindahl": ("DIAGNOSTIC_ONLY", "VALIDATION_AND_OOS_COMBINED"),
    "diversifier_tier_tag": ("DIAGNOSTIC_ONLY", "OOS"),
    "frictionless_short_attribution": ("DIAGNOSTIC_ONLY", "OOS"),
    "severe_cost_30bps_1000bps": ("DIAGNOSTIC_ONLY", "OOS"),
    "expected_L10_bootstrap_sensitivity": ("DIAGNOSTIC_ONLY", "OOS"),
    "dsr_trial_dispersion_validation": ("DIAGNOSTIC_ONLY", "VALIDATION"),
    "zero_vol_peak_to_peak": ("INTEGRITY_ONLY", "VALIDATION_AND_OOS_COMBINED"),
    "data_and_pitsic_coverage_gates": ("INTEGRITY_ONLY", "VALIDATION_AND_OOS_COMBINED"),
    "exposure_limit_breach": ("INTEGRITY_ONLY", "VALIDATION_AND_OOS_COMBINED"),
    "replay_integrity": ("INTEGRITY_ONLY", "VALIDATION_AND_OOS_COMBINED"),
}
metric_entries = {m: {"metric_role": r, "sample_stage": s} for m, (r, s) in metric_roles.items()}
assert all(r in ROLE and s in SAMPLE_STAGE for (r, s) in metric_roles.values())
# integrity metrics apply at each stage independently (a stage-invariant check, not a combined statistic)
for m in ("zero_vol_peak_to_peak", "data_and_pitsic_coverage_gates", "exposure_limit_breach",
          "replay_integrity"):
    metric_entries[m]["stage_note"] = "integrity check applied at EACH stage independently (not a combined-sample statistic)"
H["MetricRoleRegistry"] = dump({
    "record_type": "MR002_Phase3A_MetricRoleRegistry", "version": "1.0",
    "bound_from": "prereg v1.0.4 gates_frozen (role + sample) + roadmap v1.1.1 short-side classification",
    "prereg_sha256": PREREG_SHA, "role_domain": sorted(ROLE), "sample_stage_domain": sorted(SAMPLE_STAGE),
    "metrics": metric_entries,
    "primary_gate_note": "the primary statistical test is net_oos_sharpe >= 0.70 (net return INCLUDING "
        "50 bps/yr borrow financing) AND one-sided 95% bootstrap LB > 0 AND DSR >= 0.95 at N=5; all three "
        "have sample_stage=OOS and MUST NOT be evaluated during validation nor moved to the conservative view",
    "sample_stage_rule": "role alone does not prevent a correct metric from being applied to the wrong "
        "phase; every metric carries sample_stage, and OOS-sample metrics are prohibited during validation "
        "(see ValidationStageDecisionSpecification)",
    "immutability": "metric roles + sample_stages are hash-bound to this registry; they cannot change "
        "after publication (any change re-versions the registry and requires re-authorization)"},
    "MR002_Phase3A_MetricRoleRegistry_v1.0.json")

# --- WP 3A-6 addition: validation-stage advancement decision (SEPARATE from OOS gates) ---
oos_only_prohibited = sorted(m for m, (r, s) in metric_roles.items()
                             if s in ("OOS", "VALIDATION_AND_OOS_COMBINED") and r != "INTEGRITY_ONLY")
validation_stage_metrics = sorted(m for m, (r, s) in metric_roles.items()
                                  if s in ("VALIDATION",) or r == "INTEGRITY_ONLY")
H["ValidationStageDecisionSpecification"] = dump({
    "record_type": "MR002_Phase3A_ValidationStageDecisionSpecification", "version": "1.0",
    "purpose": "freezes the validation-stage advancement rule SEPARATELY from the sealed-OOS primary "
        "gates; validation does NOT evaluate net_oos_sharpe, the OOS bootstrap gate, or OOS DSR",
    "prereg_sha256": PREREG_SHA,
    "metrics_computed_during_validation": sorted(set(validation_stage_metrics)),  # canonical, set-like
    "validation_gates": {
        "validation_positive_folds_ge_3_of_5": {"config": "B", "rule": ">= 3 of 5 folds net-positive",
            "source": "gates_frozen.validation_positive_folds_min_of_5 + positive_folds_sample"},
        "parameter_stability_A_and_C_net_profitable": {"rule": "Configs A and C both net-profitable",
            "source": "gates_frozen.parameter_stability + stability_sample=validation"}},
    "validation_diagnostics_reported_not_gating": {
        "pbo_cscv": "DIAGNOSTIC_ONLY (config-B per-fold); reported, NEVER changes the advance verdict",
        "positive_pnl_regime_concentration": "DIAGNOSTIC_ONLY; reported, NEVER changes the advance verdict",
        "annual_herfindahl": "DIAGNOSTIC_ONLY; reported, NEVER changes the advance verdict",
        "directional_coherence_A_B_C": "DIAGNOSTIC_ONLY; reported, NEVER changes the advance verdict",
        "single_year_sector_side_issuer_concentration": "DIAGNOSTIC_ONLY; reported, NEVER changes the "
            "advance verdict (no post-hoc red-flag test introduced after validation is observed)",
        "dsr_trial_dispersion_validation": "validation annualized net Sharpes of A/B/C; frozen input to "
            "the OOS DSR; NOT a validation pass/fail"},
    "oos_only_metrics_prohibited_during_validation": oos_only_prohibited,
    "oos_authorization_request_conditions": ["every validation integrity gate passes",
        "Config B >= 3 of 5 folds net-positive", "Configs A and C both net-profitable",
        "no post-validation tuning requested"],
    "advancement_conditions_are_binding_and_deterministic": True,
    "advancement_conditions_exclude_diagnostics": "PBO, concentration, and directional-coherence are "
        "DIAGNOSTIC_ONLY: reported but cannot independently change the validation advancement verdict; no "
        "discretionary red-flag test may be introduced after validation is observed",
    "config_A_C_treatment": "the parameter-stability gate (A and C both net-profitable) is a VALIDATION "
        "gate; A and C are neighboring robustness configs and NEVER substitute for B in the OOS run",
    "dsr_dispersion_treatment": {"computed_during": "validation",
        "source": "validation-period annualized net Sharpes of A, B, C; sample std ddof=1; /sqrt(252)",
        "rng001_rng_entrylogic": "retained in N=5; EXCLUDED from dispersion",
        "artifact": "MR002_DSR_TrialDispersion_Validation_v1.0.json (frozen before OOS; feeds OOS DSR)"},
    "allowed_verdicts": ["VALIDATION_ADVANCE_REQUEST", "VALIDATION_DO_NOT_ADVANCE",
        "VALIDATION_INCONCLUSIVE", "INTEGRITY_FAILURE"],
    "advance_meaning": "VALIDATION_ADVANCE_REQUEST authorizes a REQUEST for separate OOS authorization; it "
        "does NOT open OOS and does NOT evaluate any OOS gate"},
    "MR002_Phase3A_ValidationStageDecisionSpecification_v1.0.json")
H["ValidationMetricSpecification"] = dump({
    "record_type": "ValidationMetricSpecification", "version": "1.0",
    "sharpe_estimator": PREREG_JSON["sharpe_estimator"], "bootstrap": PREREG_JSON["bootstrap"],
    "dsr": PREREG_JSON["dsr"], "gates_frozen": PREREG_JSON["gates_frozen"],
    "metric_role_registry_ref": "MR002_Phase3A_MetricRoleRegistry_v1.0.json",
    "metric_role_registry_sha256": H["MetricRoleRegistry"],
    "note": "definitions bound verbatim from prereg v1.0.4; no metric computed during Phase 3A"},
    "ValidationMetricSpecification_v1.0.json")
H["OOSConsumptionProtocol"] = dump({
    "record_type": "MR002_Phase3A_OOSConsumptionProtocol", "version": "1.0",
    "stages": {"O1": "seal verification and input preflight", "O2": "enrichment and integrity reconciliation",
        "O3": "portfolio replay", "O4": "metric materialization", "O5": "human-visible release"},
    "non_consumptive_requires_all": ["failure is orthogonal to performance",
        "no portfolio return series was materialized", "no metric was calculated", "no metric was logged",
        "no metric artifact was written", "no metric was displayed to an operator",
        "no configuration comparison was produced", "no directional performance fact was observed",
        "the failure and repair are fully audit-bound"],
    "non_consumptive_effect": "permits an ADJUDICATION REQUEST for one clean rerun; does NOT auto-authorize",
    "consumptive_triggers": ["returns", "PnL", "Sharpe", "drawdown", "win rate", "config comparison",
        "partial-period performance", "any directional profitable/unprofitable statement"],
    "consumptive_effect": "OOS opportunity consumed; NO repair-and-rerun under the same preregistration",
    "stage_rule": {"O1_O2": "may qualify as non-consumptive if the no-metric proof holds",
        "O3_or_later": "presumptively CONSUMES OOS unless the artifact chain proves no return/performance "
            "information was produced"},
    "attestation_artifact": "OOSConsumptionStateAttestation_v1.0.json (produced at OOS run time, not Phase 3A)"},
    "MR002_Phase3A_OOSConsumptionProtocol_v1.0.json")
H["ValidationNullModelSpecification"] = dump({
    "record_type": "ValidationNullModelSpecification", "version": "1.0",
    "purpose": "bind and explain the already-registered 5-trial DSR multiplicity ledger; invent NO sixth "
        "null, rerun NO RNG program unless preregistered, search NO alternative randomization, choose NO "
        "more favorable multiplicity adjustment",
    "dsr_multiplicity_N": PREREG_JSON["dsr"]["trials_N"], "trial_ledger_sha256": DSR_LEDGER_BOUND,
    "trial_set": ["Config A", "Config B", "Config C", "RNG-001", "RNG-EntryLogic"],
    "dispersion_rule": {"source": "validation-period annualized net Sharpes of A, B, and C",
        "estimator": "sample standard deviation, ddof=1", "per_observation_conversion": "divide by sqrt(252)",
        "rng001_rng_entrylogic": "retained in N; EXCLUDED from dispersion (no comparable frozen Sharpes)",
        "required_pre_oos_artifact": "MR002_DSR_TrialDispersion_Validation_v1.0.json (generated DURING the "
            "authorized validation run, frozen before OOS; NOT computed in Phase 3A)"},
    "confirms": "no additional trial arose after preregistration; DSR N remains 5"},
    "ValidationNullModelSpecification_v1.0.json")


# =====================================================================================
# WP 3A-7 — Numeric runtime + structural preflight
# =====================================================================================
runtime_ref = {"python": sys.version.split()[0], "python_impl": platform.python_implementation(),
    "platform": platform.platform(), "machine": platform.machine()}
try:
    import numpy  # noqa: E402
    import pandas  # noqa: E402
    import scipy  # noqa: E402
    runtime_ref.update({"numpy": numpy.__version__, "scipy": scipy.__version__, "pandas": pandas.__version__})
    try:
        bd = numpy.show_config(mode="dicts").get("Build Dependencies", {})
        runtime_ref["blas"] = bd.get("blas", {}).get("name")
        runtime_ref["blas_version"] = bd.get("blas", {}).get("version")
        runtime_ref["lapack"] = bd.get("lapack", {}).get("name")
        runtime_ref["lapack_version"] = bd.get("lapack", {}).get("version")
    except Exception:
        runtime_ref["blas"] = "capture_at_qualification"
except Exception:
    pass
H["NumericRuntimeIdentityManifest"] = dump({
    "record_type": "NumericRuntimeIdentityManifest", "version": "1.0",
    "required_bindings": ["python version", "numpy version", "scipy version", "pandas version",
        "BLAS vendor+version", "LAPACK vendor+version", "LAPACK/solver driver", "CPU architecture",
        "thread-count env vars (OMP_NUM_THREADS, OPENBLAS_NUM_THREADS, MKL_NUM_THREADS, NUMEXPR_NUM_THREADS)",
        "random-number generator algorithm", "all registered seeds", "locale", "timezone",
        "dependency lockfile SHA-256", "container-image digest or environment-build identity",
        "Python executable identity", "NumPy/SciPy binary identities where available"],
    "frozen_solver_settings": {"solver": "numpy.linalg.lstsq", "lapack": "gelsd/SVD", "dtype": "float64",
        "rcond": 1e-10},
    "registered_seeds": {"bootstrap_seed": PREREG_JSON["bootstrap"]["seed"], "rng": PREREG_JSON["bootstrap"]["rng"]},
    "threading_policy": "for deterministic replay, either FREEZE the thread-count env vars or PROVE that "
        "varying them does not change governed output hashes",
    "drafting_reference_runtime": runtime_ref,
    "lockfile_binding": "REQUIRED at validation run time (lockfile SHA-256 + container/env-build digest); "
        "not a placeholder value",
    "mismatch_policy": "a numeric-runtime identity mismatch at run time FAIL-STOPS before any metric"},
    "NumericRuntimeIdentityManifest_v1.0.json")
H["ValidationStructuralManifestSpecification"] = dump({
    "record_type": "ValidationStructuralManifestSpecification", "version": "1.0",
    "producer": "trusted sealing/custodian process (audit-bound identity + access event), BEFORE sealing",
    "value_blind_fields": ["partition content commitment", "schema identity", "table names", "row counts",
        "date bounds", "session count", "symbol/security counts", "factor-series coverage",
        "null-count summaries", "latest source date"],
    "null_count_definition": "a null count is structurally descriptive but still requires row access; it is "
        "value-blind ONLY when produced by the sealing/custodian process, NEVER by a direct developer query",
    "preauthorization_access": {"permitted": ["precommitted structural manifest", "content commitment",
        "sealed-store access history"], "prohibited": ["direct query of underlying validation/OOS rows"]},
    "postauthorization": "the authorized run verifies actual structure reproduces this precommitted manifest; "
        "recorded in BOTH SealedStoreAccessLog and OpenedObjectLedger"},
    "ValidationStructuralManifestSpecification_v1.0.json")
H["ValidationPartitionStructuralPreflight"] = dump({
    "record_type": "ValidationPartitionStructuralPreflight", "version": "1.0",
    "operates_from": "precommitted sealing metadata ONLY until validation access is separately authorized",
    "mode_domain": ["STRUCTURAL_PREFLIGHT", "PERFORMANCE_OBSERVATION"],
    "authorized_mode_preauthorization": "STRUCTURAL_PREFLIGHT",
    "structural_checks": ["partition identity", "date range", "session count", "required table presence",
        "row counts", "symbol/security coverage", "required factor-series coverage", "schema identity",
        "null-count summaries (custodian-produced)", "latest available source date",
        "no rows outside the registered partition"],
    "must_not": ["calculate returns", "calculate signals", "rank", "calculate performance",
        "query sealed rows directly"],
    "preauthorization_direct_validation_reads": 0},
    "ValidationPartitionStructuralPreflight_v1.0.json")


# =====================================================================================
# WP 3A-8 — Consolidated authorization submission + publication manifest
# =====================================================================================
H["ValidationCostExecutionSpecification"] = dump({
    "record_type": "ValidationCostExecutionSpecification", "version": "1.0",
    "cost_model_frozen_values": PREREG_JSON["cost_model_frozen_values"],
    "exposure_limits_frozen": PREREG_JSON["exposure_limits_frozen"],
    "coverage_gates": PREREG_JSON["coverage_gates"], "seam_rule": PREREG_JSON["seam_rule"],
    "short_model_ref": "ShortBorrowLocateModelSpecification_v1.0.json",
    "short_model_sha256": H["ShortBorrowLocateModelSpecification"],
    "enrichment_ref": "MR002_Phase3A_ExecutionEnrichmentEdgeCaseSpecification_v1.0.json",
    "enrichment_sha256": H["ExecutionEnrichmentEdgeCaseSpecification"],
    "note": "bound verbatim from prereg v1.0.4; no cost/exposure value changed"},
    "ValidationCostExecutionSpecification_v1.0.json")
H["ValidationInputIdentityManifest"] = dump({
    "record_type": "ValidationInputIdentityManifest", "version": "1.0",
    "governing_preregistration": {"file": PREREG, "commit": PREREG_COMMIT, "content_sha256": PREREG_SHA},
    "governing_frozen_sources": PREREG_JSON["governing_frozen_sources"],
    "governing_gate_source": PREREG_JSON["governing_gate_source"],
    "dsr_trial_ledger_sha256": DSR_LEDGER_SHA, "correction_record_sha256": CORRECTION_SHA,
    "sealed_manifest_sha256": SEALED_MANIFEST_SHA,
    "evaluator_code_identities_prerequisite": EVALUATOR_IDENTITIES,
    "validation_partition": "SEALED_AND_UNREAD (identity bound via custodian content commitment, not read)"},
    "ValidationInputIdentityManifest_v1.0.json")
H["ValidationRunSpecification"] = dump({
    "record_type": "ValidationRunSpecification", "version": "1.0",
    "run_id": "MR002-SPQ1-VALIDATION-V1 (PROPOSED; not authorized to execute)",
    "governing_preregistration_sha256": PREREG_SHA,
    "windows": PREREG_JSON["windows_literal"]["validation"],
    "folds": PREREG_JSON["validation_folds_literal_governing"], "seam_rule": PREREG_JSON["seam_rule"],
    "configs": {"validation": "A, B, C", "oos_candidate": "B only"},
    "sequencing": PREREG_JSON["sequencing"],
    "validation_stage_decision_ref": "MR002_Phase3A_ValidationStageDecisionSpecification_v1.0.json",
    "validation_stage_decision_sha256": H["ValidationStageDecisionSpecification"],
    "bound_schemas": {
        "SignalDecisionRecord_schema_sha256": SIGNAL_DECISION_RECORD_SCHEMA_SHA,
        "SignalDecisionRecord_model_module_sha256": SIGNAL_DECISION_RECORD_MODEL_SHA,
        "ExecutionEnrichmentSchema_sha256": H["ExecutionEnrichmentSchema"],
        "fail_closed": "the run MUST fail closed if EITHER the SignalDecisionRecord schema identity OR the "
            "ExecutionEnrichmentSchema identity differs from the values bound here"},
    "bound_specifications": {k: H[k] for k in (
        "MetricRoleRegistry", "ValidationStageDecisionSpecification", "ValidationMetricSpecification",
        "ValidationCostExecutionSpecification", "ValidationNullModelSpecification", "OOSConsumptionProtocol",
        "ExecutionEnrichmentSchema", "ExecutionEnrichmentEdgeCaseSpecification",
        "ExecutionEnrichmentCodeRegistry", "ShortBorrowLocateModelSpecification",
        "SealedPartitionControlSpecification", "NumericRuntimeIdentityManifest",
        "ValidationStructuralManifestSpecification", "ValidationPartitionStructuralPreflight",
        "ValidationInputIdentityManifest")},
    "runtime_critical_bindings_required_before_execution": {
        "note": "the run specification proves EXACTLY what a future execution is allowed to consume; each "
            "must be identity-verified (fail-closed on mismatch) before any validation access",
        "ValidationInputIdentityManifest_sha256": H["ValidationInputIdentityManifest"],
        "ExecutionEnrichmentSchema_sha256": H["ExecutionEnrichmentSchema"],
        "SignalDecisionRecord_schema_sha256": SIGNAL_DECISION_RECORD_SCHEMA_SHA,
        "SealedPartitionContentCommitment_runtime_instance": "ValidationPartitionContentCommitment_v1.0.json "
            "(custodian-produced; required, not present in Phase 3A)",
        "ValidationStructuralManifest_runtime_instance": "custodian value-blind structural manifest "
            "(required, not present in Phase 3A)",
        "evaluator_qualification_manifest": "REQUIRED (binds evaluator file+blob+sha256+version+commit+tree"
            "+container+lock+synthetic evidence); the mr002_valoos_* module SHAs are the Phase 3A reference"},
    "boundary": "SPECIFICATION; validation_authorization=false; opens no data; computes no performance"},
    "ValidationRunSpecification_v1.0.json")
H["ValidationAuthorization"] = dump({
    "record_type": "ValidationAuthorization", "version": "1.0",
    "state": "REQUEST / CONTRACT (NOT a grant)", "validation_authorization": False,
    "grants": "NOTHING - this artifact freezes the validation contract for owner adjudication; it does not "
        "release credentials, open data, or compute performance",
    "preconditions_for_a_future_grant": ["owner acceptance of this Phase 3A package",
        "custodian content commitments produced + sealed-store access history = 0 unauthorized",
        "numeric-runtime + structural-manifest specs satisfied", "separate explicit owner authorization event"],
    "governing_preregistration_sha256": PREREG_SHA,
    "run_specification_ref": "ValidationRunSpecification_v1.0.json",
    "run_specification_sha256": H["ValidationRunSpecification"]},
    "ValidationAuthorization_v1.0.json")

# ---- human-readable deliverables (.md) ----
H["ShortAvailabilityLimitationsStatement"] = dump_md(
    "# MR-002 Phase 3A — Short Availability & Locate Limitations Statement\n\n"
    "**Scope:** discloses the limits of the short-side realism model. Phase 3A drafting only; opens no data.\n\n"
    "## Governing distinction\n\n"
    "- The **preregistered net model** (PRIMARY_GATE) includes **borrow financing cost** (50 bps/yr; 300 "
    "bps/yr stress) and **assumes borrow availability**. `net_oos_sharpe >= 0.70` is computed on this series "
    "and is **not** moved to the conservative view.\n"
    "- The **conservative availability/locate/SSR model** (SECONDARY / ECONOMIC_OPERABILITY_GATE) adds "
    "availability, locate-failure, and Reg SHO/SSR realism. It **may block product promotion** but does "
    "**not** replace the frozen primary statistical test.\n"
    "- **Zero-borrow-cost frictionless attribution** is `DIAGNOSTIC_ONLY` "
    "(`FRICTIONLESS_SHORT_RESEARCH_DIAGNOSTIC / NOT AN IMPLEMENTABLE PERFORMANCE ESTIMATE`).\n\n"
    "## Unobservable facts (not manufactured)\n\n"
    "PIT borrow **availability / locate** is generally not reconstructable at this data tier. It is labeled "
    "`UNOBSERVABLE_LIMITATION` and handled by a **conservative proxy** (shortable only above a preregistered "
    "liquidity/size floor at close t; otherwise `REFUSED_SHORT_UNAVAILABLE`), never by synthetic locate data. "
    "Reg SHO/SSR is applied where reconstructable from PIT price and otherwise disclosed as a limitation.\n\n"
    "## Governed answers (frozen before validation)\n\n"
    "- Short cannot be located -> **refused** (fail-closed), never synthetically located or silently resized.\n"
    "- A refused short **never** creates a naked long or ghost position; the paired long gross is reduced "
    "under a preregistered reconstruction rule to preserve dollar-neutrality.\n"
    "- Buy-to-cover failure -> fail-closed `INTEGRITY_STOP`; pending exits are executed at next-open t+1, "
    "never dropped.\n\n"
    "The exact conservative-view floor and reconstruction rule are frozen in "
    "`ShortBorrowLocateModelSpecification_v1.0.json` before validation opens.\n",
    "ShortAvailabilityLimitationsStatement_v1.0.md")

submission_md = (
    "# MR-002 SPQ-1 Phase 3A — Validation Authorization Submission\n\n"
    "**Type:** specifications / manifests / schemas / diff-proofs only. **Opens no validation or OOS data; "
    "computes no performance; releases no credentials; grants no authorization "
    "(`validation_authorization = false`).**\n\n"
    f"**Governing preregistration:** `MR002_ValidationOOS_Preregistration_v1.0.4`, commit `{PREREG_COMMIT}`, "
    f"content SHA-256 `{PREREG_SHA}`.\n\n"
    "## Work packages delivered\n\n"
    "- **3A-1 Governing-source extraction** — `GoverningSourceRegistry` + `PregistrationDiffProof`: every "
    "roadmap-bound value reproduces from v1.0.4 (windows, folds, seams, primary gate net Sharpe >= 0.70, "
    "cost/exposure model, stationary Politis-Romano bootstrap L5+L10/10000/seed20260711, DSR N=5). "
    "Moving-block/L21/2000/seed42 confirmed absent.\n"
    "- **3A-2 Degrees-of-freedom attestation** — every change from prereg v1.0.3 through Phase 2B closure + "
    "the v1.0.4 bootstrap correction classified INTEGRITY/EVIDENCE/GOVERNANCE_ONLY; "
    "`SIGNAL_OR_TRIAL_AFFECTING = 0`; DSR N remains 5.\n"
    "- **3A-3 Sealed-partition control** — control spec + content-commitment + access-history + "
    "seal-verification (`OpenedObjectLedger` per-run AND `SealedStoreAccessLog` program-history; "
    "access-before-authorization = 0; metadata only, no partition values).\n"
    "- **3A-4 Short implementation contract** — PRIMARY (preregistered net-with-borrow-cost) vs SECONDARY "
    "(conservative availability/locate/SSR) vs DIAGNOSTIC (frictionless); rules classified OBSERVED/"
    "RECONSTRUCTED/CONSERVATIVE_PROXY/UNOBSERVABLE; no manufactured locate data; primary gate unchanged.\n"
    "- **3A-5 Enrichment contract** — immutable SignalDecisionRecord -> ExecutionEnrichedCandidateRecord "
    "schema, fail-closed edge-case spec, and a SEPARATE `EXECUTION_ENRICHMENT_*` code namespace.\n"
    "- **3A-6 Metrics + OOS-consumption** — `MetricRoleRegistry` (primary/secondary/diagnostic/integrity, "
    "each with a bound `sample_stage`), `ValidationStageDecisionSpecification` (validation advancement rule "
    "SEPARATE from OOS gates; OOS-only metrics prohibited during validation; verdicts VALIDATION_ADVANCE_"
    "REQUEST / DO_NOT_ADVANCE / INCONCLUSIVE / INTEGRITY_FAILURE), metric spec, OOS-consumption protocol "
    "(stages O1-O5), null-model spec (binds the 5-trial ledger + dispersion rule; the dispersion artifact "
    "is produced at validation run time, not Phase 3A).\n"
    "- **3A-7 Runtime + structural-preflight** — numeric-runtime identity manifest (versions, BLAS/LAPACK, "
    "thread vars, seeds, lockfile/container required at run time), structural-manifest spec (custodian, "
    "value-blind), and a preflight that operates only from precommitted metadata (`STRUCTURAL_PREFLIGHT`, "
    "never `PERFORMANCE_OBSERVATION`; direct sealed-row reads = 0).\n"
    "- **3A-8 Consolidated authorization** — `ValidationAuthorization` (REQUEST/CONTRACT, not a grant) + "
    "`ValidationRunSpecification` + `ValidationInputIdentityManifest` + `ValidationCostExecutionSpecification` "
    "+ this submission, all hash-bound in the publication manifest.\n\n"
    "## Phase 3A HOLD corrections applied\n\n"
    "1. `ValidationStageDecisionSpecification` added; `sample_stage` on every metric; OOS primary gates "
    "(net_oos_sharpe/bootstrap/DSR) prohibited during validation.\n"
    "2. Run spec now binds `ExecutionEnrichmentSchema` (5b2480c1...) AND the governing SignalDecisionRecord "
    "schema (49c0e550...), fail-closed on either mismatch; runtime-critical artifacts bound directly.\n"
    "3. Seal artifacts marked `artifact_kind=SPECIFICATION_TEMPLATE`, `contains_runtime_evidence=false`, "
    "`runtime_instance_required_before_authorization=true`; zero-access values are REQUIRED RUNTIME GATE "
    "VALUES (reserved runtime-evidence names for the validation/OOS instances).\n"
    "4. Count reconciliation: **package_file_count = 26, manifest_bound_artifact_count = 25, "
    "publication_manifest_self_excluded = true**; the manifest is bound externally by its Git blob/commit/"
    "tree (in the correction commit).\n\n"
    "## Boundary\n\n"
    "Validation/OOS SEALED AND UNREAD. No returns, PnL, Sharpe, DSR, ranking, or verdict. Stops for review "
    "before any validation access.\n")
H["ValidationAuthorizationSubmission"] = dump_md(submission_md, "ValidationAuthorizationSubmission_v1.0.md")

# publication manifest binds every governed artifact by SHA-256 (it excludes ITSELF)
pub = {"record_type": "MR002_Phase3A_PublicationManifest", "version": "1.0",
    "package": "SPQ-1 Phase 3A Validation Authorization Package (specifications only)",
    "governing_preregistration": {"file": PREREG, "commit": PREREG_COMMIT, "content_sha256": PREREG_SHA},
    "artifact_sha256": H,
    "manifest_bound_artifact_count": len(H),
    "package_file_count": len(H) + 1,
    "publication_manifest_self_excluded": True,
    "publication_manifest_binding": "the publication manifest does NOT hash itself; it is bound externally "
        "by its Git blob SHA + the correction commit SHA + tree SHA recorded in the commit that lands it "
        "(reported in the submission and the commit message)",
    "seal_zero_access_note": "the seal artifacts are SPECIFICATION_TEMPLATEs; their zero-access values are "
        "REQUIRED RUNTIME GATE VALUES to be evidenced by custodian runtime instances before authorization, "
        "NOT values evidenced by this package",
    "diff_proof_all_reproduce": all_reproduce,
    "dof_gate_signal_or_trial_affecting_zero": len(signal_affecting) == 0,
    "dsr_N": PREREG_JSON["dsr"]["trials_N"],
    "boundary": "DRAFTING ONLY. validation_authorization=false; validation/OOS SEALED AND UNREAD; no "
        "returns/performance computed; no credentials released; stop for review."}
H["PublicationManifest"] = dump(pub, "MR002_Phase3A_PublicationManifest_v1.0.json")

print("=== Phase 3A package generated ===")
print("artifacts:", len(H))
print("diff_proof_all_reproduce:", all_reproduce)
print("dof SIGNAL_OR_TRIAL_AFFECTING count:", len(signal_affecting), "| DSR N:", PREREG_JSON["dsr"]["trials_N"])
print("prereg v1.0.4 sha:", PREREG_SHA[:16], "== bound:", sha_file(os.path.join(RVW, PREREG)) == PREREG_SHA)
for k, v in sorted(H.items()):
    print(f"  {k}: {v[:16]}")
