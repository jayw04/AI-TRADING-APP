"""USAspending.gov cross-check (EAD Phase 1 exit gate; ADR 0037 §9 / spec §2.2a).

Government-contract data is NOT exclusive to Quiver — USAspending.gov is the official free
record (`api.usaspending.gov`), keyed by **recipient name / UEI** (not ticker). Before relying on
Quiver, reconcile a sample of its events against USAspending to (a) validate Quiver's added value
— the public-company→ticker mapping — is sound and not fabricated, and (b) calibrate a
reconciliation-based availability *proxy* (see the lag-proxy note below).

**Granularity note (honest scope).** Quiver rows are per-*action* awards; USAspending's
`spending_by_award` search returns per-*award* aggregates (its `Action Date` is often null and
`Award Amount` is the aggregate). So this is a **mapping-plausibility + availability-lag-proxy**
check, not an exact per-transaction reconciliation.

**Operational-vs-semantic outcomes (2026-07-15 review).** A transport failure (429/5xx/timeout)
must NEVER be silently counted as "not reconciled" — that would let an infrastructure defect
masquerade as a data-quality finding. Every reconciliation therefore returns a terminal
``ReconcileOutcome``; only ``VALID_NON_RECONCILIATION`` / ``AMBIGUOUS_CANDIDATE`` lower the
reconciliation rate. Operational failures make a run *incomplete*, gated separately. The client
retries them (bounded, Retry-After-aware, backoff+jitter) before giving up, and reports attempts.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

import httpx

from app.utils.tls_trust import enable_os_trust_store

USASPENDING_BASE = "https://api.usaspending.gov"
CONTRACT_AWARD_TYPES = ["A", "B", "C", "D"]  # BPA call / purchase order / delivery order / definitive


class ReconcileOutcome(StrEnum):
    """Terminal outcome of one reconciliation attempt. SEMANTIC outcomes describe the data;
    OPERATIONAL outcomes describe transport and must not be counted as non-reconciliation."""

    RECONCILED = "RECONCILED"                          # recipient found + agency consistent
    AMBIGUOUS_CANDIDATE = "AMBIGUOUS_CANDIDATE"        # recipient found, agency not consistent
    VALID_NON_RECONCILIATION = "VALID_NON_RECONCILIATION"  # no official award for recipient in window
    HTTP_429 = "HTTP_429"
    HTTP_5XX = "HTTP_5XX"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    PARSE_ERROR = "PARSE_ERROR"


SEMANTIC_OUTCOMES = frozenset({
    ReconcileOutcome.RECONCILED,
    ReconcileOutcome.AMBIGUOUS_CANDIDATE,
    ReconcileOutcome.VALID_NON_RECONCILIATION,
})
OPERATIONAL_OUTCOMES = frozenset({
    ReconcileOutcome.HTTP_429, ReconcileOutcome.HTTP_5XX, ReconcileOutcome.TIMEOUT,
    ReconcileOutcome.NETWORK_ERROR, ReconcileOutcome.PARSE_ERROR,
})


class USAspendingOperationalError(Exception):
    """Raised when a request cannot get a semantic answer after bounded retries — carries the
    terminal operational outcome and the attempt count so callers account for it without
    mislabelling the event as unreconciled."""

    def __init__(self, outcome: ReconcileOutcome, attempts: int) -> None:
        super().__init__(f"{outcome} after {attempts} attempts")
        self.outcome = outcome
        self.attempts = attempts


class USAspendingClient:
    """Read-only USAspending client (public, no auth) with bounded, Retry-After-aware retries.

    ``transport`` injects a mock for offline tests; TLS rides the OS trust store (Norton).
    ``rate_gate`` is called before every HTTP attempt — the calibration passes a shared adaptive
    rate limiter so concurrency across workers is globally bounded and backs off on 429.
    """

    def __init__(
        self, *, transport: httpx.BaseTransport | None = None, timeout: float = 40.0,
        max_attempts: int = 5, base_backoff: float = 0.5, max_backoff: float = 30.0,
        rate_gate: Callable[[], None] | None = None,
        on_429: Callable[[], None] | None = None, on_success: Callable[[], None] | None = None,
        sleep: Callable[[float], None] = time.sleep, rng: random.Random | None = None,
    ) -> None:
        enable_os_trust_store()
        self._client = httpx.Client(
            base_url=USASPENDING_BASE,
            headers={"Content-Type": "application/json", "User-Agent": "TradingWorkbench-research"},
            timeout=timeout, transport=transport, follow_redirects=True,
        )
        self._max_attempts = max_attempts
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff
        self._rate_gate = rate_gate or (lambda: None)
        self._on_429 = on_429 or (lambda: None)
        self._on_success = on_success or (lambda: None)
        self._sleep = sleep
        self._rng = rng or random.Random(0)

    def __enter__(self) -> USAspendingClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()

    def close(self) -> None:
        self._client.close()

    def _backoff(self, attempt: int, retry_after: str | None) -> float:
        if retry_after and retry_after.strip().isdigit():
            return min(float(retry_after), self._max_backoff)
        base = min(self._base_backoff * (2 ** (attempt - 1)), self._max_backoff)
        return base + self._rng.uniform(0, base * 0.25)  # jitter

    def awards_for_recipient(
        self, recipient: str, *, start_date: date, end_date: date, limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """Contract awards for ``recipient`` with an action in the window. Returns
        ``(results, attempts)``. Raises :class:`USAspendingOperationalError` if no semantic answer
        is obtained within ``max_attempts`` (429 / 5xx / timeout / network / parse)."""
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
        outcome = ReconcileOutcome.NETWORK_ERROR
        for attempt in range(1, self._max_attempts + 1):
            self._rate_gate()
            try:
                r = self._client.post("/api/v2/search/spending_by_award/", json=body)
            except httpx.TimeoutException:
                outcome = ReconcileOutcome.TIMEOUT
            except httpx.TransportError:
                outcome = ReconcileOutcome.NETWORK_ERROR
            else:
                if r.status_code == 429:
                    outcome = ReconcileOutcome.HTTP_429
                    self._on_429()
                    if attempt < self._max_attempts:
                        self._sleep(self._backoff(attempt, r.headers.get("Retry-After")))
                    continue
                if 500 <= r.status_code < 600:
                    outcome = ReconcileOutcome.HTTP_5XX
                    if attempt < self._max_attempts:
                        self._sleep(self._backoff(attempt, None))
                    continue
                r.raise_for_status()  # any other non-2xx (e.g. 400) is a bug, not a data outcome
                try:
                    results = r.json().get("results", [])
                except ValueError as e:
                    raise USAspendingOperationalError(ReconcileOutcome.PARSE_ERROR, attempt) from e
                self._on_success()
                return results, attempt
            # transport-error path (timeout/network): back off and retry
            if attempt < self._max_attempts:
                self._sleep(self._backoff(attempt, None))
        raise USAspendingOperationalError(outcome, self._max_attempts)


@dataclass(frozen=True)
class ReconcileResult:
    ticker: str
    recipient_query: str
    quiver_agency: str | None
    quiver_action_date: date
    matched: bool                       # recipient found in the official record (back-compat flag)
    agency_matched: bool
    n_candidates: int
    availability_lag_days: int | None   # min(Last Modified − action_date) over candidates (proxy)
    note: str
    outcome: ReconcileOutcome = ReconcileOutcome.RECONCILED
    attempts: int = 1
    latency_ms: float = 0.0


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
    """Plausibility-reconcile one Quiver gov-contract event against USAspending, returning a
    terminal :class:`ReconcileOutcome`. Operational failures are reported AS SUCH (not as
    non-reconciliation) so an infrastructure defect cannot masquerade as a data-quality finding."""
    start = action_date - timedelta(days=window_days)
    end = action_date + timedelta(days=window_days)
    t0 = time.monotonic()
    try:
        candidates, attempts = usa_client.awards_for_recipient(company_name, start_date=start, end_date=end)
    except USAspendingOperationalError as e:
        return ReconcileResult(
            ticker, company_name, agency, action_date, False, False, 0, None,
            f"operational:{e.outcome}", outcome=e.outcome, attempts=e.attempts,
            latency_ms=(time.monotonic() - t0) * 1000,
        )
    latency_ms = (time.monotonic() - t0) * 1000

    if not candidates:
        return ReconcileResult(
            ticker, company_name, agency, action_date, False, False, 0, None,
            "no_official_award_for_recipient_in_window",
            outcome=ReconcileOutcome.VALID_NON_RECONCILIATION, attempts=attempts, latency_ms=latency_ms,
        )

    agency_tokens = _agency_tokens(agency)
    agency_matched = bool(agency_tokens) and any(
        agency_tokens & _agency_tokens(c.get("Awarding Agency")) for c in candidates
    )

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
        outcome=ReconcileOutcome.RECONCILED if agency_matched else ReconcileOutcome.AMBIGUOUS_CANDIDATE,
        attempts=attempts, latency_ms=latency_ms,
    )
