"""USAspending.gov cross-check (EAD Phase 1 exit gate; ADR 0037 §9 / spec §2.2a).

Government-contract data is NOT exclusive to Quiver — USAspending.gov is the official free
record (`api.usaspending.gov`), keyed by **recipient name / UEI** (not ticker). Before relying on
Quiver, reconcile a sample of its events against USAspending to (a) validate Quiver's added value
— the public-company→ticker mapping — is sound and not fabricated, and (b) calibrate the
disclosure lag (`available_time = action_date + lag`) from the official availability signal.

**Granularity note (honest scope).** Quiver rows are per-*action* awards; USAspending's
`spending_by_award` search returns per-*award* aggregates (its `Action Date` is often null and
`Award Amount` is the aggregate). So this is a **mapping-plausibility + availability-lag** check,
not an exact per-transaction reconciliation: does the official record confirm this ticker's
company has contracts with the same agency near this date, and how long after the action does the
record's `Last Modified Date` fall? Thresholds are calibration-grade. Read-only, off the order path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.utils.tls_trust import enable_os_trust_store

USASPENDING_BASE = "https://api.usaspending.gov"
CONTRACT_AWARD_TYPES = ["A", "B", "C", "D"]  # BPA call / purchase order / delivery order / definitive


class USAspendingClient:
    """Minimal read-only USAspending client (public, no auth). ``transport`` injects a mock for
    offline tests; TLS rides the OS trust store (Norton)."""

    def __init__(self, *, transport: httpx.BaseTransport | None = None, timeout: float = 40.0) -> None:
        enable_os_trust_store()
        self._client = httpx.Client(
            base_url=USASPENDING_BASE,
            headers={"Content-Type": "application/json", "User-Agent": "TradingWorkbench-research"},
            timeout=timeout, transport=transport, follow_redirects=True,
        )

    def __enter__(self) -> USAspendingClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()

    def close(self) -> None:
        self._client.close()

    def awards_for_recipient(
        self, recipient: str, *, start_date: date, end_date: date, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Contract awards whose recipient matches ``recipient`` with an action in the window."""
        body = {
            "filters": {
                "award_type_codes": CONTRACT_AWARD_TYPES,
                "recipient_search_text": [recipient],
                "time_period": [{"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}],
            },
            "fields": ["Award ID", "Recipient Name", "Action Date", "Award Amount",
                       "Awarding Agency", "Last Modified Date"],
            "limit": limit,
        }
        r = self._client.post("/api/v2/search/spending_by_award/", json=body)
        r.raise_for_status()
        return r.json().get("results", [])


@dataclass(frozen=True)
class ReconcileResult:
    ticker: str
    recipient_query: str
    quiver_agency: str | None
    quiver_action_date: date
    matched: bool                       # official record confirms recipient + agency near the date
    agency_matched: bool
    n_candidates: int
    availability_lag_days: int | None   # min(Last Modified − action_date) over candidates (proxy)
    note: str


def _norm(s: str | None) -> str:
    return "".join(ch for ch in (s or "").upper() if ch.isalnum() or ch == " ").strip()


# Generic words shared by most agency names — excluded so agency matching keys on the
# distinctive tokens (ENERGY vs HOMELAND SECURITY), not "DEPARTMENT OF".
_AGENCY_STOPWORDS = frozenset({
    "DEPARTMENT", "OF", "THE", "AND", "US", "USA", "UNITED", "STATES", "OFFICE",
    "ADMINISTRATION", "AGENCY", "NATIONAL", "FEDERAL", "BUREAU", "SERVICE", "SERVICES",
})


def _agency_tokens(agency: str | None) -> set[str]:
    return {t for t in _norm(agency).split() if t not in _AGENCY_STOPWORDS}


def reconcile_event(
    *, ticker: str, company_name: str, agency: str | None, action_date: date,
    usa_client: USAspendingClient, window_days: int = 45,
) -> ReconcileResult:
    """Plausibility-reconcile one Quiver gov-contract event against USAspending. ``matched`` iff
    the official record shows the company as a contract recipient in the window; ``agency_matched``
    iff at least one candidate's awarding agency shares a token with the Quiver agency."""
    start = action_date - timedelta(days=window_days)
    end = action_date + timedelta(days=window_days)
    try:
        candidates = usa_client.awards_for_recipient(company_name, start_date=start, end_date=end)
    except Exception as e:  # noqa: BLE001 — a lookup failure is a data-quality signal, not fatal
        return ReconcileResult(ticker, company_name, agency, action_date, False, False, 0, None,
                               f"usaspending_error: {type(e).__name__}")

    if not candidates:
        return ReconcileResult(ticker, company_name, agency, action_date, False, False, 0, None,
                               "no_official_award_for_recipient_in_window")

    agency_tokens = _agency_tokens(agency)
    agency_matched = bool(agency_tokens) and any(
        agency_tokens & _agency_tokens(c.get("Awarding Agency")) for c in candidates
    )

    # availability proxy: how long after the action the official record was last modified
    lags: list[int] = []
    for c in candidates:
        lm = c.get("Last Modified Date")
        if lm:
            try:
                lm_d = datetime.fromisoformat(str(lm)[:10]).date()
                lags.append((lm_d - action_date).days)
            except ValueError:
                pass
    availability_lag = min((x for x in lags if x >= 0), default=None)

    return ReconcileResult(
        ticker=ticker, recipient_query=company_name, quiver_agency=agency,
        quiver_action_date=action_date, matched=True, agency_matched=agency_matched,
        n_candidates=len(candidates), availability_lag_days=availability_lag,
        note="ok" if agency_matched else "recipient_matched_agency_mismatch",
    )
