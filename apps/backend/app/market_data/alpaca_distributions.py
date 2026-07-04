"""Live Alpaca-backed corporate-actions distributions provider (PORT-001 total-return pricing).

Implements the ``DistributionsProvider`` seam (``app/factor_data/total_return.py``): given a set of
symbols and a window, fetch cash dividends and split multipliers (keyed by ex-date) from the Alpaca
corporate-actions API, so the Total-Return Adapter can build total-return closes for the combined-book
cross-asset ETF sleeve. The platform's Alpaca bars are raw/unadjusted (DCAP-003); distributions are a
material part of return for bond/commodity ETFs (TLT/IEF/DBC), so the sleeve needs total-return bars.

Why Alpaca and not Sharadar: the Sharadar ``actions`` table has zero coverage for the cross-asset ETFs
(they are absent from ``actions`` and ``sep`` alike) — Alpaca is the only live source for these symbols.
The original deferral ("Norton blocks data.alpaca.markets", ``total_return.py``) was laptop-only; the
live runtime is AWS, where the fetch works.

Discipline (mirrors ``SharadarProvider`` / ``bar_cache``):
- **Read-only.** Never touches the order path, risk engine, or DB. Pure market-data read.
- **Fail-open.** Any error after bounded retry yields empty series, so the adapter degrades to raw
  closes and a rebalance never breaks. ``prefetch`` never raises.
- **Validated.** Every record is checked before it can affect a price (see ``_parse_and_validate``);
  malformed records are dropped-and-counted, not propagated.
- **OS-trust-store TLS** injected before any HTTPS (ADR 0017), a no-op on the box.

One batched fetch (all symbols) per rebalance; results are grouped by symbol and cached on the instance
for the life of that rebalance (see the design doc for the cache lifecycle). The concerns
(fetch / retry / validate / group / cache) are intentionally kept as named private methods on one class
— a layered decomposition would be over-engineering for a 9-symbol weekly fetch (design doc §8 note 11).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
import structlog

from app.brokers.alpaca.credentials import load_credentials
from app.observability import metrics
from app.utils.tls_trust import enable_os_trust_store

logger = structlog.get_logger(__name__)

# Transient-failure retry (mirrors SharadarProvider._get_with_retry, but shorter: one weekly fetch,
# not a broad-universe ingest). Retry transport errors / 429 / 5xx; 4xx (auth/bad-request) fail fast.
_MAX_RETRIES = 2
_RETRY_BACKOFF_BASE = 0.5  # seconds → 0.5, 1.0
_DEFAULT_TIMEOUT_S = 10.0
_LATENCY_TARGET_S = 2.0  # above this we log a warning (operational SLO; see design doc §4.1)

_PROVIDER = "alpaca"


@dataclass
class FetchSummary:
    """Metadata about one batched fetch — the evidence payload the strategy logs per rebalance."""

    provider: str
    provider_sdk: str
    fetched_at: str
    window: tuple[str, str]
    symbols: int
    dividends: int
    splits: int
    rejected: int
    elapsed_ms: int
    fallback: bool


def _attr(item: Any, name: str) -> Any:
    """Read ``name`` from a pydantic model or a plain dict (tests pass dicts)."""
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def _to_ts(value: Any) -> pd.Timestamp | None:
    """Coerce a date/datetime/str to a normalized (tz-naive, midnight) Timestamp; None if unparseable."""
    if value is None:
        return None
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.normalize()


class AlpacaDistributionsProvider:
    """Fetch + validate + group + cache corporate-action distributions for the total-return adapter.

    ``client`` is injectable so tests run offline with a fake exposing ``get_corporate_actions(req)``.
    Cache is per-instance, in-memory, single-rebalance (see design doc §4.1 cache lifecycle).
    """

    def __init__(self, client: Any | None = None, *, timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        self._client = client
        self._timeout_s = timeout_s
        self._cache: dict[str, tuple[pd.Series, pd.Series]] = {}

    # -- public surface -------------------------------------------------------

    async def prefetch(
        self, symbols: list[str], start: pd.Timestamp | date, end: pd.Timestamp | date
    ) -> FetchSummary:
        """One batched, retried, validated fetch for all ``symbols``; populate the cache. Never raises.

        Returns a ``FetchSummary`` for the evidence signal; on failure ``fallback=True`` and the cache
        is left empty (⇒ every symbol yields raw pricing)."""
        syms = sorted({s.upper() for s in symbols})
        start_ts, end_ts = _to_ts(start), _to_ts(end)
        metrics.distribution_requests_total.labels(provider=_PROVIDER).inc()
        t0 = time.perf_counter()
        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, self._fetch_sync, syms, start, end)
            elapsed = time.perf_counter() - t0
            self._cache, n_div, n_split, n_rej = self._parse_and_validate(data, syms, start_ts, end_ts)
        except Exception as exc:  # fail-open — degrade to raw closes
            elapsed = time.perf_counter() - t0
            self._cache = {}
            metrics.distribution_failures_total.labels(provider=_PROVIDER).inc()
            logger.warning("distributions_fetch_failed", provider=_PROVIDER,
                           symbols=len(syms), error=str(exc)[:200])
            return self._summary(syms, start_ts, end_ts, 0, 0, 0, elapsed, fallback=True)

        metrics.distribution_fetch_seconds.labels(provider=_PROVIDER).observe(elapsed)
        for kind, n in (("dividend", n_div), ("split", n_split), ("rejected", n_rej)):
            if n:
                metrics.distribution_records_total.labels(provider=_PROVIDER, kind=kind).inc(n)
        if elapsed > _LATENCY_TARGET_S:
            logger.warning("distributions_fetch_slow", provider=_PROVIDER,
                           elapsed_ms=int(elapsed * 1000), target_ms=int(_LATENCY_TARGET_S * 1000))
        return self._summary(syms, start_ts, end_ts, n_div, n_split, n_rej, elapsed, fallback=False)

    def distributions(
        self, symbol: str, start: pd.Timestamp, end: pd.Timestamp
    ) -> tuple[pd.Series, pd.Series]:
        """Return ``(dividends, splits)`` for ``symbol`` from the prefetched cache; empty series if
        absent/invalid. ``start``/``end`` are accepted for Protocol conformance (the batched prefetch
        already bounded the window)."""
        div, spl = self._cache.get(symbol.upper(), (None, None))
        if div is None or spl is None:
            empty = pd.Series(dtype="float64")
            return empty, empty.copy()
        return div, spl

    # -- internals ------------------------------------------------------------

    def _build_client(self) -> Any:
        """Lazily construct the live Alpaca corporate-actions client (creds + OS-trust-store TLS)."""
        if self._client is not None:
            return self._client
        from alpaca.data.historical.corporate_actions import CorporateActionsClient

        enable_os_trust_store()  # ADR 0017 — idempotent; no-op once injected
        creds = load_credentials()
        self._client = CorporateActionsClient(api_key=creds.api_key, secret_key=creds.api_secret)
        return self._client

    def _fetch_sync(self, symbols: list[str], start: Any, end: Any) -> dict[str, list[Any]]:
        """Blocking batched corp-actions fetch with bounded retry. Runs in an executor thread.

        Retries transport errors / 429 / 5xx; non-transient 4xx (auth) fail fast. Returns the
        ``{category: [items]}`` data mapping."""
        from alpaca.data.requests import CorporateActionsRequest

        client = self._build_client()
        req = CorporateActionsRequest(symbols=list(symbols), start=start, end=end)
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = client.get_corporate_actions(req)
                data = getattr(resp, "data", resp)
                return data if isinstance(data, dict) else {}
            except Exception as exc:  # noqa: BLE001 — classify, then retry-or-raise
                last_exc = exc
                if not _is_transient(exc) or attempt >= _MAX_RETRIES:
                    raise
                sleep_s = _RETRY_BACKOFF_BASE * (2**attempt)
                logger.warning("distributions_fetch_retry", provider=_PROVIDER,
                               attempt=attempt + 1, sleep_s=sleep_s, error=str(exc)[:160])
                time.sleep(sleep_s)
        raise last_exc if last_exc else RuntimeError("unreachable")  # pragma: no cover

    def _parse_and_validate(
        self, data: dict[str, list[Any]], symbols: list[str],
        start: pd.Timestamp | None, end: pd.Timestamp | None,
    ) -> tuple[dict[str, tuple[pd.Series, pd.Series]], int, int, int]:
        """Group cash dividends + splits by symbol into per-ex-date series, dropping invalid records.

        Validation (drop-and-count, never raise): dividend rate finite & >= 0; split new_rate>0 &
        old_rate>0; ex_date present & within [start, end]; de-duplicate ex_date (keep last by
        process_date); series sorted ascending; no NaN. Returns (cache, n_div, n_split, n_rejected)."""
        allowed = {s.upper() for s in symbols}
        # symbol -> ex_date -> (value, process_date) ; dedup keeps the latest-processed record
        divs: dict[str, dict[pd.Timestamp, tuple[float, pd.Timestamp]]] = {}
        splits: dict[str, dict[pd.Timestamp, tuple[float, pd.Timestamp]]] = {}
        n_rej = 0

        def _in_window(ex: pd.Timestamp | None) -> bool:
            if ex is None:
                return False
            if start is not None and ex < start:
                return False
            return not (end is not None and ex > end)

        def _keep(bucket: dict[str, dict[pd.Timestamp, tuple[float, pd.Timestamp]]],
                  sym: str, ex: pd.Timestamp, value: float, proc: pd.Timestamp | None) -> None:
            proc = proc if proc is not None else ex
            prior = bucket.setdefault(sym, {}).get(ex)
            if prior is None or proc >= prior[1]:
                bucket[sym][ex] = (value, proc)

        # --- cash dividends ---
        for item in data.get("cash_dividends", []) or []:
            sym = str(_attr(item, "symbol") or "").upper()
            ex = _to_ts(_attr(item, "ex_date"))
            rate = _attr(item, "rate")
            try:
                rate_f = float(rate)
            except (TypeError, ValueError):
                rate_f = float("nan")
            if sym not in allowed or not _in_window(ex) or not pd.notna(rate_f) or rate_f < 0:
                n_rej += 1
                continue
            _keep(divs, sym, ex, rate_f, _to_ts(_attr(item, "process_date")))

        # --- splits (forward + reverse); multiplier s = new_rate / old_rate ---
        for cat in ("forward_splits", "reverse_splits"):
            for item in data.get(cat, []) or []:
                sym = str(_attr(item, "symbol") or "").upper()
                ex = _to_ts(_attr(item, "ex_date"))
                try:
                    new_r, old_r = float(_attr(item, "new_rate")), float(_attr(item, "old_rate"))
                except (TypeError, ValueError):
                    new_r, old_r = float("nan"), float("nan")
                if (sym not in allowed or not _in_window(ex) or not (pd.notna(new_r) and pd.notna(old_r))
                        or new_r <= 0 or old_r <= 0):
                    n_rej += 1
                    continue
                _keep(splits, sym, ex, new_r / old_r, _to_ts(_attr(item, "process_date")))

        cache: dict[str, tuple[pd.Series, pd.Series]] = {}
        n_div = n_split = 0
        for sym in allowed:
            dser = self._series(divs.get(sym, {}))
            sser = self._series(splits.get(sym, {}))
            n_div += len(dser)
            n_split += len(sser)
            cache[sym] = (dser, sser)
        return cache, n_div, n_split, n_rej

    @staticmethod
    def _series(by_ex: dict[pd.Timestamp, tuple[float, pd.Timestamp]]) -> pd.Series:
        """Build a sorted, NaN-free ex_date -> value series from the dedup bucket."""
        if not by_ex:
            return pd.Series(dtype="float64")
        s = pd.Series({ex: v for ex, (v, _proc) in by_ex.items()}, dtype="float64").sort_index()
        return s[s.notna()]

    @staticmethod
    def _summary(symbols: list[str], start: pd.Timestamp | None, end: pd.Timestamp | None,
                 n_div: int, n_split: int, n_rej: int, elapsed_s: float, *, fallback: bool
                 ) -> FetchSummary:
        import alpaca

        return FetchSummary(
            provider=_PROVIDER,
            provider_sdk=f"alpaca-py {getattr(alpaca, '__version__', '?')}",
            fetched_at=datetime.now(UTC).isoformat(),
            window=(start.date().isoformat() if start is not None else "",
                    end.date().isoformat() if end is not None else ""),
            symbols=len(symbols),
            dividends=n_div,
            splits=n_split,
            rejected=n_rej,
            elapsed_ms=int(elapsed_s * 1000),
            fallback=fallback,
        )


def _is_transient(exc: Exception) -> bool:
    """Retry transport/timeout errors and HTTP 429/5xx; treat other 4xx (auth/bad-request) as fatal.

    Unknown exceptions default to transient (network hiccup) so a flaky connection is retried rather
    than immediately failing open."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(exc, "code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    return True
