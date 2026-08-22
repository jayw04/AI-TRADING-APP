"""Write-time provenance — every harness output is stamped or invalid (memo §6.10).

Implements the §5.5 design requirement generalized by the 2026-08-11 amendment:
every published record carries immutable write provenance sufficient to
identify creation time, source artifact and hash, producing code/version,
invocation/run ID, and write class. Harness outputs are always
``write_class="reconstruction"`` — they are reconstructions from raw data, not
live collection, and never backfill/repair/manual.

``created_at`` is caller-supplied (injectable) so tests are deterministic and
the stamp records the caller's clock discipline, not this module's.
"""

from __future__ import annotations

from typing import Any

from app.research.gapper_stage0 import __version__

#: The §5.5 write-class vocabulary.
WRITE_CLASSES = frozenset({"collection", "reconstruction", "backfill", "repair", "manual"})

#: Every output of this harness is a reconstruction — frozen, not configurable.
HARNESS_WRITE_CLASS = "reconstruction"

REQUIRED_KEYS = (
    "created_at",
    "source_artifact",
    "source_sha256",
    "code_version",
    "run_id",
    "write_class",
)


class ProvenanceError(ValueError):
    """The output's provenance stamp is missing or invalid."""


def make_provenance(
    *,
    created_at: str,
    source_artifact: str,
    source_sha256: str,
    run_id: str,
    write_class: str = HARNESS_WRITE_CLASS,
    code_version: str = __version__,
) -> dict[str, str]:
    """Build a provenance stamp; validates the write class and non-emptiness."""
    if write_class not in WRITE_CLASSES:
        raise ProvenanceError(f"write_class {write_class!r} not in {sorted(WRITE_CLASSES)}")
    stamp_dict = {
        "created_at": created_at,
        "source_artifact": source_artifact,
        "source_sha256": source_sha256,
        "code_version": code_version,
        "run_id": run_id,
        "write_class": write_class,
    }
    for key, value in stamp_dict.items():
        if not value or not str(value).strip():
            raise ProvenanceError(f"provenance field {key!r} must be non-empty")
    return stamp_dict


def stamp(output: dict[str, Any], provenance: dict[str, str]) -> dict[str, Any]:
    """Return a copy of ``output`` carrying ``provenance``. The stamp is
    attached at write time — never retroactively repaired."""
    stamped = dict(output)
    stamped["provenance"] = dict(provenance)
    return stamped


def validate_provenance(
    output: dict[str, Any], *, expected_write_class: str = HARNESS_WRITE_CLASS
) -> None:
    """Raise :class:`ProvenanceError` unless ``output`` carries a complete,
    well-formed stamp of the expected write class. Unstamped ⇒ invalid."""
    prov = output.get("provenance")
    if not isinstance(prov, dict):
        raise ProvenanceError("output has no provenance stamp — unstamped outputs are invalid")
    missing = [k for k in REQUIRED_KEYS if not prov.get(k) or not str(prov[k]).strip()]
    if missing:
        raise ProvenanceError(f"provenance stamp missing/empty fields: {missing}")
    if prov["write_class"] not in WRITE_CLASSES:
        raise ProvenanceError(f"unknown write_class {prov['write_class']!r}")
    if prov["write_class"] != expected_write_class:
        raise ProvenanceError(
            f"write_class {prov['write_class']!r} != expected {expected_write_class!r} "
            "for a harness output"
        )
