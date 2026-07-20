"""Source registry, development-partition manifest, and immutable input manifests (Phase 2A)."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

from ..identities import canonical_sha256
from . import (
    DEV_END,
    DEV_SESSIONS,
    DEV_START,
    DEV_TIMEZONE,
    GOVERNED_SESSION_LIST_SHA256,
)

VALIDATION_BOUNDARY = "2019-10-03"   # first sealed validation session (windows_literal)
OOS_BOUNDARY = "2023-02-17"          # first sealed OOS session
FORBIDDEN_PREFIXES = ("validation", "oos", "sealed")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class SourceRecord:
    source_name: str
    source_owner: str
    source_type: str
    permitted_partition: str
    registered_path: str
    schema_identity: str
    snapshot_identity: str          # SHA-256 of the immutable source object
    coverage_interval: str
    availability_semantics: str
    adjustment_semantics: str


@dataclass(frozen=True)
class DevelopmentPartitionManifest:
    development_start: str
    development_end: str
    development_sessions: int
    validation_boundary: str
    oos_boundary: str
    governed_session_list_sha256: str
    timezone: str
    permitted_source_objects: tuple[str, ...]
    forbidden_source_prefixes: tuple[str, ...]
    partition_guard_identity: str
    dev_snapshot_identity: str

    def canonical(self) -> dict[str, object]:
        return asdict(self)

    @property
    def identity(self) -> str:
        return canonical_sha256(self.canonical())


def build_development_manifest(
    permitted_objects: list[str],
    partition_guard_identity: str,
    dev_snapshot_identity: str,
) -> DevelopmentPartitionManifest:
    return DevelopmentPartitionManifest(
        development_start=DEV_START,
        development_end=DEV_END,
        development_sessions=DEV_SESSIONS,
        validation_boundary=VALIDATION_BOUNDARY,
        oos_boundary=OOS_BOUNDARY,
        governed_session_list_sha256=GOVERNED_SESSION_LIST_SHA256,
        timezone=DEV_TIMEZONE,
        permitted_source_objects=tuple(sorted(permitted_objects)),
        forbidden_source_prefixes=FORBIDDEN_PREFIXES,
        partition_guard_identity=partition_guard_identity,
        dev_snapshot_identity=dev_snapshot_identity,
    )


def build_input_manifest(record_type: str, records: list[dict[str, object]]) -> dict[str, object]:
    """Deterministic immutable manifest: records sorted + canonically hashed."""
    ordered = sorted(records, key=lambda r: canonical_sha256(r))
    return {
        "record_type": record_type,
        "count": len(ordered),
        "record_identities": [canonical_sha256(r) for r in ordered],
        "manifest_sha256": canonical_sha256(
            {"record_type": record_type, "ids": [canonical_sha256(r) for r in ordered]}
        ),
    }
