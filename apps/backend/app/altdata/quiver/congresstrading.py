"""Congressional-trading normalizer (EAD; CONGRESS-001; ADR 0037).

Maps a raw Quiver ``congresstrading`` row into the canonical ``CorporateEvent`` (the existing
Event Store schema — no new store). Row shape:

    {"Representative": "Nancy Pelosi", "BioGuideID": "P000197", "ReportDate": "2026-07-05",
     "TransactionDate": "2026-06-20", "Ticker": "NVDA", "Transaction": "Purchase",
     "Range": "$1,000,001 - $5,000,000", "House": "Representatives"}

**available_time (the PIT anchor) is DIRECTLY OBSERVABLE — the CONGRESS-001 advantage.** Unlike
gov-contracts (whose ``Date`` was a useless snapshot needing a calibrated lag), a congressional
trade is private until its STOCK-Act filing on ``ReportDate``. So ``available_time = ReportDate``
(the public-disclosure moment) — **no lag to calibrate**. ``event_date = TransactionDate`` (the
trade). The study (``run_congress001``) enters on the **first trading day strictly after**
``available_time`` (plan §0.2), never on ``TransactionDate`` (look-ahead into non-public info).

``direction`` (buy/sell) and ``range_low`` (conservative dollar floor) are parsed into ``payload``
for the study's Purchase-only primary + cluster-materiality. Identity resolves through CAP-024.
Read-only, off the order path.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from typing import Any, Protocol

from app.altdata.events.store import CorporateEvent
from app.altdata.security_master import ResolutionResult


class SecurityResolver(Protocol):
    """The slice of CAP-024 the normalizer needs (so a fake can stand in for tests)."""

    def resolve_security(
        self, *, issuer_name: str | None = ..., ticker: str | None = ...,
        cik: int | None = ..., as_of: date | None = ...,
    ) -> ResolutionResult: ...


EVENT_TYPE = "congress_trade"
SOURCE = "quiver"
PROVIDER_DATASET = "congress_trading"
DATA_SOURCE_ID = "DCAP-007"

# Transaction -> direction. Purchases are the CONGRESS-001 primary; sales are diagnostic (plan §8).
# Anything else (Exchange, transfers) is non-directional -> direction None -> excluded by the study.
_BUY = {"purchase", "buy"}
_SELL = {"sale", "sale (partial)", "sale (full)", "sell"}


def _as_date(s: Any) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _direction(transaction: Any) -> str | None:
    t = str(transaction or "").strip().lower()
    if t in _BUY:
        return "buy"
    if t in _SELL:
        return "sell"
    return None


def _range_low(rng: Any) -> int | None:
    """Conservative lower-bound dollars from a Quiver ``Range`` band, e.g. ``"$1,001 - $15,000"``
    -> ``1001``. Takes the FIRST dollar figure (the floor). ``None`` if unparseable."""
    if rng is None:
        return None
    m = re.search(r"\$?\s*([\d,]+)", str(rng))
    if not m:
        return None
    digits = m.group(1).replace(",", "")
    return int(digits) if digits.isdigit() else None


def _source_event_id(row: dict[str, Any]) -> str:
    """Deterministic idempotency key — Quiver rows carry no id. Stable across backfill/refresh
    (same disclosed trade => same id => no double-count; ADR 0037 §2.6)."""
    parts = "|".join(str(row.get(k, "")) for k in
                     ("Representative", "TransactionDate", "ReportDate", "Ticker", "Transaction", "Range"))
    return "qct_" + hashlib.sha1(parts.encode("utf-8")).hexdigest()[:20]


def _raw_payload_hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def congress_to_event(
    row: dict[str, Any], *, security_master: SecurityResolver,
) -> CorporateEvent | None:
    """Build one ``congress_trade`` event; ``None`` if it lacks the fields needed to be PIT-honest
    (a ticker + a parseable ``ReportDate`` — the observable disclosure date)."""
    ticker_raw = str(row.get("Ticker") or "").strip().upper()
    report = _as_date(row.get("ReportDate"))
    if not ticker_raw or report is None:
        return None
    transaction = _as_date(row.get("TransactionDate"))  # the trade date (event_date); may be None

    res = security_master.resolve_security(ticker=ticker_raw)
    # ⭐ available_time = the OBSERVABLE disclosure date (no lag calibration, unlike gov-contracts).
    available = datetime(report.year, report.month, report.day, tzinfo=UTC)
    seid = _source_event_id(row)

    payload = {
        "representative": row.get("Representative"),
        "bioguide_id": row.get("BioGuideID"),
        "house": row.get("House"),
        "transaction_raw": row.get("Transaction"),
        "direction": _direction(row.get("Transaction")),   # "buy" | "sell" | None
        "range_raw": row.get("Range"),
        "range_low": _range_low(row.get("Range")),          # conservative dollar floor
        "report_date": str(report),
        "transaction_date": str(transaction) if transaction else None,
    }
    return CorporateEvent(
        cik=res.cik or 0,
        ticker=res.resolved_ticker or ticker_raw,
        event_type=EVENT_TYPE,
        source=SOURCE,
        accession=seid,
        filed_at=available,                       # legacy PIT anchor == available_time here
        event_date=transaction,                   # the trade date (may be None)
        payload=payload,
        available_time=available,                 # ⭐ observable ReportDate
        resolved_security_id=res.resolved_security_id,
        issuer_name_raw=None,
        ticker_raw=ticker_raw,
        unresolved_reason=res.unresolved_reason,
        raw_payload_hash=_raw_payload_hash(row),
        provider_dataset=PROVIDER_DATASET,
        source_event_id=seid,
        data_source_id=DATA_SOURCE_ID,
        research_eligible=res.is_resolved,         # eligible iff resolved (available_time always set)
    )
