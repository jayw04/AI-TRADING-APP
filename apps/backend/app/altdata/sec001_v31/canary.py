"""The frozen one-accession canary rule: which accession, and whether it may be spent.

Two owner rulings live here, and both exist to stop a non-repeatable accession being spent
on a foregone conclusion.

**Do not spend a scarce left-bracket accession.** The 19 pre-window filings in Envelope B are
the only evidence that reaches the 2021-02-08 edge — three CIKs have none at all — so they
are not transport test material. Envelope B remains the sole acquisition authority; Envelope
A is *not* an authority here, it only supplies the exclusion list. Note that the first entry
of B's own array **is** one of the 19, so an unfiltered "first entry" rule would have picked
the scarcest possible candidate.

**Screen on size before spending a document request.** EOF-only admission,
``LIVE_MAX_CONTINUATIONS = 0`` and a 983,040-byte stop threshold together mean a document at
or above that size can never reach EOF, so it is predetermined to return
``EVIDENCE_UNAVAILABLE``. Discovering that by spending the request would consume the
accession to learn something the transport bound already implied. Equality is excluded too:
at exactly the threshold the bounded reader fills its window and reports truncation.

A candidate that fails the screen is **not** consumed. It has spent an index request and
holds a resolved locator, and it stays available for a future authority that permits
continuation.

The ordering rule is frozen here rather than chosen later: **Envelope B's own key order,
with the 19 bracket accessions removed, first retained entry**. No tuple re-sorting, no
selection informed by anything observed afterwards.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from app.altdata.sec001_v31.authority import AcquisitionAuthority

#: Strict. A document at or above the stop threshold cannot reach EOF under the frozen
#: transport bound, so it is ineligible before any request is made.
CANARY_MAX_DOCUMENT_BYTES: Final = 983_040

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


def _envelope(repo_root: Path) -> dict[str, Any]:
    from app.altdata.sec001_v31.authority import ENVELOPE_PATH

    return json.loads((repo_root / ENVELOPE_PATH).read_text(encoding="utf-8"))


def bracket_accessions(repo_root: Path) -> frozenset[str]:
    """The exact 19 pre-window boundary accessions, from the sealed selection record."""
    from app.altdata.sec001_v31.authority import SELECTION_PATH

    sel = json.loads((repo_root / SELECTION_PATH).read_text(encoding="utf-8"))
    rows = sel["pre_window_boundary_accessions"]
    return frozenset(r["accession"] for r in rows)


def candidate_order(authority: AcquisitionAuthority, repo_root: Path) -> list[CanaryCandidate]:
    """Envelope B's own key order, minus the 19 brackets. Frozen before any lookup."""
    env = _envelope(repo_root)
    if env["manifest_sha256"] != authority.manifest_sha256:
        raise RuntimeError("envelope does not descend from the loaded authority's manifest")
    excluded = bracket_accessions(repo_root)

    out: list[CanaryCandidate] = []
    for i, r in enumerate(env["acquisition_keys_envelope_B"]):
        if r["accession"] in excluded:
            continue
        authority.require_authorized(r["cik"], r["form"], r["accession"], r["accepted_at"])
        out.append(
            CanaryCandidate(
                position=i,
                cik=int(r["cik"]),
                form=r["form"],
                accession=r["accession"],
                accepted_at=r["accepted_at"],
            )
        )
    return out


def first_candidate(authority: AcquisitionAuthority, repo_root: Path) -> CanaryCandidate:
    order = candidate_order(authority, repo_root)
    if not order:
        raise RuntimeError("no non-bracket candidate exists in Envelope B")
    return order[0]


def screen(document_size: int | None) -> tuple[bool, str]:
    """May a document request be spent on this candidate? Decided before the request."""
    if document_size is None or document_size <= 0:
        return False, INELIGIBLE_SIZE_UNKNOWN
    if document_size >= CANARY_MAX_DOCUMENT_BYTES:
        return False, INELIGIBLE_TOO_LARGE
    return True, ELIGIBLE
