"""WP0A-Q cover-page acquisition: authority-bound, crash-safe, exactly-once.

Every refusal decidable from governed state is decided **before a byte is requested**: the
filing must be exactly one of the authorized ``(cik, form, accession, accepted_at)`` tuples
in the selected envelope, its form must be permitted, and its acceptance must be at or
before the frozen cutoff. All three come out of hash-verified artifacts, not from caller
arguments.

**Transaction ordering.** Intent is journalled *before* the request rather than success
after it, so neither crash window can produce a wrong answer: a failure before the response
leaves ``REQUEST_INTENT``/``REQUEST_SENT`` (an interrupted acquisition, adjudicated, never
silently retried against a frozen cap), and a failure before custody leaves ``PARSED`` — not
"acquired and complete". The accession reaches ``SEALED`` only after its evidence has been
atomically published *and* re-read and digest-verified.

**Continuation is not a live knob.** ``LIVE_MAX_CONTINUATIONS`` is the frozen setting and is
read directly; the orchestrator takes no override. Mock transport tests exercise nonzero
continuation against ``BoundedFetcher`` directly, which is where that machinery belongs
until the owner freezes a nonzero policy prospectively.

The locator's *filename* still cannot reach identity, but its *filing identity* is now fully
authenticated: the URL must be byte-identical to the authority's canonical derivation for
this CIK, accession and document basename.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Final

from app.altdata.sec001_v31 import cover_parser
from app.altdata.sec001_v31.authority import (
    LIVE_MAX_CONTINUATIONS,
    AcquisitionAuthority,
    NotAuthorized,
)
from app.altdata.sec001_v31.clock import accepted_at_utc
from app.altdata.sec001_v31.custody import (
    INTERRUPTED_STATES,
    RESUMABLE_STATES,
    AccessionState,
    AcquisitionJournal,
    TransactionalEvidenceStore,
)
from app.altdata.sec001_v31.layers import (
    FilingMetadata,
    LocatorMismatch,
    Observation,
    TransportLocator,
)
from app.altdata.sec001_v31.transport import FETCH_OK, BoundedFetcher, DurableLedger

REFUSED_FORM: Final = "REFUSED_NON_PERMITTED_FORM"
REFUSED_CUTOFF: Final = "REFUSED_ACCEPTED_AFTER_CUTOFF"
REFUSED_NOT_IN_ENVELOPE: Final = "REFUSED_NOT_IN_AUTHORIZED_ENVELOPE"
REFUSED_SEALED: Final = "REFUSED_ALREADY_SEALED"
REFUSED_EVIDENCE_UNAVAILABLE: Final = "REFUSED_TERMINAL_EVIDENCE_UNAVAILABLE"
#: The journal has no record of an accession the legacy ledger calls acquired. The two
#: stores disagree about whether a request was ever made, so neither answer may be acted
#: on: this is a HOLD, never an ordinary duplicate refusal.
INCONSISTENT_CUSTODY_STATE: Final = "INCONSISTENT_CUSTODY_STATE"
ACQUIRED: Final = "ACQUIRED"

#: The registrant CIK the cover page declares disagrees with the CIK on the index record.
#: A FILING/OBSERVATION identity conflict, deliberately NOT the competing-binding conjunct:
#: an index CIK is acquisition metadata and is not itself an admissible security->CIK
#: binding. The genuine conjunct lives in ``bindings.py``.
INDEX_COVER_CIK_MISMATCH: Final = "INDEX_COVER_CIK_MISMATCH"

__all__ = [
    "ACQUIRED",
    "INCONSISTENT_CUSTODY_STATE",
    "INDEX_COVER_CIK_MISMATCH",
    "REFUSED_CUTOFF",
    "REFUSED_EVIDENCE_UNAVAILABLE",
    "REFUSED_FORM",
    "REFUSED_NOT_IN_ENVELOPE",
    "REFUSED_SEALED",
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
    accession_state: str | None = None


def refusal_reasons() -> tuple[str, ...]:
    """Every pre-network refusal, for documentation and adjudication."""
    return (
        REFUSED_FORM,
        REFUSED_CUTOFF,
        REFUSED_NOT_IN_ENVELOPE,
        REFUSED_SEALED,
        REFUSED_EVIDENCE_UNAVAILABLE,
        INCONSISTENT_CUSTODY_STATE,
    )


class CoverAcquisition:
    """Acquire cover-page identity evidence for authorized filings only."""

    #: Frozen, not configurable. The live-authorized continuation policy is zero.
    max_continuations: Final = LIVE_MAX_CONTINUATIONS

    def __init__(
        self,
        authority: AcquisitionAuthority,
        fetcher: BoundedFetcher,
        store: TransactionalEvidenceStore,
        ledger: DurableLedger,
        journal: AcquisitionJournal,
    ) -> None:
        self.authority = authority
        self.fetcher = fetcher
        self.store = store
        self.ledger = ledger
        self.journal = journal

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

        # ---- custody reconciliation: the JOURNAL is authoritative ---------------------
        # Review finding (P0): this previously consulted the legacy acquired-set first, so a
        # crash between mark_acquired() and sealing came back as REFUSED_DUPLICATE and never
        # reached guard_fresh() -- an interrupted acquisition silently reported as an
        # ordinary duplicate. Journal state is now decided first, and the ledger is only a
        # cross-check.
        state = self.journal.state_of(meta.accession)
        ledger_says_acquired = self.ledger.already_acquired(meta.cik, meta.form, meta.accession)

        if state is AccessionState.SEALED:
            rec = self.journal.get(meta.accession)
            digest = rec.artifact_sha256 if rec else None
            verified = bool(digest) and self.store.verify(
                meta.cik, meta.accession, a.source_variant, str(digest)
            )
            if not verified:
                # Sealed, but the artifact is gone or altered: the invariant is broken and
                # this is an adjudication, not a refetch.
                return AcquisitionResult(
                    INCONSISTENT_CUSTODY_STATE,
                    diagnostics={
                        "accession": meta.accession,
                        "reason": "sealed_but_artifact_missing_or_corrupt",
                        "artifact_sha256": digest,
                    },
                    accession_state=state.value,
                )
            return AcquisitionResult(
                REFUSED_SEALED,
                diagnostics={"accession": meta.accession, "artifact_sha256": digest},
                accession_state=state.value,
            )

        if state is AccessionState.EVIDENCE_UNAVAILABLE:
            return AcquisitionResult(
                REFUSED_EVIDENCE_UNAVAILABLE,
                diagnostics={"accession": meta.accession},
                accession_state=state.value,
            )

        if state in INTERRUPTED_STATES:
            # Raises rather than returns: a mid-flight accession is not a status a fail-soft
            # caller may absorb.
            self.journal.guard_fresh(meta.accession)

        if state in RESUMABLE_STATES and ledger_says_acquired:
            return AcquisitionResult(
                INCONSISTENT_CUSTODY_STATE,
                diagnostics={
                    "accession": meta.accession,
                    "reason": "ledger_reports_acquired_but_journal_is_not_terminal",
                    "journal_state": state.value,
                },
                accession_state=state.value,
            )

        # The bytes must belong to the filing they will be recorded as, by every component.
        locator.assert_matches(meta)
        a.require_canonical_url(meta.cik, meta.accession, locator.primary_document, locator.url)

        # ---- intent is durable BEFORE the request ------------------------------------
        self.journal.transition(
            meta.accession, meta.cik, meta.form, AccessionState.REQUEST_INTENT, url=locator.url
        )
        before = self.ledger.document_requests
        try:
            outcome = self.fetcher.get_document_complete(
                locator.url, max_continuations=self.max_continuations
            )
        finally:
            spent = self.ledger.document_requests - before
            self.journal.transition(
                meta.accession,
                meta.cik,
                meta.form,
                AccessionState.REQUEST_SENT,
                document_requests_spent=spent,
            )
        self.ledger.mark_acquired(meta.cik, meta.form, meta.accession)

        if outcome.status != FETCH_OK:
            self.journal.transition(
                meta.accession,
                meta.cik,
                meta.form,
                AccessionState.EVIDENCE_UNAVAILABLE,
                reason=outcome.reason,
            )
            return AcquisitionResult(
                ACQUIRED,
                parse_status=cover_parser.STATUS_EVIDENCE_UNAVAILABLE,
                diagnostics={"http_status": outcome.http_status, "reason": outcome.reason},
                document_requests_spent=spent,
                accession_state=AccessionState.EVIDENCE_UNAVAILABLE.value,
            )

        self.journal.transition(
            meta.accession, meta.cik, meta.form, AccessionState.RESPONSE_RETAINED
        )

        # The parser receives bytes only. The locator is not in scope here.
        parsed = cover_parser.parse_cover_identity(
            outcome.body,
            eof_reached=outcome.eof_reached,
            truncated=outcome.truncated,
            bytes_consumed=outcome.bytes_consumed,
        )
        self.journal.transition(
            meta.accession, meta.cik, meta.form, AccessionState.PARSED, parse_status=parsed.status
        )

        result = AcquisitionResult(
            ACQUIRED,
            parse_status=parsed.status,
            diagnostics=dict(parsed.diagnostics),
            document_requests_spent=spent,
            accession_state=AccessionState.PARSED.value,
        )

        if not parsed.is_bound:
            self.journal.transition(
                meta.accession,
                meta.cik,
                meta.form,
                AccessionState.EVIDENCE_UNAVAILABLE,
                parse_status=parsed.status,
            )
            result.accession_state = AccessionState.EVIDENCE_UNAVAILABLE.value
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
            self.journal.transition(
                meta.accession,
                meta.cik,
                meta.form,
                AccessionState.EVIDENCE_UNAVAILABLE,
                reason=INDEX_COVER_CIK_MISMATCH,
            )
            result.accession_state = AccessionState.EVIDENCE_UNAVAILABLE.value
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
        # Atomic publication, then verification, and only then SEALED.
        _path, digest = self.store.publish_accession_set(
            meta.cik,
            meta.accession,
            a.source_variant,
            [o.to_record() for o in observations],
            obs_ids,
            provenance,
        )
        self.journal.seal(meta.accession, digest)

        result.observations = observations
        result.artifact_identities = [
            TransactionalEvidenceStore.identity(meta.cik, meta.accession, a.source_variant, oid)
            for oid in obs_ids
        ]
        result.accession_state = AccessionState.SEALED.value
        return result
