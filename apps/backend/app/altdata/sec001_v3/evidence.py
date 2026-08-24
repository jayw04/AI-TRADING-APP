"""Per-request source evidence for the SEC-001 V3 classification crawl.

One record per HTTP *attempt* — not per document. A document that succeeded on its third
try produces three records, two with ``outcome="retry"`` and one with ``outcome="ok"``.
That is deliberate: the retry history is part of how the crawl behaved against SEC's
infrastructure, and a record that only shows successes cannot answer "were we throttled?"
after the fact.

Digest policy. Two digests are recorded and they are not interchangeable:

``sha256_wire``  over the bytes as they arrived on the wire, before any content-encoding
                 is undone. This is what "the source" literally was.
``sha256_body``  over the decoded body — the bytes the parser actually saw. This is the
                 digest that is reproducible across fetches, because gzip output depends
                 on the server's compression level and SEC does not promise stability
                 there.

Recording only one of them would force a later reader to guess which question a single
digest answers. Provenance questions resolve against ``sha256_wire``; "did the content
change between two crawls" resolves against ``sha256_body``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.altdata.sec001_v3.forbidden import append_jsonl, assert_dataclass_clean


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now_iso() -> str:
    """Retrieval timestamps are always explicit UTC.

    The laptop runs local time and the box host runs EDT while its containers run UTC;
    a naive ``datetime.now()`` has been the root cause of four separate timezone
    incidents in this repository. There is no unqualified clock read in this package.
    """
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SourceEvidence:
    """What was requested, what came back, and what it hashed to."""

    # request identity
    uri: str
    method: str
    attempt: int                 # 1-based
    requested_utc: str

    # response
    http_status: int | None      # None == transport failure, no status was received
    received_utc: str
    elapsed_ms: int
    outcome: str                 # ok | retry | halt | error | exhausted

    # payload
    sha256_wire: str | None = None
    sha256_body: str | None = None
    wire_bytes: int | None = None
    body_bytes: int | None = None
    content_encoding: str | None = None

    # provenance of the *filing* this request belongs to, where applicable
    cik: int | None = None
    ticker: str | None = None
    accession: str | None = None
    form: str | None = None

    # free-text reason for non-ok outcomes (exception class, Retry-After, etc.)
    detail: str | None = None

    # frozen policy fingerprint, so a record is self-describing without its manifest
    crawl_id: str = ""
    ua: str = ""


@dataclass
class EvidenceLog:
    """Append-only JSONL sink for :class:`SourceEvidence`."""

    path: Path
    written: int = field(default=0)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, ev: SourceEvidence) -> SourceEvidence:
        append_jsonl(ev, self.path)
        self.written += 1
        return ev


# Import-time guard: an emitted record type may never declare a coverage quantity.
assert_dataclass_clean(SourceEvidence)
