"""Read-only Quiver Quant HTTP client (EAD Phase 1; ADR 0037).

Quiver is a **paid** alt-data vendor (Hobbyist for the MVP). Auth is a single token sent as
``Authorization: Token <key>`` (DRF-style — NOT ``Bearer``). Two gotchas this client handles:

  * **Cloudflare.** Quiver sits behind Cloudflare, which 403s any request without a browser
    ``User-Agent`` (``error code: 1010``) — *even with a valid token*. So a browser-like UA is
    mandatory, not optional.
  * **Norton TLS (ADR 0017).** Outbound TLS rides the OS trust store so SSL inspection on the
    dev machine does not break the handshake.

Sync by design — ingestion is a batch job, not request-path. Read-only (GET only); imports
nothing from the order path. Empty ``QUIVER_API_KEY`` ⇒ ``QuiverDisabled`` (never an
unauthenticated fetch). See ``Docs/design/…BuildSpec_v0.4.md`` §2.1 and the ``quiver-api-connection`` memory.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.config import get_settings
from app.utils.tls_trust import enable_os_trust_store

QUIVER_BASE = "https://api.quiverquant.com"

# Cloudflare requires a browser signature; a bare client UA gets a 403 error-1010 regardless of
# the token. This is a real, load-bearing default (see the quiver-api-connection memory).
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
DEFAULT_RATE_PER_SEC = 4.0  # conservative; Quiver Hobbyist is rate-limited


class QuiverDisabled(RuntimeError):
    """Raised when no ``QUIVER_API_KEY`` is configured — Quiver ingestion is off rather than
    fetching unauthenticated (which Cloudflare/Quiver would reject anyway)."""


class QuiverClient:
    """A throttled, read-only Quiver client.

    ``api_key`` / ``user_agent`` default to settings/the browser UA. Pass ``transport`` (an
    ``httpx.BaseTransport``) for offline tests. Use as a context manager or call ``close()``.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        user_agent: str | None = None,
        rate_limit_per_sec: float = DEFAULT_RATE_PER_SEC,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        key = (api_key if api_key is not None else get_settings().quiver_api_key).strip()
        if not key:
            raise QuiverDisabled(
                "QUIVER_API_KEY is not set — Quiver ingestion is disabled. Put the token in "
                ".env (local) / SSM (/workbench/prod/QUIVER_API_KEY on the box)."
            )
        enable_os_trust_store()  # ADR 0017 — idempotent; beats Norton SSL inspection
        ua = (user_agent or DEFAULT_USER_AGENT).strip()
        self._min_interval = 1.0 / max(0.1, float(rate_limit_per_sec))
        self._last = 0.0
        self._client = httpx.Client(
            base_url=QUIVER_BASE,
            headers={
                "Authorization": f"Token {key}",
                "User-Agent": ua,               # mandatory — Cloudflare (see module docstring)
                "Accept": "application/json",
            },
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )

    def __enter__(self) -> QuiverClient:
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

    def get_json(self, path: str) -> Any:
        self._throttle()
        r = self._client.get(path)
        r.raise_for_status()
        return r.json()

    # --- Government Contracts (GOVCONTRACT-001 MVP) ------------------------------------------
    # Use the *…all* endpoints: event-level individual awards with per-row dates. The plain
    # ``govcontracts`` endpoint returns quarterly aggregates (no date) — not event-driven-usable.

    def govcontracts_history(self, ticker: str) -> list[dict[str, Any]]:
        """Full per-ticker award history: rows of ``{Ticker, Date, Description, Agency, Amount,
        action_date}``. ``action_date`` is the event; ``Date`` is a Quiver snapshot date (NOT a
        disclosure timestamp — see the normalizer)."""
        return self.get_json(f"/beta/historical/govcontractsall/{ticker.strip().upper()}")

    def govcontracts_live(self) -> list[dict[str, Any]]:
        """Recent cross-market awards (bulk) — the daily-incremental source."""
        return self.get_json("/beta/live/govcontractsall")

    # --- Congressional Trading (CONGRESS-001) -----------------------------------------------
    # Rows carry a real disclosure date (``ReportDate``) *and* the trade date (``TransactionDate``),
    # so — unlike gov contracts — the PIT anchor is directly observable (no lag calibration).

    def congresstrading_history(self, ticker: str) -> list[dict[str, Any]]:
        """Full per-ticker congressional-trade history: rows of ``{Representative, BioGuideID,
        ReportDate, TransactionDate, Ticker, Transaction, Range, House}``. ``TransactionDate`` is
        the trade (private until disclosed); ``ReportDate`` is the public STOCK-Act filing date."""
        return self.get_json(f"/beta/historical/congresstrading/{ticker.strip().upper()}")

    def congresstrading_live(self) -> list[dict[str, Any]]:
        """Recent cross-market congressional trades (bulk) — the daily-incremental source."""
        return self.get_json("/beta/live/congresstrading")
