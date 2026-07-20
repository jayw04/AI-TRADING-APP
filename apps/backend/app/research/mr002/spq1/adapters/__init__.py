"""SPQ-1 Phase 2A — development-data source & adapter qualification (LIMITED REAL-DATA).

Read-only adapters that turn the registered MR-002 DEVELOPMENT partition (frozen 2013-01-02 ->
2019-10-02, 1700 governed sessions, governed_session_list_sha256 b873421...) into the qualified
Phase-1 typed inputs. One-way flow only:

    registered source -> source adapter -> validation/PIT checks -> immutable input manifest
    -> qualified Phase-1 typed input

Adapters never reach back into source systems, contain no SQL/S3/HTTP/vendor SDK in the signal
math, and access ONLY the hash-bound development-only snapshot (materialized by dev_snapshot) behind
the mandatory PartitionGuard. Validation/OOS partitions are technically excluded. No performance
metric is computed, retained, or interpreted; a narrow Phase-1 input-conversion check is a schema
compatibility test only, and any incidental z-score is an unexamined implementation artifact.
"""
from __future__ import annotations

# Frozen development-partition bounds (governing prereg windows_literal.development).
DEV_START = "2013-01-02"
DEV_END = "2019-10-02"
DEV_SESSIONS = 1700
GOVERNED_SESSION_LIST_SHA256 = (
    "b873421516ba5c4bbeb4ff3859e574f64f7251a956a2ba6ddea0e753981dad3f"
)
DEV_TIMEZONE = "America/New_York"  # registered regular-session policy (dates are EOD)

# Registered source object identities (repo-relative; bound by SHA-256 at qualification time).
REGISTERED_RESEARCH_DB = "apps/backend/data/mr002_research.duckdb"
REGISTERED_PROVENANCE_DB = "apps/backend/data/mr002_provenance.duckdb"


def abs_path(registered_relative: str) -> str:
    """Resolve a repo-relative registered path to an absolute filesystem path (CWD-independent)."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[7]
    return str(repo_root / registered_relative)

ADAPTER_CODE_VERSION = "spq1-phase2a-v1.0-development"


def normalize_utc_iso(value: object) -> str:
    """Normalize any stored timestamp to UTC ISO-8601 'YYYY-MM-DDTHH:MM:SSZ'.

    Makes availability comparisons lexically == chronologically ordered and deterministic, regardless
    of the source timezone offset.
    """
    from datetime import UTC, datetime

    s = str(value).strip()
    if s.endswith("Z") and "T" in s:
        return s
    for candidate in (s, f"{s}T00:00:00+00:00"):
        try:
            dt = datetime.fromisoformat(candidate)
            break
        except ValueError:
            continue
    else:
        return s
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
