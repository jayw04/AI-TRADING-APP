"""Authenticated, journaled resolution of a filing's primary document and its size.

Review finding (P0): ``archive_url`` authenticated the CIK and accession and rejected unsafe
path syntax, but the **last path component still came from the caller**. A caller could pass
any safe basename and the resulting URL would be perfectly "canonical" — canonically built
from the wrong filename. Under CIK-once that is worse than a bad fetch: a wrong filename
returns 404, becomes ``EVIDENCE_UNAVAILABLE``, and permanently consumes a non-repeatable
accession. The selection record limits ``primaryDocument`` to a transport locator, which
does not authorize inventing it — a locator must still be *authentic as a locator*.

So the filename is resolved from SEC, for the exact authorized accession, immediately before
acquisition:

    verified Envelope-B accession -> authorized filing-detail lookup -> the page must
        reference that accession -> Document + authoritative Size from the document table
        -> canonical archive_url()

⭐ The representation is the **filing-detail ``…-index.html`` page**, established from a
governed fixture under WP0A-Q-LOCATOR-DISCOVERY. An earlier revision used the
accession-directory ``index.json`` and matched ``item.type == form``; that model was invented
by its own test fixture and was wrong in every particular. Parsing is delegated to
``filing_detail``, which slices the one in-scope table before reading anything, because the
same page carries SIC elsewhere.

**Only two new transport facts are taken.** ``form`` and ``accepted_at`` are already frozen
in the envelope; SEC is not asked to re-state what the owner has already sealed. Filename
content still carries zero security-identity meaning — no ticker is parsed out of it, and it
never reaches an observation.

**The lookup is itself exactly-once.** It has lifecycle states of its own
(``LOCATOR_INTENT`` -> ``LOCATOR_REQUEST_SENT`` -> ``LOCATOR_RESOLVED``) because it is a
counted request against a frozen budget: a crash after the index request but before the
result is persisted must be visible on restart, not silently repeated. Re-resolving an
accession already at ``LOCATOR_RESOLVED`` replays the stored result and issues no request.

**A determinate failure is not a crash.** An earlier revision recorded
``LOCATOR_REQUEST_SENT`` in a ``finally`` and raised on every failure, so a request that
*completed* and then failed to parse was indistinguishable from an interruption: the
accession was left looking mid-flight and became a HOLD. That is how schema discovery would
have stranded the very accession it was run on. A completed response now records
``LOCATOR_RESPONSE_RECEIVED`` with its status, length and digest, and a determinate parse
outcome lands in ``LOCATOR_SCHEMA_UNSUPPORTED`` / ``LOCATOR_NO_PRIMARY_DOCUMENT`` — resumable
states that keep the accession unspent. Only a genuine interruption, where no response
outcome was durably recorded, may remain ``LOCATOR_REQUEST_SENT``. A determinate verdict is
replayed on a later call rather than re-requested, so it also stays exactly-once.

**Size is authoritative or the resolution fails.** The canary rule needs the document's real
size *before* any document request, and the per-accession filing index is the representation
that carries it. If a chosen representation cannot supply both an authoritative filename and
an authoritative size, this module fails closed and says so rather than quietly reaching for
another endpoint to make a screen pass.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

from app.altdata.sec001_v31.authority import (
    AcquisitionAuthority,
    NotAuthorized,
    require_safe_document_name,
)
from app.altdata.sec001_v31.custody import AccessionState, AcquisitionJournal
from app.altdata.sec001_v31.filing_detail import (
    NO_PRIMARY_ROW,
    SEQ1_TYPE_MISMATCH,
    FilingDetailError,
    parse_primary_document,
)
from app.altdata.sec001_v31.layers import TransportLocator
from app.altdata.sec001_v31.transport import FETCH_OK, BoundedFetcher

RESOLVED: Final = "LOCATOR_RESOLVED"
RESOLVER_SCHEMA_UNSUPPORTED: Final = "RESOLVER_SCHEMA_UNSUPPORTED"
RESOLVER_INDEX_UNAVAILABLE: Final = "RESOLVER_INDEX_UNAVAILABLE"
RESOLVER_ACCESSION_MISMATCH: Final = "RESOLVER_ACCESSION_MISMATCH"
RESOLVER_NO_PRIMARY_DOCUMENT: Final = "RESOLVER_NO_PRIMARY_DOCUMENT"
RESOLVER_AMBIGUOUS_PRIMARY_DOCUMENT: Final = "RESOLVER_AMBIGUOUS_PRIMARY_DOCUMENT"
RESOLVER_SIZE_UNAVAILABLE: Final = "RESOLVER_SIZE_UNAVAILABLE"
RESOLVER_UNSAFE_DOCUMENT_NAME: Final = "RESOLVER_UNSAFE_DOCUMENT_NAME"


class LocatorResolutionError(RuntimeError):
    """The locator could not be authenticated. No document request may follow."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass(frozen=True)
