#!/usr/bin/env python3
"""Seal ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001 (construction freeze).

Does not inspect candidate observation rows. Does not submit broker orders.
Uses the same RFC8785-JCS + SHA-256(manifest_body) procedure as the campaign
freeze tooling.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "backend" / "scripts"))
from adr0043_dbox_freeze_manifest import body_sha256  # noqa: E402


def file_sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def walk_check(obj: object, path: str = "$") -> list[str]:
    errs: list[str] = []
    if obj is None:
        errs.append(f"null at {path}")
    elif isinstance(obj, str):
        banned = (
            "REQUIRED_FILL",
            "TBD",
            "TODO",
            "FIXME",
            "FILL_ME",
            "CHANGEME",
            "LOCAL_UNPUBLISHED",
        )
        for p in banned:
            if p in obj:
                errs.append(f"placeholder {p} at {path}")
                break
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            errs.extend(walk_check(v, f"{path}[{i}]"))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            errs.extend(walk_check(v, f"{path}.{k}"))
    return errs


def main() -> int:
    schemas = {
        "O3": {
            "schema_id": "ADR0043-PH0-D-BOX-O34-O3-ARCHIVE-SCHEMA-001",
            "path": "docs/design/schemas/ADR0043_Phase0_O34_O3_Archive.schema.json",
            "sha256": file_sha(
                "docs/design/schemas/ADR0043_Phase0_O34_O3_Archive.schema.json"
            ),
        },
        "O4A": {
            "schema_id": "ADR0043-PH0-D-BOX-O34-O4A-ARCHIVE-SCHEMA-001",
            "path": "docs/design/schemas/ADR0043_Phase0_O34_O4A_Archive.schema.json",
            "sha256": file_sha(
                "docs/design/schemas/ADR0043_Phase0_O34_O4A_Archive.schema.json"
            ),
        },
        "O4B": {
            "schema_id": "ADR0043-PH0-D-BOX-O34-O4B-ARCHIVE-SCHEMA-001",
            "path": "docs/design/schemas/ADR0043_Phase0_O34_O4B_Archive.schema.json",
            "sha256": file_sha(
                "docs/design/schemas/ADR0043_Phase0_O34_O4B_Archive.schema.json"
            ),
        },
    }

    sealed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest_body: dict = {
        "document_purpose": (
            "O34 construction freeze — precommits eligibility and construction "
            "rules before any record selection"
        ),
        "governing_refs": {
            "authorization_id": "ADR0043-PH0-D-BOX-O34-ACQ-AUTH-001",
            "authorization_status": "APPROVED_EFFECTIVE_AMENDED",
            "authorization_effective_utc": "2026-07-30T00:21:33Z",
            "authorization_merge_commit": (
                "9a264e5c7e1aa376b65cab6cb514b7185acd5ea0"
            ),
            "authorization_content_commit": (
                "1db1a80ebac5d91d59a2b70b087a1783ec039b7f"
            ),
            "authorization_path": (
                "docs/design/ADR0043_Phase0_D_BOX_O34_Acquisition_Authorization_v1.0.md"
            ),
            "authorization_path_sha256": file_sha(
                "docs/design/ADR0043_Phase0_D_BOX_O34_Acquisition_Authorization_v1.0.md"
            ),
            "option2a_closeout_id": "ADR0043-PH0-D-BOX-OPTION2A-CLOSE-001",
            "option2a_evidence_merge": (
                "5cb711c5be35d53c3d42277adbd0dc379dead44c"
            ),
            "design_package_id": "ADR0043-PH0-D-BOX-O34-EVIDENCE-ACQ-001 v1.0",
            "design_package_path": (
                "docs/design/ADR0043_Phase0_D_BOX_O34_Evidence_Acquisition_v1.0.md"
            ),
            "design_package_sha256": file_sha(
                "docs/design/ADR0043_Phase0_D_BOX_O34_Evidence_Acquisition_v1.0.md"
            ),
            "campaign_freeze_reference": "ADR0043-PH0-D-BOX-FREEZE-MANIFEST-002",
            "campaign_freeze_body_sha256": (
                "d35de863e85153f8f1a4768b62b7d89a2043525433ec8841631cb8a7c20a2d1f"
            ),
            "offline_baseline_commit": (
                "d1c2fbf0a394c66728f6cc489577ae180ccdfb03"
            ),
            "offline_baseline_tag": "adr0043-phase0-offline-complete",
            "controlling_design_id": "ADR0043-PH0-CTRL-001 v1.1",
            "integration_design_id": "ADR0043-PH0-INTEGRATION-DESIGN-001 v1.0",
        },
        "account_3_identity": {
            "workbench_account_id": 3,
            "broker_account_id": "PA34USW0Q8UO",
            "broker_environment": "paper",
            "limits_digest_id": "july24_frozen_limits_row_id_3_audit_153",
            "limits_digest_sha256": (
                "da6659334909a68a2e800d429ff36e7c7de1d18f169082836c07de2973ef706f"
            ),
            "july24_digest_mutation": "FORBIDDEN",
        },
        "hold_and_blocks": {
            "broker_order_submission": "HOLD",
            "new_live_fills_observations_sessions": "NOT_AUTHORIZED",
            "gate_execution_or_reopening": "NOT_AUTHORIZED",
            "d_wire": "BLOCKED",
            "production_imports": "NOT_AUTHORIZED",
            "deployed_path_observation": "NOT_AUTHORIZED",
            "canary_enforce_caps_july24_changes": "NOT_AUTHORIZED",
            "production_stack_commit_excluded": (
                "b0058bf335628f8dbde09a93915314f3a1f7743b"
            ),
            "production_modification": "FORBIDDEN",
        },
        "sequence_gate": {
            "required_order": [
                "FILL",
                "READINESS_VALIDATION",
                "SEAL",
                "COUNTERSIGN",
                "SEPARATE_CONSTRUCTION_START_DECISION",
                "RECORD_SELECTION",
            ],
            "current_step_at_seal": "SEAL",
            "record_selection_authorized_by_this_document": False,
            "exploratory_selection_before_seal": "FORBIDDEN",
            "source_inventory_inspection_for_selection_before_seal": "FORBIDDEN",
        },
        "time_standard": {
            "timezone": "UTC",
            "format": "RFC3339",
            "precision": "second",
        },
        "eligibility_window": {
            "start_inclusive_utc": "2026-06-30T00:00:00Z",
            "end_exclusive_utc": "2026-07-30T00:21:33Z",
            "bounds_policy": "start_inclusive_end_exclusive",
            "start_basis": (
                "ADR0032_AWS_paper_cutover_era_bound_from_governing_ops_docs_"
                "not_outcome_inspection"
            ),
            "end_basis": (
                "O34-ACQ-AUTH-001 effective timestamp — exclude "
                "post-authorization observations"
            ),
        },
        "source_inventories": {
            "policy": (
                "Pin read-only locations and snapshot-binding protocol without "
                "selecting observation rows. Live mutable stores require "
                "construction-start capture of exact file/object SHA-256 before "
                "selection. Capture is not selection."
            ),
            "entries": [
                {
                    "source_id": "SRC-MKT-QUOTE-LAWFUL-001",
                    "source_class": "historical_market_and_quote_data",
                    "read_only_location": (
                        "Lawful local/S3 market and quote stores already "
                        "available under prior Workbench authority; concrete "
                        "object Version IDs bound at construction-start capture"
                    ),
                    "snapshot_binding_status": (
                        "PROTOCOL_BOUND_CAPTURE_AT_CONSTRUCTION_START"
                    ),
                    "snapshot_sha256": (
                        "NOT_YET_CAPTURED_CONSTRUCTION_START_REQUIRED"
                    ),
                    "mutation_after_bound_snapshot": "STOP_INCONCLUSIVE",
                },
                {
                    "source_id": "SRC-APP-AUDIT-PLAN-CKPT-TERM-001",
                    "source_class": (
                        "application_audit_plan_checkpoint_terminal_records"
                    ),
                    "read_only_location": (
                        "Account-3 scoped tables/records in workbench "
                        "persistence (audit_log, plans/ExecutionPlan artifacts, "
                        "checkpoints, terminal packages) as present on "
                        "authorized read-only host path "
                        "/opt/workbench/data/workbench.sqlite — READ ONLY; "
                        "production stack b0058bf reference-only and must not "
                        "be modified"
                    ),
                    "snapshot_binding_status": (
                        "PROTOCOL_BOUND_CAPTURE_AT_CONSTRUCTION_START"
                    ),
                    "snapshot_sha256": (
                        "NOT_YET_CAPTURED_CONSTRUCTION_START_REQUIRED"
                    ),
                    "snapshot_capture_method": (
                        "SHA-256 of sqlite file bytes (or governed export dump) "
                        "recorded in construction-start decision before any "
                        "SELECT/filter/join"
                    ),
                    "mutation_after_bound_snapshot": "STOP_INCONCLUSIVE",
                },
                {
                    "source_id": "SRC-ACCT3-PAPER-PRIOR-AUTH-001",
                    "source_class": "account_3_paper_records_prior_authority",
                    "read_only_location": (
                        "Account workbench_account_id=3 / broker PA34USW0Q8UO "
                        "paper records created under prior authority within "
                        "eligibility_window; same sqlite host path as "
                        "SRC-APP-AUDIT-PLAN-CKPT-TERM-001"
                    ),
                    "snapshot_binding_status": (
                        "PROTOCOL_BOUND_CAPTURE_AT_CONSTRUCTION_START"
                    ),
                    "snapshot_sha256": (
                        "NOT_YET_CAPTURED_CONSTRUCTION_START_REQUIRED"
                    ),
                    "mutation_after_bound_snapshot": "STOP_INCONCLUSIVE",
                },
                {
                    "source_id": "SRC-GOV-GIT-IMMUTABLE-001",
                    "source_class": "governing_git_and_design_pins",
                    "read_only_location": (
                        "Repository commits and design artifacts listed in "
                        "governing_refs"
                    ),
                    "snapshot_binding_status": "BOUND",
                    "snapshot_sha256": (
                        "BOUND_VIA_GOVERNING_REFS_COMMITS_AND_FILE_SHA256"
                    ),
                    "note": (
                        "Immutable governance pins only; not empirical "
                        "observation rows"
                    ),
                },
            ],
        },
        "inclusion_rules": [
            {
                "rule_id": "INC-001",
                "description": (
                    "Include account-3 (workbench_account_id=3, broker "
                    "PA34USW0Q8UO) ExecutionPlan episodes with "
                    "plan_created_at_utc in eligibility_window"
                ),
            },
            {
                "rule_id": "INC-002",
                "description": (
                    "Include only records whose source_lineage resolves to a "
                    "source_id in source_inventories.entries with successful "
                    "snapshot binding at construction-start"
                ),
            },
            {
                "rule_id": "INC-003",
                "description": (
                    "O4-A rows may include only fields available at or before "
                    "FIRST_BROKER_SUBMISSION_BOUNDARY for that episode"
                ),
            },
            {
                "rule_id": "INC-004",
                "description": (
                    "O4-B rows may include only episodes meeting "
                    "O4B-TERM-COMPLETE-001"
                ),
            },
        ],
        "exclusion_rules": [
            {
                "rule_id": "EXC-001",
                "description": (
                    "Exclude WP7 hermetic fixtures and inline KOKU / obs-a / "
                    "obs-b / arc-1 test identities"
                ),
            },
            {
                "rule_id": "EXC-002",
                "description": (
                    "Exclude test_adr0043_dbox_freeze_manifest.py stubs"
                ),
            },
            {
                "rule_id": "EXC-003",
                "description": (
                    "Exclude phase0_o4_replay.py hermetic inline fixtures as "
                    "empirical observations"
                ),
            },
            {
                "rule_id": "EXC-004",
                "description": (
                    "Exclude WP0 seal 20260729T161843Z production ops snapshot "
                    "as O3/O4 empirical corpus"
                ),
            },
            {
                "rule_id": "EXC-005",
                "description": (
                    "Exclude ADR 0048 SEP/ACTIONS corpus and other "
                    "non-ADR0043 Phase-0 programs (silent cross-program import "
                    "prohibited)"
                ),
            },
            {
                "rule_id": "EXC-006",
                "description": (
                    "Exclude adr0043_gate_replay_v1.0 CI PR replay artifacts"
                ),
            },
            {
                "rule_id": "EXC-007",
                "description": (
                    "Exclude acct7/v13 journals and wrong-purpose research "
                    "program evidence"
                ),
            },
            {
                "rule_id": "EXC-008",
                "description": (
                    "Exclude Option 2A hermetic CORR-06/O1/O2 evidence root "
                    "docs/design/evidence/dbox_option2a_run_001/ as O3/O4 "
                    "empirical observations"
                ),
            },
            {
                "rule_id": "EXC-009",
                "description": (
                    "Exclude unit-test fixtures and synthetic examples "
                    "converted to empirical rows"
                ),
            },
            {
                "rule_id": "EXC-010",
                "description": (
                    "Exclude non-account-3 events; exclude post-window records; "
                    "exclude manufactured sample-size fillers"
                ),
            },
            {
                "rule_id": "EXC-011",
                "description": (
                    "Exclude production OrderRouter live path observation on "
                    "deployed commit b0058bf"
                ),
            },
        ],
        "deduplication": {
            "o3_key_fields_ordered": ["workbench_account_id", "plan_id"],
            "o4a_key_fields_ordered": [
                "workbench_account_id",
                "plan_id",
                "evidence_plane",
            ],
            "o4b_key_fields_ordered": [
                "workbench_account_id",
                "plan_id",
                "evidence_plane",
            ],
            "evidence_plane_values": ["DECISION_TIME", "FORENSIC"],
            "collision_policy": "FAIL_CLOSED_STOP_INCONCLUSIVE",
        },
        "unit_of_observation": {
            "definition": (
                "One ExecutionPlan episode (plan_id) for account 3 within "
                "eligibility_window"
            ),
            "o3_mapping": "One O3 observation row per included plan_id after dedup",
            "o4a_mapping": (
                "One O4-A observation row per included plan_id with "
                "reconstructable FIRST_BROKER_SUBMISSION_BOUNDARY cutoff"
            ),
            "o4b_mapping": (
                "One O4-B observation row per included plan_id meeting terminal "
                "completeness; linked to same episode_id as O4-A without "
                "payload merge"
            ),
        },
        "symbol_session_clustering": {
            "cluster_key": ["symbol", "session_calendar_date_utc"],
            "independence_assumption": (
                "Plans in the same symbol-session cluster are positively "
                "dependent; report n_raw and n_eff<=n_raw; do not treat "
                "cluster mates as independent for sample-sufficiency claims"
            ),
            "counting_policy": (
                "Emit both raw observation counts and cluster counts; sample "
                "sufficiency must not invent new observations"
            ),
        },
        "o4a_cutoff_rule": {
            "cutoff_event": "FIRST_BROKER_SUBMISSION_BOUNDARY",
            "reconstruction_method": (
                "For each plan_id, reconstruct cutoff_at_utc as the timestamp "
                "of the first broker submission attempt/order event "
                "attributable to that plan from audit/plan/terminal records in "
                "the bound source snapshot; if no submission occurred, cutoff "
                "is the last pre-submit decision event recorded for the plan; "
                "if neither can be reconstructed → STOP_INCONCLUSIVE for that "
                "episode (and stop campaign construction if required stratum "
                "cannot be filled without invention)"
            ),
            "prohibited_post_cutoff_fields": [
                "fills",
                "terminal_broker_state",
                "post_submit_quotes",
            ],
            "lookahead_policy": "FAIL_CLOSED_REJECT_OR_STOP",
        },
        "o4b_terminal_completeness_rule": {
            "criteria_id": "O4B-TERM-COMPLETE-001",
            "criteria": [
                "Non-empty fills array for the episode",
                (
                    "Terminal loss/accounting inputs present or explicitly "
                    "reason-coded as unavailable with FAIL_CLOSED exclusion"
                ),
                (
                    "Episode linkage to O4-A episode_id without merging "
                    "O4-A/O4-B payloads"
                ),
            ],
            "incomplete_observation_treatment": (
                "EXCLUDE_WITH_REASON_CODE_O4B_INCOMPLETE; if exclusion would "
                "require manufacturing replacements → STOP_INCONCLUSIVE"
            ),
            "code_contract_alignment": (
                "phase0_o4_replay.ForensicEvidence requires fills; "
                "FORENSIC_MISSING_FILLS refuse"
            ),
        },
        "missing_data_treatment": {
            "policy": "FAIL_CLOSED",
            "reason_codes": [
                "MISSING_SOURCE_SNAPSHOT",
                "MISSING_PROVENANCE",
                "MISSING_CUTOFF",
                "MISSING_TERMINAL_COMPLETE",
                "AMBIGUOUS_DEDUP",
                "POST_SNAPSHOT_MUTATION",
                "UNAUTHORIZED_BROKER_CALL",
                "SAMPLE_REQUIRES_NEW_OBSERVATIONS",
                "O4B_INCOMPLETE",
                "CROSS_PROGRAM_EVIDENCE",
                "SYNTHETIC_OR_FIXTURE",
            ],
        },
        "permitted_transformations": [
            {
                "transform_id": "T-001",
                "description": (
                    "Deterministic field projection/normalization to target "
                    "archive schemas"
                ),
                "deterministic": True,
            },
            {
                "transform_id": "T-002",
                "description": (
                    "Deterministic joins on precommitted keys (plan_id, "
                    "episode_id, account_id)"
                ),
                "deterministic": True,
            },
            {
                "transform_id": "T-003",
                "description": (
                    "Deterministic classification into O3 / O4-A / O4-B rows "
                    "per freeze rules"
                ),
                "deterministic": True,
            },
            {
                "transform_id": "T-004",
                "description": (
                    "Deterministic archive packaging (canonical JSON bytes) "
                    "and SHA-256 computation"
                ),
                "deterministic": True,
            },
            {
                "transform_id": "T-005",
                "description": "Deterministic reason-code tagging for exclusions",
                "deterministic": True,
            },
        ],
        "prohibited_substitutions": [
            "Manufacturing observations to satisfy sample size",
            (
                "Converting unit-test fixtures or synthetic examples into "
                "empirical observations"
            ),
            "Silent import of another research program evidence",
            "Changing historical records",
            "Generating new orders, fills, attempts, or sessions",
            (
                "Outcome-conditioned rewrite of eligibility or sampling rules "
                "after inspection"
            ),
            "Mixing O4-A and O4-B payloads into one archive",
        ],
        "expected_count_reconciliation": {
            "policy": (
                "Formulas precommitted; numeric counts filled only after "
                "selection under construction-start and must reconcile or STOP"
            ),
            "formulas": {
                "n_source_after_filters": (
                    "COUNT distinct source_row_key after INC/EXC and "
                    "eligibility_window on bound snapshots"
                ),
                "n_deduplicated_observations": (
                    "COUNT after applying deduplication keys with FAIL_CLOSED "
                    "on collision"
                ),
                "n_o3_emitted": (
                    "COUNT O3 rows emitted; must equal "
                    "n_deduplicated_observations for O3 mapping"
                ),
                "n_o4a_emitted": (
                    "COUNT O4-A rows with reconstructable cutoff; excluded "
                    "MISSING_CUTOFF reason-coded"
                ),
                "n_o4b_emitted": (
                    "COUNT O4-B rows meeting O4B-TERM-COMPLETE-001; incomplete "
                    "excluded with O4B_INCOMPLETE"
                ),
                "identity": (
                    "n_source_after_filters >= n_deduplicated_observations; "
                    "emitted counts + excluded reason-code counts must equal "
                    "prior stage counts"
                ),
            },
            "pre_selection_numeric_counts": "NOT_APPLICABLE_BEFORE_SELECTION",
        },
        "target_archive_schemas": {
            "O3": schemas["O3"],
            "O4_A": schemas["O4A"],
            "O4_B": schemas["O4B"],
        },
        "storage_paths": {
            "staging_root": "docs/design/evidence/dbox_o34_acq_001/staging/",
            "constructed_root": (
                "docs/design/evidence/dbox_o34_acq_001/constructed/"
            ),
            "qualified_root": "docs/design/evidence/dbox_o34_acq_001/qualified/",
            "rejected_root": "docs/design/evidence/dbox_o34_acq_001/rejected/",
            "s3_policy": (
                "Optional S3 pin only after CONSTRUCTED; must include Version "
                "ID + SHA-256 fail-closed; no unpinned latest"
            ),
            "archive_hashes_at_freeze": (
                "NOT_APPLICABLE_ARCHIVES_NOT_YET_CONSTRUCTED"
            ),
        },
        "archive_outcomes": {
            "CONSTRUCTED": "Candidate archive bytes + hashes under this freeze",
            "QUALIFIED": "Independent qualification report proves bindability",
            "REJECTED_AS_NON_BINDABLE": (
                "Failed qualification or stop condition"
            ),
            "gate_ready_requires": (
                "QUALIFIED plus later campaign amendment — not automatic from "
                "CONSTRUCTED"
            ),
        },
        "qualification_criteria": {
            "independent_role": (
                "Qualifier must be a separate operator/session from the "
                "constructor; constructor may not self-qualify"
            ),
            "required_proofs": [
                "complete_provenance",
                "no_O4A_lookahead",
                "no_O4A_O4B_evidence_mixing",
                "reproducible_source_to_archive_row_lineage",
                "count_reconciliation",
                "hash_and_schema_validation",
                "no_prohibited_synthetic_or_cross_program_substitution",
            ],
            "report_path_pattern": (
                "docs/design/evidence/dbox_o34_acq_001/qualification/QUAL-*.md"
            ),
        },
        "broker_reads": {
            "policy": (
                "None by default. Read-only broker history only if separately "
                "declared here and proven side-effect-free before use."
            ),
            "operations": [],
            "undeclared_broker_calls": (
                "STOP_INCONCLUSIVE_OR_REQUIRE_AMENDMENT"
            ),
        },
        "stop_conditions": [
            "Required source snapshot unavailable",
            "Provenance cannot be proven",
            "Decision-time cutoff cannot be reconstructed",
            "Terminal completeness cannot be established",
            "Deduplication is ambiguous",
            "Source records modified after bound snapshot",
            "Broker calls beyond authorized reads required",
            "Sample sufficiency would require generating new observations",
        ],
        "predetermined_inconclusive_handling": {
            "on_stop_condition": (
                "Close construction INCONCLUSIVE or require superseding freeze "
                "+ owner acknowledgment; do not invent observations"
            ),
            "on_empty_eligible_set": (
                "INCONCLUSIVE — do not manufacture sample"
            ),
            "does_not_lift_hold_or_d_wire": True,
        },
        "rule_change_policy": {
            "after_outcome_inspection": (
                "FORBIDDEN without superseding freeze manifest and owner "
                "acknowledgment"
            ),
            "in_place_mutation_of_sealed_body": "FORBIDDEN",
        },
    }

    errs = walk_check(manifest_body)
    if errs:
        print("READINESS FAIL:")
        for e in errs:
            print(" -", e)
        return 1

    digest = body_sha256(manifest_body)
    print("READINESS PASS")
    print("body_sha256", digest)
    print("sealed_at_utc", sealed_at)

    doc = {
        "schema_version": 1,
        "document_id": "ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001",
        "manifest_body": manifest_body,
        "seal": {
            "algorithm": "sha256",
            "canonicalization": "RFC8785-JCS",
            "encoding": "UTF-8-no-BOM",
            "final_newline": "excluded",
            "body_sha256": digest,
            "sealed_at_utc": sealed_at,
            "manifest_status": "SEALED",
            "operator": "cursor-agent",
            "operator_acknowledgment_kind": "construction_freeze_seal_operator",
            "owner_countersignature": (
                "Owner acknowledgment (Jay Wang) — typed governance "
                "acknowledgment"
            ),
            "owner_acknowledgment_kind": "construction_freeze_countersignature",
            "post_seal_state": (
                "SEALED — construction-start and record selection NOT YET "
                "AUTHORIZED"
            ),
            "authorization_ruling_ref": "ADR0043-PH0-D-BOX-O34-ACQ-AUTH-001",
            "verifier_note": (
                "SHA-256 over RFC8785-JCS of manifest_body only; same "
                "canonicalization as ADR0043 D-BOX campaign freeze tooling"
            ),
        },
    }

    out = ROOT / "docs/design/ADR0043_Phase0_D_BOX_O34_ACQ_Freeze_Manifest_001_SEALED.json"
    out.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert body_sha256(loaded["manifest_body"]) == digest
    assert loaded["seal"]["body_sha256"] == digest
    print("WROTE", out.as_posix())
    print("VERIFY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
