"""MR-002 validation/OOS evaluator — report-schema kernel (Workstream B, Increment 1).

Builds the immutable per-window report record with canonical (sorted-key) serialization and a
deterministic output hash. In Increment 1 EVERY report is synthetic: the development-free flags are
asserted true. The kernel records governing identities (prereg / ledger / resolution), code +
dependency + fixture identities, metric values, gate results, diagnostics, hard-stop evidence, the
seed, and the self-hash.
"""

from __future__ import annotations

import hashlib
import json

RECORD_TYPE = "MR002_ValOOS_Report"
SCHEMA_VERSION = "increment1-synthetic-1.0"


def canonical_bytes(obj: dict) -> bytes:
    """Deterministic serialization: sorted keys, compact separators, UTF-8, ensure_ascii."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def build_report(*, window: str, disposition: str, governing_identity: dict, code_identity: dict,
                 dependency_identity: dict, fixture_identity: dict, metric_values: dict,
                 gate_results: list, diagnostics: list, hard_stop_evidence, seed: int) -> dict:
    """Assemble a report dict and stamp its output hash. The hash is computed over the record with
    the `output_hash` field removed, then re-inserted (self-referential-safe)."""
    record = {
        "record_type": RECORD_TYPE,
        "schema_version": SCHEMA_VERSION,
        "window": window,
        "disposition": disposition,
        "governing_prereg_identity": governing_identity.get("prereg_sha256"),
        "governing_ledger_identity": governing_identity.get("ledger_sha256"),
        "governing_resolution_identity": governing_identity.get("resolution_sha256"),
        "dsr_trials_N": governing_identity.get("dsr_trials_N"),
        "code_identity": code_identity,
        "dependency_identity": dependency_identity,
        "fixture_identity": fixture_identity,
        "metric_values": metric_values,
        "gate_results": gate_results,
        "diagnostics": diagnostics,
        "hard_stop_evidence": hard_stop_evidence,
        "seed": seed,
        # development-free assertions (Increment 1: synthetic only)
        "validation_data_read": False,
        "oos_data_read": False,
        "development_performance_computed": False,
        "synthetic_fixture_only": True,
    }
    digest = hashlib.sha256(canonical_bytes(record)).hexdigest()
    record["output_hash"] = digest
    return record


def report_hash(record: dict) -> str:
    """Recompute the hash the way build_report did (over the record minus output_hash)."""
    r = {k: v for k, v in record.items() if k != "output_hash"}
    return hashlib.sha256(canonical_bytes(r)).hexdigest()
