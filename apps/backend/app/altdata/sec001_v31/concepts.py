"""The positive identity-concept allowlist for the WP0A-Q cover-page parser.

**SIC-blindness here is structural, not an output filter.** The parser does not read every
Inline-XBRL concept and then discard the forbidden ones — a design in which SIC has already
been extracted and merely happens not to be written. It scans for *these four concept names
and no others*, and a value is materialised only after its concept name has matched the
allowlist. An unknown or forbidden concept therefore never becomes a retained semantic
value; there is no code path in which it could.

The four concepts map onto the frozen seven-field observation schema. ``form``,
``accession`` and ``accepted_at`` are registrant-filing metadata and come from the index
layer, never from the document.

``FORBIDDEN_CONCEPT_VOCABULARY`` exists **only so tests can prove non-extraction** and so a
reviewer can confirm by inspection that the parser never consults it. Nothing in
``cover_parser`` imports it. The disjointness assertion below fails at import time if anyone
ever widens the allowlist into it.
"""

from __future__ import annotations

from typing import Final

#: concept name -> frozen observation field. The ONLY concepts the parser will materialise.
COVER_IDENTITY_CONCEPTS: Final[dict[str, str]] = {
    "dei:EntityCentralIndexKey": "cik",
    "dei:TradingSymbol": "trading_symbol",
    "dei:Security12bTitle": "security_12b_title",
    "dei:SecurityExchangeName": "security_exchange_name",
}

#: The three concepts that together constitute one Section 12(b) security-class tuple.
#: ``cik`` is entity-level and is not part of the class tuple.
CLASS_TUPLE_FIELDS: Final[tuple[str, ...]] = (
    "trading_symbol",
    "security_12b_title",
    "security_exchange_name",
)

#: The frozen retained schema. An observation carrying any other key fails closed.
RETAINED_FIELD_SCHEMA: Final[tuple[str, ...]] = (
    "accepted_at",
    "cik",
    "trading_symbol",
    "security_12b_title",
    "security_exchange_name",
    "form",
    "accession",
)

#: Test-only vocabulary. NEVER imported by the parser — see the module docstring. Present so
#: that a fixture can embed these concepts and a test can assert that no value derived from
#: them appears in any emitted observation, artifact or log line.
FORBIDDEN_CONCEPT_VOCABULARY: Final[tuple[str, ...]] = (
    "dei:EntityStandardIndustrialClassificationCode",
    "dei:EntityStandardIndustrialClassification",
    "dei:EntitySicCode",
    "us-gaap:Revenues",
    "us-gaap:NetIncomeLoss",
    "us-gaap:EarningsPerShareBasic",
    "us-gaap:SharePrice",
    "us-gaap:StockholdersEquity",
    "dei:EntityPublicFloat",
)

# Fails at import if the allowlist is ever widened into forbidden territory.
assert not (set(COVER_IDENTITY_CONCEPTS) & set(FORBIDDEN_CONCEPT_VOCABULARY)), (
    "identity allowlist overlaps the forbidden concept vocabulary"
)
assert set(CLASS_TUPLE_FIELDS) <= set(COVER_IDENTITY_CONCEPTS.values())
assert set(COVER_IDENTITY_CONCEPTS.values()) <= set(RETAINED_FIELD_SCHEMA)
