"""SPQ-1 Phase 3B — formal replacement-opening request + owner grant record (2026-08-17).

Formalizes the draft REQUEST bound to the v3.6 execution identity, and records the owner GRANT
given 2026-08-17 with its conditions verbatim in substance. Named by CLASSIFICATION and BOUND
IDENTITY, never by ordinal (owner instruction); the historical count of spent openings is recorded
separately. Nothing here releases anything: the latch release is a separate evented act.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
V36_ID = "c4852231019531f58d3f213c782d11dfc375e5b974ea9568e271144f6212b85a"


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _write(record: dict, name: str) -> str:
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    with open(os.path.join(_HERE, name), "wb") as fh:
        fh.write(_canonical(record))
    print(f"wrote {name}")
    print(f"identity {record['record_identity_sha256']}")
    return record["record_identity_sha256"]


request = {
    "record_type": "MR002_Phase3B_ReplacementOpeningRequest",
    "version": "v36-1.0",
    "artifact_kind": "OPENING_REQUEST",
    "produced_at": "2026-08-17T00:00:00Z",
    "classification": "REPLACEMENT_FOR_PRE_RESEARCH_EXECUTION_REFUSAL",
    "bound_to": {
        "execution_identity": V36_ID,
        "git_source_checkpoint": "961c38aba578112bac48884ec31f12cbf357075a",
        "ceremony_evidence_checkpoint": "f7fad57283eb56446a4c084dad047f06c203d4ba",
        "archive_sha256": "024db8fa9df03bebc4d9e441bb37ad8a4212e3d2bb64999e545fe30fc389c074",
        "staged_config_sha256": "1959dcd3fa1208ec5c7b5deec4c2a32a00dd0b19face8f3ca17a936c02a6aea9",
        "runtime_identity": "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51",
        "staging_record": "MR002_Phase3B_StagingRecord_v3.6 (a1e198e7...)",
        "ceremony_record": "MR002_Phase3B_DryPreflightCeremony_v3.6 (fc4a65bd...)",
        "provenance_correction": "MR002_Phase3B_V35ProvenanceCorrection_v1.0 (047131fe...)",
    },
    "purpose": (
        "Obtain the first interpretable MR-002 validation result under the frozen Config A/B/C "
        "specification, with Config B as the primary profitability verdict configuration, solely "
        "to determine whether MR-002 merits OOS progression toward paper trading. This opening "
        "does not authorize additional exploratory tuning, new configurations, or unrelated "
        "research."
    ),
    "opening_history_recorded_separately": {
        "historical_count_of_spent_openings": 4,
        "research_verdict_before_this_request": "NONE",
        "ordinal_naming_deliberately_avoided": "named by classification and bound identity (owner instruction 2026-08-17)",
    },
    "grants": "NOTHING. A request grants nothing.",
}

grant = {
    "record_type": "MR002_Phase3B_ReplacementOpeningAuthorization",
    "version": "3.0",
    "artifact_kind": "OWNER_GRANT",
    "produced_at": "2026-08-17T00:00:00Z",
    "authorized_by": "owner GRANT 2026-08-17, verbatim in substance",
    "grant": {
        "classification": "REPLACEMENT_FOR_PRE_RESEARCH_EXECUTION_REFUSAL",
        "disposition": "GRANTED, subject to Tier 3 CI green before release",
        "bound_execution_identity": V36_ID,
        "git_source_checkpoint": "961c38aba578112bac48884ec31f12cbf357075a",
        "ceremony_evidence_checkpoint": "f7fad57283eb56446a4c084dad047f06c203d4ba",
        "primary_economic_verdict_configuration": "Config B = 2.00",
        "authorization_count": 1,
    },
    "conditions": {
        "ci": (
            "Tier 3 CI green for the pushed batch before release. Feature-branch pushes do not "
            "trigger the workflow by design, so the certification is a manual workflow_dispatch "
            "FULL run on the branch at f7fad57 (Actions run 32078434247). If red for a relevant "
            "MR-002 correctness failure: do not open; diagnose only that blocking failure."
        ),
        "pre_release_reconfirmation": [
            "staged config sha 1959dcd3...",
            "archive sha 024db8fa...",
            "code identity c4852231... (four-way)",
            "runtime identity 194efbdf...",
            "config mapping {A: 1.75, B: 2.00, C: 2.25}",
            "containment/latch in the expected pre-release state (host->reader explicitDeny, host->sealed explicitDeny)",
        ],
        "release_scope": "ONE replacement opening for this identity only",
        "execution_discipline": "no tuning, no retries, no alternate configurations, no manual data inspection, no mid-run intervention",
        "run_stop_conditions": {
            "refusal_before_interpretable_result": "preserve evidence, restore containment; another replacement opening is NOT automatically authorized",
            "valid_abc_outputs": "the execution/governance phase is OVER; no new engineering cycle for incidental imperfections",
        },
        "post_result_decision_tree": {
            "config_b_passes_frozen_validation_gates": "adjudicate the result -> proceed to the already-governed OOS step",
            "config_b_fails": "inspect the economic result only enough to determine whether a specifically justified strategy improvement exists; otherwise STOP MR-002",
        },
        "not_authorized": "no new infrastructure, classifier expansion, general governance cleanup, additional data exploration, or unrelated MR-002 research",
    },
    "grants": "ONE replacement validation execution bound to the identity above, under the conditions above.",
}

rid = _write(request, "MR002_Phase3B_ReplacementOpeningRequest_v36_v1.0.json")
grant["request_record_identity"] = rid
_write(grant, "MR002_Phase3B_ReplacementOpeningAuthorization_v3.0.json")
