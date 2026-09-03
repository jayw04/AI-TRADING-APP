"""Persisted source bytes sufficient to reproduce every SIC decision without refetching.

The invariant this module exists to establish:

    Every SIC observation OR absence used by the frozen spine is backed by persisted exact
    source bytes sufficient to reproduce the parser decision, without asking EDGAR again.

Why it was added. The first two canaries produced a provenance chain whose digests attested
to bytes that no longer existed anywhere. When the ABT result raised the question "does this
2000 filing actually contain a SIC field?", the only way to answer was to re-request the
document — exactly what the fair-access budget and the frozen-population discipline exist to
minimise. Digest-only evidence is too weak for a program that has to adjudicate *absence*.

Retention is bounded and, deliberately, **not outcome-dependent**: bytes are kept for every
filing, not only for the ones that failed to yield a SIC. Retaining evidence only where the
result was interesting is how a corpus acquires a selection bias that nobody can later
measure.

What is kept, per filing:

``HEADER_INDEX``            the exact response body the parser consumed
``HEADER_TERMINATED``       document start through the closing ``</SEC-HEADER>`` tag
``DOCUMENT_EOF_...``        the complete body, which is within the frozen ceiling by
                            construction (EOF was reached before the cap)
``ACQUISITION_...``         exactly the bytes acquired up to the ceiling

Where a decision was assembled from several contiguous ranges, the retained artifact is the
canonical concatenation. The reconstruction procedure and every constituent request digest
are recorded alongside it, so the canonical artifact is independently auditable rather than
merely asserted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from app.altdata.sec001_v3.forbidden import assert_dataclass_clean

SEC_HEADER_CLOSE = b"</SEC-HEADER>"
SEC_HEADER_OPEN = b"<SEC-HEADER>"


@dataclass
class RangeAttempt:
    """One constituent request that contributed bytes to a decision artifact."""

    uri: str
    range_header: str | None
    http_status: int | None
    content_range: str | None
    byte_length: int
    sha256: str


@dataclass
class SourceDecisionBytes:
    """The exact bytes behind one filing's SIC decision, plus how they were assembled."""

    accession: str
    uri: str
    acquisition_status: str
    byte_length: int
    sha256: str
    reconstruction: str
    attempts: list[RangeAttempt] = field(default_factory=list)
    form: str | None = None
    parser_result: str | None = None       # filled by the driver after the spine parses
    artifact_path: str | None = None

    # Independent, orthogonal predicates about the retained bytes. Each is a separate
    # observable fact; none of them is permitted to imply `no_pit_sic`, which is a
    # downstream determination about historical evidence.
    document_complete: bool = False
    sec_header_open_present: bool = False
    sec_header_close_present: bool = False
    sic_field_present_anywhere: bool = False
    sic_field_present_inside_sec_header: bool = False


assert_dataclass_clean(RangeAttempt, SourceDecisionBytes)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def predicates(data: bytes, sic_pattern: object | None = None) -> dict[str, bool]:
    """Independent structural predicates over retained bytes.

    ``sic_pattern`` is the frozen spine's own compiled ``SIC_RE`` when available, so the
    "is a SIC field present" question is answered by the authoritative parser's own
    expression rather than a lookalike defined here. Falling back to a literal marker
    search keeps the predicate meaningful when the pattern is not supplied, and the
    fallback is deliberately coarser rather than cleverer.
    """
    open_at = data.find(SEC_HEADER_OPEN)
    close_at = data.find(SEC_HEADER_CLOSE)

    if sic_pattern is not None:
        text = data.decode("utf-8", errors="replace")
        m = sic_pattern.search(text)  # type: ignore[attr-defined]
        anywhere = m is not None
        sic_at = m.start() if m else -1
        # Offsets differ between bytes and decoded text only where replacement occurred;
        # for the containment test we re-locate the tag in the same decoded text.
        close_text = text.find(SEC_HEADER_CLOSE.decode())
        open_text = text.find(SEC_HEADER_OPEN.decode())
        inside = bool(
            anywhere and open_text != -1 and sic_at > open_text
            and (close_text == -1 or sic_at < close_text)
        )
    else:
        sic_at = data.upper().find(b"STANDARD INDUSTRIAL CLASSIFICATION")
        anywhere = sic_at != -1
        inside = bool(anywhere and open_at != -1 and sic_at > open_at
                      and (close_at == -1 or sic_at < close_at))

    return {
        "sec_header_open_present": open_at != -1,
        "sec_header_close_present": close_at != -1,
        "sic_field_present_anywhere": anywhere,
        "sic_field_present_inside_sec_header": inside,
    }


def write_artifact(directory: Path, accession: str, data: bytes) -> Path:
    """Persist the canonical decision bytes for one filing, atomically."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{accession}.bin"
    tmp = path.with_suffix(".bin.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path
