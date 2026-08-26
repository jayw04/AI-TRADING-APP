"""WP0A-Q cover-page acquisition orchestration.

Every refusal that can be decided from metadata is decided **before a byte is requested**.
A non-permitted form and a post-cutoff acceptance timestamp are properties of the index
record, so spending a document request to discover them would be both wasteful and a
scope leak — the frozen form set and the frozen cutoff are the authority, and this module
enforces them at the door.

The transport locator is used for exactly one thing: building the request URL. It is not
passed to the parser, and no field of it can reach an observation — see ``layers``.

One accession may legitimately support several observations when the document itself
declares several security classes. That is one acquisition and several observations, never
several acquisitions: ``CIK-once`` is about *fetching*, and the class tuples are read out of
the single retained artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Final

from app.altdata.sec001_v31 import cover_parser
from app.altdata.sec001_v31.layers import (
    FilingMetadata,
    Observation,
    SecurityClassEvidence,
    TransportLocator,
)
from app.altdata.sec001_v31.transport import FETCH_OK, BoundedFetcher, CreateOnceStore

ET: Final = timezone(timedelta(hours=-4))

REFUSED_FORM: Final = "REFUSED_NON_PERMITTED_FORM"
REFUSED_CUTOFF: Final = "REFUSED_ACCEPTED_AFTER_CUTOFF"
REFUSED_DUPLICATE: Final = "REFUSED_ALREADY_ACQUIRED"
ACQUIRED: Final = "ACQUIRED"

#: The registrant CIK the cover page declares disagrees with the CIK on the index record.
#: This is a FILING/OBSERVATION identity conflict, deliberately NOT the competing-binding
#: conjunct: an index CIK is acquisition metadata and is not itself an admissible
#: security->CIK binding, so calling it a competing binding would let filing metadata
#: masquerade as identity evidence. The observation is inadmissible, this filing proves no
#: candidate binding, and affected cells stay DISPUTED unless other admissible evidence
#: resolves them. The genuine NO_COMPETING_SECURITY_CIK_BINDING conjunct -- two admissible
#: bindings overlapping for one security -- is evaluated in ``bindings.py``.
INDEX_COVER_CIK_MISMATCH: Final = "INDEX_COVER_CIK_MISMATCH"


def accepted_at_utc(stamp: str) -> datetime:
    """EDGAR stamps acceptance with a ``Z`` suffix on an Eastern clock. Read it as Eastern.

    Conservative by construction: it can only move a timestamp *later*, so it can only
    exclude filings from an at-or-before-cutoff test, never admit one.
    """
    return (
        datetime.fromisoformat(stamp.replace("Z", "").replace("z", "").strip())
        .replace(tzinfo=ET)
        .astimezone(UTC)
    )


@dataclass
class AcquisitionPolicy:
    permitted_forms: frozenset[str]
    cutoff_utc: datetime
    source_variant: str = "PRIMARY_DOCUMENT_COVER"


@dataclass
class AcquisitionResult:
    status: str
    parse_status: str | None = None
    observations: list[Observation] = field(default_factory=list)
    artifact_identities: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    document_requests_spent: int = 0


class CoverAcquisition:
    def __init__(
        self, policy: AcquisitionPolicy, fetcher: BoundedFetcher, store: CreateOnceStore
    ) -> None:
        self.policy = policy
        self.fetcher = fetcher
        self.store = store
        self._acquired: set[tuple[int, str, str]] = set()

    def acquire(self, meta: FilingMetadata, locator: TransportLocator) -> AcquisitionResult:
        # ---- preflight: decided from metadata, before any request --------------------
        if meta.form not in self.policy.permitted_forms:
            return AcquisitionResult(REFUSED_FORM, diagnostics={"form": meta.form})

        if accepted_at_utc(meta.accepted_at) > self.policy.cutoff_utc:
            return AcquisitionResult(REFUSED_CUTOFF, diagnostics={"accepted_at": meta.accepted_at})

        key = (meta.cik, meta.form, meta.accession)
        if key in self._acquired:
            return AcquisitionResult(REFUSED_DUPLICATE, diagnostics={"key": list(map(str, key))})

        # ---- acquisition -------------------------------------------------------------
        before = self.fetcher.ledger.document_requests
        outcome = self.fetcher.get_document(locator.url)
        spent = self.fetcher.ledger.document_requests - before
        self._acquired.add(key)

        if outcome.status != FETCH_OK:
            return AcquisitionResult(
                ACQUIRED,
                parse_status=cover_parser.STATUS_EVIDENCE_UNAVAILABLE,
                diagnostics={"http_status": outcome.http_status, "fetch": outcome.status},
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

        # A registrant's own declared CIK must agree with the index record. Never reconcile
        # toward either value. Classified as a filing-identity conflict, not a competing
        # security binding -- see INDEX_COVER_CIK_MISMATCH above.
        if parsed.cik != meta.cik:
            result.parse_status = INDEX_COVER_CIK_MISMATCH
            result.diagnostics["reason"] = "cover_cik_disagrees_with_index"
            result.diagnostics["index_cik"] = meta.cik
            result.diagnostics["cover_cik"] = parsed.cik
            result.diagnostics["consequence"] = (
                "observation inadmissible; candidate binding not proven by this observation; "
                "affected cells remain DISPUTED unless other admissible evidence resolves them"
            )
            return result

        for ev in parsed.class_tuples:
            obs = Observation.build(meta, ev)
            ident = CreateOnceStore.identity(
                meta.cik,
                meta.accession,
                self.policy.source_variant,
                obs.observation_id(self.policy.source_variant),
            )
            self.store.put(ident, obs.to_record())
            result.observations.append(obs)
            result.artifact_identities.append(ident)
        return result


def evidence_only(ev: SecurityClassEvidence) -> tuple[str, str, str]:
    """The class tuple, for tests and adjudication. Ticker alone is never sufficient."""
    return (ev.trading_symbol, ev.security_12b_title, ev.security_exchange_name)
