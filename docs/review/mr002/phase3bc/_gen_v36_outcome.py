"""SPQ-1 Phase 3B — v3.6 replacement-opening outcome (2026-08-18): PASS, evidence ADMISSIBLE.

The corrected relaunch (owner-ruled clean dependency projection, 2nd authorized release of the
SAME unconsumed opening) ran end to end: S11_PUBLISHED, exit 0, qualification PASS, zero
materiality-gate breaches. This is the FIRST admissible validation evidence in MR-002 history.
The v3.5 semantic adjudication closed the exact gate that killed opening 4: KNOWN_UNADJUDICATED
went from 68 units / 30 symbols to 0 / 0. No performance statistic was read; the Config B
economic adjudication is the owner's next step under the grant's decision tree.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


record = {
    "record_type": "MR002_Phase3B_ReplacementOpeningOutcome",
    "version": "v36-1.0",
    "artifact_kind": "OPENING_OUTCOME_CLASSIFICATION",
    "produced_at": "2026-08-18T00:00:00Z",
    "executed_under": (
        "owner GRANT 2026-08-17 (ReplacementOpeningAuthorization v3.0, 7d037e75..., request "
        "899baf20...), CI-green condition substituted by owner ruling '1' (equivalence "
        "certification). The strict bundle-inventory STOP was honored without release; the owner "
        "then ruled the bundle delta NOT accepted and directed a clean projection. This was the "
        "SECOND authorized latch release of the same unconsumed opening; owner ruled it does not "
        "increment the historical opening count."
    ),
    "classification": {
        "outcome": "A",
        "definition": "COMPLETED + QUALIFICATION PASS + EVIDENCE ADMISSIBLE",
        "evidence_admissible": True,
        "opening_consumed_with": "PASS",
        "research_verdict": "NONE YET - deliberately not derived here",
        "first_admissible_evidence": (
            "the FIRST admissible validation evidence in MR-002 history. Openings 1-3 refused "
            "pre-research and produced no deliverable set; opening 4 completed but breached the "
            "KNOWN_UNADJUDICATED materiality gate on the unique-symbol limb (68 units across 30 "
            "securities), so its population was inadmissible."
        ),
        "what_closed_the_run4_breach": (
            "LabelAdjudication v2.0 (`relation`, `spinoff`) + Corrigendum v1.0 (spinoffdividend "
            "OUT of the gap term), carried into v3.6 c4852231... This run: "
            "KNOWN_UNADJUDICATED = 0 units, 0 symbols, breached=false."
        ),
    },
    "launch_correction": {
        "prior_refusal_root_cause": (
            "LAUNCH_HARNESS_DEPENDENCY_OMISSION (ExecutionRefusalEvent v36-1.0, 8ea1a8b3...) - "
            "the bound dependency-bundle mount was omitted"
        ),
        "dependency_supply": (
            "clean projection /opt/mr002/deps_v11_clean built path-by-path from the frozen "
            "DependencyBundle v1.1 map: 2,919 files, inventory 7c50b2ab... REPRODUCED, zero "
            "extras, source /opt/mr002/deps untouched at 4,015 files"
        ),
        "mounts": (
            "projection mounted read-only at in-container /opt/mr002/deps; "
            "PYTHONPATH=/work/apps/backend:/opt/mr002/deps (bundle top-level names disjoint from "
            "the image, so ordering is shadow-free)"
        ),
        "import_preflight": (
            "PASS from the projection under --network=none BEFORE release: boto3 1.43.70, "
            "botocore 1.43.70, pyarrow 20.0.0 - the prior failure class closed"
        ),
    },
    "identities": {
        "code_identity": "c4852231019531f58d3f213c782d11dfc375e5b974ea9568e271144f6212b85a",
        "governing_identity": "2a1fb7755a57b97f9831cf257c6e60c8bd5baf77eab39541b75ae88c27cb5b43",
        "runtime_identity": "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51",
        "staged_config_sha256": "1959dcd3...",
        "archive_sha256": "024db8fa...",
        "config_mapping": {"A": 1.75, "B": 2.00, "C": 2.25},
        "git_source_checkpoint": "961c38aba578112bac48884ec31f12cbf357075a",
        "ceremony_evidence_checkpoint": "f7fad57283eb56446a4c084dad047f06c203d4ba",
    },
    "execution": {
        "ssm_command_id": "c0764596-6359-48e5-96c3-983fa8755322",
        "started_utc": "2026-08-17T23:36:03Z",
        "ended_utc": "2026-08-18T00:23:29Z",
        "wall_clock": "approximately 47 minutes",
        "state": "S11_PUBLISHED",
        "state_history": [
            "S0_INIT", "S1_CODE_IDENTITY_VERIFIED", "S2_CONTRACT_IDENTITY_VERIFIED",
            "S3_CONFIG_BOUND", "S4_RUNTIME_VERIFIED", "S5_INPUTS_STAGED",
            "S6_OUTPUTS_PREPARED", "S7_PRE_ACCESS_READY", "S8_READER_ASSUMED",
            "S9_OPENING_CONSUMED", "S10_ENRICHED",
        ],
        "disposition": "PASS",
        "exit_code": 0,
        "error": None,
        "opening_consumed": True,
        "partial_run": False,
        "published_at_utc": "2026-08-18T00:23:27Z",
        "output_root": "/opt/mr002/v36/out_exec2",
        "run_id": "MR002-SPQ1-P3B-VALIDATION-V1",
    },
    "consumed_objects": {
        "reader_kind": "S3",
        "sealed_reads": 8,
        "oos_reads": 0,
        "ledger_chain_verifies": True,
        "pinned_version_ids": {},
    },
    "cloudtrail_affirmative": {
        "window_utc": "2026-08-17T23:30:00Z - 2026-08-18T00:30:00Z",
        "reader_assumptions": 1,
        "the_one_event": {
            "event_time": "2026-08-17T23:36:05Z",
            "seconds_after_launch": 2,
            "role_arn": "arn:aws:iam::219024422756:role/mr002-validation-reader",
            "role_session_name": "mr002-p3b-validation-v1",
            "principal": (
                "arn:aws:sts::219024422756:assumed-role/mr002-phase3c-run-host/"
                "i-00c1034f7026db45e (inScopeOf the host instance)"
            ),
            "source_ip": "54.162.175.64",
            "user_agent_corroboration": (
                "Boto3/1.43.70 Botocore/1.43.70 Python 3.13 - exactly the bound bundle versions "
                "proven in the import preflight"
            ),
            "event_id": "9b21704a-a620-4ed5-8057-83732140b5c8",
            "request_id": "43846750-6d15-48d3-a48c-9165cfb602b6",
        },
        "everything_else_in_window": (
            "routine EC2 instance-role refreshes (run host at 00:15:42Z, paper box, WS5 canary) "
            "and an AWS service role - ZERO further events name mr002-validation-reader and "
            "nothing touches the sealed or OOS partitions"
        ),
        "raw_capture": (
            "retained in session scratchpad only (the raw events embed STS session tokens and are "
            "deliberately NOT committed)"
        ),
    },
    "containment": {
        "latch_restored_before_collection": True,
        "restored_canonical_sha256": "44f5549a97042d2829a3027e764105b0ab272774ec3bb343d224bfba999fab48",
        "byte_identical_to_pre_release_capture": True,
        "reverified_at_collection_2026_08_18": (
            "read-only re-check from the workstation: live policy canonical sha == 44f5549a..., "
            "8 statements, simulate host->reader = explicitDeny"
        ),
        "oos": "NEVER OPENED - 0 reads, remains sealed",
        "host": "STOPPED after collection; termination-protected; multi-MB evidence on EBS root",
    },
    "gates_none_breached": {
        "any_materiality_gate_breached": False,
        "KNOWN_UNADJUDICATED": {
            "breached": False, "units": 0, "unique_symbols": 0,
            "note": "the run-4 breach driver, closed by the semantic adjudication",
        },
        "UNKNOWN_VOCABULARY": {
            "breached": False, "units": 0, "unregistered_kinds_observed": [],
            "observed_vocabulary_all_registered": [
                "acquisitionby", "acquisitionof", "delisted", "dividend",
                "relation", "spinoff", "spinoffdividend", "split",
            ],
        },
        "IDENTITY_UNRESOLVED": {
            "breached": False, "units": 1785, "unique_symbols": 2,
            "fraction": 0.007071771548103894, "max_fraction": 0.02, "max_unique_symbols": 10,
        },
        "ACTION_COMPOSITION_UNRESOLVED": {
            "breached": False, "units": 3, "unique_symbols": 2,
            "fraction": 1.188533033294772e-05, "max_fraction": 0.01, "max_unique_symbols": 5,
        },
    },
    "population_accounting": {
        "units_enumerated": 331600,
        "units_producer_refused": 79188,
        "units_bridge_refused": 1788,
        "units_accepted": 250624,
        "identity": "331600 == 79188 + 1788 + 250624",
        "reconciliation_balances": True,
    },
    "enrichment_census": {
        "records_examined": 250624,
        "successful_enrichment": 250216,
        "delisting": 22,
        "no_official_open": 386,
        "trading_halt": 0,
        "halt_note": (
            "the 0 under trading_halt is ZERO BY CONSTRUCTION per the open "
            "HALT-EVIDENCE-INPUT-GAP; it is NOT an observation that no halts occurred"
        ),
        "corporate_action_transition": 0,
        "identity_conflict": 0,
        "price_conflict": 0,
        "missing_source": 0,
        "future_information": 0,
        "one_terminal_code_per_record": True,
    },
    "integrity_census": {
        "all_gates_zero": True,
        "future_information_violations": 0,
        "decision_record_mutations": 0,
        "duplicate_enrichment_identities": 0,
        "missing_decision_enrichment_bindings": 0,
        "unreconciled_validation_units": 0,
        "unregistered_data_source_reads": 0,
        "oos_reads": 0,
    },
    "seam": {
        "adjudications_examined": 250624,
        "admitted": 247694,
        "not_admitted_gap_filter": 2522,
        "not_adjudicated": 408,
        "economically_adjudicated": 250216,
        "orphans_and_state_violations": 0,
    },
    "evidence": {
        "host_path": "/opt/mr002/v36/out_exec2",
        "published_here": (
            "docs/review/mr002/phase3bc/v36_published/ - six small governed files fetched via "
            "SSM 2026-08-18 with the latch closed, each byte-verified against the publication "
            "record's bound sha256"
        ),
        "retained_on_host_and_bound_by_hash": {
            "ValidationDecisionExecutionBindingReport_v1.0.json": "9e46c89a... 17,543,812 B",
            "ValidationExecutionEnrichmentManifest_v1.0.json": "808c7903... 121,990,793 B",
            "ValidationUnitReconciliation_v1.0.json": "396a843d... 77,408,737 B",
        },
        "multi_mb_reverified_at_collection": (
            "all three re-hashed on host at collection (SSM 36934786-4fc0-47f0-b060-3cee105db9ab) "
            "- byte-identical to the publication record"
        ),
        "stdout_log": (
            "177 B, 6ff57ea9..., verbatim terminal JSON: run_id MR002-SPQ1-P3B-VALIDATION-V1, "
            "mode execute, disposition PASS, exit_code 0, state S11_PUBLISHED, "
            "opening_consumed true, error null"
        ),
    },
    "state_after": {
        "admissible_validation_evidence": (
            "the v3.6 deliverable set - 7 deliverables, hashes bound in "
            "MR002_ValOOS_validation_Publication.json"
        ),
        "openings_spent_historical": 4,
        "openings_note": (
            "owner ruled the replacement grant does not increment the historical count; the "
            "replacement opening is CONSUMED with PASS"
        ),
        "research_verdict": "NONE YET",
        "next": (
            "owner-governed Config B economic adjudication under the grant's decision tree: "
            "passes the frozen validation gates -> adjudicate -> the already-governed OOS step; "
            "fails -> a specifically justified improvement or STOP MR-002. NOTHING is proposed "
            "here and no further opening is requested."
        ),
    },
    "grants": "NOTHING. Outcome evidence only.",
    "what_was_deliberately_not_read": (
        "no performance statistic was extracted, inspected or reported during execution, "
        "collection or this classification. Classification precedes interpretation; the economic "
        "verdict is the owner's next adjudication and reading a result outside that adjudication "
        "would contaminate it."
    ),
}

# The eight pinned version IDs, verbatim from ValidationOpenedObjectLedger_v1.0.json
record["consumed_objects"]["pinned_version_ids"] = {
    "reference/crosswalk.parquet": "ux3JpvSp7lSneFcMHhxRZ_Tp6_gx60eK",
    "reference/sic_mapping.parquet": "_wAa1EJ0wECpUcd4DH7KhrYsYl765kWL",
    "validation/actions.parquet": "wJ6QFkebGAidGzoWO.qzUMYjy.b6zLrx",
    "validation/anchors.parquet": "7Br5aFGWFabpIJmPgwUBQRgdhQwc2GIK",
    "validation/etf_prices.parquet": ".mZyHPHgamUNlHpdePGQZq.djUapjrpo",
    "validation/prices.parquet": "eC8XZGBPXa6vPDW_WKPvwV8HtF05_tty",
    "validation/sic_observations.parquet": "OkvwAKSX8W8W3HJiBoxZ9KC4ON6Vgj5t",
    "validation/universe.parquet": "8Le8rLdT2wvdSenjEQdPaUAgdmSzx3ZO",
}
record["consumed_objects"]["version_id_note"] = (
    "identical to opening 4's pinned set - the sealed store is byte-identical across openings"
)

body = _canonical(record)
record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
with open(os.path.join(_HERE, "MR002_Phase3B_ReplacementOpeningOutcome_v36_v1.0.json"), "wb") as fh:
    fh.write(_canonical(record))
print("identity", record["record_identity_sha256"])
