"""Inline-XBRL cover-page fixture builder for the WP0A-Q harness tests.

Fixtures deliberately embed forbidden concepts (SIC, revenue, share price, public float) so
that non-extraction can be *proved* rather than assumed. A test that only ever feeds the
parser clean documents proves nothing about SIC-blindness.
"""

from __future__ import annotations

from app.altdata.sec001_v31.concepts import FORBIDDEN_CONCEPT_VOCABULARY

#: Values placed on forbidden concepts. If any of these strings ever appears in an emitted
#: observation, artifact or diagnostic, extraction happened.
FORBIDDEN_VALUES = {
    "dei:EntityStandardIndustrialClassificationCode": "7370",
    "dei:EntityStandardIndustrialClassification": "Services-Computer Programming",
    "dei:EntitySicCode": "7372",
    "us-gaap:Revenues": "307394000000",
    "us-gaap:NetIncomeLoss": "73795000000",
    "us-gaap:EarningsPerShareBasic": "5.84",
    "us-gaap:SharePrice": "182.41",
    "us-gaap:StockholdersEquity": "283379000000",
    "dei:EntityPublicFloat": "1234567890",
}


def fact(concept: str, value: str, context: str) -> str:
    tag = (
        "nonFraction" if value.replace(".", "").isdigit() and "us-gaap" in concept else "nonNumeric"
    )
    return f'<ix:{tag} name="{concept}" contextRef="{context}">{value}</ix:{tag}>'


def forbidden_block(context: str = "c-entity") -> str:
    """Every forbidden concept, tagged as a real filing would tag it."""
    return "\n".join(
        fact(c, FORBIDDEN_VALUES.get(c, "999"), context) for c in FORBIDDEN_CONCEPT_VOCABULARY
    )


def cover_doc(
    *,
    cik: str | None = "0001652044",
    classes: list[tuple[str, str, str, str]] | None = None,
    include_forbidden: bool = True,
    pad_before: int = 0,
    pad_after: int = 0,
    extra_cik: str | None = None,
) -> bytes:
    """Build an Inline-XBRL cover page.

    ``classes`` is a list of ``(symbol, title, exchange, context)``. Pass ``""`` for a field
    to omit that fact entirely, which is how an incomplete or ticker-only class is built.
    """
    parts: list[str] = ['<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"><body>']
    if pad_before:
        parts.append("<!--" + "P" * pad_before + "-->")
    if include_forbidden:
        parts.append(forbidden_block())
    if cik:
        parts.append(fact("dei:EntityCentralIndexKey", cik, "c-entity"))
    if extra_cik:
        parts.append(fact("dei:EntityCentralIndexKey", extra_cik, "c-entity-2"))
    for symbol, title, exchange, ctx in classes or []:
        if title:
            parts.append(fact("dei:Security12bTitle", title, ctx))
        if symbol:
            parts.append(fact("dei:TradingSymbol", symbol, ctx))
        if exchange:
            parts.append(fact("dei:SecurityExchangeName", exchange, ctx))
    if pad_after:
        parts.append("<!--" + "Q" * pad_after + "-->")
    parts.append("</body></html>")
    return "\n".join(parts).encode("utf-8")


#: The decisive multi-class case: one CIK, two independently declared Section 12(b) classes.
ALPHABET_CLASSES = [
    ("GOOGL", "Class A Common Stock, $0.001 par value", "Nasdaq Global Select Market", "c-classA"),
    ("GOOG", "Class C Capital Stock, $0.001 par value", "Nasdaq Global Select Market", "c-classC"),
]
