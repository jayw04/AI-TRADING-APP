"""Populate FREEZE-MANIFEST-003 UNSEALED draft from FREEZE-002 + QUALIFIED archives."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # repo root


def sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def main() -> None:
    src = json.loads(
        (
            ROOT
            / "docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_002_SEALED.json"
        ).read_text(encoding="utf-8")
    )
    body = copy.deepcopy(src["manifest_body"])

    campaign_sha = sha("docs/design/ADR0043_Phase0_D_BOX_Campaign_Scope_v1.2.md")
    adapter_sha = sha(
        "apps/backend/app/risk/loss_control/phase0_o34_archive_adapter.py"
    )
    validator_sha = sha("apps/backend/scripts/adr0043_dbox_freeze_manifest.py")
    validator_test_sha = sha(
        "apps/backend/tests/scripts/test_adr0043_dbox_freeze_manifest.py"
    )
    adapter_test_sha = sha(
        "apps/backend/tests/risk/test_phase0_o34_archive_adapter.py"
    )
    schema_sha = sha(
        "docs/design/schemas/ADR0043_Phase0_D_BOX_Freeze_Manifest.schema.json"
    )
    qual_report_sha = sha(
        "docs/design/evidence/dbox_o34_acq_001/qualification/QUAL_001_report.json"
    )
    qual_doc_sha = sha(
        "docs/design/ADR0043_Phase0_D_BOX_O34_ACQ_Qualification_Report_v1.0.md"
    )

    o3_path = (
        "docs/design/evidence/dbox_o34_acq_001/constructed/"
        "20260730T022316Z/O3_CANDIDATE.json"
    )
    o4a_path = (
        "docs/design/evidence/dbox_o34_acq_001/constructed/"
        "20260730T022316Z/O4A_CANDIDATE.json"
    )
    o4b_path = (
        "docs/design/evidence/dbox_o34_acq_001/constructed/"
        "20260730T022316Z/O4B_CANDIDATE.json"
    )
    o3_sha = "53b3310c8db3cdfd3d60a2de3bec990a6eaab8864dd592afc4590e57fc9008b0"
    o4a_sha = "3ba73e61f5e8955a184d820c0aba4ed387de453c30fc6a22d168d84074403c49"
    o4b_sha = "e349f49465aa2689e6c24e20d6ae32286f0a447bfbcdf3b2fbbc531c656bae95"
    assert sha(o3_path) == o3_sha
    assert sha(o4a_path) == o4a_sha
    assert sha(o4b_path) == o4b_sha

    # Not a PLACEHOLDER_RE token; content-bound until published tip replaces it.
    content_tip = "content_bound_pre_publish_tip_v1_2_o34"

    body["governing_refs"].update(
        {
            "campaign_scope_id": "ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.2",
            "campaign_scope_sha256": campaign_sha,
            "campaign_scope_path": (
                "docs/design/ADR0043_Phase0_D_BOX_Campaign_Scope_v1.2.md"
            ),
            "prior_campaign_scope_id": "ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.1",
            "prior_campaign_scope_sha256": (
                "60e23e980d98ab277eff0a86598ff4abf666954d3006aca32d5249d789b6a4ab"
            ),
            "superseded_freeze_manifest": (
                "ADR0043-PH0-D-BOX-FREEZE-MANIFEST-002"
            ),
            "prior_freeze_manifest_body_sha256": (
                "d35de863e85153f8f1a4768b62b7d89a2043525433ec8841631cb8a7c20a2d1f"
            ),
            "option2a_evidence_merge_commit": (
                "5cb711c5be35d53c3d42277adbd0dc379dead44c"
            ),
            "o34_qualification_merge_commit": (
                "646d81abfdd98ce4ca99dde7821a26e869a50824"
            ),
            "o34_construction_merge_commit": (
                "5def3824937b85e859345f6691f2cb37b432105f"
            ),
            "o34_qual_report_path": (
                "docs/design/evidence/dbox_o34_acq_001/qualification/"
                "QUAL_001_report.json"
            ),
            "o34_qual_report_sha256": qual_report_sha,
            "o34_qual_doc_path": (
                "docs/design/ADR0043_Phase0_D_BOX_O34_ACQ_Qualification_Report_v1.0.md"
            ),
            "o34_qual_doc_sha256": qual_doc_sha,
            "construction_freeze_body_sha256": (
                "80dfd8ec6d90182cdeabaab2d1457720ca417bcd5cb1511b4dd9d77989951bb0"
            ),
            "sqlite_snapshot_sha256": (
                "26bae1f5b754c4ff80e031126674d1818ae4a9a90e4faa6b36820f2690278d5b"
            ),
            "capture_id": "20260730T022316Z",
        }
    )

    body["campaign"] = {
        "campaign_id": "ADR0043-PH0-D-BOX-CAMPAIGN-RUN-003",
        "runbook_version": "ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.2",
        "campaign_label": (
            "O3/O4-A/O4-B EXECUTION CAMPAIGN — O5 DEFERRED — NO D-WIRE ELIGIBILITY"
        ),
        "option": "SUCCESSOR_O34_AFTER_2A",
        "account_policy": "account_3_only",
        "packages_executable": ["O3", "O4-A", "O4-B"],
        "packages_inherited_approve": ["CORR-06", "O1", "O2"],
        "packages_deferred": ["O5"],
        "inherited_approve_binding": {
            "source_campaign": (
                "ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.1 Option 2A"
            ),
            "evidence_merge_commit": (
                "5cb711c5be35d53c3d42277adbd0dc379dead44c"
            ),
            "freeze_manifest_002_body_sha256": (
                "d35de863e85153f8f1a4768b62b7d89a2043525433ec8841631cb8a7c20a2d1f"
            ),
            "reopen_policy": (
                "FORBIDDEN unless separate owner ruling explicitly orders "
                "rerun/reopen/re-adjudication"
            ),
        },
        "phase0_modes_allowed": [
            "DISABLED",
            "OBSERVE_ONLY_ISOLATED_HARNESS",
        ],
        "phase0_modes_forbidden": [
            "OBSERVE_ONLY_DEPLOYED_PRODUCTION",
            "PREFLIGHT_REFUSE",
            "CANARY_AUTHORIZED",
        ],
        "d_wire_eligibility": (
            "BLOCKED — O5 deferred with anchors []; all-PASS on O3/O4-A/O4-B "
            "does not grant D-WIRE"
        ),
        "execution_order": ["O3", "O4-A", "O4-B"],
    }

    body["schema_binding"]["sha256"] = schema_sha
    body["schema_binding"]["commit"] = (
        "646d81abfdd98ce4ca99dde7821a26e869a50824"
    )
    body["schema_binding"]["note"] = (
        "Schema file hash rebound at FREEZE-003 populate; "
        "additionalProperties policy unchanged from FREEZE-002 era"
    )

    body["code_and_tools"]["freeze_manifest_validator"].update(
        {
            "commit": content_tip,
            "sha256": validator_sha,
            "tests_sha256": validator_test_sha,
            "local_pytest_result": (
                "adapter + readiness probe pending local pytest at populate"
            ),
            "tooling_merge_commit": (
                "646d81abfdd98ce4ca99dde7821a26e869a50824"
            ),
            "pr": "none_yet_pre_publish",
        }
    )
    body["code_and_tools"]["harness_input_contract"] = {
        "plan_id_mapping": "ord:<orders.id>",
        "accepted": True,
        "binding_note": (
            "QUALIFIED archives use plan_id=ord:<orders.id> because no "
            "execution_plan table exists in bound sqlite snapshot; accepted "
            "harness input contract before start decision"
        ),
        "adapter": {
            "path": (
                "apps/backend/app/risk/loss_control/phase0_o34_archive_adapter.py"
            ),
            "sha256": adapter_sha,
            "tests_path": (
                "apps/backend/tests/risk/test_phase0_o34_archive_adapter.py"
            ),
            "tests_sha256": adapter_test_sha,
            "commit": content_tip,
        },
        "readiness_fail_closed": (
            "If harness cannot consume mapping deterministically, "
            "FREEZE-003 readiness FAILS"
        ),
        "o4_runners": (
            "phase0_o4_replay DecisionTimeEvidence / ForensicEvidence via "
            "adapter row mappers"
        ),
        "runtime": "isolated_harness_only",
    }
    body["code_and_tools"]["implementation_commit"] = (
        "d1c2fbf0a394c66728f6cc489577ae180ccdfb03"
    )
    body["code_and_tools"]["harness_commit"] = content_tip
    body["code_and_tools"]["deployment_commit"] = content_tip
    body["code_and_tools"]["harness_commit_note"] = (
        "Isolated harness only; adapter + campaign v1.2 content-bound "
        "pre-publish. Production b0058bf reference-only FORBIDDEN to modify."
    )

    body["repository_state"] = {
        "git_commit_full": content_tip,
        "implementation_baseline": (
            "d1c2fbf0a394c66728f6cc489577ae180ccdfb03"
        ),
        "working_tree": (
            "DIRTY_PRE_PUBLISH — campaign v1.2 + adapter + validator "
            "readiness + FREEZE-003 uncommitted at populate"
        ),
        "clean_tree_proof": (
            "not_clean_pre_publish — seal requires published clean tip"
        ),
        "worktree_path_local": "C:/LLM-RAG-APP/ai-trading-app-adr0043-ph0",
        "branch": "main",
        "submodules": "none",
        "qualification_tip_on_main": (
            "646d81abfdd98ce4ca99dde7821a26e869a50824"
        ),
    }

    body["datasets"] = {
        "entries": [
            {
                "sealed_archive_id": "O3-CAND-20260730T022316Z",
                "storage": "local_sealed",
                "path": o3_path,
                "size_bytes": 164706,
                "sha256": o3_sha,
                "role": "O3",
                "qualification_status": "QUALIFIED",
                "n_observations": 292,
                "post_unseal_substitution": "FORBIDDEN",
            },
            {
                "sealed_archive_id": "O4A-CAND-20260730T022316Z",
                "storage": "local_sealed",
                "path": o4a_path,
                "size_bytes": 190328,
                "sha256": o4a_sha,
                "role": "O4-A",
                "qualification_status": "QUALIFIED",
                "n_observations": 287,
                "post_unseal_substitution": "FORBIDDEN",
            },
            {
                "sealed_archive_id": "O4B-CAND-20260730T022316Z",
                "storage": "local_sealed",
                "path": o4b_path,
                "size_bytes": 260426,
                "sha256": o4b_sha,
                "role": "O4-B",
                "qualification_status": "QUALIFIED",
                "n_observations": 286,
                "post_unseal_substitution": "FORBIDDEN",
            },
        ],
        "post_unseal_substitution": "FORBIDDEN",
        "o3_status": "QUALIFIED",
        "o3_predetermined_disposition": "EXECUTABLE_AFTER_START",
        "qualification_id": "ADR0043-PH0-D-BOX-O34-ACQ-QUAL-001",
        "qualification_merge": "646d81abfdd98ce4ca99dde7821a26e869a50824",
        "gate_ready_at_qualification": False,
    }

    body["o5_live_fill_anchors"]["anchors"] = []
    body["o5_live_fill_anchors"]["predetermined_disposition"] = "INCONCLUSIVE"
    body["o5_live_fill_anchors"]["disposition_note"] = (
        "O5 deferred under CAMPAIGN-001 v1.2; anchors []; generating new "
        "live fills forbidden"
    )

    gp = body["gate_packages"]
    gp["campaign_mode"] = "SUCCESSOR_O34_V1_2"
    gp["executable_gates"] = ["O3", "O4-A", "O4-B"]
    gp["deferred_gates"] = ["O5"]
    gp["inherited_approve_gates"] = ["CORR-06", "O1", "O2"]
    gp["d_wire_eligibility"] = (
        "FAIL_CLOSED — even all-PASS on O3/O4 leaves D-WIRE BLOCKED while "
        "O5 deferred with anchors []"
    )

    for g in ("CORR-06", "O1", "O2"):
        c = gp["pass_criteria"][g]
        c["execution_status"] = "INHERITED_APPROVE"
        c["predetermined_disposition"] = (
            "APPROVE — inherited from Option 2A; not rerun under v1.2"
        )
        c["inherited_from"] = {
            "evidence_merge": "5cb711c5be35d53c3d42277adbd0dc379dead44c",
            "freeze_002_body_sha256": (
                "d35de863e85153f8f1a4768b62b7d89a2043525433ec8841631cb8a7c20a2d1f"
            ),
        }
        c["reopen_policy"] = "FORBIDDEN unless separate owner ruling"
        c["pass_possible_under_v1_2_by_rerun"] = False
        c["load_bearing_for_d_wire"] = True

    o3 = gp["pass_criteria"]["O3"]
    o3.update(
        {
            "execution_status": "EXECUTABLE_AFTER_START",
            "predetermined_disposition": "none — adjudicate after run",
            "deferred_reason": "none",
            "pass_possible_under_v1_1": False,
            "pass_possible_under_v1_2": True,
            "load_bearing_for_d_wire": True,
            "required_inputs": [
                "datasets.entries[O3]",
                "harness_input_contract.plan_id_mapping=ord:<orders.id>",
                "phase0_o34_archive_adapter",
                "quote_provenance_rules",
            ],
            "protocol_ids": [
                "O3-historical-replay-v1",
                "phase0_o34_archive_adapter.iter_o3_replay_bundles",
            ],
            "required_checks": [
                "archive_sha256_match",
                "ord_plan_id_parse",
                "replay_plan_quote_authority_loss_checkpoint_recovery",
                "false_reachable_scoring_recorded",
                "model_coverage_recorded",
            ],
        }
    )

    o4a = gp["pass_criteria"]["O4-A"]
    o4a.update(
        {
            "observation_set_id": "O4A-CAND-20260730T022316Z",
            "observation_set_binding": (
                "QUALIFIED local_sealed archive O4A-CAND-20260730T022316Z"
            ),
            "execution_status": "EXECUTABLE_AFTER_START",
            "predetermined_disposition": "none — adjudicate after run",
            "discovery_verdict": "QUALIFIED",
            "deferred_reason": "none",
            "pass_possible_under_v1_1": False,
            "pass_possible_under_v1_2": True,
            "load_bearing_for_d_wire": True,
            "required_inputs": [
                "datasets.entries[O4-A]",
                "harness_input_contract.plan_id_mapping=ord:<orders.id>",
                "phase0_o34_archive_adapter.o4a_row_to_decision_time",
                "decision_time_evidence_bundle",
            ],
            "no_mix_rule": (
                "DecisionTimeEvidence must not contain fill/terminal fields; "
                "refuse mix with O4-B archive payloads"
            ),
        }
    )

    o4b = gp["pass_criteria"]["O4-B"]
    o4b.update(
        {
            "observation_set_id": "O4B-CAND-20260730T022316Z",
            "observation_set_binding": (
                "QUALIFIED local_sealed archive O4B-CAND-20260730T022316Z"
            ),
            "execution_status": "EXECUTABLE_AFTER_START",
            "predetermined_disposition": "none — adjudicate after run",
            "discovery_verdict": "QUALIFIED",
            "deferred_reason": "none",
            "pass_possible_under_v1_1": False,
            "pass_possible_under_v1_2": True,
            "load_bearing_for_d_wire": True,
            "required_inputs": [
                "datasets.entries[O4-B]",
                "harness_input_contract.plan_id_mapping=ord:<orders.id>",
                "phase0_o34_archive_adapter.o4b_row_to_forensic",
                "forensic_terminal_evidence_bundle",
            ],
            "no_mix_rule": (
                "ForensicEvidence is a separate bundle; O4-A and O4-B must "
                "not share mixed evidence payloads"
            ),
        }
    )

    o5 = gp["pass_criteria"]["O5"]
    o5.update(
        {
            "execution_status": "DEFERRED",
            "predetermined_disposition": "INCONCLUSIVE",
            "deferred_reason": (
                "Tier-A anchors absent (anchors []); generating new live "
                "fills forbidden under HOLD"
            ),
            "load_bearing_for_d_wire": True,
            "pass_possible_under_v1_2": False,
        }
    )

    body["hold"] = {
        "broker_order_submission": "HOLD",
        "production_imports": "NOT_AUTHORIZED",
        "deployed_path_observe_only": "NOT_AUTHORIZED",
        "canary": "HOLD",
        "enforce": "NOT_AUTHORIZED",
        "cap_changes": "NOT_AUTHORIZED",
        "july24_limits_digest_changes": "NOT_AUTHORIZED",
        "d_wire": "DEFERRED_AND_BLOCKED",
        "campaign_start": "REQUIRES_SEPARATE_OWNER_DECISION_AFTER_SEAL",
        "production_stack_b0058bf_modification": "FORBIDDEN",
        "inherited_approve_reopen": "FORBIDDEN unless separate owner ruling",
        "o5_new_live_fill_generation": "FORBIDDEN",
    }

    body["amendment_record"] = {
        "from_campaign": "ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.1",
        "to_campaign": "ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.2",
        "from_freeze": "ADR0043-PH0-D-BOX-FREEZE-MANIFEST-002",
        "to_freeze": "ADR0043-PH0-D-BOX-FREEZE-MANIFEST-003",
        "prior_freeze_body_sha256": (
            "d35de863e85153f8f1a4768b62b7d89a2043525433ec8841631cb8a7c20a2d1f"
        ),
        "option2a_in_place_reopen": "FORBIDDEN",
        "inherited_approve": ["CORR-06", "O1", "O2"],
        "executable": ["O3", "O4-A", "O4-B"],
        "deferred": ["O5"],
        "qualification": "ADR0043-PH0-D-BOX-O34-ACQ-QUAL-001 QUALIFIED",
    }

    body["wp5_replacement_policy"]["prior_manifest_body_sha256"] = (
        "d35de863e85153f8f1a4768b62b7d89a2043525433ec8841631cb8a7c20a2d1f"
    )
    body["wp5_replacement_policy"]["replacement_manifest_document_id"] = (
        "ADR0043-PH0-D-BOX-FREEZE-MANIFEST-003"
    )
    body["wp5_replacement_policy"]["replacement_used"] = True
    body["wp5_replacement_policy"]["replacement_note"] = (
        "Successor freeze for CAMPAIGN v1.2; FREEZE-002 not mutated in place"
    )

    doc = {
        "schema_version": 1,
        "document_id": "ADR0043-PH0-D-BOX-FREEZE-MANIFEST-003",
        "manifest_body": body,
        "seal": {
            "algorithm": "sha256",
            "canonicalization": "RFC8785-JCS",
            "encoding": "UTF-8-no-BOM",
            "final_newline": "excluded",
            "body_sha256": None,
            "sealed_at_utc": None,
            "manifest_status": "UNSEALED_DRAFT",
            "operator": None,
            "operator_acknowledgment_kind": "none",
            "owner_countersignature": None,
            "owner_acknowledgment_kind": "none",
            "verifier_script": {
                "path": "apps/backend/scripts/adr0043_dbox_freeze_manifest.py",
                "commit": content_tip,
                "sha256": validator_sha,
            },
            "post_seal_state": (
                "UNSEALED — populate complete; readiness then seal"
            ),
            "campaign_start": (
                "HOLD — requires separate owner start decision after seal"
            ),
        },
    }

    out = (
        ROOT
        / "docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_003_UNSEALED_DRAFT.json"
    )
    out.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out}")
    print(f"campaign_sha={campaign_sha}")
    print(f"adapter_sha={adapter_sha}")
    print(f"validator_sha={validator_sha}")


if __name__ == "__main__":
    main()
