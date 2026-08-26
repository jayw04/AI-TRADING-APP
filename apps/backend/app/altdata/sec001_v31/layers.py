"""The three layers WP0A-Q must keep apart, and the fail-closed observation record.

The V3.1 design exists because a convenience shortcut destroyed V3: registrant continuity
was allowed to stand in for a security->registrant relationship. The same shortcut has a
transport-shaped sibling — reading a ticker out of a document *filename* and letting it
decide which security a filing belongs to. Both are prevented here by construction rather
than by review vigilance:

``TransportLocator``
    Where bytes come from: primary-document filename, URL, range and retry state. EDGAR
    filenames routinely embed a ticker (``goog-20250630.htm``). That substring is **not
    evidence of anything** and must never reach an observation.

``FilingMetadata``
    Which registrant filed what, and when: CIK, form, accession, accepted timestamp. Comes
    from the index layer. Establishes registrant filing existence — *necessary, never
    sufficient*.

``SecurityClassEvidence``
    What the registrant itself declared on the cover page: trading symbol, Section 12(b)
    security title, exchange, and the Inline-XBRL context that binds them into one class.

The separation is enforced, not merely documented. ``Observation.build`` accepts a
``FilingMetadata`` and a ``SecurityClassEvidence`` and has no parameter of type
``TransportLocator``; ``SecurityClassEvidence`` carries a ``source`` that only the parser
sets, and ``build`` rejects any other provenance. There is consequently no expression that
promotes a locator into an observation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Final

from app.altdata.sec001_v31.concepts import RETAINED_FIELD_SCHEMA

#: The only provenance ``Observation.build`` accepts. Set by the cover parser alone.
PARSED_FROM_COVER: Final = "INLINE_XBRL_COVER"


class IdentityScopeViolation(RuntimeError):
    """An observation tried to carry a field outside the frozen seven-field schema."""


class ProvenanceViolation(RuntimeError):
    """Security-class evidence reached an observation without cover-page provenance."""


@dataclass(frozen=True)
class TransportLocator:
    """Where to fetch bytes from. **Never** an identity source.

    ``primary_document`` is retained here and nowhere else, deliberately: it is needed to
    build the request URL and is useless — indeed forbidden — for anything past that.
    """

    cik: int
    accession: str
    primary_document: str
    url: str

    def __repr__(self) -> str:
        # The filename is symbol-bearing. Keep it out of logs and tracebacks.
        return (
            f"TransportLocator(cik={self.cik}, accession={self.accession!r}, document=<redacted>)"
        )


@dataclass(frozen=True)
class FilingMetadata:
    """Registrant filing metadata from the index layer. Necessary, never sufficient."""

    cik: int
    form: str
    accession: str
    accepted_at: str


@dataclass(frozen=True)
class SecurityClassEvidence:
    """One Section 12(b) security-class tuple as the registrant declared it.

    ``context_ref`` is the Inline-XBRL context the three facts shared. It is what makes a
    multi-class issuer resolvable: two classes of one registrant appear under two contexts,
    so each security identity matches its *own* declared class rather than inheriting a
    CIK-wide ticker assignment.
    """

    trading_symbol: str
    security_12b_title: str
    security_exchange_name: str
    context_ref: str
    source: str = PARSED_FROM_COVER


@dataclass(frozen=True)
class Observation:
    """One retained cover-page observation. Exactly the seven frozen fields."""

    accepted_at: str
    cik: int
    trading_symbol: str
    security_12b_title: str
    security_exchange_name: str
    form: str
    accession: str
    context_ref: str = field(default="", compare=False, repr=False)

    @classmethod
    def build(cls, meta: FilingMetadata, ev: SecurityClassEvidence) -> Observation:
        if ev.source != PARSED_FROM_COVER:
            raise ProvenanceViolation(
                f"security-class evidence has provenance {ev.source!r}, not {PARSED_FROM_COVER!r}; "
                "only the cover parser may originate identity evidence"
            )
        if not (ev.trading_symbol and ev.security_12b_title and ev.security_exchange_name):
            raise IdentityScopeViolation(
                "incomplete class tuple may not become an observation; it is DISPUTED"
            )
        return cls(
            accepted_at=meta.accepted_at,
            cik=meta.cik,
            trading_symbol=ev.trading_symbol,
            security_12b_title=ev.security_12b_title,
            security_exchange_name=ev.security_exchange_name,
            form=meta.form,
            accession=meta.accession,
            context_ref=ev.context_ref,
        )

    def observation_id(self, source_variant: str) -> str:
        """Immutable identity: CIK / accession / source_variant / class context."""
        key = f"{self.cik}|{self.accession}|{source_variant}|{self.context_ref}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]

    def to_record(self) -> dict[str, Any]:
        """Serialise, failing closed on any field outside the frozen schema."""
        rec = {
            "accepted_at": self.accepted_at,
            "cik": self.cik,
            "trading_symbol": self.trading_symbol,
            "security_12b_title": self.security_12b_title,
            "security_exchange_name": self.security_exchange_name,
            "form": self.form,
            "accession": self.accession,
        }
        extra = set(rec) - set(RETAINED_FIELD_SCHEMA)
        missing = set(RETAINED_FIELD_SCHEMA) - set(rec)
        if extra or missing:
            raise IdentityScopeViolation(
                f"observation schema violation: extra={sorted(extra)} missing={sorted(missing)}"
            )
        return rec
