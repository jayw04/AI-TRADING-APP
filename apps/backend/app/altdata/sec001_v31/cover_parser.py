"""Inline-XBRL cover-page identity parser for WP0A-Q. Positive allowlist, fail closed.

**Why the scanner is shaped the way it is.** A conventional XBRL reader parses every fact
into a concept->value map and the caller then takes what it wants. Under that design SIC has
already been extracted and merely happens not to be written down, which is precisely what
the manifest forbids. So this scanner matches *opening tags only*, reads the ``name``
attribute, and slices the element's content **only after** the name has matched
``COVER_IDENTITY_CONCEPTS``. For any other concept the content is never sliced, never
decoded, and never bound to a name. ``FORBIDDEN_CONCEPT_VOCABULARY`` is not imported here —
there is nothing to filter against, because nothing forbidden is ever read.

**Why contexts matter more than tickers.** A multi-class registrant declares each class in
its own Inline-XBRL context: Alphabet's Class A and Class C appear as two contexts under one
CIK, each with its own ``Security12bTitle``/``TradingSymbol``/``SecurityExchangeName``. This
parser therefore groups facts by ``contextRef`` and emits one class tuple per context. A
CIK-wide ticker assignment is not something it can express. A context that carries a symbol
but no Section 12(b) title yields **DISPUTED**, never a binding — ticker equality is
insufficient at every hop.

**Completeness requires EOF. Distance from the truncation point proves nothing.**
::

    IDENTITY_EVIDENCE_COMPLETE = EOF_REACHED_WITHIN_BOUND
                              OR STRUCTURALLY_PROVEN_IDENTITY_REGION_COMPLETE

An earlier revision of this module admitted an observation when the last identity fact lay
more than a margin before the truncation point. That was unsound: another class can sit
80 KiB further on, and a bounded read that stopped early cannot see it. Admitting such a
filing would turn a genuine two-class registrant into apparent single-class evidence — the
exact class-level distinction WP0A-Q exists to protect.

The second disjunct is **not implemented, deliberately.** Inline XBRL permits facts anywhere
in the document, including an ``ix:hidden`` block at the very end, and ``dei`` class facts
are not confined to any container whose close can be recognised at a knowable offset. No
universally defensible structural boundary therefore exists, and inventing one that depended
on which symbols or how many tuples had been seen would make completeness a function of the
observed values — the failure mode the rule is meant to exclude. EOF is the only admission
rule, and the cost is that a filing whose end is not reached within the frozen bounds is
``EVIDENCE_UNAVAILABLE``. That is preferable to manufacturing a class-complete observation.

``CLASS_ENUMERATION_MARGIN_BYTES`` survives only as **defence in depth**: it refuses early
and cheaply, and it catches a caller that claims EOF while also reporting truncation. It is
never a positive proof of completeness.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Final

from app.altdata.sec001_v31.concepts import CLASS_TUPLE_FIELDS, COVER_IDENTITY_CONCEPTS
from app.altdata.sec001_v31.layers import SecurityClassEvidence

# Opening tags of Inline-XBRL facts. Attributes only -- content is deliberately NOT captured.
_FACT_OPEN: Final = re.compile(rb"<ix:(nonNumeric|nonFraction)\b([^>]*)>", re.IGNORECASE)
_ATTR: Final = re.compile(rb"""(\w+)\s*=\s*["']([^"']*)["']""")
_TAG: Final = re.compile(rb"<[^>]*>")
_WS: Final = re.compile(r"\s+")

#: Defence in depth only. Never a positive completeness proof -- see the module docstring.
CLASS_ENUMERATION_MARGIN_BYTES: Final = 65536

STATUS_BOUND: Final = "BOUND"
STATUS_DISPUTED_TICKER_ONLY: Final = "DISPUTED_TICKER_ONLY"
STATUS_DISPUTED_INCOMPLETE: Final = "DISPUTED_INCOMPLETE_CLASS_TUPLE"
STATUS_DISPUTED_NO_FACTS: Final = "DISPUTED_NO_IDENTITY_FACTS"
STATUS_FAIL_COMPETING_CLASS: Final = "FAIL_CLOSED_COMPETING_CLASS_BINDING"
STATUS_FAIL_MULTIPLE_CIK: Final = "FAIL_CLOSED_MULTIPLE_ENTITY_CIK"
STATUS_FAIL_NO_CIK: Final = "FAIL_CLOSED_NO_ENTITY_CIK"
STATUS_EVIDENCE_UNAVAILABLE: Final = "EVIDENCE_UNAVAILABLE_BOUNDED_READ"


@dataclass
class ParseResult:
    status: str
    cik: int | None = None
    class_tuples: list[SecurityClassEvidence] = field(default_factory=list)
    diagnostics: dict[str, object] = field(default_factory=dict)

    @property
    def is_bound(self) -> bool:
        return self.status == STATUS_BOUND


def _clean(raw: bytes) -> str:
    return _WS.sub(" ", html.unescape(_TAG.sub(b"", raw).decode("utf-8", "replace"))).strip()


def _scan(buf: bytes) -> tuple[dict[str, dict[str, str]], dict[str, str], int]:
    """Return (context -> {field: value}, entity-level {field: value}, last fact end offset).

    Only concepts in the allowlist have their content read.
    """
    by_context: dict[str, dict[str, str]] = {}
    entity: dict[str, str] = {}
    last_end = 0

    for m in _FACT_OPEN.finditer(buf):
        attrs = dict(_ATTR.findall(m.group(2)))
        name_b = attrs.get(b"name")
        if name_b is None:
            continue
        concept = name_b.decode("ascii", "replace")

        # ---- the structural gate -------------------------------------------------
        # Content is sliced ONLY for an allowlisted concept. A forbidden or unknown
        # concept's value is never read into any variable.
        field_name = COVER_IDENTITY_CONCEPTS.get(concept)
        if field_name is None:
            continue
        # -------------------------------------------------------------------------

        tag = m.group(1)
        close = buf.find(b"</ix:" + tag + b">", m.end())
        if close == -1:
            continue
        value = _clean(buf[m.end() : close])
        last_end = max(last_end, close)
        if not value:
            continue

        ctx_b = attrs.get(b"contextRef") or attrs.get(b"contextref") or attrs.get(b"ContextRef")
        ctx = ctx_b.decode("ascii", "replace") if ctx_b else ""

        if field_name == "cik":
            entity.setdefault(ctx or "_", value)
        else:
            by_context.setdefault(ctx, {})[field_name] = value

    return by_context, entity, last_end


def parse_cover_identity(
    buf: bytes,
    *,
    eof_reached: bool,
    truncated: bool = False,
    bytes_consumed: int | None = None,
    enumeration_margin_bytes: int = CLASS_ENUMERATION_MARGIN_BYTES,
) -> ParseResult:
    """Parse cover-page identity facts from a document read.

    ``eof_reached`` is the **only** admission rule for completeness. It is a required
    keyword so that no caller can obtain a binding by forgetting to state it.
    """
    consumed = bytes_consumed if bytes_consumed is not None else len(buf)
    diag: dict[str, object] = {
        "eof_reached": eof_reached,
        "truncated": truncated,
        "bytes_consumed": consumed,
    }

    # ---- completeness gate, evaluated BEFORE anything is parsed --------------------
    # Deliberately independent of the document's content: it cannot depend on which
    # symbols were seen, or on how many class tuples were found, because those are
    # exactly the quantities a truncated read is unable to bound.
    if not eof_reached:
        return ParseResult(
            STATUS_EVIDENCE_UNAVAILABLE,
            None,
            [],
            {**diag, "reason": "bounded_read_did_not_reach_eof"},
        )

    by_context, entity, last_end = _scan(buf)
    diag["contexts_seen"] = len(by_context)
    diag["last_identity_fact_offset"] = last_end

    # Defence in depth: a caller claiming EOF while also reporting truncation is
    # self-contradictory. Refuse rather than trust the claim.
    if truncated and last_end and (consumed - last_end) < enumeration_margin_bytes:
        return ParseResult(
            STATUS_EVIDENCE_UNAVAILABLE,
            None,
            [],
            {**diag, "reason": "eof_claimed_but_read_reports_truncation"},
        )

    cik_values = {v for v in entity.values() if v}
    if len({re.sub(r"\D", "", v).lstrip("0") for v in cik_values}) > 1:
        return ParseResult(
            STATUS_FAIL_MULTIPLE_CIK, None, [], {**diag, "reason": "multiple_entity_cik"}
        )

    if not by_context and not cik_values:
        return ParseResult(STATUS_DISPUTED_NO_FACTS, None, [], diag)

    if not cik_values:
        return ParseResult(STATUS_FAIL_NO_CIK, None, [], diag)
    cik = int(re.sub(r"\D", "", next(iter(cik_values))))

    complete: list[SecurityClassEvidence] = []
    partial = 0
    symbol_only = 0
    for ctx, fields in sorted(by_context.items()):
        if all(fields.get(f) for f in CLASS_TUPLE_FIELDS):
            complete.append(
                SecurityClassEvidence(
                    trading_symbol=fields["trading_symbol"],
                    security_12b_title=fields["security_12b_title"],
                    security_exchange_name=fields["security_exchange_name"],
                    context_ref=ctx,
                )
            )
        else:
            partial += 1
            if fields.get("trading_symbol") and not fields.get("security_12b_title"):
                symbol_only += 1
    diag["complete_class_tuples"] = len(complete)
    diag["partial_contexts"] = partial

    if not complete:
        if symbol_only:
            return ParseResult(STATUS_DISPUTED_TICKER_ONLY, cik, [], diag)
        return ParseResult(STATUS_DISPUTED_INCOMPLETE, cik, [], diag)

    # Competing class bindings inside ONE filing: the same title claiming two symbols, or the
    # same symbol claiming two titles. One accepted timestamp is one effective instant, so
    # this is a contradiction rather than a change over time. Distinct from the cross-filing
    # NO_COMPETING_SECURITY_CIK_BINDING conjunct, which `bindings.py` evaluates.
    by_title: dict[str, set[str]] = {}
    by_symbol: dict[str, set[str]] = {}
    for ev in complete:
        by_title.setdefault(ev.security_12b_title, set()).add(ev.trading_symbol)
        by_symbol.setdefault(ev.trading_symbol, set()).add(ev.security_12b_title)
    if any(len(v) > 1 for v in by_title.values()) or any(len(v) > 1 for v in by_symbol.values()):
        return ParseResult(
            STATUS_FAIL_COMPETING_CLASS, cik, [], {**diag, "reason": "competing_class_binding"}
        )

    return ParseResult(STATUS_BOUND, cik, complete, diag)
