"""Trend-following factor engine (TREND-001): per-name time-series trend + participation.

The factor-library home for the TREND-001 construction (promoted from
``scripts/trend_research.py`` so the Factor Lab can run it as a config). In-trend iff a
name's last close (strictly before ``as_of``) is above its ``sma_days``-day SMA — the
per-name generalization of the platform's market-regime filter. The book holds in-trend
names equal-weight at 1/N each, so gross exposure = (#in-trend / N): it de-risks to cash
in downtrends (the participation mechanism that distinguishes trend from momentum).

PIT/deterministic/prices-only; no order path / broker / DB / LLM. The 200-day window is
frozen from the validated research.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.factor_data.factors.engine import DEFAULT_MIN_NAMES, FactorUnavailable
from app.factor_data.store import FactorDataStore
from app.factor_data.universe import universe_asof

DEFAULT_SMA_DAYS = 200  # frozen = the platform's regime-filter window


def in_trend_names(
    store: FactorDataStore, as_of: date, *, n: int, sma_days: int = DEFAULT_SMA_DAYS,
) -> tuple[list[str], list[str]]:
    """(universe, in-trend subset) as of `as_of`: in-trend iff the last close strictly
    before `as_of` is above its `sma_days`-day SMA. Point-in-time, no look-ahead."""
    universe = universe_asof(store, as_of, n=n)
    in_trend: list[str] = []
    start = as_of - timedelta(days=int(sma_days * 2) + 15)  # ~70% of calendar days trade
    for t in universe:
        df = store.get_prices(t, start, as_of, adjusted=True)
        if df.empty:
            continue
        closes = [
            float(c)
            for dt, c in zip(df["date"], df["close"], strict=False)
            if c is not None and float(c) > 0 and dt.date() < as_of
        ]
        closes = closes[-sma_days:]
        if len(closes) < sma_days:
            continue
        if closes[-1] > sum(closes) / len(closes):
            in_trend.append(t)
    return universe, in_trend


def trend_weights(
    store: FactorDataStore, as_of: date, *, n: int = 500, sma_days: int = DEFAULT_SMA_DAYS,
) -> dict[str, float]:
    """Book construction: each in-trend name weighted 1/|universe| → gross = #in-trend/N,
    the remainder is cash (the participation mechanism). Σ ≤ 1; {} if the universe is empty."""
    universe, in_trend = in_trend_names(store, as_of, n=n, sma_days=sma_days)
    if not universe:
        return {}
    w = 1.0 / len(universe)
    return {t: w for t in in_trend}


def trend_scores(
    store: FactorDataStore, as_of: date, *, n: int = 500, sma_days: int = DEFAULT_SMA_DAYS,
    min_names: int = DEFAULT_MIN_NAMES,
) -> pd.DataFrame:
    """Per-name in-trend flag (1.0 in-trend / 0.0 not) as a score frame, for the
    diversification correlation. Raises FactorUnavailable on a degenerate cross-section."""
    universe, in_trend = in_trend_names(store, as_of, n=n, sma_days=sma_days)
    if len(universe) < min_names:
        raise FactorUnavailable(f"trend universe too thin at {as_of}: {len(universe)}")
    flags = {t: (1.0 if t in set(in_trend) else 0.0) for t in universe}
    ser = pd.Series(flags, name="score", dtype="float64").sort_index()
    ser.index.name = "ticker"
    return pd.DataFrame({"score": ser}).sort_values("score", ascending=False, kind="stable")
