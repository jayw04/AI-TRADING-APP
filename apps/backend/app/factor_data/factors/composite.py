"""Composite multi-factor scoring (P12 §3).

Blends several standardized factors (momentum + value/quality) into one cross-sectional
``score`` — the piece the single-factor ``engine.momentum_scores`` did not provide. Each factor's
raw cross-section is winsorized + z-scored over the universe (the existing ``cross_section``
helpers), then the z-scores are blended (equal-weight by default) and ranked. Point-in-time and
deterministic: identical store + args → identical ranking.

> **Honest defaults (P12 §3 OQ2/OQ3):** equal-weight z-scores (no in-sample optimization); a name
> missing a factor is **mean-imputed to z=0** for the composite (so momentum-only names aren't
> dropped) or **dropped** for a pure single-factor study — selectable via ``missing``.

Factors:
- ``"momentum"`` — the 6-1 price factor (``compute_momentum_batch``).
- any of ``FUNDAMENTAL_FACTORS`` — value/quality, PIT via ``accepted_date`` (``fundamental`` module).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.factor_data.factors.cross_section import winsorize, zscore
from app.factor_data.factors.engine import FactorUnavailable
from app.factor_data.factors.fundamental import (
    FUNDAMENTAL_FACTORS,
    build_fundamental_factor_matrices,
)
from app.factor_data.factors.momentum import (
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_SKIP_DAYS,
    compute_momentum_batch,
)
from app.factor_data.store import FactorDataStore
from app.factor_data.universe import universe_asof

MOMENTUM = "momentum"


def _momentum_raw(store: FactorDataStore, as_of: date, tickers: list[str], *,
                  lookback_days: int, skip_days: int) -> dict[str, float]:
    batch = compute_momentum_batch(store, tickers, as_of,
                                   lookback_days=lookback_days, skip_days=skip_days)
    return {t: v for t, v in batch.items() if v is not None}


def _fundamental_raw(store: FactorDataStore, as_of: date, tickers: list[str],
                     factors: list[str]) -> dict[str, dict[str, float]]:
    """Raw value/quality factor values for ``tickers`` at ``as_of`` (PIT). Reuses the pure
    ``build_fundamental_factor_matrices`` over a single rebalance date."""
    rows: list[dict] = []
    closes: dict[str, pd.Series] = {}
    for t in tickers:
        f = store.get_fundamentals(t, as_of=as_of)
        for _, r in f.iterrows():
            d = r.to_dict()
            d["ticker"] = t
            rows.append(d)
        p = store.get_prices(t, as_of - timedelta(days=10), as_of, adjusted=True)
        if not p.empty:
            closes[t] = p.set_index("date")["close"]
    if not rows or not closes:
        return {fac: {} for fac in factors}
    fundamentals = pd.DataFrame(rows)
    close = pd.DataFrame(closes)
    close.index = pd.to_datetime(close.index)
    mats = build_fundamental_factor_matrices(fundamentals, close, [pd.Timestamp(as_of)])
    out: dict[str, dict[str, float]] = {}
    for fac in factors:
        m = mats.get(fac, pd.DataFrame())
        if m.empty:
            out[fac] = {}
            continue
        row = m.iloc[-1]
        out[fac] = {t: float(row[t]) for t in row.index if pd.notna(row[t])}
    return out


def composite_scores(
    store: FactorDataStore,
    as_of: date,
    *,
    factors: list[str],
    weights: dict[str, float] | None = None,
    n: int = 500,
    min_names: int = 20,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    skip_days: int = DEFAULT_SKIP_DAYS,
    missing: str = "impute",
) -> pd.DataFrame:
    """Rank the ``as_of`` universe by a blended z-score of ``factors``.

    Per factor: raw cross-section → winsorize → z-score over the universe. Blend (``weights`` or
    equal) → composite ``score`` → sort descending. ``missing="impute"`` fills an absent factor
    with z=0; ``"drop"`` keeps only names with every factor present. Raises ``FactorUnavailable``
    if fewer than ``min_names`` names survive.
    """
    if not factors:
        raise ValueError("composite_scores needs at least one factor")
    bad = [f for f in factors if f != MOMENTUM and f not in FUNDAMENTAL_FACTORS]
    if bad:
        raise ValueError(f"unknown factor(s): {bad}")
    if missing not in ("impute", "drop"):
        raise ValueError("missing must be 'impute' or 'drop'")

    tickers = universe_asof(store, as_of, n=n)
    if len(tickers) < min_names:
        raise FactorUnavailable(f"universe too thin at {as_of}: {len(tickers)} < {min_names}")

    raw: dict[str, dict[str, float]] = {}
    if MOMENTUM in factors:
        raw[MOMENTUM] = _momentum_raw(store, as_of, tickers,
                                      lookback_days=lookback_days, skip_days=skip_days)
    fund = [f for f in factors if f in FUNDAMENTAL_FACTORS]
    if fund:
        raw.update(_fundamental_raw(store, as_of, tickers, fund))

    # z-score each factor over the universe cross-section
    zs: dict[str, pd.Series] = {}
    for fac in factors:
        s = pd.Series(raw.get(fac, {}), dtype="float64").reindex(tickers)
        zs[fac] = zscore(winsorize(s))
    zmat = pd.DataFrame(zs)
    zmat = zmat.fillna(0.0) if missing == "impute" else zmat.dropna(how="any")

    w = weights or {f: 1.0 / len(factors) for f in factors}
    composite = sum(zmat[f] * float(w.get(f, 0.0)) for f in factors)
    df = pd.DataFrame({"score": composite}).dropna()
    df = df.sort_values(["score"], ascending=False, kind="stable")
    df = df.reindex(sorted(df.index, key=lambda t: (-df.at[t, "score"], t)))
    if len(df) < min_names:
        raise FactorUnavailable(f"composite too thin at {as_of}: {len(df)} < {min_names}")
    return df
