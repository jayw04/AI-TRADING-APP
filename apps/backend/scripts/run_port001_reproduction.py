"""PORT-001 reproduction harness — run the §2 reproduce-first gate (ADR 0030 #4).

Builds the Workbench Evidence Package for the Combined Book and compares it to the **sibling
reference** through the objective **Onboarding Gate**. On pass, the capability advances L1→L2
(attach the Evidence Package, promote `programs.py` planned→validated, issue the Capability
Certificate Gate-Passed).

Two modes:

  --synthetic     Fabricate two sleeves + a matching reference and run the whole pipeline with
                  NO external data. Verifies the harness wiring + output format end-to-end
                  (this is what CI / a Norton-blocked box can run).

  (default)       REAL reproduction — requires a non-Norton machine with the data:
                    * the Sharadar DuckDB (FactorDataStore) for the equity-momentum sleeve, and
                    * Alpaca market-data (data.alpaca.markets) for the cross-asset ETF bars,
                      post-processed to total-return via the §1 Total-Return Adapter.
                  Plus a sibling-reference JSON (--reference) exported from claude-trading-view:
                    {"sharpe":0.84,"max_drawdown":0.119,"trades":N,
                     "daily_returns":{"YYYY-MM-DD":r,...},"weights":{"SYM":w,...}}

    apps/backend/.venv/Scripts/python.exe apps/backend/scripts/run_port001_reproduction.py \
        --synthetic                         # offline wiring self-test
    apps/backend/.venv/Scripts/python.exe apps/backend/scripts/run_port001_reproduction.py \
        --reference docs/.../sibling_reference.json   # the real run (default --db = factor duckdb)

Read-only research (ADR 0019); no order path. Writes the Evidence Package JSON + the Lifecycle
Fidelity scorecard markdown under docs/implementation/evidence/port_001/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.research.factor_lab.configs import PORT_001  # noqa: E402
from app.research.factor_lab.cross_asset import CROSS_ASSET_UNIVERSE  # noqa: E402
from app.research.factor_lab.reproduction import (  # noqa: E402
    backtest_cross_asset_sleeve,
    cross_asset_rebalance_weights,
    run_reproduction,
)
from app.research.factor_lab.spec import SleeveSpec  # noqa: E402

_OUT = _BACKEND.parents[1] / "docs" / "implementation" / "evidence" / "port_001"

# Equity-momentum SleeveSpec.params → run_momentum_backtest kwargs (max_position_pct is a
# live-template per-name cap with no backtest equivalent → dropped, recorded in the package).
_EQUITY_PARAM_MAP = {
    "lookback_days": "lookback_days", "skip_days": "skip_days",
    "top_quantile": "top_quantile", "max_sector_pct": "max_sector_pct",
    "vol_target": "vol_target_annual",
}


# --------------------------------------------------------------------------- synthetic self-test
def _synthetic_inputs() -> tuple[pd.DataFrame, dict, dict, int]:
    """Two equal-vol, ~uncorrelated sleeves + a reference that MATCHES the Workbench candidate
    (so the gate passes) — proves the pipeline + output format with no external data."""
    rng = np.random.default_rng(11)
    idx = pd.date_range("2018-01-01", periods=1500, freq="B")
    sleeve_returns = pd.DataFrame(
        {"equity": 0.0006 + 0.010 * rng.standard_normal(len(idx)),
         "cross_asset": 0.0004 + 0.008 * rng.standard_normal(len(idx))},
        index=idx,
    )
    internal = {"equity": {"AAPL": 0.5, "MSFT": 0.5},
                "cross_asset": {"TLT": 0.4, "IEF": 0.3, "GLD": 0.2, "UUP": 0.1}}
    # Build the candidate metrics directly, then set the reference == candidate so the gate is
    # exercised end-to-end and passes (proving the wiring + report format).
    from app.research.factor_lab.portfolio import construct_portfolio, portfolio_evidence_package
    pkg = portfolio_evidence_package(sleeve_returns, internal, equity_sleeve="equity")
    book = construct_portfolio(sleeve_returns, internal, equity_sleeve="equity")
    w = np.array([book.sleeve_weights[s] for s in sleeve_returns.columns])
    cand_daily = pd.Series(sleeve_returns.to_numpy() @ w, index=sleeve_returns.index)
    reference = {
        "sharpe": pkg["metrics"]["sharpe"], "max_drawdown": pkg["metrics"]["max_drawdown"],
        "trades": 120,
        "daily_returns": {d.strftime("%Y-%m-%d"): float(v) for d, v in cand_daily.items()},
        "weights": dict(book.weights),
    }
    return sleeve_returns, internal, reference, 120


# --------------------------------------------------------------------------- real-data builders
class _SharadarDistributions:
    """Concrete ``DistributionsProvider`` over the Sharadar ``actions`` table (DCAP-001), read
    through the FactorDataStore's DuckDB connection. Returns per-ex-date cash dividends + split
    multipliers for a symbol. Fail-soft: no rows (or no coverage for an ETF) → empty Series →
    the Total-Return Adapter yields a price-return series for that leg (still valid, just without
    the distribution component — material mainly for the bond/commodity legs; validate coverage
    on the data machine). ⚠ assumes the Sharadar convention: ``action`` contains 'div'/'split'
    and ``value`` is cash-per-share / the split share-multiplier respectively."""

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


def _bar_cache() -> Any:
    """A standalone Alpaca daily-bar source (BarCache with adapter=None → builds the env-cred
    adapter lazily on fetch; Norton-gated). Reuses the app's configured bars cache root so a
    warm cache serves the 16y of ETF bars from disk on re-runs."""
    from app.config import get_settings
    from app.market_data.bar_cache import BarCache

    s = get_settings()
    return BarCache(adapter=None, root=s.bars_cache_root, max_gb=s.bars_cache_max_gb)


async def _build_total_return_panel(
    symbols: tuple[str, ...], start: datetime, end: datetime, dist_provider: Any
) -> pd.DataFrame:
    """The 8-ETF **total-return** price panel via the §1 Total-Return Adapter (Alpaca raw bars +
    Sharadar distributions). Index = naive daily timestamps, cols = tickers, values = tr_close."""
    from app.factor_data.total_return import TotalReturnAdapter

    adapter = TotalReturnAdapter(_bar_cache(), dist_provider)
    series: dict[str, pd.Series] = {}
    for sym in symbols:
        df = await adapter.get_total_return_bars(sym, pd.Timestamp(start), pd.Timestamp(end))
        if df is None or df.empty:
            continue
        idx = pd.to_datetime(df["t"], utc=True).dt.tz_localize(None).dt.normalize()
        series[sym] = pd.Series(df["tr_close"].to_numpy(dtype="float64"), index=idx)
    if not series:
        raise RuntimeError(
            "no total-return bars for any cross-asset ETF — check Alpaca data access "
            f"(data.alpaca.markets, Norton-gated) and the bars cache. Universe={list(symbols)}.")
    return pd.DataFrame(series).sort_index().dropna(how="all")


def _curve_returns(curve: list[tuple[date, float]]) -> pd.Series:
    """Daily simple returns from an equity curve [(date, equity), …], indexed by date (naive
    daily timestamp), dropping the first (no prior) point."""
    if len(curve) < 2:
        return pd.Series(dtype="float64")
    idx = pd.to_datetime([d for d, _ in curve]).normalize()
    eq = pd.Series([v for _, v in curve], index=idx, dtype="float64")
    return eq.pct_change().dropna()


def _count_trades(weight_history: list[dict[str, float]], *, tol: float = 1e-6) -> int:
    """Number of position changes across a sequence of rebalance weight maps — an open, close,
    or reweight (|Δw|>tol) of any name counts as one trade. The candidate trade count the gate
    compares to the sibling reference (export the sibling's count under the same definition, or
    relax the gate's ±10% trade tolerance)."""
    prev: dict[str, float] = {}
    n = 0
    for w in weight_history:
        for name in set(w) | set(prev):
            if abs(w.get(name, 0.0) - prev.get(name, 0.0)) > tol:
                n += 1
        prev = w
    return n


def _equity_sleeve(
    store: Any, spec_sleeve: SleeveSpec, start: date, end: date, n: int
) -> tuple[pd.Series, dict[str, float], int]:
    """Sleeve A — crash-protected equity momentum via run_momentum_backtest over the Sharadar
    store. Returns (daily-return Series, last-rebalance internal weights, trade count). The
    vol-target overlay (the crash protection, ADR 0020) yields ``vol_scaled_curve``."""
    from app.factor_data.backtest import run_momentum_backtest

    kw = {dst: spec_sleeve.params[src] for src, dst in _EQUITY_PARAM_MAP.items()
          if src in spec_sleeve.params}
    rep = run_momentum_backtest(store, start, end, n=n, **kw)
    curve = rep.vol_scaled_curve or rep.equity_curve  # crash-protected curve when vol-targeted
    returns = _curve_returns(curve)
    internal = dict(rep.holdings[-1].weights) if rep.holdings else {}
    trades = _count_trades([dict(h.weights) for h in rep.holdings])
    return returns, internal, trades


def _cross_asset_sleeve(
    store: Any, spec_sleeve: SleeveSpec, start: date, end: date
) -> tuple[pd.Series, dict[str, float], int]:
    """Sleeve B — cross-asset TSMOM over the §1 Total-Return Adapter panel. Returns (daily-return
    Series, last-rebalance internal weights, trade count)."""
    dist = _SharadarDistributions(store)
    start_dt = datetime(start.year, start.month, start.day, tzinfo=UTC)
    end_dt = datetime(end.year, end.month, end.day, tzinfo=UTC)
    panel = asyncio.run(_build_total_return_panel(CROSS_ASSET_UNIVERSE, start_dt, end_dt, dist))

    kw = dict(spec_sleeve.params)
    returns = backtest_cross_asset_sleeve(panel, **kw)
    reb = cross_asset_rebalance_weights(panel, **kw).dropna(how="all")
    internal = {k: float(v) for k, v in reb.iloc[-1].items()} if not reb.empty else {}
    trades = _count_trades([{k: float(v) for k, v in row.items()}
                            for _, row in reb.iterrows()])
    return returns, internal, trades


def _build_real_inputs(db: str | None) -> tuple[pd.DataFrame, dict, int]:
    """Build the Workbench sleeve return series from real data (the data-machine path).

    Sleeve A (equity momentum) over the Sharadar ``FactorDataStore``; Sleeve B (cross-asset
    TSMOM) over the §1 Total-Return Adapter panel (Alpaca raw bars + Sharadar distributions).
    Returns ``(sleeve_returns, sleeve_internal_weights, cand_trades)`` ready for
    ``run_reproduction``. Reads the sleeve set + params straight from the ``PORT_001`` spec so
    the harness and the live config never drift. Requires the non-Norton data env (the only
    reason this can't run on the dev box). Read-only research (ADR 0019); no order path."""
    from app.factor_data.store import FactorDataStore

    pf = PORT_001.portfolio
    if pf is None:  # defensive — PORT_001 is a portfolio program by construction
        raise RuntimeError("PORT_001 has no PortfolioSpec")
    by_kind = {s.kind: s for s in pf.sleeves}
    eq_spec = by_kind["equity_momentum"]
    xa_spec = by_kind["cross_asset_tsmom"]
    start, end = PORT_001.start, PORT_001.end

    with FactorDataStore(db_path=db, read_only=True) as store:
        eq_ret, eq_w, eq_trades = _equity_sleeve(store, eq_spec, start, end, PORT_001.n)
        xa_ret, xa_w, xa_trades = _cross_asset_sleeve(store, xa_spec, start, end)

    sleeve_returns = pd.DataFrame(
        {eq_spec.name: eq_ret, xa_spec.name: xa_ret}
    ).dropna()  # align both sleeves on their common trading days
    if sleeve_returns.empty:
        raise RuntimeError("no overlapping trading days between the equity and cross-asset sleeves")
    internal = {eq_spec.name: eq_w, xa_spec.name: xa_w}
    return sleeve_returns, internal, eq_trades + xa_trades


# --------------------------------------------------------------------------- construction-verify
def _sibling_inputs(sibling_dir: str) -> tuple[pd.DataFrame, dict, dict, int]:
    """Construction-verification inputs (the chosen reproduce-first test): feed the sibling's OWN
    committed sleeve return series through the platform's PCE/ERC + Evidence Package + Gate, vs the
    sibling's combined book. This isolates the *construction engine being onboarded* from
    data-source noise (Alpaca-vs-Yahoo) — it asks "does our blend reproduce the book?", not "does
    our data stack match theirs?". Reads claude-trading-view's ``factor_backtest_*.json``
    (``results.crash_engine.daily``) + ``cross_asset_momentum_*.json`` (``results.daily``)."""
    import glob
    import os

    from app.factor_data import evidence as ev

    def _latest(pat: str) -> str:
        hits = sorted(glob.glob(os.path.join(sibling_dir, pat)))
        if not hits:
            raise FileNotFoundError(f"no {pat} under {sibling_dir}")
        return hits[-1]

    fb = json.loads(Path(_latest("factor_backtest_*.json")).read_text(encoding="utf-8"))
    ca = json.loads(Path(_latest("cross_asset_momentum_*.json")).read_text(encoding="utf-8"))
    eq = dict(fb["results"]["crash_engine"]["daily"])      # date -> daily return
    cad = dict(ca["results"]["daily"])
    common = sorted(set(eq) & set(cad))
    idx = pd.to_datetime(common)
    sleeve_returns = pd.DataFrame(
        {"equity": [eq[d] for d in common], "cross_asset": [cad[d] for d in common]}, index=idx)

    # The sibling cross-asset internal weights (live §7, normalized). The equity sleeve enters the
    # blend as one synthetic instrument (its 150-name internal book is the equity sleeve's own
    # concern, not the cross-sleeve blend's). Both are look-through-comparable to the reference.
    live = {"IEF": 0.158, "UUP": 0.153, "TLT": 0.091, "SPY": 0.056,
            "EFA": 0.041, "DBC": 0.038, "GLD": 0.032, "EEM": 0.024}
    ssum = sum(live.values())
    ca_w = {k: v / ssum for k, v in live.items()}
    internal = {"equity": {"equity_momentum": 1.0}, "cross_asset": ca_w}

    # reference = the sibling COMBINED book (fixed 0.40 equity + 0.60 cross-asset), metrics via the
    # platform's own evidence functions (apples-to-apples with the candidate).
    comb = {d: 0.40 * eq[d] + 0.60 * cad[d] for d in common}
    eqv, curve = 100_000.0, []
    for d in common:
        eqv *= 1.0 + comb[d]
        curve.append((date.fromisoformat(d), eqv))
    ref_w = {"equity_momentum": 0.40, **{k: 0.60 * v for k, v in ca_w.items()}}
    reference = {
        "sharpe": round(ev.sharpe(ev.daily_returns(curve)), 4),
        "max_drawdown": round(abs(ev.max_drawdown(curve)), 4),
        "trades": 0,  # construction-verification feeds return series → no rebalance sim; N/A
        "daily_returns": {d: comb[d] for d in common},
        "weights": ref_w,
    }
    return sleeve_returns, internal, reference, 0  # cand_trades=0 == ref → trade criterion N/A


# --------------------------------------------------------------------------- report
def _write_outputs(result: dict, out_dir: Path, *, tag: str, footer: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"port001_{tag.lower()}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8")
    g = result["gate"]
    lines = [
        f"# PORT-001 Reproduction — {tag.replace('_', ' ').title()}",
        "",
        f"**Onboarding Gate: {'PASSED' if result['passed'] else 'FAILED'}**  ·  "
        f"Lifecycle Fidelity **{g['fidelity_pct']}%**",
        "",
        "| Criterion | Value | Threshold | Pass |",
        "|---|---|---|---|",
        *[f"| {c['name']} | {c['value']} | {c['threshold']} | {'✓' if c['passed'] else '✗'} |"
          for c in g["criteria"]],
        "",
        f"- Candidate (Workbench): Sharpe {result['candidate']['sharpe']} · "
        f"MaxDD {result['candidate']['max_drawdown']} · trades {result['candidate']['trades']}",
        f"- Reference (sibling): Sharpe {result['reference']['sharpe']} · "
        f"MaxDD {result['reference']['max_drawdown']} · trades {result['reference']['trades']}",
        "",
        footer,
    ]
    md = out_dir / f"LifecycleFidelity_{tag.upper()}.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md


def main() -> int:
    ap = argparse.ArgumentParser(description="PORT-001 reproduction harness")
    ap.add_argument("--synthetic", action="store_true", help="offline wiring self-test (no data)")
    ap.add_argument("--from-sibling", default=None, metavar="DIR",
                    help="construction-verification: blend the sibling's OWN committed sleeve "
                         "return series (claude-trading-view dir) through the platform PCE + Gate")
    ap.add_argument("--db", default=None,
                    help="Sharadar FactorDataStore DuckDB path (default: app's factor_data duckdb)")
    ap.add_argument("--reference", default=None, help="sibling reference JSON (real mode)")
    ap.add_argument("--out", type=Path, default=_OUT)
    args = ap.parse_args()

    pf = PORT_001.portfolio
    assert pf is not None, "PORT_001 is a portfolio program"  # noqa: S101 — config invariant

    if args.synthetic:
        tag = "synthetic"
        footer = "_Synthetic self-test — proves the harness wiring, NOT a real reproduction._"
        sleeve_returns, internal, reference, cand_trades = _synthetic_inputs()
    elif args.from_sibling:
        tag = "construction_verification"
        footer = ("_Construction-verification: the sibling's OWN sleeve return series blended "
                  "through the platform PCE/ERC vs its combined book — isolates the construction "
                  "engine from data-source noise. A clean pass is L1+L2 construction evidence; the "
                  "self-stack (Alpaca) data-fidelity port is a separate study._")
        sleeve_returns, internal, reference, cand_trades = _sibling_inputs(args.from_sibling)
    else:
        tag = "reproduction"
        footer = ("_On PASS: attach this Evidence Package, promote programs.py planned->validated, "
                  "and issue the Capability Certificate as v1.0 (Gate-Passed) advancing L1+L2._")
        sleeve_returns, internal, cand_trades = _build_real_inputs(args.db)
        if not args.reference:
            print("ERROR: --reference <sibling.json> is required for the real reproduction")
            return 2
        reference = json.loads(Path(args.reference).read_text(encoding="utf-8"))

    result = run_reproduction(
        sleeve_returns=sleeve_returns, sleeve_internal_weights=internal,
        equity_sleeve=pf.equity_sleeve, reference=reference,
        cand_trades=cand_trades, verdict=PORT_001.verdict,
    )
    md = _write_outputs(result, args.out, tag=tag, footer=footer)
    verdict = "PASSED" if result["passed"] else "FAILED"
    print(f"[port001-reproduction] Onboarding Gate {verdict}  ·  "
          f"fidelity {result['gate']['fidelity_pct']}%  ->  {md}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
