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

    verified Envelope-B accession -> authorized index lookup -> exact accession match
        -> primaryDocument + authoritative size -> canonical archive_url()

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
import json
from dataclasses import dataclass
from typing import Any, Final

from app.altdata.sec001_v31.authority import (
    AcquisitionAuthority,
    NotAuthorized,
    require_safe_document_name,
)
from app.altdata.sec001_v31.custody import AccessionState, AcquisitionJournal
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
    """The per-accession filing index. It is the representation that carries sizes."""
    authority.require_authorized_accession(accession)
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/index.json"
    authority.require_origin(url)
    return url


def _select_primary(items: list[dict[str, Any]], form: str) -> dict[str, Any]:
    """The primary document is the item EDGAR types as the filing's own form."""
    matches = [i for i in items if str(i.get("type", "")).strip() == form]
    if not matches:
        raise LocatorResolutionError(RESOLVER_NO_PRIMARY_DOCUMENT, f"no index item typed {form!r}")
    if len(matches) > 1:
        names = sorted(str(i.get("name")) for i in matches)
        raise LocatorResolutionError(
            RESOLVER_AMBIGUOUS_PRIMARY_DOCUMENT, f"{len(matches)} items typed {form!r}: {names}"
        )
    return matches[0]


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
        doc = json.loads(outcome.body.decode("utf-8"))
        directory = doc.get("directory") or {}

        # The response must be the index of THIS accession, not merely a valid index.
        stated = str(directory.get("name", ""))
        if accession.replace("-", "") not in stated.replace("-", ""):
            raise self._determinate(
                accession,
                cik,
                form,
                AccessionState.LOCATOR_SCHEMA_UNSUPPORTED,
                RESOLVER_ACCESSION_MISMATCH,
                f"index directory {stated!r} is not {accession}",
                digest,
            )

        try:
            item = _select_primary(list(directory.get("item") or []), form)
        except LocatorResolutionError as exc:
            state = (
                AccessionState.LOCATOR_NO_PRIMARY_DOCUMENT
                if exc.reason == RESOLVER_NO_PRIMARY_DOCUMENT
                else AccessionState.LOCATOR_SCHEMA_UNSUPPORTED
            )
            raise self._determinate(
                accession, cik, form, state, exc.reason, str(exc), digest
            ) from exc

        raw_size: object = item.get("size")
        if raw_size is None or raw_size == "" or raw_size == 0:
            raise self._determinate(
                accession,
                cik,
                form,
                AccessionState.LOCATOR_SCHEMA_UNSUPPORTED,
                RESOLVER_SIZE_UNAVAILABLE,
                "the index gave no authoritative size for the primary document",
                digest,
            )
        if not isinstance(raw_size, (int, str)):
            raise self._determinate(
                accession,
                cik,
                form,
                AccessionState.LOCATOR_SCHEMA_UNSUPPORTED,
                RESOLVER_SIZE_UNAVAILABLE,
                f"unusable size type {type(raw_size).__name__}",
                digest,
            )
        try:
            size = int(raw_size)
        except (TypeError, ValueError) as exc:
            raise self._determinate(
                accession,
                cik,
                form,
                AccessionState.LOCATOR_SCHEMA_UNSUPPORTED,
                RESOLVER_SIZE_UNAVAILABLE,
                f"unparsable size {raw_size!r}",
                digest,
            ) from exc

        try:
            name = require_safe_document_name(str(item.get("name", "")))
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
        # The raw index body is not retained; only these facts and its digest.
        del doc, directory, outcome

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
