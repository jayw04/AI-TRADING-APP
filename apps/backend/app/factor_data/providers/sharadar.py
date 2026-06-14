"""Sharadar (Nasdaq Data Link) read-only REST provider.

Pulls the SHARADAR datatables (`SEP` / `TICKERS` / `ACTIONS`) over the Nasdaq
Data Link v3 datatables API, following `qopts.cursor_id` pagination, into pandas
DataFrames. REST via httpx — no vendor SDK (P9 §0 confirmed this is sufficient).

Discipline (ADR 0018):
- Read-only. This module never touches the order path, risk engine, or BarCache.
- OS-trust-store TLS is injected before any HTTPS (ADR 0017) so ingestion reaches
  Nasdaq Data Link under a TLS-inspecting proxy (Norton on the dev box).
- The API key is sent as a query param and **never logged** (ADR 0018 §5). The
  only thing logged about the key is its length.
"""

from __future__ import annotations

from typing import Any

import httpx
import pandas as pd
import structlog

from app.config import get_settings
from app.utils.tls_trust import enable_os_trust_store

logger = structlog.get_logger(__name__)

# v3 datatables base; each SHARADAR table is a path segment (SEP/TICKERS/ACTIONS).
NDL_BASE = "https://data.nasdaq.com/api/v3/datatables/SHARADAR"

# Nasdaq returns up to 10k rows/page; a safety bound on pages so a runaway
# cursor can't loop forever. A full SEP per-ticker pull is a handful of pages.
_MAX_PAGES = 1000


class SharadarConfigError(RuntimeError):
    """Raised when the Nasdaq Data Link API key is not configured."""


class SharadarProvider:
    """Thin REST client over the SHARADAR datatables.

    Construct once and reuse across `fetch_table` calls; the underlying
    `httpx.Client` (and its connection pool) is held for the provider's life.
    Use as a context manager, or call `close()` when done.
    """

    def __init__(self, api_key: str | None = None, *, timeout: float = 60.0) -> None:
        # OS trust store first — before httpx builds its first SSL context.
        enable_os_trust_store()
        self._api_key = api_key if api_key is not None else get_settings().nasdaq_data_link_api_key
        if not self._api_key:
            raise SharadarConfigError(
                "NASDAQ_DATA_LINK_API_KEY is not set; cannot reach Sharadar. "
                "Set it in .env (read-only factor data, ADR 0018)."
            )
        self._client = httpx.Client(follow_redirects=True, timeout=timeout)
        logger.info("sharadar_provider_init", api_key_len=len(self._api_key))

    def __enter__(self) -> SharadarProvider:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def fetch_table(self, name: str, **filters: object) -> pd.DataFrame:
        """Fetch a full SHARADAR datatable, following cursor pagination.

        ``name`` is the datatable name in the URL (e.g. ``SEP``, ``TICKERS``,
        ``ACTIONS``). ``filters`` are passed as query params — e.g.
        ``ticker="AAPL"`` or ``**{"date.gte": "1998-01-01"}``. Returns a single
        concatenated DataFrame (empty if the table returns no rows). The API key
        is injected here and never logged.
        """
        frames: list[pd.DataFrame] = []
        cursor: str | None = None
        pages = 0
        rows = 0
        while pages < _MAX_PAGES:
            params: dict[str, Any] = dict(filters)
            params["api_key"] = self._api_key
            if cursor:
                params["qopts.cursor_id"] = cursor
            resp = self._client.get(f"{NDL_BASE}/{name}.json", params=params)
            resp.raise_for_status()
            payload = resp.json()
            datatable = payload["datatable"]
            cols = [c["name"] for c in datatable["columns"]]
            frames.append(pd.DataFrame(datatable["data"], columns=cols))
            rows += len(datatable["data"])
            cursor = payload.get("meta", {}).get("next_cursor_id")
            pages += 1
            if not cursor:
                break
        logger.info("sharadar_fetch_table", table=name, pages=pages, rows=rows)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)
