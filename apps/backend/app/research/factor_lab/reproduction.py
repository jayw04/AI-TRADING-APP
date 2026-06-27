"""PORT-001 reproduction engine (the §2 reproduce-first core; ADR 0030 #4).

Turns the built-but-data-gated PCE into a runnable reproduction: backtest each sleeve into a
daily return series, ERC-blend them into the Workbench Evidence Package, and compare it to the
**sibling reference** through the objective **Onboarding Gate**. On pass (within tolerance,
drift attributed), the capability advances L1→L2.

Pure / deterministic over the inputs:
  - ``backtest_cross_asset_sleeve`` rolls the §1 cross-asset TSMOM sleeve over a total-return
    panel → its daily return series (tested with a synthetic panel).
  - ``run_reproduction`` blends the sleeve return series + compares to the reference (tested
    with synthetic sleeves + a matching reference).

The *real* sleeve return series (equity momentum over the Sharadar store; cross-asset over the
§1 Total-Return Adapter) are built by the CLI harness `scripts/run_port001_reproduction.py` on
a non-Norton machine with the data. This module is the engine that harness drives.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.research.factor_lab.cross_asset import cross_asset_tsmom
from app.research.factor_lab.onboarding_gate import GateResult, onboarding_gate
from app.research.factor_lab.portfolio import construct_portfolio, portfolio_evidence_package
from app.research.factor_lab.spec import VerdictSpec


def cross_asset_rebalance_weights(
    panel: pd.DataFrame, *, rebalance_freq: str = "W-FRI", **sleeve_kwargs: Any
) -> pd.DataFrame:
    """Per-rebalance as-of sleeve weights (rows = panel dates, cols = tickers): the cross-asset
    TSMOM weights recomputed at each rebalance date, NaN before the first qualifying rebalance.
    The basis for both ``backtest_cross_asset_sleeve`` (ffill → held weights) and the harness's
    internal-weights/trade-count needs. Pure."""
    px = panel.sort_index()
    cols = list(px.columns)
    reb_dates = pd.Series(px.index, index=px.index).resample(rebalance_freq).last().dropna()
    weights = pd.DataFrame(index=px.index, columns=cols, dtype=float)  # NaN until first rebalance
    for d in reb_dates:
        pos = int(px.index.get_loc(d))
        sleeve = cross_asset_tsmom(px, asof=pos, **sleeve_kwargs)
        if sleeve.status == "ok":
            weights.loc[d] = [sleeve.weights.get(c, 0.0) for c in cols]
    return weights


def backtest_cross_asset_sleeve(
    panel: pd.DataFrame, *, rebalance_freq: str = "W-FRI", **sleeve_kwargs: Any
) -> pd.Series:
    """Roll the cross-asset TSMOM sleeve over a **total-return** price panel → the sleeve's daily
    return series. At each rebalance date the as-of weights are computed and held until the next
    rebalance; daily return = Σ (prior-day weights × asset daily total-returns). Pure."""
    px = panel.sort_index()
    rets = px.pct_change().fillna(0.0)
    weights = cross_asset_rebalance_weights(px, rebalance_freq=rebalance_freq, **sleeve_kwargs)
    weights = weights.ffill().fillna(0.0)  # hold weights between rebalances; cash before the first
    return (weights.shift(1).fillna(0.0) * rets).sum(axis=1)


def _aligned(ref: dict[str, float], cand: dict[str, float]) -> tuple[np.ndarray, np.ndarray]:
    """Align two {symbol: weight} maps onto the union of symbols (absent → 0) for weight corr.
    Symbol keys are upper-cased first: ``construct_portfolio`` canonicalizes tickers to upper
    case, so a reference keyed in any case must still align (else identical books anti-correlate)."""
    ru = {str(k).upper(): float(v) for k, v in ref.items()}
    cu = {str(k).upper(): float(v) for k, v in cand.items()}
    keys = sorted(set(ru) | set(cu))
    return (np.array([ru.get(k, 0.0) for k in keys]),
            np.array([cu.get(k, 0.0) for k in keys]))


def run_reproduction(
    *,
    sleeve_returns: pd.DataFrame,
    sleeve_internal_weights: dict[str, dict[str, float]],
    equity_sleeve: str,
    reference: dict[str, Any],
    cand_trades: int,
    regime: str = "GREEN",
    initial_equity: float = 100_000.0,
    deterministic: bool = True,
    verdict: VerdictSpec | None = None,
) -> dict[str, Any]:
    """Build the Workbench Evidence Package from the sleeve returns and run the Onboarding Gate
    against the sibling ``reference`` (keys: ``sharpe``, ``max_drawdown``, ``trades``,
    ``daily_returns`` {date: ret}, ``weights`` {symbol: weight}). Returns the package, the gate
    result, and the pass/fail. Pure/deterministic."""
    pkg = portfolio_evidence_package(
        sleeve_returns, sleeve_internal_weights, equity_sleeve=equity_sleeve,
        regime=regime, initial_equity=initial_equity, verdict=verdict,
    )
    m = pkg["metrics"]

    # the Workbench combined daily-return series (for the daily-return correlation criterion)
    book = construct_portfolio(
        sleeve_returns, sleeve_internal_weights, equity_sleeve=equity_sleeve, regime=regime,
    )
    cols = list(sleeve_returns.columns)
    w = np.array([book.sleeve_weights.get(s, 0.0) for s in cols], dtype=float)
    cand_daily = pd.Series(
        book.regime_multiplier * (sleeve_returns[cols].to_numpy(dtype=float) @ w),
        index=sleeve_returns.index,
    )

    ref_w, cand_w = _aligned(reference.get("weights", {}), book.weights)
    ref_daily = pd.Series(reference.get("daily_returns", {}), dtype=float)
    if not ref_daily.empty:
        ref_daily.index = pd.to_datetime(ref_daily.index)  # align ISO-date keys to cand timestamps
    gate: GateResult = onboarding_gate(
        ref_sharpe=float(reference["sharpe"]), cand_sharpe=float(m["sharpe"]),
        # compare drawdown MAGNITUDES — be robust to the caller's sign convention (the candidate
        # package reports max_drawdown as a negative fraction; references may be either sign).
        ref_maxdd=abs(float(reference["max_drawdown"])), cand_maxdd=abs(float(m["max_drawdown"])),
        ref_daily_returns=ref_daily,
        cand_daily_returns=cand_daily,
        ref_weights=ref_w, cand_weights=cand_w,
        ref_trades=int(reference["trades"]), cand_trades=int(cand_trades),
        deterministic=deterministic,
    )
    return {
        "evidence_package": pkg,
        "gate": gate.as_scorecard(),
        "passed": gate.passed,
        "candidate": {"sharpe": m["sharpe"], "max_drawdown": m["max_drawdown"],
                      "trades": int(cand_trades)},
        "reference": {"sharpe": reference["sharpe"], "max_drawdown": reference["max_drawdown"],
                      "trades": reference["trades"]},
    }


# --------------------------------------------------------------------------- self-stack builders
# The "build the Workbench sleeves from the platform's OWN data stack" path — shared by the CLI
# harness (`--db` real mode) and the Factor Lab runner (`_run_portfolio`). Heavy deps are imported
# locally so this module stays light/research-pure at import time. The cross-asset sleeve reads
# live ETF bars (Alpaca via the bar provider) — the one network dependency, off the order path.

# Equity-momentum SleeveSpec.params → run_momentum_backtest kwargs (max_position_pct is a
# live-template per-name cap with no backtest equivalent → dropped, recorded in the package).
_EQUITY_PARAM_MAP = {
    "lookback_days": "lookback_days", "skip_days": "skip_days",
    "top_quantile": "top_quantile", "max_sector_pct": "max_sector_pct",
    "vol_target": "vol_target_annual",
}


class SharadarDistributions:
    """Concrete ``DistributionsProvider`` over the Sharadar ``actions`` table (DCAP-001), read
    through the FactorDataStore's DuckDB connection. Fail-soft: no rows (or no coverage for an
    ETF) → empty Series → the Total-Return Adapter yields a price-return leg (still valid). ⚠
    assumes the Sharadar convention: ``action`` contains 'div'/'split' and ``value`` is
    cash-per-share / the split share-multiplier."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def distributions(
        self, symbol: str, start: pd.Timestamp, end: pd.Timestamp
    ) -> tuple[pd.Series, pd.Series]:
        try:
            rows = self._store.con.execute(
                "SELECT date, action, value FROM actions "
                "WHERE ticker = ? AND date BETWEEN ? AND ? ORDER BY date",
                [symbol, pd.Timestamp(start).date(), pd.Timestamp(end).date()],
            ).fetchall()
        except Exception:  # noqa: BLE001 — missing table / sparse coverage → price-return leg
            rows = []
        div: dict[pd.Timestamp, float] = {}
        spl: dict[pd.Timestamp, float] = {}
        for d, action, value in rows:
            if value is None:
                continue
            a = str(action or "").lower()
            ts = pd.Timestamp(d)
            if "div" in a:
                div[ts] = div.get(ts, 0.0) + float(value)
            elif "split" in a:
                spl[ts] = float(value)
        return pd.Series(div, dtype="float64"), pd.Series(spl, dtype="float64")