class ResolvedLocator:
    """An authenticated locator plus the facts the canary screen needs."""

    cik: int
    accession: str
    form: str
    accepted_at: str
    primary_document: str
    document_size: int
    url: str
    index_body_sha256: str

    def transport_locator(self) -> TransportLocator:
        return TransportLocator(
            cik=self.cik,
            accession=self.accession,
            primary_document=self.primary_document,
            url=self.url,
        )


def index_url(authority: AcquisitionAuthority, cik: int, accession: str) -> str:
    """The filing-detail page for an AUTHORIZED accession.

    ⛔ Not the accession-directory ``index.json``: that is a directory listing and carries no
    filing-form ``Type`` column.
    """
    authority.require_authorized_accession(accession)
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/"
        f"{accession.replace('-', '')}/{accession}-index.html"
    )
    authority.require_origin(url)
    return url


_DETERMINATE_FAILURES: Final = frozenset(
    {
        AccessionState.LOCATOR_SCHEMA_UNSUPPORTED,
        AccessionState.LOCATOR_NO_PRIMARY_DOCUMENT,
    }
)


class LocatorResolver:
    """Resolve and authenticate one authorized accession's primary document."""

    def __init__(
        self,
        authority: AcquisitionAuthority,
        fetcher: BoundedFetcher,
        journal: AcquisitionJournal,
    ) -> None:
        self.authority = authority
        self.fetcher = fetcher
        self.journal = journal

    def _determinate(
        self,
        accession: str,
        cik: int,
        form: str,
        state: AccessionState,
        reason: str,
        detail: str,
        digest: str,
    ) -> LocatorResolutionError:
        """Record a determinate outcome and return the error to raise.

        The accession lands in a resumable state carrying the reason and the response
        digest, so it is neither stranded nor silently retried.
        """
        self.journal.transition(
            accession, cik, form, state, reason=reason, detail=detail, index_body_sha256=digest
        )
        return LocatorResolutionError(reason, detail)

    def resolve(self, cik: int, accession: str) -> ResolvedLocator:
        a = self.authority
        key = a.require_authorized_accession(accession)
        if key[0] != cik:
            raise NotAuthorized(
                f"accession {accession} is authorized under CIK {key[0]}, not {cik}"
            )
        _cik, form, _acc, accepted_at = key

        # Replay a determinate verdict rather than spending another index request.
        rec = self.journal.get(accession)
        if rec is not None and rec.state in _DETERMINATE_FAILURES:
            raise LocatorResolutionError(
                str(rec.detail.get("reason", RESOLVER_SCHEMA_UNSUPPORTED)),
                f"replayed determinate outcome {rec.state.value} "
                f"(response sha256 {rec.detail.get('index_body_sha256')}); no new request issued",
            )
        if rec is not None and rec.state is AccessionState.LOCATOR_RESOLVED:
            d = rec.detail
            return ResolvedLocator(
                cik=cik,
                accession=accession,
                form=form,
                accepted_at=accepted_at,
                primary_document=d["primary_document"],
                document_size=int(d["document_size"]),
                url=d["locator_url"],
                index_body_sha256=d["index_body_sha256"],
            )
        self.journal.guard_fresh(accession)

        url = index_url(a, cik, accession)
        self.journal.transition(accession, cik, form, AccessionState.LOCATOR_INTENT, index_url=url)
        # LOCATOR_REQUEST_SENT means exactly "in flight, no outcome recorded". It is set
        # before the call and superseded the moment an outcome is known.
        self.journal.transition(accession, cik, form, AccessionState.LOCATOR_REQUEST_SENT)
        outcome = self.fetcher.get_index(url)

        digest = hashlib.sha256(outcome.body).hexdigest()
        self.journal.transition(
            accession,
            cik,
            form,
            AccessionState.LOCATOR_RESPONSE_RECEIVED,
            http_status=outcome.http_status,
            response_bytes=outcome.bytes_consumed,
            index_body_sha256=digest,
        )

        if outcome.status != FETCH_OK:
            raise self._determinate(
                accession,
                cik,
                form,
                AccessionState.LOCATOR_SCHEMA_UNSUPPORTED,
                RESOLVER_INDEX_UNAVAILABLE,
                f"http {outcome.http_status} ({outcome.reason})",
                digest,
            )
        # The response must belong to THIS accession, not merely be a valid page.
        if (
            accession.encode() not in outcome.body
            and accession.replace("-", "").encode() not in outcome.body
        ):
            raise self._determinate(
                accession,
                cik,
                form,
                AccessionState.LOCATOR_SCHEMA_UNSUPPORTED,
                RESOLVER_ACCESSION_MISMATCH,
                f"page does not reference {accession}",
                digest,
            )

        # Parsing is delegated to `filing_detail`, which slices the one in-scope table
        # before reading anything. Size comes from that table's Size column, so it is the
        # same authoritative figure -- there is no separate size lookup to get wrong.
        try:
            primary = parse_primary_document(outcome.body, form)
        except FilingDetailError as exc:
            # A sequence-1 row of the wrong type is still "no primary document of the
            # sealed form" -- determinate, and explicitly not a reason to try sequence 2.
            no_row = exc.reason in (NO_PRIMARY_ROW, SEQ1_TYPE_MISMATCH)
            raise self._determinate(
                accession,
                cik,
                form,
                AccessionState.LOCATOR_NO_PRIMARY_DOCUMENT
                if no_row
                else AccessionState.LOCATOR_SCHEMA_UNSUPPORTED,
                RESOLVER_NO_PRIMARY_DOCUMENT if no_row else RESOLVER_SCHEMA_UNSUPPORTED,
                str(exc),
                digest,
            ) from exc

        size = primary.size
        try:
            name = require_safe_document_name(primary.document)
        except NotAuthorized as exc:
            raise self._determinate(
                accession,
                cik,
                form,
                AccessionState.LOCATOR_SCHEMA_UNSUPPORTED,
                RESOLVER_UNSAFE_DOCUMENT_NAME,
                str(exc),
                digest,
            ) from exc

        locator_url = a.archive_url(cik, accession, name)
        # The raw page is not retained; only these facts and its digest.
        del outcome

        self.journal.transition(
            accession,
            cik,
            form,
            AccessionState.LOCATOR_RESOLVED,
            primary_document=name,
            document_size=size,
            locator_url=locator_url,
            index_body_sha256=digest,
        )
        return ResolvedLocator(
            cik=cik,
            accession=accession,
            form=form,
            accepted_at=accepted_at,
            primary_document=name,
            document_size=size,
            url=locator_url,
            index_body_sha256=digest,
        )


