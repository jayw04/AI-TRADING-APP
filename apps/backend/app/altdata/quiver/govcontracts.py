"""Government-contract normalizer (EAD Phase 1; GOVCONTRACT-001; ADR 0037).

Maps a raw Quiver ``govcontractsall`` row into the canonical ``CorporateEvent`` (the existing
Event Store schema — no new store). Row shape:

    {"Ticker": "LMT", "Date": "2026-07-05", "Description": "...", "Agency": "...",
     "Amount": 248831.0, "action_date": "2026-07-02"}

**available_time (the load-bearing PIT decision).** Quiver's ``Date`` is a *snapshot / record-
update* date, NOT a disclosure timestamp (empirically ~99 distinct values over 4y, median
``Date − action_date`` ≈ 1600 days). Using it would badly misstate availability. So
``available_time = action_date + DISCLOSURE_LAG`` — a **conservative, PIT-safe** approximation
(later than reality, never earlier), pending calibration by the Phase-1 USAspending cross-check.
``event_date = action_date`` (the underlying event). Quiver's ``Date`` is kept in ``payload`` as
``quiver_snapshot_date`` for provenance only.

Identity is resolved through the Point-in-Time Security Master (CAP-024): a row is
``research_eligible`` only when it resolves to a security. Read-only, off the order path.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from app.altdata.events.store import CorporateEvent
from app.altdata.security_master import ResolutionResult


class SecurityResolver(Protocol):
    """The slice of CAP-024 the normalizer needs (so a fake can stand in for tests)."""

    def resolve_security(
        self, *, issuer_name: str | None = ..., ticker: str | None = ...,
        cik: int | None = ..., as_of: date | None = ...,
    ) -> ResolutionResult: ...


EVENT_TYPE = "gov_contract_award"
SOURCE = "quiver"
PROVIDER_DATASET = "government_contracts"
DATA_SOURCE_ID = "DCAP-007"

# Disclosure lag: available_time = action_date + lag. PIT-safe (larger = later entry, never
# look-ahead). **Locked at 21 (GOVCONTRACT-001 pre-registration v0.2, 2026-07-05):** FPDS requires
# reporting within 3 business days; USAspending processing adds ~days-to-2-weeks; 21 clears both
# comfortably. The USAspending cross-check's ~46-day `Last Modified` signal is an inflated
# record-maintenance proxy, so it is NOT used as the primary. Robustness is tested at {14, 46}
# (plan §6a) — separate from the primary; it must not become a search for the best result.
DISCLOSURE_LAG_DAYS = 21


def _as_date(s: Any) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _source_event_id(row: dict[str, Any]) -> str:
    """Deterministic idempotency key — Quiver rows carry no id. Stable across backfill/refresh
    (same award ⇒ same id ⇒ no double-count; ADR 0037 §2.6 idempotency gate)."""
    parts = "|".join(str(row.get(k, "")) for k in ("Ticker", "action_date", "Agency", "Amount", "Description"))
    return "qgc_" + hashlib.sha1(parts.encode("utf-8")).hexdigest()[:20]


def _raw_payload_hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def govcontract_to_event(
    row: dict[str, Any], *, security_master: SecurityResolver,
    disclosure_lag_days: int = DISCLOSURE_LAG_DAYS,
) -> CorporateEvent | None:
    """Build one ``gov_contract_award`` event; ``None`` if it lacks the fields needed to be
    PIT-honest (a ticker + a parseable ``action_date``)."""
    ticker_raw = str(row.get("Ticker") or "").strip().upper()
    action = _as_date(row.get("action_date"))
    if not ticker_raw or action is None:
        return None

    res = security_master.resolve_security(ticker=ticker_raw)
    available = datetime(action.year, action.month, action.day, tzinfo=UTC) + timedelta(days=disclosure_lag_days)
    seid = _source_event_id(row)

    payload = {
        "description": row.get("Description"),
        "agency": row.get("Agency"),
        "amount": row.get("Amount"),
        "action_date": str(action),
        "quiver_snapshot_date": row.get("Date"),   # provenance only — NOT an availability signal
    }
    return CorporateEvent(
        cik=res.cik or 0,                           # 0 = unresolved (row is not research_eligible)
        ticker=res.resolved_ticker or ticker_raw,
        event_type=EVENT_TYPE,
        source=SOURCE,
        accession=seid,                             # event_id = "{seid}:gov_contract_award"
        filed_at=available,                         # legacy PIT anchor == available_time here
        event_date=action,
        payload=payload,
        available_time=available,
        resolved_security_id=res.resolved_security_id,
        issuer_name_raw=None,
        ticker_raw=ticker_raw,
        unresolved_reason=res.unresolved_reason,
        raw_payload_hash=_raw_payload_hash(row),
        provider_dataset=PROVIDER_DATASET,
        source_event_id=seid,
        data_source_id=DATA_SOURCE_ID,
        research_eligible=res.is_resolved,          # eligible iff resolved (available_time always set)
    )
