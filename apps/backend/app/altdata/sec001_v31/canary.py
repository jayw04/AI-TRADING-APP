"""The frozen one-accession canary rule: which accession, and whether it may be spent.

Two owner rulings live here, and both exist to stop a non-repeatable accession being spent
on a foregone conclusion.

**Do not spend a scarce left-bracket accession.** The 19 pre-window filings in Envelope B are
the only evidence that reaches the 2021-02-08 edge — three CIKs have none at all — so they
are not transport test material. Envelope B remains the sole acquisition authority; Envelope
A is *not* an authority here, it only supplies the exclusion list. Note that the first entry
of B's own array **is** one of the 19, so an unfiltered "first entry" rule would have picked
the scarcest possible candidate.

**Screen on size before spending a document request.** EOF-only admission and a finite
window count together mean a document at or above the aggregate ceiling can never reach EOF,
so it is predetermined to return ``EVIDENCE_UNAVAILABLE``. Discovering that by spending the
requests would consume the accession to learn something the transport bound already implied.
Equality is excluded too: at exactly the ceiling the reader fills its last window and reports
truncation.

A candidate that fails the screen is **not** consumed. It has spent an index request and
holds a resolved locator, and it stays available for a future authority that permits
continuation.

The ordering rule is frozen here rather than chosen later: **Envelope B's own key order,
with the 19 bracket accessions removed, first retained entry**. No tuple re-sorting, no
selection informed by anything observed afterwards. Both inputs come from the hash-verified
authority object; this module reads no file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.altdata.sec001_v31.authority import (
    MAX_DOCUMENT_BYTES,
    AcquisitionAuthority,
)

#: Strict, and derived rather than typed: a document at or above the aggregate ceiling
#: cannot reach EOF within the frozen window count, so it is ineligible before any request is
#: made. Under the owner's C=7 ruling this is 8 x 983,040. The per-read bound is unchanged --
#: what the census bought was more bounded reads, not bigger ones.
CANARY_MAX_DOCUMENT_BYTES: Final = MAX_DOCUMENT_BYTES

ELIGIBLE: Final = "CANARY_ELIGIBLE"
INELIGIBLE_TOO_LARGE: Final = "CANARY_INELIGIBLE_DOCUMENT_AT_OR_ABOVE_BOUND"
INELIGIBLE_SIZE_UNKNOWN: Final = "CANARY_INELIGIBLE_SIZE_NOT_AUTHORITATIVE"


@dataclass(frozen=True)
class CanaryCandidate:
    position: int
    cik: int
    form: str
    accession: str
    accepted_at: str


def candidate_order(authority: AcquisitionAuthority) -> list[CanaryCandidate]:
    """Envelope B's own key order, minus the 19 brackets. Frozen before any lookup.

    Reads **only** hash-verified in-memory authority data. The previous revision re-read the
    envelope and selection files from disk after the authority had verified them, which left
    a window in which a local edit could change the bracket list and promote a scarce
    boundary filing into the canary slot.
    """
    excluded = authority.bracket_accessions
    return [
        CanaryCandidate(position=i, cik=cik, form=form, accession=accession, accepted_at=accepted)
        for i, (cik, form, accession, accepted) in enumerate(authority.ordered_keys)
        if accession not in excluded
    ]


def first_candidate(authority: AcquisitionAuthority) -> CanaryCandidate:
    order = candidate_order(authority)
    if not order:
        raise RuntimeError("no non-bracket candidate exists in Envelope B")
    return order[0]


def is_out_of_population(authority: AcquisitionAuthority, accession: str) -> bool:
    """True when an accession is outside Envelope B entirely.

    Schema-discovery work must target one of these, so that nothing in the canary set --
    candidate or bracket -- can be touched by it.
    """
    return all(k[2] != accession for k in authority.ordered_keys)


def screen(document_size: int | None) -> tuple[bool, str]:
    """May a document request be spent on this candidate? Decided before the request."""
    if document_size is None or document_size <= 0:
        return False, INELIGIBLE_SIZE_UNKNOWN
    if document_size >= CANARY_MAX_DOCUMENT_BYTES:
        return False, INELIGIBLE_TOO_LARGE
    return True, ELIGIBLE
