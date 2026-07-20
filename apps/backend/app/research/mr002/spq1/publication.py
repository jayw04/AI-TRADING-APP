"""Immutable synthetic publication package (§14).

Deterministically ordered, canonicalized, SHA-256 bound, atomic, non-overwriting, fail-closed on
partial output. No S3 / production DB / broker / live adapter. The manifest self-hashes the ordered
artifact digests plus the bound identities and cutoff timestamp.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass

from .identities import canonical_sha256, sha256_hex
from .models import ExecutionEnrichedCandidateRecord, SignalDecisionRecord

__all__ = ["PublicationPackage", "PublicationError", "build_publication", "write_publication"]


class PublicationError(Exception):
    """Publication I/O guard (overwrite / partial-output). Not part of the signal taxonomy."""


@dataclass(frozen=True)
class PublicationPackage:
    decision_records: list[dict[str, object]]
    execution_enrichments: list[dict[str, object]]
    decision_manifest: dict[str, object]
    execution_manifest: dict[str, object]
    input_identities: dict[str, str]
    producer_identity: str
    schema_identities: dict[str, str]
    cutoff_timestamp: str
    manifest_sha256: str

    def canonical(self) -> dict[str, object]:
        return {
            "decision_records": self.decision_records,
            "execution_enrichments": self.execution_enrichments,
            "decision_manifest": self.decision_manifest,
            "execution_manifest": self.execution_manifest,
            "input_identities": self.input_identities,
            "producer_identity": self.producer_identity,
            "schema_identities": self.schema_identities,
            "cutoff_timestamp": self.cutoff_timestamp,
            "manifest_sha256": self.manifest_sha256,
        }


def build_publication(
    decisions: list[SignalDecisionRecord],
    enrichments: list[ExecutionEnrichedCandidateRecord],
    input_identities: dict[str, str],
    producer_identity: str,
    schema_identities: dict[str, str],
    cutoff_timestamp: str,
) -> PublicationPackage:
    """Assemble the deterministically-ordered, self-hashed publication package."""
    dec = sorted((d.canonical() for d in decisions), key=lambda r: str(r["candidate_id"]))
    enr = sorted(
        (e.canonical() for e in enrichments),
        key=lambda r: str(r["decision_record_identity"]),
    )
    decision_manifest = {
        "count": len(dec),
        "record_identities": [canonical_sha256(r) for r in dec],
    }
    execution_manifest = {
        "count": len(enr),
        "record_identities": [canonical_sha256(r) for r in enr],
    }
    manifest_body = {
        "decision_manifest": decision_manifest,
        "execution_manifest": execution_manifest,
        "input_identities": input_identities,
        "producer_identity": producer_identity,
        "schema_identities": schema_identities,
        "cutoff_timestamp": cutoff_timestamp,
    }
    manifest_sha = canonical_sha256(manifest_body)
    return PublicationPackage(
        decision_records=dec,
        execution_enrichments=enr,
        decision_manifest=decision_manifest,
        execution_manifest=execution_manifest,
        input_identities=input_identities,
        producer_identity=producer_identity,
        schema_identities=schema_identities,
        cutoff_timestamp=cutoff_timestamp,
        manifest_sha256=manifest_sha,
    )


def write_publication(package: PublicationPackage, path: str) -> str:
    """Atomically write the package; refuse to overwrite; fail closed on partial output.

    Returns the SHA-256 of the written bytes.
    """
    if os.path.exists(path):
        raise PublicationError(f"refusing to overwrite existing publication artifact: {path}")
    payload = json.dumps(package.canonical(), sort_keys=True, indent=1).encode("utf-8")
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".partial")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)  # atomic on POSIX and Windows
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return sha256_hex(payload)