def curve_returns(curve: list) -> pd.Series:
    """Daily simple returns from an equity curve [(date, equity), …], date-indexed, first dropped."""
    if len(curve) < 2:
        return pd.Series(dtype="float64")
    idx = pd.to_datetime([d for d, _ in curve]).normalize()
    eq = pd.Series([v for _, v in curve], index=idx, dtype="float64")
    return eq.pct_change().dropna()


def count_trades(weight_history: list[dict[str, float]], *, tol: float = 1e-6) -> int:
    """Number of position changes across a sequence of rebalance weight maps — an open, close, or
    reweight (|Δw|>tol) of any name counts as one trade."""
    prev: dict[str, float] = {}
    n = 0
    for w in weight_history:
        for name in set(w) | set(prev):
            if abs(w.get(name, 0.0) - prev.get(name, 0.0)) > tol:
                n += 1
        prev = w
    return n


def default_bar_cache() -> Any:
    """A standalone Alpaca daily-bar source (BarCache, adapter=None → builds the env-cred adapter
    lazily on fetch; rides the ADR-0017 truststore past Norton). Reuses the app's configured cache
    root so a warm cache serves history from disk."""
    from app.config import get_settings
    from app.market_data.bar_cache import BarCache

    s = get_settings()
    return BarCache(adapter=None, root=s.bars_cache_root, max_gb=s.bars_cache_max_gb)


