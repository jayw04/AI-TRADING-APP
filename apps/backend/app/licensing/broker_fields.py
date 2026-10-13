"""PU-1 field-level classification of Alpaca broker/trading API responses.

The broker API is a MIXED source. An order id, a quantity and the owner's own cash balance are the
owner's operational records (``owner_generated_records``, COMMERCIAL_OK); ``market_value``,
``current_price``, ``unrealized_pl`` and marked-to-market account equity are market data
(``alpaca_market_data``, PERSONAL). Both arrive in the same response, so the classification is per
FIELD (``broker_field_classification.json``) and a derived artifact is tainted by the subset of
fields it actually consumed, not by the whole response and not by none of it.

Conservative by construction:

* a field, or a whole response kind, that is not in the table is ``MARKET_DATA``;
* an unreadable or malformed table classifies EVERYTHING as ``MARKET_DATA``;
* consuming no fields at all yields an empty lineage, which the gate treats as ``UNKNOWN``.

Nothing here reads a broker, changes what is fetched, or is importable from the order path
(``check_pu1_presentation_gate.sh`` enforces the direction). Use ``subset_with_lineage`` when you
hold a response dict and ``sources_of_fields`` / ``scope_of_fields`` when you only know the field
names (e.g. a DB column mirror of a broker field).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.licensing.gate import safe_effective_scope
from app.licensing.registry import ALPACA_MARKET_DATA, OWNER_GENERATED_RECORDS
from app.licensing.render import PERSONAL_FOOTER, footer_for
from app.licensing.scopes import LicenseScope, Scoped

TABLE_PATH = Path(__file__).with_name("broker_field_classification.json")

# Public helper names. ``scripts/check_pu1_registry_closure.py`` treats a module as "going through
# the helper" only if it CALLS one of these (an import alone is not enough).
HELPER_NAMES = frozenset(
    {
        "classify_field",
        "sources_of_fields",
        "scope_of_fields",
        "subset_with_lineage",
        "taint_from_fields",
        "field_license_block",
        "market_data_field_names",
    }
)


class FieldClass(StrEnum):
    OWNER_RECORD = "OWNER_RECORD"
    MARKET_DATA = "MARKET_DATA"


_SOURCE_OF_CLASS: dict[FieldClass, str] = {
    FieldClass.OWNER_RECORD: OWNER_GENERATED_RECORDS,
    FieldClass.MARKET_DATA: ALPACA_MARKET_DATA,
}


@dataclass(frozen=True)
class FieldVerdict:
    kind: str
    field: str
    field_class: FieldClass
    listed: bool  # False => classified conservatively because the table does not name it
    review: bool = False  # True => an owner ruling is still pending on this classification

    @property
    def source_id(self) -> str:
        return _SOURCE_OF_CLASS[self.field_class]


@lru_cache(maxsize=1)
def _table() -> dict[str, dict[str, tuple[FieldClass, bool]]] | None:
    """kind -> field -> (class, review). ``None`` when the table is unusable (fail closed)."""
    try:
        doc = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
        kinds = doc["kinds"]
        out: dict[str, dict[str, tuple[FieldClass, bool]]] = {}
        for kind, body in kinds.items():
            fields: dict[str, tuple[FieldClass, bool]] = {}
            for name, spec in body["fields"].items():
                fields[str(name).strip().lower()] = (
                    FieldClass(spec["class"]),
                    bool(spec.get("review", False)),
                )
            out[str(kind).strip().lower()] = fields
        return out
    except (OSError, ValueError, KeyError, TypeError):
        return None


def reset_cache() -> None:
    """Drop the cached table (tests)."""
    _table.cache_clear()
    _enforced_names.cache_clear()


def classify_field(kind: str, field: str) -> FieldVerdict:
    """Classification of one field of one response kind. Unknown kind/field => MARKET_DATA."""
    k, f = str(kind).strip().lower(), str(field).strip().lower()
    table = _table()
    if table is not None:
        hit = table.get(k, {}).get(f)
        if hit is not None:
            return FieldVerdict(k, f, hit[0], True, hit[1])
    return FieldVerdict(k, f, FieldClass.MARKET_DATA, False)


def sources_of_fields(kind: str, used_fields: Iterable[str]) -> frozenset[str]:
    """Licence source ids of the fields actually consumed. No fields => empty set (which the gate
    reads as UNKNOWN: a lineage that names nothing proves nothing)."""
    return frozenset(classify_field(kind, f).source_id for f in used_fields)


def scope_of_fields(kind: str, used_fields: Iterable[str]) -> LicenseScope:
    """Effective scope of the subset of ``kind`` fields that were used (registry verdict)."""
    return safe_effective_scope(sources=sources_of_fields(kind, used_fields))


def subset_with_lineage(
    response: Mapping[str, Any], kind: str, used_fields: Iterable[str]
) -> Scoped[dict[str, Any]]:
    """The ``used_fields`` subset of a broker response, carrying the sources of exactly those
    fields. A requested field that the response lacks is still counted (the consumer depends on
    it), and a response field that was not requested is not (it was not consumed)."""
    used = tuple(used_fields)
    subset = {f: response.get(f) for f in used if f in response}
    return Scoped.of(subset, sources_of_fields(kind, used))


def taint_from_fields(
    value: Any,
    *consumed: tuple[str, Iterable[str]],
    extra_sources: Iterable[str] = (),
) -> Scoped[Any]:
    """Taint a derived artifact with every field it consumed: ``consumed`` is
    ``(kind, used_fields)`` pairs; ``extra_sources`` carries non-broker lineage (e.g. a
    ``Scoped.sources`` of another input). The result's sources are the union."""
    sources: set[str] = set(extra_sources)
    for kind, fields in consumed:
        sources |= sources_of_fields(kind, fields)
    return Scoped.of(value, sources)


def field_license_block(kind: str, used_fields: Iterable[str]) -> dict[str, Any]:
    """API/report block for a response built from ``used_fields`` of ``kind``: the combined
    ``license_scope`` / ``license_sources`` / ``license_footer`` plus ``license_field_sources``
    (field -> source id), so owner-record fields and market-data fields of the SAME response stay
    distinguishable while the response as a whole carries the most restrictive scope."""
    used = tuple(used_fields)
    srcs = sources_of_fields(kind, used)
    scope = safe_effective_scope(sources=srcs)
    return {
        "license_scope": scope.name,
        "license_sources": sorted(srcs),
        "license_footer": PERSONAL_FOOTER if footer_for(scope) else None,
        "license_field_sources": {f: classify_field(kind, f).source_id for f in used},
    }


@lru_cache(maxsize=1)
def _enforced_names() -> frozenset[str]:
    try:
        doc = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
        return frozenset(str(n).lower() for n in doc["ast_enforced_market_data_names"])
    except (OSError, ValueError, KeyError, TypeError):
        return frozenset()


def market_data_field_names() -> frozenset[str]:
    """Field names the build-time AST check enforces (a subset of the MARKET_DATA fields)."""
    return _enforced_names()
