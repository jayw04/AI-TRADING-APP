"""MR-002 OQ-1 — frozen process exit-code taxonomy + canonical refusal record (Component 5).

Every nonzero exit produces a canonical, deterministic refusal record. No secrets or host paths are
exposed (paths are basename-only; environment values are never echoed).
"""

from __future__ import annotations

import hashlib
import json

# frozen exit-code contract
EXIT = {
    "PASS": 0,
    "IDENTITY_REFUSAL": 10,          # code / governance identity refusal
    "ENVIRONMENT_REFUSAL": 11,       # dependency / environment refusal
    "SEALED_ACCESS_REFUSAL": 12,     # sealed-data access refusal
    "INTEGRITY_STOP": 13,            # canonicalization / integrity stop
    "DETERMINISM_MISMATCH": 14,      # deterministic-output mismatch
    "PUBLICATION_REFUSAL": 15,       # publication refusal
    "UNSUPPORTED_INVOCATION": 16,    # unsupported invocation
    "INTERNAL_FAILURE": 20,          # unexpected internal failure
}
REASON_TO_EXIT = {
    "REFUSED_CODE_OR_DATA_IDENTITY": EXIT["IDENTITY_REFUSAL"],
    "REFUSED_ENVIRONMENT_IDENTITY": EXIT["ENVIRONMENT_REFUSAL"],
    "REFUSED_SEALED_ACCESS": EXIT["SEALED_ACCESS_REFUSAL"],
    "INTEGRITY_STOP": EXIT["INTEGRITY_STOP"],
    "DETERMINISM_MISMATCH": EXIT["DETERMINISM_MISMATCH"],
    "REFUSED_PUBLICATION": EXIT["PUBLICATION_REFUSAL"],
    "UNSUPPORTED_INVOCATION": EXIT["UNSUPPORTED_INVOCATION"],
}


def exit_code_for(reason_code: str) -> int:
    family = reason_code.split(":", 1)[0]
    return REASON_TO_EXIT.get(family, EXIT["INTERNAL_FAILURE"])


def _safe(v):
    """Basename-only for anything path-like; never echo secrets/host paths."""
    if isinstance(v, str) and ("\\" in v or "/" in v):
        return v.replace("\\", "/").rsplit("/", 1)[-1]
    return v


def refusal_record(*, reason_code: str, stage: str, expected, observed, code_commit: str,
                   container_digest: str, dependency_lock_hash: str, timestamp: str,
                   stack_trace_hash: str | None = None) -> dict:
    """Canonical refusal record (deterministic; caller supplies a fixed timestamp for reproducibility)."""
    rec = {
        "record_type": "MR002_OQ1_Refusal",
        "reason_code": reason_code,
        "exit_code": exit_code_for(reason_code),
        "stage": stage,
        "expected_identity": _safe(expected),
        "observed_identity": _safe(observed),
        "timestamp": timestamp,
        "code_commit": code_commit,
        "container_digest": container_digest,
        "dependency_lock_hash": dependency_lock_hash,
        "no_data_access_assertions": {"validation_data_read": False, "oos_data_read": False,
                                      "development_performance_computed": False, "real_data_accessed": False},
        "stack_trace_hash": stack_trace_hash,
    }
    rec["record_hash"] = hashlib.sha256(
        json.dumps(rec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return rec
