"""Read-only, fair-access-compliant SEC EDGAR HTTP client (ADR 0027).

EDGAR is free and unauthenticated, but the SEC's fair-access policy requires a descriptive
``User-Agent`` (org + contact) on every request and a client-side cap of <= 10 requests/sec.
This client enforces both: an empty ``User-Agent`` raises ``EdgarDisabled`` (never an
un-throttled anonymous fetch), and a min-interval throttle keeps us under the rate ceiling.

Sync by design — ingestion is a batch job, not request-path. The client is read-only (GET
only); it imports nothing from the order path. Outbound TLS rides the OS trust store
(ADR 0017) like the other vendors, so Norton SSL inspection does not break it.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.config import get_settings

# EDGAR hosts: structured JSON (submissions, company_tickers) vs the filing archives.
DATA_HOST = "https://data.sec.gov"
WWW_HOST = "https://www.sec.gov"


class EdgarDisabled(RuntimeError):
    """Raised when no ``SEC_EDGAR_USER_AGENT`` is configured — EDGAR ingestion is off
    rather than silently fetching anonymously (which the SEC may block)."""


class EdgarClient:
    """A throttled, read-only EDGAR client.

    ``user_agent`` / ``rate_limit_per_sec`` default to settings. Pass ``transport`` (an
    ``httpx.BaseTransport``) for offline tests. Use as a context manager or call ``close()``.
    """

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        rate_limit_per_sec: float | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        s = get_settings()
        ua = (user_agent if user_agent is not None else s.sec_edgar_user_agent).strip()
        if not ua:
            raise EdgarDisabled(
                "SEC_EDGAR_USER_AGENT is not set — EDGAR ingestion is disabled. Set a "
                "descriptive User-Agent ('Org Name contact@example.com') per SEC fair access."
            )
        self._ua = ua
        rate = rate_limit_per_sec if rate_limit_per_sec is not None else s.sec_edgar_rate_limit_per_sec
        self._min_interval = 1.0 / max(0.1, float(rate))
        self._last = 0.0
        self._client = httpx.Client(
            headers={"User-Agent": self._ua, "Accept-Encoding": "gzip, deflate"},
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )

    def __enter__(self) -> EdgarClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last = time.monotonic()

    def get_json(self, url: str) -> Any:
        self._throttle()
        r = self._client.get(url)
        r.raise_for_status()
        return r.json()

    def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        """GET text; optional extra headers (e.g. a Range header to read only an SGML
        header block from a large full-submission archive file)."""
        self._throttle()
        r = self._client.get(url, headers=headers)
        r.raise_for_status()
        return r.text
