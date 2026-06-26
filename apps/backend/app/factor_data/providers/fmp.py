"""Financial Modeling Prep (FMP) read-only REST provider — fundamentals layer.

Pulls FMP's company fundamentals (income statement, balance sheet, cash flow,
ratios, key metrics, company profile) and the delisted-companies universe over
FMP's **`/stable` API**, into pandas DataFrames. REST via httpx — no vendor SDK,
mirroring `SharadarProvider`.

The fundamentals carry SEC ``filingDate`` / ``acceptedDate`` columns, which the
factor layer uses for point-in-time as-of joins (no look-ahead) — the same PIT
discipline ADR 0018 mandates.

Discipline (ADR 0018):
- Read-only. Never touches the order path, risk engine, or BarCache.
- OS-trust-store TLS is injected before any HTTPS (ADR 0017) so ingestion reaches
  FMP under a TLS-inspecting proxy (Norton on the dev box).
- The API key is sent as the ``apikey`` query param and **never logged**. The only
  thing logged about the key is its length.

API note: FMP retired its legacy ``/api/v3`` and ``/api/v4`` endpoints on
2026-08-31 (they now 403 for non-legacy keys). This provider targets the current
``/stable`` API, whose endpoints take ``symbol`` / ``period`` / ``limit`` query
params and return a JSON array of records.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import pandas as pd
import structlog

from app.config import get_settings
from app.utils.tls_trust import enable_os_trust_store

logger = structlog.get_logger(__name__)

# FMP's current ("stable") API base. Each dataset is a path segment.
FMP_STABLE_BASE = "https://financialmodelingprep.com/stable"

# Transient-failure retry, matching SharadarProvider: a broad-universe ingest
# issues thousands of back-to-back GETs; a single connection reset (Norton SSL
# inspection / server drop) shouldn't kill the run. Retry transport errors and
# 429/5xx with exponential backoff; other 4xx (auth/gated/bad request) fail fast.
_MAX_RETRIES = 4
_RETRY_BACKOFF_BASE = 1.0  # seconds → 1, 2, 4, 8


class FMPConfigError(RuntimeError):
    """Raised when the FMP API key is not configured."""


class FMPError(RuntimeError):
    """Raised when FMP returns an error payload (e.g. a gated/legacy endpoint, or
    an ``{"Error Message": ...}`` body) rather than a data array."""


class FMPProvider:
    """Thin REST client over FMP's ``/stable`` fundamentals endpoints.

    Construct once and reuse across calls; the underlying ``httpx.Client`` (and its
    connection pool) is held for the provider's life. Use as a context manager, or
    call ``close()`` when done.
    """

    def __init__(self, api_key: str | None = None, *, timeout: float = 60.0) -> None:
        # OS trust store first — before httpx builds its first SSL context.
        enable_os_trust_store()
        self._api_key = api_key if api_key is not None else get_settings().fmp_api_key
        if not self._api_key:
            raise FMPConfigError(
                "FMP_API_KEY is not set; cannot reach Financial Modeling Prep. "
                "Set it in .env (read-only factor data, ADR 0018)."
            )
        self._client = httpx.Client(follow_redirects=True, timeout=timeout)
        logger.info("fmp_provider_init", api_key_len=len(self._api_key))

    def __enter__(self) -> FMPProvider:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get_with_retry(self, endpoint: str, params: dict[str, Any]) -> httpx.Response:
        """GET with bounded exponential-backoff retry on transient failures.

        Retries transport errors (connection reset / read timeout) and 429/5xx;
        any other 4xx (auth/gated/bad request — e.g. a legacy endpoint's 403) fails
        fast. Raises the last error after ``_MAX_RETRIES`` attempts."""
        url = f"{FMP_STABLE_BASE}/{endpoint}"
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = self._client.get(url, params=params)
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if not (status == 429 or 500 <= status < 600) or attempt >= _MAX_RETRIES:
                    raise
            except httpx.TransportError:  # ReadError / ConnectError / RemoteProtocolError / …
                if attempt >= _MAX_RETRIES:
                    raise
            sleep_s = _RETRY_BACKOFF_BASE * (2**attempt)
            logger.warning("fmp_fetch_retry", endpoint=endpoint, attempt=attempt + 1, sleep_s=sleep_s)
            time.sleep(sleep_s)
        raise RuntimeError("unreachable: retry loop exhausted")  # pragma: no cover

    def fetch(self, endpoint: str, **params: object) -> pd.DataFrame:
        """Fetch a ``/stable`` endpoint and return its JSON array as a DataFrame.

        ``endpoint`` is the path segment (e.g. ``income-statement``,
        ``delisted-companies``). ``params`` are query params (e.g. ``symbol="AAPL"``,
        ``period="quarter"``, ``limit=40``). The API key is injected here and never
        logged. An empty array yields an empty DataFrame; an FMP error object
        (``{"Error Message": ...}``) or any non-array payload raises ``FMPError``.
        """
        q: dict[str, Any] = {k: v for k, v in params.items() if v is not None}
        q["apikey"] = self._api_key
        resp = self._get_with_retry(endpoint, q)
        payload = resp.json()
        if isinstance(payload, dict):
            # FMP signals errors as an object, e.g. {"Error Message": "..."}.
            msg = payload.get("Error Message") or payload.get("error") or str(payload)[:160]
            raise FMPError(f"FMP {endpoint} returned an error payload: {msg}")
        if not isinstance(payload, list):
            raise FMPError(f"FMP {endpoint} returned an unexpected payload type: {type(payload).__name__}")
        logger.info("fmp_fetch", endpoint=endpoint, rows=len(payload))
        return pd.DataFrame(payload)

    # ---- typed convenience methods (the fundamentals + universe surface) ----

    def income_statement(self, symbol: str, *, period: str = "annual", limit: int = 40) -> pd.DataFrame:
        """Income statement (revenue, EBITDA, net income, shares out, …) with
        ``filingDate``/``acceptedDate`` for PIT. ``period`` is 'annual' or 'quarter'."""
        return self.fetch("income-statement", symbol=symbol, period=period, limit=limit)

    def balance_sheet(self, symbol: str, *, period: str = "annual", limit: int = 40) -> pd.DataFrame:
        """Balance sheet (total debt, equity, assets, cash, …)."""
        return self.fetch("balance-sheet-statement", symbol=symbol, period=period, limit=limit)

    def cash_flow(self, symbol: str, *, period: str = "annual", limit: int = 40) -> pd.DataFrame:
        """Cash-flow statement (free cash flow, operating CF, capex, …)."""
        return self.fetch("cash-flow-statement", symbol=symbol, period=period, limit=limit)

    def ratios(self, symbol: str, *, period: str = "annual", limit: int = 40) -> pd.DataFrame:
        """Pre-computed ratios (margins, returns, leverage)."""
        return self.fetch("ratios", symbol=symbol, period=period, limit=limit)

    def key_metrics(self, symbol: str, *, period: str = "annual", limit: int = 40) -> pd.DataFrame:
        """Key metrics (enterprise value, EV multiples, …)."""
        return self.fetch("key-metrics", symbol=symbol, period=period, limit=limit)

    def profile(self, symbol: str) -> pd.DataFrame:
        """Company profile (sector/industry/market cap snapshot)."""
        return self.fetch("profile", symbol=symbol)

    def delisted_companies(self, *, limit: int = 100, page: int = 0) -> pd.DataFrame:
        """The delisted-companies list (survivorship-bias mitigation): symbol,
        company, exchange, ipoDate, delistedDate."""
        return self.fetch("delisted-companies", limit=limit, page=page)
