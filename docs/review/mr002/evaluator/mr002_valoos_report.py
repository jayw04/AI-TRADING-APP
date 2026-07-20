"""MR-002 validation/OOS evaluator — report-schema kernel (Increment 1 v1.1).

Canonical, exact-float, deterministic report. Every computed float in the hashed payload is encoded
as {"display": <float>, "exact_hex": <float.hex()>} — signed zero preserved, NaN/Infinity rejected,
allow_nan=False, no NumPy scalar reaches json.dumps, no sets, string keys only. The canonical hash is
computed over the EXACT representation (the hex strings), directly avoiding the Stage-3 signed-zero
failure class. The record carries BOTH research_gate_verdict and run_disposition.
"""

from __future__ import annotations

import hashlib
import json
import math

RECORD_TYPE = "MR002_ValOOS_Report"
SCHEMA_VERSION = "increment1-v1.2-synthetic"


class CanonicalizationError(Exception):
    """Non-finite float, NumPy scalar, set, or non-string key reached the canonical payload."""


def _is_numpy_scalar(x) -> bool:
    # np.float64/np.int64/... report module 'numpy'. Note np.float64 IS a Python float subclass,
    # so this check MUST run before the plain-float branch.
    return type(x).__module__ == "numpy"


def encode_float(x) -> dict:
    """{display, exact_hex} via float.hex(); finite-only; signed zero preserved."""
    if _is_numpy_scalar(x):
        raise CanonicalizationError(f"NUMPY_SCALAR:{type(x).__name__}")
    if isinstance(x, bool):
        raise CanonicalizationError("BOOL_AS_FLOAT")
    xf = float(x)
    if not math.isfinite(xf):
        raise CanonicalizationError(f"NONFINITE_FLOAT:{xf}")
    return {"display": xf, "exact_hex": xf.hex()}


def _canonicalize(obj):
    if _is_numpy_scalar(obj):
        raise CanonicalizationError(f"NUMPY_SCALAR:{type(obj).__name__}")
    if obj is None or isinstance(obj, bool) or isinstance(obj, (int, str)):
        return obj
    if isinstance(obj, float):
        return encode_float(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if not isinstance(k, str):
                raise CanonicalizationError(f"NON_STRING_KEY:{k!r}")
            out[k] = _canonicalize(v)
        return out
    if isinstance(obj, (set, frozenset)):
        raise CanonicalizationError("SET_NOT_ALLOWED")
    if isinstance(obj, (list, tuple)):
        return [_canonicalize(v) for v in obj]
    raise CanonicalizationError(f"UNSUPPORTED_TYPE:{type(obj).__name__}")


def _serialize(canonical_obj) -> bytes:
    """Serialize an ALREADY-canonical object (no float re-encoding)."""
    return json.dumps(canonical_obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def canonical_bytes(obj: dict) -> bytes:
    """Canonicalize a RAW object (encode floats, reject non-finite/numpy/set/non-str-key) then
    serialize."""
    return _serialize(_canonicalize(obj))


def build_report(*, window: str, verdict: dict, governing_identity: dict, code_identity: dict,
                 dependency_identity: dict, dependency_lock_sha256: str, fixture_identity: dict,
                 metric_values: dict, gate_results: list, diagnostics: list, hard_stop_evidence,
                 seed: int) -> dict:
    """Assemble the canonical report and stamp its output_hash (over the record minus output_hash).
    `verdict` is the gate-engine evaluate() dict (research_gate_verdict / run_disposition / stop_code).
    `dependency_lock_sha256` is the sha256 of the frozen dependency-lock file, embedded per Ruling 3."""
    record = {
        "record_type": RECORD_TYPE,
        "schema_version": SCHEMA_VERSION,
        "window": window,
        "research_gate_verdict": verdict.get("research_gate_verdict"),
        "run_disposition": verdict.get("run_disposition"),
        "stop_code": verdict.get("stop_code"),
        "governing_prereg_identity": governing_identity.get("prereg_sha256"),
        "governing_ledger_identity": governing_identity.get("ledger_sha256"),
        "governing_dsr_resolution_identity": governing_identity.get("resolution_sha256"),
        "governing_correction_identity": governing_identity.get("correction_sha256"),
        "governing_dispersion_resolution_identity": governing_identity.get("dispersion_resolution_sha256"),
        "dsr_trials_N": governing_identity.get("dsr_trials_N"),
        "code_identity": code_identity,
        "dependency_identity": dependency_identity,
        "dependency_lock_sha256": dependency_lock_sha256,
        "fixture_identity": fixture_identity,
        "metric_values": metric_values,
        "gate_results": gate_results,
        "diagnostics": diagnostics,
        "hard_stop_evidence": hard_stop_evidence,
        "seed": seed,
        "validation_data_read": False,
        "oos_data_read": False,
        "development_performance_computed": False,
        "synthetic_fixture_only": True,
    }
    canonical = _canonicalize(record)
    canonical["output_hash"] = hashlib.sha256(_serialize(canonical)).hexdigest()
    return canonical


def report_hash(record: dict) -> str:
    """Recompute the hash over an already-canonical record minus its output_hash (no re-encoding)."""
    r = {k: v for k, v in record.items() if k != "output_hash"}
    return hashlib.sha256(_serialize(r)).hexdigest()
