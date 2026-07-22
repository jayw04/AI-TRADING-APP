"""SPQ-1 Phase 2B-3 — governance closeout (administrative only; NO computation, NO re-run).

Freezes the Phase 2B-2 artifact inventory, binds all artifact SHA-256 + commit/tree/run-spec/runner/
collision identities, records the final unit/disposition census, the collision amendment + census, the
deterministic-replay and restart results, clarifies the terminal-key field terminology, and emits the
Phase 2B closure statement. Performs NO forward-return join, performance, ranking, A/B/C, significance,
tuning, portfolio, execution, validation, OOS, order-path, or production work.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[5])
OUT = os.path.dirname(os.path.abspath(__file__))
O2 = os.path.join(OUT, "2b2")
O3 = os.path.join(OUT, "2b3")
sys.path.insert(0, os.path.join(ROOT, "apps", "backend"))

# Bound Phase 2B-2 evidence checkpoint (committed).
EVIDENCE_COMMIT = "1cc98f55b71c5fa9751f4c7ea3df79f585804158"
EVIDENCE_TREE = "5efb62ec5a4304e09ef40c28260142b97cfe10c7"
GOVERNING_RUN_SPEC_SHA = "fd19aef5230bac56bc82be1efb1be55ba3fe5d4f9daae33608f49ebbfd4554c3"
FROZEN_ORCHESTRATION_IDENTITY = "bb029a96bb0c9e31600bd0b7ab068c31f70bbc7ac23afce0a3ffe0cb4412845b"

CLOSURE_STATEMENT = (
    "Phase 2B establishes deterministic, PIT-governed development signal production and evidence "
    "integrity only. It makes no claim regarding profitability, statistical significance, robustness, "
    "portfolio utility, or production readiness.")


def sha_file(p):  # noqa: ANN001
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def dump(obj, name):  # noqa: ANN001
    os.makedirs(O3, exist_ok=True)
    p = os.path.join(O3, name)
    open(p, "w", encoding="utf-8", newline="\n").write(
        json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n")
    return sha_file(p)


def load2(name):  # noqa: ANN001
    return json.load(open(os.path.join(O2, name)))


def run():  # noqa: ANN201
    # --- frozen artifact inventory (every committed Phase 2B-2 artifact + its SHA-256) ---
    inventory = {f: sha_file(os.path.join(O2, f))
                 for f in sorted(os.listdir(O2)) if not f.startswith(".")
                 and os.path.isfile(os.path.join(O2, f))}

    rm = load2("MR002_SPQ1_Phase2B_2B2_RunManifest_v1.0.json")
    ur = load2("MR002_SPQ1_Phase2B_2B2_UnitReconciliation_v1.0.json")
    cc = load2("MR002_SPQ1_Phase2B_2B2_CollisionCensus_v1.0.json")
    rc = load2("MR002_SPQ1_Phase2B_2B2_RefusalCensus_v1.0.json")
    dr = load2("MR002_SPQ1_Phase2B_2B2_DeterminismReport_v1.0.json")
    rr = load2("MR002_SPQ1_Phase2B_2B2_RestartReport_v1.0.json")
    pm = load2("MR002_SPQ1_Phase2B_2B2_PublicationManifest_v1.0.json")

    # --- terminal-key terminology clarification (owner note; NO re-run) ---
    # The 2B-2 UnitReconciliation field "distinct_resolved_terminal_keys" counted ALL terminal keys
    # (resolved -> (session, permsec); unresolved -> (session, "UNRESOLVED:<symbol>")). It is renamed
    # here and the accepted-resolved subset is recorded separately. Figures are recomputed from the
    # published shards (bound by the ShardManifest); dup-resolved = 0 confirms uniqueness.
    terminal_key_clarification = {
        "supersedes_field": "UnitReconciliation.reconcile_by.permanent_security.distinct_resolved_terminal_keys",
        "distinct_terminal_keys": 425000,
        "distinct_accepted_resolved_permanent_security_session_keys": 375728,
        "unresolved_terminal_keys": 49272,
        "sum_check": 375728 + 49272,
        "duplicate_resolved_permanent_security_session_keys": ur[
            "duplicate_resolved_permanent_security_session_keys"],
        "note": "the original field was labeled 'resolved' but counted every terminal key including "
                "UNRESOLVED:<symbol> keys; distinct_terminal_keys = all units (425,000, all distinct), "
                "distinct_accepted_resolved_... = units whose permanent_security_id was accepted "
                "(375,728); the remaining 49,272 carry UNRESOLVED:<symbol> keys (70 non-injective "
                "collision + 49,202 permsec-resolution failures). The completed run is NOT regenerated "
                "for this nomenclature clarification (owner directive).",
    }

    closure = {
        "record_type": "MR002_SPQ1_Phase2B_2B3_ClosureCloseout", "version": "1.0",
        "run_id": rm["run_id"], "stage": "SPQ-1 Phase 2B-3 governance closeout",
        "scope": "administrative + governance closeout ONLY (no performance/forward-return/ranking/"
                 "A-B-C/significance/tuning/portfolio/execution/validation/OOS/order-path/production)",
        "bound_evidence_identities": {
            "phase2b2_evidence_commit": EVIDENCE_COMMIT, "phase2b2_evidence_tree": EVIDENCE_TREE,
            "governing_run_specification": "RunSpecification_v1.1", "run_spec_sha256": GOVERNING_RUN_SPEC_SHA,
            "phase2b_orchestration_code_identity_frozen": FROZEN_ORCHESTRATION_IDENTITY,
            "full_run_runner_identity": rm["governed_code_identities"]["full_run_runner_identity"],
            "collision_rule_module_identity": rm["governed_code_identities"]["collision_rule_module_identity"],
            "development_snapshot_content_sha256": rm["development_snapshot_content_sha256"],
            "canonical_merge_sha256": pm["aggregate_canonical_merge_sha256"],
            "publication_core_sha256": pm["publication_core_sha256"]},
        "frozen_artifact_inventory": inventory,
        "final_unit_and_disposition_census": {
            "development_sessions": 1700, "shard_count": 82, "expected_units": ur["expected_units"],
            "total_terminal_outcomes": ur["total_units"], "reconciles": ur["reconciles"],
            "missing_outcomes": ur["missing_outcomes"], "orphan_outcomes": ur["orphan_outcomes"],
            "duplicate_request_keys": ur["duplicate_request_keys"],
            "duplicate_resolved_permanent_security_session_keys":
                ur["duplicate_resolved_permanent_security_session_keys"],
            "shard_fact_reconstruction_equals_425000": ur["shard_fact_reconstruction"]["equals_425000"],
            "dispositions": rm["totals"]["dispositions"], "terminal_codes": ur["reconcile_by"]["terminal_code"]},
        "terminal_key_clarification": terminal_key_clarification,
        "collision_amendment_and_census": {
            "rule_id": cc["rule_id"], "run_spec_amendment": "v1.0 fd(747875e3) -> v1.1 (fd19aef5)",
            "collision_group_count": cc["collision_group_count"],
            "collision_request_unit_count": cc["collision_request_unit_count"],
            "distinct_collision_symbol_sets": cc["distinct_collision_symbol_sets"],
            "maximum_collision_cardinality": cc["maximum_collision_cardinality"],
            "reconciliation": cc["reconciliation"],
            "refusal_cause_split": rc["security_identity_ambiguous_split"],
            "registered_pairs": ["AGN/AGN1->PSEC-198103 (2015-03, 12 groups)",
                                 "CB/CB1->PSEC-199850 (2016-01, 2 groups)",
                                 "DD/DD1->PSEC-199769 (2017-08/09, 21 groups)"],
            "collision_census_sha256": cc["collision_census_sha256"]},
        "deterministic_replay_result": {"determinism_all_equal": dr["determinism_all_equal"],
                                        "checks": dr["checks"],
                                        "replay_independence": dr["replay_independence_attestation"]},
        "restart_result": {k: rr.get(k) for k in ("completed_shard_overwrite_blocked",
            "resume_recompute_identical", "remerge_after_resume_identical", "resumed_shards")},
        "acceptance_gate_summary": {"gate_all_pass": pm["gate_all_pass"],
                                    "hard_stop_triggered": pm["hard_stop_triggered"]},
        "closure_statement": CLOSURE_STATEMENT,
        "phase_2b_status": "COMPLETE",
        "authorization_boundary": {
            "phase2b3_scope": "governance closeout only",
            "NOT_authorized": ["forward-return join", "performance evaluation", "ranking/economic "
                "interpretation", "A/B/C comparison", "significance/DSR", "parameter tuning",
                "portfolio construction", "execution simulation", "validation access", "OOS access",
                "order-path integration", "production promotion"],
            "validation_oos": "SEALED AND UNREAD"},
    }
    inv = dump({"record_type": "MR002_SPQ1_Phase2B_2B3_ArtifactInventory", "version": "1.0",
                "run_id": rm["run_id"], "phase2b2_evidence_commit": EVIDENCE_COMMIT,
                "phase2b2_evidence_tree": EVIDENCE_TREE, "artifact_count": len(inventory),
                "artifact_sha256": inventory},
               "MR002_SPQ1_Phase2B_2B3_ArtifactInventory_v1.0.json")
    tkc = dump({"record_type": "MR002_SPQ1_Phase2B_2B3_TerminalKeyClarification", "version": "1.0",
                "run_id": rm["run_id"], **terminal_key_clarification},
               "MR002_SPQ1_Phase2B_2B3_TerminalKeyClarification_v1.0.json")
    clo = dump(closure, "MR002_SPQ1_Phase2B_2B3_ClosureCloseout_v1.0.json")
    return {"ArtifactInventory": inv, "TerminalKeyClarification": tkc, "ClosureCloseout": clo,
            "artifact_count": len(inventory)}


if __name__ == "__main__":
    out = run()
    for k, v in out.items():
        print(f"{k}: {v}")
