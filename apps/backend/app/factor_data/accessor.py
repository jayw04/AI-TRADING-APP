"""Sandboxed, read-only factor accessor for strategy code (P9 §2).

`FactorAccessor` is the deliberate, reviewable extension point through which a
strategy reaches point-in-time factor data — the factor analog of how
`StrategyContext` wraps `BarCache`. It:

- holds a `FactorDataStore` opened **read-only** (a live strategy can never mutate
  the factor store, and a read handle won't contend with an ingest);
- imports no order path, no broker, and holds no DB session or network client;
- exposes only three read methods (never the raw store handle / connection /
  ingest methods);
- is point-in-time by construction: `as_of=None` resolves to the store's latest
  price date, and an `as_of` past that clamps **down** (never forward).

`store=None` means factor data is not provisioned for this run — every method
raises `FactorDataUnavailable` with a clear message, mirroring how an absent
Alpaca key degrades the bar cache rather than crashing the engine.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.factor_data.factors.engine import momentum_scores
from app.factor_data.factors.momentum import (
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_SKIP_DAYS,
    compute_momentum,
)
from app.factor_data.store import FactorDataStore
from app.factor_data.universe import universe_asof


class FactorDataUnavailable(RuntimeError):
    """Raised when a strategy reaches for factor data that is not provisioned."""


class FactorAccessor:
    """Read-only, PIT-clamped facade over a `FactorDataStore` for strategy code."""

    def __init__(self, store: FactorDataStore | None) -> None:
        self._store = store

    @property
    def store(self) -> FactorDataStore | None:
        """Read-only access to the underlying FactorDataStore (for activation jobs)."""
        return self._store

    def _require_store(self) -> FactorDataStore:
        if self._store is None:
            raise FactorDataUnavailable(
                "factor data is not provisioned for this run (no store). Ingest the "
                "Sharadar spine first — see docs/runbook/factor-data.md."
            )
        return self._store

    def _resolve_as_of(self, as_of: date | None) -> date:
        """Latest price date when `as_of` is None; clamp a future `as_of` down to it."""
        store = self._require_store()
        _, latest = store.price_date_bounds()
        if latest is None:
            raise FactorDataUnavailable("factor store has no price history; ingest first")
        if as_of is None or as_of > latest:
            return latest
        return as_of

    def momentum_scores(
        self, as_of: date | None = None, *, n: int = 500,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS, skip_days: int = DEFAULT_SKIP_DAYS,
    ) -> pd.DataFrame:
        """Cross-sectional momentum scores as of `as_of` (default: latest store date).

        `lookback_days` / `skip_days` select the momentum window (default 105/21 =
        6-1; a strategy can request e.g. 252/0 = 12-month). The window only changes
        which trailing return is ranked — the PIT/read-only guarantees are unchanged.
        """
        store = self._require_store()
        return momentum_scores(
            store, self._resolve_as_of(as_of), n=n,
            lookback_days=lookback_days, skip_days=skip_days,
        )

    def momentum_for(self, ticker: str, as_of: date | None = None) -> float | None:
        """Single-name momentum as of `as_of`; `None` if history is insufficient."""
        store = self._require_store()
        resolved = self._resolve_as_of(as_of)
        floor, _ = store.price_date_bounds()
        assert floor is not None  # _resolve_as_of would have raised otherwise
        px = store.get_prices(ticker, floor, resolved, adjusted=True)
        return compute_momentum(px, resolved)

    def universe(self, as_of: date | None = None, *, n: int = 500) -> list[str]:
        """Point-in-time tradeable universe as of `as_of` (default: latest store date)."""
        store = self._require_store()
        return universe_asof(store, self._resolve_as_of(as_of), n=n)

    def sectors(self, tickers: list[str]) -> dict[str, str | None]:
        """Sharadar sector per ticker (None if unknown) — for sector-aware
        selection (P10 §3). Reference data, so no PIT clamp; a store without the
        sector column yields all-None so callers can fail open."""
        store = self._require_store()
        return store.get_sectors(tickers)

    def market_breadth(
        self, as_of: date | None = None, *, n: int = 500, ma_days: int = 200,
    ) -> float | None:
        """Market breadth as of `as_of` (P10 §5, ADR 0022): the fraction of the
        construction universe trading above its `ma_days` MA, in [0, 1], or `None`
        when it can't be read honestly (caller fails open). PIT-clamped."""
        from app.factor_data.regime import market_breadth

        store = self._require_store()
        return market_breadth(store, self._resolve_as_of(as_of), n=n, ma_days=ma_days)

    def vix_percentile(
        self, as_of: date | None = None, *, symbol: str = "^VIX", lookback_days: int = 252,
    ) -> float | None:
        """Trailing VIX percentile as of `as_of` (P10 §5, ADR 0022): the latest VIX
        close's percentile rank within its prior `lookback_days` window, in [0, 1]
        (~1 = stress), or `None` when the series is unavailable / too short (caller
        fails open). PIT-clamped."""
        from app.factor_data.regime import vix_percentile

        store = self._require_store()
        return vix_percentile(store, self._resolve_as_of(as_of), symbol=symbol,
                              lookback_days=lookback_days)
