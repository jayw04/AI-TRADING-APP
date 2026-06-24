"""Sector-rotation factor engine (SEC-001): sector-neutral top-K momentum baskets.

The factor-library home for the SEC-001 V2 construction (promoted from
``scripts/sector_rotation_v2_research.py`` so the Factor Lab can run it as a config).
Two public surfaces, both PIT/deterministic/prices-only:

- ``sector_scores`` — each ticker scored by **its sector's** mean 12-1 momentum (the
  cross-section used for the diversification correlation + blend, like a single-factor
  score frame).
- ``sector_basket_weights`` — the **book construction**: the top-K strongest sectors as
  sector-neutral equal-weight baskets (each sector a 1/K sleeve, equal-weight within),
  weights summing to 1.

Faithful to the validated V2 research; no order path / broker / DB / LLM.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

import pandas as pd

from app.factor_data.factors.engine import DEFAULT_MIN_NAMES, FactorUnavailable
from app.factor_data.factors.momentum import compute_momentum_batch
from app.factor_data.store import FactorDataStore
from app.factor_data.universe import universe_asof

# Frozen from SEC-001 V2 (identical to V1's signal): 12-1 sector momentum.
DEFAULT_LOOKBACK_DAYS = 252
DEFAULT_SKIP_DAYS = 21


def _sector_ranking(
    store: FactorDataStore, as_of: date, *, n: int, lookback_days: int, skip_days: int,
    min_names: int,
) -> tuple[list[str], dict[str, list[str]], dict[str, float], dict[str, str | None]]:
    """(sectors ranked strong→weak, {sector: names}, {sector: mean momentum}, {ticker: sector}).

    Each sector's score is the **mean** 12-1 momentum of its names (not max — a sector
    with one spiky name doesn't out-rank a uniformly-strong one). Raises FactorUnavailable
    on a degenerate cross-section."""
    tickers = universe_asof(store, as_of, n=n)
    if len(tickers) < min_names:
        raise FactorUnavailable(f"sector universe too thin at {as_of}: {len(tickers)}")
    sectors = store.get_sectors(tickers)
    mom = compute_momentum_batch(store, tickers, as_of, lookback_days=lookback_days, skip_days=skip_days)
    moms_by_sector: dict[str, list[float]] = defaultdict(list)
    names_by_sector: dict[str, list[str]] = defaultdict(list)
    for t in tickers:
        s, m = sectors.get(t), mom.get(t)
        if s is not None and m is not None:
            moms_by_sector[s].append(m)
            names_by_sector[s].append(t)
    if not moms_by_sector:
        raise FactorUnavailable(f"no sectored names with momentum at {as_of}")
    sec_mom = {s: sum(v) / len(v) for s, v in moms_by_sector.items()}
    ranked = sorted(sec_mom, key=lambda s: sec_mom[s], reverse=True)
    return ranked, dict(names_by_sector), sec_mom, sectors


def sector_ranking(
    store: FactorDataStore, as_of: date, *, n: int = 500,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS, skip_days: int = DEFAULT_SKIP_DAYS,
    min_names: int = DEFAULT_MIN_NAMES,
) -> tuple[list[str], dict[str, list[str]], dict[str, float]]:
    """(sectors ranked strong→weak, {sector: names}, {sector: mean momentum}) at `as_of`.

    The public, cacheable ranking the basket/V1 book constructions are built from — the
    Factor Lab runner precomputes this once per rebalance, then slices it for the K-band,
    the all-sector control, walk-forward and cost sweep (matching the bespoke harness)."""
    ranked, names_by_sector, sec_mom, _sectors = _sector_ranking(
        store, as_of, n=n, lookback_days=lookback_days, skip_days=skip_days, min_names=min_names)
    return ranked, names_by_sector, sec_mom


def basket_weights_from_ranking(
    ranked: list[str], names_by_sector: dict[str, list[str]], *, k: int,
) -> dict[str, float]:
    """Top-K sector-neutral equal-weight baskets from a precomputed ranking (the SEC-001
    V2 construction). Each of the K strongest sectors gets a 1/K sleeve, equal-weight
    within → a name's weight = (1/K)·(1/n_sector). Σ=1, long-only. K ≥ #sectors → all
    sectors. Returns {} when no chosen sector has names."""
    chosen = [s for s in ranked[:k] if names_by_sector.get(s)]
    if not chosen:
        return {}
    sleeve = 1.0 / len(chosen)
    weights: dict[str, float] = {}
    for s in chosen:
        names = names_by_sector[s]
        per = sleeve / len(names)
        for t in names:
            weights[t] = weights.get(t, 0.0) + per
    return weights


def v1_quantile_weights_from_ranking(
    names_by_sector: dict[str, list[str]], sec_mom: dict[str, float], *, top_q: float = 0.20,
) -> dict[str, float]:
    """SEC-001 V1 stock-level book from a precomputed ranking: score each ticker by ITS
    sector's momentum, hold the top-quantile equal-weight. For the H3 construction-
    isolation comparison (V2 baskets vs V1 stock-level). Σ=1, long-only; {} if empty."""
    scored: list[tuple[str, float]] = [
        (t, sec_mom[s]) for s, names in names_by_sector.items() for t in names
    ]
    if not scored:
        return {}
    scored.sort(key=lambda x: x[1], reverse=True)
    k = max(1, math.ceil(len(scored) * top_q))
    chosen = [t for t, _ in scored[:k]]
    w = 1.0 / len(chosen)
    return {t: w for t in chosen}


def sector_scores(
    store: FactorDataStore, as_of: date, *, n: int = 500,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS, skip_days: int = DEFAULT_SKIP_DAYS,
    min_names: int = DEFAULT_MIN_NAMES,
) -> pd.DataFrame:
    """Per-ticker score = its sector's mean 12-1 momentum (sorted desc). PIT, deterministic.

    The cross-section for the diversification correlation + blend (the book itself is built
    by ``sector_basket_weights``)."""
    ranked, names_by_sector, sec_mom, sectors = _sector_ranking(
        store, as_of, n=n, lookback_days=lookback_days, skip_days=skip_days, min_names=min_names)
    scores: dict[str, float] = {}
    for s in ranked:
        for t in names_by_sector[s]:
            scores[t] = sec_mom[s]
    ser = pd.Series(scores, name="score", dtype="float64").sort_index()
    ser.index.name = "ticker"
    return pd.DataFrame({"score": ser}).sort_values("score", ascending=False, kind="stable")


def sector_basket_weights(
    store: FactorDataStore, as_of: date, *, n: int = 500, k: int = 3,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS, skip_days: int = DEFAULT_SKIP_DAYS,
    min_names: int = DEFAULT_MIN_NAMES,
) -> dict[str, float]:
    """Top-K strongest sectors as sector-neutral equal-weight baskets (the V2 construction).

    Each of the K chosen sectors gets a 1/K sleeve, equal-weight within → a name's weight =
    (1/K)·(1/n_sector). Weights sum to 1 (long-only, fully invested). K ≥ #sectors → all
    sectors. Returns {} when the cross-section is too thin (the sim skips that rebalance)."""
    try:
        ranked, names_by_sector, _sec_mom = sector_ranking(
            store, as_of, n=n, lookback_days=lookback_days, skip_days=skip_days, min_names=min_names)
    except FactorUnavailable:
        return {}
    return basket_weights_from_ranking(ranked, names_by_sector, k=k)
