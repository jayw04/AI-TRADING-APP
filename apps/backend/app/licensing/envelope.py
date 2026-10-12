"""PU-1 taint tagging for governed artifacts.

``tag_envelope`` returns a NEW mapping with ``license_scope`` / ``license_sources`` placed next to
``artifact_sha256``. It never mutates its input and is meant to be applied BEFORE a digest is
computed over a new envelope. Existing sealed/pinned envelopes (factor-data coverage receipts,
governed-corpus manifests, ADR-0043 reconciliation records, ...) must NOT be re-serialised with the
extra field because that would change a pinned digest; for those, ``write_sidecar`` records the
scope in a ``<artifact>.license.json`` file bound to the artifact's own SHA-256 instead.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from app.licensing.gate import safe_effective_scope
from app.licensing.registry import normalize_source_id
from app.licensing.scopes import LicenseScope

SCOPE_KEY = "license_scope"
SOURCES_KEY = "license_sources"
SIDECAR_SUFFIX = ".license.json"


def _sorted_sources(sources: Iterable[str]) -> list[str]:
    return sorted({normalize_source_id(s) for s in sources})


def tag_envelope(envelope: Mapping[str, Any], sources: Iterable[str]) -> dict[str, Any]:
    """Copy of ``envelope`` with ``license_scope`` (+ ``license_sources``) beside ``artifact_sha256``."""
    srcs = _sorted_sources(sources)
    scope = safe_effective_scope(sources=srcs, declared_scope=envelope.get(SCOPE_KEY))
    out: dict[str, Any] = {}
    placed = False
    for k, v in envelope.items():
        if k in (SCOPE_KEY, SOURCES_KEY):
            continue
        out[k] = v
        if k == "artifact_sha256":
            out[SCOPE_KEY] = scope.name
            out[SOURCES_KEY] = srcs
            placed = True
    if not placed:
        out[SCOPE_KEY] = scope.name
        out[SOURCES_KEY] = srcs
    return out


def envelope_scope(envelope: Mapping[str, Any]) -> LicenseScope:
    """Effective scope of a tagged envelope, recomputed from its sources (a missing/forged label
    cannot make it more permissive). Untagged => ``UNKNOWN``."""
    raw_sources = envelope.get(SOURCES_KEY)
    sources = [str(s) for s in raw_sources] if isinstance(raw_sources, list) else []
    return safe_effective_scope(sources=sources, declared_scope=envelope.get(SCOPE_KEY))


def sidecar_path(artifact: Path) -> Path:
    return artifact.with_name(artifact.name + SIDECAR_SUFFIX)


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".partial")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_sidecar(artifact: Path, sources: Iterable[str]) -> dict[str, Any]:
    """Write ``<artifact>.license.json`` binding the artifact's SHA-256 to its scope + sources."""
    srcs = _sorted_sources(sources)
    record = {
        "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        SCOPE_KEY: safe_effective_scope(sources=srcs).name,
        SOURCES_KEY: srcs,
    }
    atomic_write(
        sidecar_path(artifact),
        (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return record


def scope_of_file(artifact: Path) -> LicenseScope:
    """Scope of a file from its sidecar. No sidecar, unreadable sidecar, or a digest that no longer
    matches the file => ``UNKNOWN`` (blocked)."""
    try:
        record = json.loads(sidecar_path(artifact).read_text(encoding="utf-8"))
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return LicenseScope.UNKNOWN
    if not isinstance(record, dict) or record.get("artifact_sha256") != digest:
        return LicenseScope.UNKNOWN
    return envelope_scope(record)
