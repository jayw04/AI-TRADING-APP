"""Tests for ADR-0043 D-BOX freeze-manifest readiness / JCS body-hash tooling.

Hermetic only — no OrderRouter, broker, or live path imports.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "adr0043_dbox_freeze_manifest.py"
)


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "adr0043_dbox_freeze_manifest", SCRIPT
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_mod()


def _minimal_ready_body() -> dict:
    gate = {
        "required_inputs": ["x"],
        "protocol_ids": ["p1"],
        "required_checks": ["c1"],
        "maximum_failures": 0,
        "failure_thresholds": {},
        "inconclusive_conditions": [],
        "required_artifacts": ["a.json"],
        "evaluator_version": "test@1",
        "adjudicator_role": "owner",
        "reruns_allowed": False,
        "failed_attempt_preservation": "retain",
    }
    o4a = {
        **gate,
        "observation_set_id": "obs-a",
        "replay_boundary": "pre-submit only",
    }
    o4b = {
        **gate,
        "observation_set_id": "obs-b",
        "replay_boundary": "terminal fills",
    }
    o5 = {
        **gate,
        "clopper_pearson_confidence": "0.95_one_sided",
        "clopper_pearson_acceptance_bound": "0.05",
    }
    return {
        "governing_refs": {"x": "y"},
        "campaign": {"campaign_id": "c"},
        "code_and_tools": {
            "freeze_manifest_validator": {
                "path": "apps/backend/scripts/adr0043_dbox_freeze_manifest.py",
                "commit": "a" * 40,
                "sha256": "b" * 64,
            }
        },
        "repository_state": {"git_commit_full": "c" * 40},
        "runtime_identity": {"os_image": "test"},
        "account_3_identity": {"workbench_account_id": 3},
        "limits_and_loss_control": {
            "limits_digest_id": "july24",
            "limits_digest_sha256": "d" * 64,
        },
        "datasets": {
            "entries": [
                {
                    "name": "corpus",
                    "storage": "local_sealed",
                    "path": "/tmp/x",
                    "size_bytes": 1,
                    "sha256": "e" * 64,
                    "sealed_archive_id": "arc-1",
                }
            ]
        },
        "o5_live_fill_anchors": {
            "anchors": [],
            "inadequate_anchors_disposition": "O5_INCONCLUSIVE",
        },
        "evidence_tier_assignments": {"tier_A": ["a"]},
        "sample_and_stratum_definitions": {
            "independence_and_clustering_assumptions": "unit=plan"
        },
        "permitted_broker_reads": {"operations": []},
        "permitted_writes": {
            "operations": [
                {
                    "op_id": "checkpoint_account3",
                    "kind": "account_3_checkpoint",
                    "targets": [
                        {
                            "object_type": "logical",
                            "name": "tuple",
                            "allowed_fields_or_path_patterns": ["plan_hash"],
                            "prohibited_neighbor_fields": ["password"],
                        }
                    ],
                }
            ]
        },
        "broker_read_side_effect_proof": {"method": "none"},
        "gate_packages": {
            "pass_criteria": {
                "CORR-06": gate,
                "O1": gate,
                "O2": gate,
                "O3": gate,
                "O4-A": o4a,
                "O4-B": o4b,
                "O5": o5,
            }
        },
        "hold": {"broker_order_submission": "HOLD"},
        "time_standard": {"format": "RFC3339"},
        "schema_binding": {
            "path": "docs/design/schemas/ADR0043_Phase0_D_BOX_Freeze_Manifest.schema.json",
            "commit": "f" * 40,
            "sha256": "1" * 64,
        },
        "wp5_replacement_policy": {"in_place_mutation_of_sealed_manifest": "FORBIDDEN"},
    }


def test_jcs_key_order_stable(mod):
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert mod.canonical_manifest_body_bytes(a) == mod.canonical_manifest_body_bytes(b)
    assert mod.body_sha256(a) == mod.body_sha256(b)


def test_jcs_rejects_float(mod):
    with pytest.raises(ValueError, match="floats"):
        mod.canonical_manifest_body_bytes({"x": 0.05})


def test_seal_excludes_envelope_from_hash(mod):
    body = {"k": "v"}
    h1 = mod.body_sha256(body)
    doc = {
        "manifest_body": body,
        "seal": {
            "body_sha256": h1,
            "sealed_at_utc": "2026-07-29T00:00:00Z",
            "manifest_status": "SEALED",
            "operator": "x",
        },
    }
    assert mod.body_sha256(doc["manifest_body"]) == h1


def test_readiness_rejects_required_fill(mod):
    doc = {
        "manifest_body": {
            **_minimal_ready_body(),
            "campaign": {"campaign_id": "REQUIRED_FILL"},
        },
        "seal": {"manifest_status": "UNSEALED_DRAFT"},
    }
    errs = mod.readiness_check(doc)
    assert any("REQUIRED_FILL" in e for e in errs)


def test_readiness_accepts_empty_anchors_and_reads(mod):
    doc = {
        "manifest_body": _minimal_ready_body(),
        "seal": {"manifest_status": "UNSEALED_DRAFT"},
    }
    errs = mod.readiness_check(doc)
    assert errs == []


def test_verify_seal_mismatch(mod, tmp_path: Path):
    body = _minimal_ready_body()
    good = mod.body_sha256(body)
    doc = {
        "schema_version": 1,
        "document_id": "ADR0043-PH0-D-BOX-FREEZE-MANIFEST-001",
        "manifest_body": body,
        "seal": {
            "algorithm": "sha256",
            "canonicalization": "RFC8785-JCS",
            "encoding": "UTF-8-no-BOM",
            "final_newline": "excluded",
            "body_sha256": "0" * 64,
            "sealed_at_utc": "2026-07-29T12:00:00Z",
            "manifest_status": "SEALED",
            "operator": "t",
            "operator_acknowledgment_kind": "typed_governance_acknowledgment",
            "owner_countersignature": "t",
            "owner_acknowledgment_kind": "typed_governance_acknowledgment",
            "verifier_script": {
                "path": "apps/backend/scripts/adr0043_dbox_freeze_manifest.py",
                "commit": "a" * 40,
                "sha256": "b" * 64,
            },
        },
    }
    p = tmp_path / "m.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    assert mod.cmd_verify_seal(p) == 1
    doc["seal"]["body_sha256"] = good
    p.write_text(json.dumps(doc), encoding="utf-8")
    assert mod.cmd_verify_seal(p) == 0


def test_o3_absent_allows_empty_datasets(mod):
    body = _minimal_ready_body()
    body["datasets"] = {
        "entries": [],
        "o3_status": "ABSENT",
        "o3_predetermined_disposition": "INCONCLUSIVE — REQUIRED CORPUS ABSENT",
    }
    for gate in ("O4-A", "O4-B"):
        body["gate_packages"]["pass_criteria"][gate]["execution_status"] = "DEFERRED"
        body["gate_packages"]["pass_criteria"][gate][
            "predetermined_disposition"
        ] = "INCONCLUSIVE — SET ABSENT"
        body["gate_packages"]["pass_criteria"][gate]["observation_set_id"] = "ABSENT"
    doc = {"manifest_body": body, "seal": {"manifest_status": "UNSEALED_DRAFT"}}
    assert mod.readiness_check(doc) == []


def test_o34_executable_requires_harness_contract(mod):
    body = _minimal_ready_body()
    body["campaign"] = {
        "campaign_id": "c",
        "packages_executable": ["O3", "O4-A", "O4-B"],
    }
    doc = {"manifest_body": body, "seal": {"manifest_status": "UNSEALED_DRAFT"}}
    errs = mod.readiness_check(doc)
    assert any("harness_input_contract" in e for e in errs)


def test_script_has_no_order_path_imports():
    text = SCRIPT.read_text(encoding="utf-8")
    for needle in (
        "import order_router",
        "from app.services.order_router",
        "from app.services import order_router",
        "import alpaca",
        "from app.risk.loss_control.gate",
    ):
        assert needle not in text


def test_schema_file_present_and_hashed():
    repo = Path(__file__).resolve().parents[4]
    schema = (
        repo
        / "docs"
        / "design"
        / "schemas"
        / "ADR0043_Phase0_D_BOX_Freeze_Manifest.schema.json"
    )
    assert schema.is_file()
    digest = hashlib.sha256(schema.read_bytes()).hexdigest()
    assert len(digest) == 64