async def build_total_return_panel(
    symbols: tuple[str, ...] | list[str], start: Any, end: Any, *,
    bar_provider: Any, dist_provider: Any,
) -> pd.DataFrame:
    """Total-return ETF price panel via the §1 Total-Return Adapter (raw bars + distributions).
    Index = naive daily timestamps, cols = tickers, values = tr_close."""
    from app.factor_data.total_return import TotalReturnAdapter

    adapter = TotalReturnAdapter(bar_provider, dist_provider)
    series: dict[str, pd.Series] = {}
    for sym in symbols:
        df = await adapter.get_total_return_bars(sym, pd.Timestamp(start), pd.Timestamp(end))
        if df is None or df.empty:
            continue
        idx = pd.to_datetime(df["t"], utc=True).dt.tz_localize(None).dt.normalize()
        series[sym] = pd.Series(df["tr_close"].to_numpy(dtype="float64"), index=idx)
    if not series:
        raise RuntimeError(
            f"no total-return bars for any cross-asset ETF (check Alpaca access). Universe={list(symbols)}.")
    return pd.DataFrame(series).sort_index().dropna(how="all")


def build_equity_sleeve(
    store: Any, params: dict[str, Any], start: Any, end: Any, n: int
) -> tuple[pd.Series, dict[str, float], int]:
    """Sleeve A — crash-protected equity momentum via run_momentum_backtest over the Sharadar
    store. Returns (daily-return Series, last-rebalance internal weights, trade count)."""
    from app.factor_data.backtest import run_momentum_backtest

    kw = {dst: params[src] for src, dst in _EQUITY_PARAM_MAP.items() if src in params}
    rep = run_momentum_backtest(store, start, end, n=n, **kw)
    curve = rep.vol_scaled_curve or rep.equity_curve  # crash-protected curve when vol-targeted
    returns = curve_returns(curve)
    internal = dict(rep.holdings[-1].weights) if rep.holdings else {}
    trades = count_trades([dict(h.weights) for h in rep.holdings])
    return returns, internal, trades