def replay_from_journal(
    authority: AcquisitionAuthority,
    journal: AcquisitionJournal,
    cik: int,
    accession: str,
    journal_key: str | None = None,
) -> ResolvedLocator:
    """Reconstruct an already-resolved locator from retained journal detail. NO request.

    ``resolve()`` replays only while the record still *reads* ``LOCATOR_RESOLVED``, and a
    document attempt on the same accession moves that state onward -- attempt #1 left the
    record at ``REQUEST_SENT``, so its perfectly valid locator became unreplayable even
    though every fact was still retained. The locator's evidence predates the document
    attempt and remains valid; only the state cursor moved.

    Fails closed if any retained fact is missing, and re-verifies that the retained URL is
    still the canonical derivation, so stale or tampered detail cannot be replayed into a
    request.
    """
    key = authority.require_authorized_accession(accession)
    if key[0] != cik:
        raise NotAuthorized(f"accession {accession} is authorized under CIK {key[0]}, not {cik}")
    _cik, form, _acc, accepted_at = key

    rec = journal.get(journal_key or accession)
    if rec is None:
        raise LocatorResolutionError(
            RESOLVER_SCHEMA_UNSUPPORTED, f"no journal record for {accession}"
        )
    d = rec.detail
    required = ("primary_document", "document_size", "locator_url", "index_body_sha256")
    missing = [k for k in required if not d.get(k)]
    if missing:
        raise LocatorResolutionError(
            RESOLVER_SCHEMA_UNSUPPORTED,
            f"retained locator detail is incomplete: missing {missing}",
        )

    authority.require_canonical_url(
        cik, accession, str(d["primary_document"]), str(d["locator_url"])
    )
    return ResolvedLocator(
        cik=cik,
        accession=accession,
        form=form,
        accepted_at=accepted_at,
        primary_document=str(d["primary_document"]),
        document_size=int(d["document_size"]),
        url=str(d["locator_url"]),
        index_body_sha256=str(d["index_body_sha256"]),
    )
