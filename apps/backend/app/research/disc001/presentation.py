"""OpportunityPresentationAdapter — snapshot (+ live GAP) → Opportunities widget.

GET /opportunities reads this. It does not run family screens. SEP families
come from the latest snapshot; GAP is merged from the current gappers file so
the premarket cadence is preserved. Fail-closed families stay unavailable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.research.disc001.engine import assemble_all, screen_gap
from app.research.disc001.snapshot import read_snapshot, resolve_snapshot_dir
from app.research.disc001.spec import (
    FAMILY_HORIZON,
    FAMILY_OPERATOR_NAME,
    PRICE_SOURCE_GAP,
    SCREEN_ID,
    SCREEN_VERSION,
    UNIVERSE_ID,
    FamilyId,
)


def _empty_family(fid: FamilyId, *, available: bool, reason: str | None) -> dict[str, Any]:
    return {
        "family_id": str(fid),
        "operator_name": FAMILY_OPERATOR_NAME[fid],
        "horizon": FAMILY_HORIZON[fid],
        "available": available,
        "unavailable_reason": reason,
        "count": 0,
        "items": [],
    }


def _gap_from_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    from app.research.disc001.adapter import _card_to_dict, _gap_rows_from_payload

    rows = _gap_rows_from_payload(payload)
    if rows is None:
        return _empty_family(
            FamilyId.GAP,
            available=False,
            reason="pre-market gappers file missing or unreadable",
        )
    result = screen_gap(
        rows, available=True, unavailable_reason=None, price_source=PRICE_SOURCE_GAP
    )
    return {
        "family_id": str(FamilyId.GAP),
        "operator_name": FAMILY_OPERATOR_NAME[FamilyId.GAP],
        "horizon": FAMILY_HORIZON[FamilyId.GAP],
        "available": True,
        "unavailable_reason": None,
        "count": len(result.items),
        "items": [_card_to_dict(c) for c in result.items],
    }


def load_watchlist_widget(
    *,
    gappers_payload: dict[str, Any] | None,
    snapshot_dir: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    snap = read_snapshot(resolve_snapshot_dir(snapshot_dir))
    gap = _gap_from_payload(gappers_payload)

    if snap is None:
        families = {
            str(FamilyId.OVERSOLD): _empty_family(
                FamilyId.OVERSOLD,
                available=False,
                reason="no CandidateSnapshot on disk",
            ),
            str(FamilyId.MOM_NEAR): _empty_family(
                FamilyId.MOM_NEAR,
                available=False,
                reason="no CandidateSnapshot on disk",
            ),
            str(FamilyId.MOM_CORE): _empty_family(
                FamilyId.MOM_CORE,
                available=False,
                reason="no CandidateSnapshot on disk",
            ),
            str(FamilyId.GAP): gap,
        }
        return {
            "as_of": gap_as_of_fallback(gappers_payload, now),
            "as_of_session": None,
            "universe_id": UNIVERSE_ID,
            "screen_id": SCREEN_ID,
            "screen_version": SCREEN_VERSION,
            "subtitle": "Watch, not a signal",
            "vix": None,
            "families": families,
            "all_items": gap.get("items") or [],
            "all_count": gap.get("count") or 0,
            "stale": True,
        }

    families = dict(snap.get("families") or {})
    presented: dict[str, Any] = {}
    for fid in (FamilyId.OVERSOLD, FamilyId.MOM_NEAR, FamilyId.MOM_CORE, FamilyId.GAP):
        raw = families.get(str(fid)) or {}
        presented[str(fid)] = {
            "family_id": str(fid),
            "operator_name": FAMILY_OPERATOR_NAME[fid],
            "horizon": FAMILY_HORIZON[fid],
            "available": bool(raw.get("available", False)),
            "unavailable_reason": raw.get("unavailable_reason"),
            "count": int(raw.get("count") or len(raw.get("items") or [])),
            "items": list(raw.get("items") or []),
        }
    presented[str(FamilyId.GAP)] = gap

    from app.research.disc001.engine import FamilyResult

    rebuilt_families: dict[FamilyId, FamilyResult] = {}
    for fid in (FamilyId.OVERSOLD, FamilyId.MOM_NEAR, FamilyId.GAP, FamilyId.MOM_CORE):
        blob = presented[str(fid)]
        if not blob["available"]:
            rebuilt_families[fid] = FamilyResult(fid, False, blob.get("unavailable_reason"), ())
            continue
        rebuilt_families[fid] = FamilyResult(
            fid, True, None, tuple(_item_to_card(item) for item in blob["items"])
        )
    all_cards = assemble_all(rebuilt_families)

    return {
        "as_of": now,
        "as_of_session": snap.get("as_of"),
        "universe_id": snap.get("universe_id", UNIVERSE_ID),
        "screen_id": snap.get("screen_id", SCREEN_ID),
        "screen_version": snap.get("screen_version", SCREEN_VERSION),
        "subtitle": snap.get("subtitle") or "Watch, not a signal",
        "vix": snap.get("vix"),
        "families": presented,
        "all_items": [
            {
                "symbol": c.symbol,
                "family_ids": [str(f) for f in c.family_ids],
                "horizon": c.horizon,
                "status": str(c.status),
                "name": c.name,
                "sector": c.sector,
                "chips": [{"key": ch.key, "value": ch.value} for ch in c.chips],
                "why": c.why,
                "tradability": c.tradability,
                "price_source": c.price_source,
                "close": c.close,
                "market_cap": c.market_cap,
                "adv20": c.adv20,
            }
            for c in all_cards
        ],
        "all_count": len(all_cards),
        "stale": False,
    }


def gap_as_of_fallback(payload: dict[str, Any] | None, now: datetime) -> datetime:
    if payload and payload.get("scanned_at"):
        return payload["scanned_at"]
    return now


def _item_to_card(item: dict[str, Any]) -> Any:
    from app.research.disc001.engine import CandidateCard, ReasonChip
    from app.research.disc001.spec import EvidenceStatus, FamilyId

    families = tuple(FamilyId(f) for f in (item.get("family_ids") or []))
    status_raw = item.get("status") or "Watch"
    try:
        status = EvidenceStatus(status_raw)
    except ValueError:
        status = EvidenceStatus.WATCH
    chips = tuple(
        ReasonChip(str(c.get("key")), str(c.get("value")))
        for c in (item.get("chips") or [])
        if isinstance(c, dict)
    )
    return CandidateCard(
        symbol=str(item.get("symbol") or ""),
        family_ids=families or (FamilyId.OVERSOLD,),
        horizon=str(item.get("horizon") or ""),
        status=status,
        name=item.get("name"),
        sector=item.get("sector"),
        chips=chips,
        why=str(item.get("why") or ""),
        tradability=str(item.get("tradability") or "not measured (Phase 1)"),
        price_source=str(item.get("price_source") or ""),
        close=item.get("close"),
        market_cap=item.get("market_cap"),
        adv20=item.get("adv20"),
    )
