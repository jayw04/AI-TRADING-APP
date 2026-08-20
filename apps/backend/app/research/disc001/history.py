"""Map CandidateSnapshot cards to Opportunity History occurrence drafts.

Research plane (ADR 0051). Pure functions — no DB, no order path, no MDQ.
Ingest persistence lives in ``app.services.opportunity_history``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.research.disc001.spec import (
    FAMILY_HORIZON,
    PRICE_SOURCE_GAP,
    PRICE_SOURCE_SEP,
    SCREEN_ID,
    SCREEN_VERSION,
    FamilyId,
)

HISTORY_FAMILIES: tuple[str, ...] = (
    str(FamilyId.OVERSOLD),
    str(FamilyId.MOM_NEAR),
    str(FamilyId.MOM_CORE),
    str(FamilyId.GAP),
)


@dataclass(frozen=True)
class OccurrenceDraft:
    """Immutable facts taken from one snapshot family card."""

    symbol: str
    candidate_date: str
    family: str
    horizon: str
    status_at_proposal: str
    proposal_price: float
    proposal_price_source: str
    adjustment_basis: str
    reason_json: dict[str, Any]
    screen_id: str
    screen_version: str
    snapshot_sha256: str
    snapshot_generated_at: str


def occurrences_from_payload(payload: dict[str, Any]) -> tuple[OccurrenceDraft, ...]:
    """Family rows only — never the All-tab union, never a live GAP overlay."""
    as_of = str(payload.get("as_of") or "")
    screen_id = str(payload.get("screen_id") or SCREEN_ID)
    screen_version = str(payload.get("screen_version") or SCREEN_VERSION)
    sha = str(payload.get("sha256") or "")
    built_at = str(payload.get("built_at") or "")
    families = payload.get("families") or {}
    out: list[OccurrenceDraft] = []
    for family in HISTORY_FAMILIES:
        fam = families.get(family) or {}
        if not isinstance(fam, dict) or not fam.get("available", False):
            continue
        horizon = str(fam.get("horizon") or FAMILY_HORIZON[FamilyId(family)])
        for item in fam.get("items") or []:
            draft = _draft_from_card(
                item,
                family=family,
                horizon=horizon,
                as_of=as_of,
                screen_id=screen_id,
                screen_version=screen_version,
                sha=sha,
                built_at=built_at,
            )
            if draft is not None:
                out.append(draft)
    return tuple(out)


def _draft_from_card(
    item: Any,
    *,
    family: str,
    horizon: str,
    as_of: str,
    screen_id: str,
    screen_version: str,
    sha: str,
    built_at: str,
) -> OccurrenceDraft | None:
    if not isinstance(item, dict):
        return None
    symbol = str(item.get("symbol") or "").strip().upper()
    close = item.get("close")
    if not symbol or as_of == "" or close is None:
        return None
    try:
        price = float(close)
    except (TypeError, ValueError):
        return None
    source = str(item.get("price_source") or "")
    if family == str(FamilyId.GAP):
        source = source or PRICE_SOURCE_GAP
        basis = PRICE_SOURCE_GAP
    else:
        source = source or PRICE_SOURCE_SEP
        basis = PRICE_SOURCE_SEP
    chips = item.get("chips") or []
    if not isinstance(chips, list):
        chips = []
    return OccurrenceDraft(
        symbol=symbol,
        candidate_date=as_of,
        family=family,
        horizon=horizon,
        status_at_proposal=str(item.get("status") or ""),
        proposal_price=price,
        proposal_price_source=source,
        adjustment_basis=basis,
        reason_json={"chips": chips, "why": str(item.get("why") or "")},
        screen_id=screen_id,
        screen_version=screen_version,
        snapshot_sha256=sha,
        snapshot_generated_at=built_at,
    )