def build_cross_asset_sleeve(
    store: Any, params: dict[str, Any], start: Any, end: Any, *, bar_provider: Any
) -> tuple[pd.Series, dict[str, float], int]:
    """Sleeve B — cross-asset TSMOM over the §1 Total-Return Adapter panel. Returns (daily-return
    Series, last-rebalance internal weights, trade count)."""
    import asyncio
    from datetime import UTC, datetime

    from app.research.factor_lab.cross_asset import CROSS_ASSET_UNIVERSE

    dist = SharadarDistributions(store)
    s = start if hasattr(start, "year") else pd.Timestamp(start).date()
    e = end if hasattr(end, "year") else pd.Timestamp(end).date()
    start_dt = datetime(s.year, s.month, s.day, tzinfo=UTC)
    end_dt = datetime(e.year, e.month, e.day, tzinfo=UTC)
    panel = asyncio.run(
        build_total_return_panel(CROSS_ASSET_UNIVERSE, start_dt, end_dt,
                                 bar_provider=bar_provider, dist_provider=dist))
    kw = dict(params)
    returns = backtest_cross_asset_sleeve(panel, **kw)
    reb = cross_asset_rebalance_weights(panel, **kw).dropna(how="all")
    internal = {k: float(v) for k, v in reb.iloc[-1].items()} if not reb.empty else {}
    trades = count_trades([{k: float(v) for k, v in row.items()} for _, row in reb.iterrows()])
    return returns, internal, trades


def build_self_stack_inputs(
    spec: Any, store: Any, *, bar_provider: Any | None = None
) -> tuple[pd.DataFrame, dict[str, dict[str, float]], int]:
    """Build the Workbench sleeve return series from the platform's OWN data stack, straight off
    a portfolio ``ProgramSpec`` (so the harness, the runner, and the live config never drift):
    Sleeve A (equity momentum) over the Sharadar store; Sleeve B (cross-asset TSMOM) over the §1
    Total-Return Adapter panel (Alpaca bars + Sharadar distributions). Returns ``(sleeve_returns,
    sleeve_internal_weights, cand_trades)``. Read-only research (ADR 0019); no order path."""
    pf = spec.portfolio
    if pf is None:
        raise RuntimeError(f"{spec.id} has no PortfolioSpec")
    by_kind = {s.kind: s for s in pf.sleeves}
    eq_spec = by_kind["equity_momentum"]
    xa_spec = by_kind["cross_asset_tsmom"]
    bars = bar_provider if bar_provider is not None else default_bar_cache()

    eq_ret, eq_w, eq_trades = build_equity_sleeve(store, eq_spec.params, spec.start, spec.end, spec.n)
    xa_ret, xa_w, xa_trades = build_cross_asset_sleeve(
        store, xa_spec.params, spec.start, spec.end, bar_provider=bars)

    sleeve_returns = pd.DataFrame({eq_spec.name: eq_ret, xa_spec.name: xa_ret}).dropna()
    if sleeve_returns.empty:
        raise RuntimeError("no overlapping trading days between the equity and cross-asset sleeves")
    internal = {eq_spec.name: eq_w, xa_spec.name: xa_w}
    return sleeve_returns, internal, eq_trades + xa_trades
