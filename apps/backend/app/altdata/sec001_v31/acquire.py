"""WP0A-Q cover-page acquisition orchestration, bound to the frozen authority.

Every refusal that can be decided from governed state is decided **before a byte is
requested**. The decisive one is new (review finding P0): a filing must be *exactly* one of
the authorized ``(cik, form, accession, accepted_at)`` tuples in the selected envelope. Form
and cutoff checks remain, but they are now consequences of the authority rather than
caller-supplied values — the authority is loaded from hash-verified artifacts and its
``permitted_forms`` and ``cutoff_utc`` come out of the sealed manifest.

The transport locator is **authenticated** against the filing metadata before use, and the
URL is preferably built by the authority from governed identifiers. Its *filename* still
cannot reach identity; its *filing identity* must match, or the bytes could belong to a
different accession than the record they will be stamped with.

One accession may legitimately support several observations when the document declares
several security classes. That is one acquisition and several observations, never several
acquisitions — and the whole set is committed atomically, so a filing's classes are never
partially retained.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Final

from app.altdata.sec001_v31 import cover_parser
from app.altdata.sec001_v31.authority import AcquisitionAuthority, NotAuthorized
from app.altdata.sec001_v31.clock import accepted_at_utc
from app.altdata.sec001_v31.layers import (
    FilingMetadata,
    LocatorMismatch,
    Observation,
    TransportLocator,
)
from app.altdata.sec001_v31.transport import (
    FETCH_OK,
    BoundedFetcher,
    CreateOnceStore,
    DurableLedger,
)

REFUSED_FORM: Final = "REFUSED_NON_PERMITTED_FORM"
REFUSED_CUTOFF: Final = "REFUSED_ACCEPTED_AFTER_CUTOFF"
REFUSED_DUPLICATE: Final = "REFUSED_ALREADY_ACQUIRED"
REFUSED_NOT_IN_ENVELOPE: Final = "REFUSED_NOT_IN_AUTHORIZED_ENVELOPE"
ACQUIRED: Final = "ACQUIRED"

#: The registrant CIK the cover page declares disagrees with the CIK on the index record.
#: A FILING/OBSERVATION identity conflict, deliberately NOT the competing-binding conjunct:
#: an index CIK is acquisition metadata and is not itself an admissible security->CIK
#: binding, so calling it a competing binding would let filing metadata masquerade as
#: identity evidence. The genuine conjunct lives in ``bindings.py``.
INDEX_COVER_CIK_MISMATCH: Final = "INDEX_COVER_CIK_MISMATCH"

__all__ = [
    "ACQUIRED",
    "INDEX_COVER_CIK_MISMATCH",
    "REFUSED_CUTOFF",
    "REFUSED_DUPLICATE",
    "REFUSED_FORM",
    "REFUSED_NOT_IN_ENVELOPE",
    "AcquisitionResult",
    "CoverAcquisition",
    "LocatorMismatch",
    "NotAuthorized",
    "accepted_at_utc",
    "refusal_reasons",
]


@dataclass
class AcquisitionResult:
    status: str
    parse_status: str | None = None
    observations: list[Observation] = field(default_factory=list)
    artifact_identities: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    document_requests_spent: int = 0


def refusal_reasons() -> tuple[str, ...]:
    """Every pre-network refusal, for documentation and adjudication."""
    return (REFUSED_FORM, REFUSED_CUTOFF, REFUSED_NOT_IN_ENVELOPE, REFUSED_DUPLICATE)


class CoverAcquisition:
    """Acquire cover-page identity evidence for authorized filings only."""

    def __init__(
        self,
        authority: AcquisitionAuthority,
        fetcher: BoundedFetcher,
        store: CreateOnceStore,
        ledger: DurableLedger,
        *,
        max_continuations: int = 0,
    ) -> None:
        self.authority = authority
        self.fetcher = fetcher
        self.store = store
        self.ledger = ledger
        self.max_continuations = max_continuations

    def acquire(self, meta: FilingMetadata, locator: TransportLocator) -> AcquisitionResult:
        a = self.authority

        # ---- preflight: governed state only, before any request ----------------------
        if meta.form not in a.permitted_forms:
            return AcquisitionResult(REFUSED_FORM, diagnostics={"form": meta.form})

        if accepted_at_utc(meta.accepted_at) > a.cutoff_utc:
            return AcquisitionResult(REFUSED_CUTOFF, diagnostics={"accepted_at": meta.accepted_at})

        if not a.is_authorized(meta.cik, meta.form, meta.accession, meta.accepted_at):
            return AcquisitionResult(
                REFUSED_NOT_IN_ENVELOPE,
                diagnostics={
                    "cik": meta.cik,
                    "form": meta.form,
                    "accession": meta.accession,
                    "envelope": a.selected_envelope,
                    "authorized_count": len(a.authorized_keys),
                },
            )

        # CIK-once, durable across restarts.
        if self.ledger.already_acquired(meta.cik, meta.form, meta.accession):
            return AcquisitionResult(REFUSED_DUPLICATE, diagnostics={"accession": meta.accession})

        # The bytes must belong to the filing they will be recorded as.
        locator.assert_matches(meta)
        a.require_origin(locator.url)

        # ---- acquisition -------------------------------------------------------------
        before = self.ledger.document_requests
        outcome = self.fetcher.get_document_complete(
            locator.url, max_continuations=self.max_continuations
        )
        spent = self.ledger.document_requests - before
        self.ledger.mark_acquired(meta.cik, meta.form, meta.accession)

        if outcome.status != FETCH_OK:
            return AcquisitionResult(
                ACQUIRED,
                parse_status=cover_parser.STATUS_EVIDENCE_UNAVAILABLE,
                diagnostics={"http_status": outcome.http_status, "reason": outcome.reason},
                document_requests_spent=spent,
            )

        # The parser receives bytes only. The locator is not in scope here.
        parsed = cover_parser.parse_cover_identity(
            outcome.body,
            eof_reached=outcome.eof_reached,
            truncated=outcome.truncated,
            bytes_consumed=outcome.bytes_consumed,
        )

        result = AcquisitionResult(
            ACQUIRED,
            parse_status=parsed.status,
            diagnostics=dict(parsed.diagnostics),
            document_requests_spent=spent,
        )
        if not parsed.is_bound:
            return result

        if parsed.cik != meta.cik:
            result.parse_status = INDEX_COVER_CIK_MISMATCH
            result.diagnostics.update(
                {
                    "reason": "cover_cik_disagrees_with_index",
                    "index_cik": meta.cik,
                    "cover_cik": parsed.cik,
                    "consequence": (
                        "observation inadmissible; candidate binding not proven by this "
                        "observation; affected cells remain DISPUTED unless other admissible "
                        "evidence resolves them"
                    ),
                }
            )
            return result

        observations = [Observation.build(meta, ev) for ev in parsed.class_tuples]
        obs_ids = [o.observation_id(a.source_variant) for o in observations]
        provenance = {
            "body_sha256": hashlib.sha256(outcome.body).hexdigest(),
            "bytes_consumed": outcome.bytes_consumed,
            "eof_reached": outcome.eof_reached,
            "total_bytes": outcome.total_bytes,
            "continuations": outcome.continuations,
            "http_status": outcome.http_status,
            "attempts": outcome.attempts,
            "manifest_sha256": a.manifest_sha256,
            "envelope_sha256": a.envelope_sha256,
            "selection_sha256": a.selection_sha256,
            "document_requests_spent": spent,
        }
        # One atomic commit for the whole accession: a filing's classes are never partial.
        self.store.put_accession_set(
            meta.cik,
            meta.accession,
            a.source_variant,
            [o.to_record() for o in observations],
            obs_ids,
            provenance,
        )
        result.observations = observations
        result.artifact_identities = [
            CreateOnceStore.identity(meta.cik, meta.accession, a.source_variant, oid)
            for oid in obs_ids
        ]
        return result
