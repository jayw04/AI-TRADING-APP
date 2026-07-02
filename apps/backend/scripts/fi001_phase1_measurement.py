"""FI-001 Phase 1 — Measurement.

The first executable of the FI-001 charter (Multi-Factor Interaction & Portfolio
Engineering), run only after the charter was frozen (PR #324). Phase 1 measures how
the platform's VALIDATED books interact, WITHOUT re-optimizing any factor:

  - full-sample pairwise return correlation matrix
  - rolling correlation (63d / 126d) -> stability profile (min/mean/max)
  - STRESS correlation: each pair's correlation restricted to momentum's worst
    drawdown window (H3 -- does diversification survive when momentum is bleeding?)
  - holdings overlap (mean pairwise Jaccard across common rebalances)
  - a single diversification score (0-100) from the pairwise correlations

Each book is produced by `run_momentum_backtest(score_fn=<frozen scorer>)` -- identical
construction to the live books (weekly, long-only, equal-weight, survivorship-free),
varying ONLY the score function, so the comparison is apples-to-apples.

Sector arm: `sector_scores` needs a sector-populated store (`tickers.sector`); a store
without it is skipped with a notice (run on the box, as MOM-002 v2 did). Momentum /
Low-Vol / Trend run anywhere.

    cd apps/backend
    .venv/Scripts/python.exe scripts/fi001_phase1_measurement.py \
        --start 2019-01-01 --end 2026-06-13 --n 150 --report-dir research/fi001/phase1/

Outputs a console summary + (with --report-dir) fi001_phase1_report.md + _results.json.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.factor_data.backtest import run_momentum_backtest  # noqa: E402
from app.factor_data.factors.low_vol import low_vol_scores  # noqa: E402
from app.factor_data.factors.sector import sector_scores  # noqa: E402
from app.factor_data.factors.trend import trend_scores  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402
from app.services.portfolio_analytics import diversification_score, jaccard, pearson  # noqa: E402

# Book -> score_fn factory. Momentum is the default path (score_fn=None). Each scorer
# is consumed at its OWN frozen definition (charter: no factor re-optimization).
BOOKS = ["momentum", "low_vol", "trend", "sector"]


def _score_fn(book: str, n: int):
    if book == "momentum":
        return None  # default momentum path
    if book == "low_vol":
        return lambda store, d: low_vol_scores(store, d, n=n)
    if book == "trend":
        return lambda store, d: trend_scores(store, d, n=n)
    if book == "sector":
        return lambda store, d: sector_scores(store, d, n=n)
    raise ValueError(book)


def _returns_series(curve: list[tuple[date, float]]) -> pd.Series:
    """Daily simple-return series indexed by date (aligned across books via concat)."""
    if len(curve) < 2:
        return pd.Series(dtype=float)
    s = pd.Series({pd.Timestamp(d): eq for d, eq in curve}).sort_index()
    return s.pct_change().dropna()


def _worst_drawdown_window(curve: list[tuple[date, float]]) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """The [peak, trough] date span of the deepest drawdown of an equity curve."""
    if len(curve) < 2:
        return None
    s = pd.Series({pd.Timestamp(d): eq for d, eq in curve}).sort_index()
    run_max = s.cummax()
    dd = s / run_max - 1.0
    trough = dd.idxmin()
    peak = s.loc[:trough].idxmax()  # last peak before the trough
    return (peak, trough)


@dataclass
class BookResult:
    book: str
    n_rebalances: int
    cagr: float | None
    sharpe: float | None
    max_drawdown: float | None


def _corr(a: pd.Series, b: pd.Series) -> float | None:
    df = pd.concat([a, b], axis=1, keys=["a", "b"]).dropna()
    return pearson(df["a"].tolist(), df["b"].tolist()) if len(df) >= 3 else None


def _rolling_corr_profile(a: pd.Series, b: pd.Series, window: int) -> dict:
    df = pd.concat([a, b], axis=1, keys=["a", "b"]).dropna()
    if len(df) < window + 5:
        return {"window": window, "mean": None, "min": None, "max": None}
    rc = df["a"].rolling(window).corr(df["b"]).dropna()
    if rc.empty:
        return {"window": window, "mean": None, "min": None, "max": None}
    return {"window": window, "mean": round(float(rc.mean()), 3),
            "min": round(float(rc.min()), 3), "max": round(float(rc.max()), 3)}


def main() -> int:
    ap = argparse.ArgumentParser(description="FI-001 Phase 1 measurement.")
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2026-06-13")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    store = FactorDataStore(read_only=True)
    bounds = store.price_date_bounds()
    sector_cov = store.con.execute(
        "SELECT count(*) FROM tickers WHERE sector IS NOT NULL"
    ).fetchone()[0]

    books = list(BOOKS)
    if sector_cov == 0:
        books.remove("sector")
        sector_note = ("Sector arm SKIPPED: store has 0 tickers with sector data "
                       "(run on the sector-populated box store).")
    else:
        sector_note = None

    print(f"FI-001 Phase 1 Measurement -- universe {args.n}, {start}..{end}")
    print(f"Store bounds {bounds[0]}..{bounds[1]}; sector coverage {sector_cov}")
    if sector_note:
        print("NOTE: " + sector_note)
    print()

    results: list[BookResult] = []
    returns: dict[str, pd.Series] = {}
    holdings_by_date: dict[str, dict[pd.Timestamp, set[str]]] = {}
    dd_windows: dict[str, tuple[pd.Timestamp, pd.Timestamp] | None] = {}

    from app.factor_data import evidence as ev
    for book in books:
        print(f"running {book} ...", flush=True)
        rep = run_momentum_backtest(store, start, end, n=args.n, score_fn=_score_fn(book, args.n))
        curve = rep.equity_curve
        returns[book] = _returns_series(curve)
        holdings_by_date[book] = {pd.Timestamp(h.rebalance_date): set(h.tickers) for h in rep.holdings}
        dd_windows[book] = _worst_drawdown_window(curve)
        results.append(BookResult(
            book=book, n_rebalances=len(rep.rebalances),
            cagr=(round(ev.cagr(curve), 4) if len(curve) > 1 else None),
            sharpe=(round(ev.sharpe(ev.daily_returns(curve)), 3) if len(curve) > 1 else None),
            max_drawdown=(round(ev.max_drawdown(curve), 4) if len(curve) > 1 else None),
        ))
    store.close()

    # pairwise correlations (full-sample + stress) + rolling stability
    pairs: list[dict] = []
    mom_dd = dd_windows.get("momentum")
    for i, a in enumerate(books):
        for b in books[i + 1:]:
            full = _corr(returns[a], returns[b])
            # stress correlation: restrict both series to momentum's worst-DD window
            stress = None
            if mom_dd is not None:
                lo, hi = mom_dd
                stress = _corr(returns[a].loc[lo:hi], returns[b].loc[lo:hi])
            # holdings overlap: mean Jaccard over common rebalance dates
            common = set(holdings_by_date[a]) & set(holdings_by_date[b])
            jac = ([jaccard(holdings_by_date[a][d], holdings_by_date[b][d]) for d in common]
                   if common else [])
            overlap = round(sum(jac) / len(jac), 3) if jac else None
            pairs.append({
                "pair": f"{a} <-> {b}",
                "corr_full": (round(full, 3) if full is not None else None),
                "corr_stress_momDD": (round(stress, 3) if stress is not None else None),
                "roll63": _rolling_corr_profile(returns[a], returns[b], 63),
                "roll126": _rolling_corr_profile(returns[a], returns[b], 126),
                "holdings_overlap": overlap,
            })

    corr_vals = [p["corr_full"] for p in pairs if p["corr_full"] is not None]
    div_score = diversification_score(corr_vals) if corr_vals else None

    # ---- console ----
    print(f"\n{'book':10}{'rebs':>6}{'CAGR':>9}{'Sharpe':>8}{'MaxDD':>9}")
    for r in results:
        cg = f"{r.cagr*100:.1f}%" if r.cagr is not None else "n/a"
        dd = f"{r.max_drawdown*100:.1f}%" if r.max_drawdown is not None else "n/a"
        print(f"{r.book:10}{r.n_rebalances:>6}{cg:>9}{str(r.sharpe):>8}{dd:>9}")
    print(f"\nDiversification score (0-100, 100=well diversified): {div_score}")
    if mom_dd:
        print(f"Momentum worst-DD window (stress): {mom_dd[0].date()}..{mom_dd[1].date()}")
    print(f"\n{'pair':22}{'corr':>7}{'stress':>8}{'r63 mean':>10}{'r63 max':>9}{'overlap':>9}")
    for p in pairs:
        print(f"{p['pair']:22}{str(p['corr_full']):>7}{str(p['corr_stress_momDD']):>8}"
              f"{str(p['roll63']['mean']):>10}{str(p['roll63']['max']):>9}{str(p['holdings_overlap']):>9}")

    # ---- report ----
    if args.report_dir:
        import json
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "fi001_phase1_results.json").write_text(json.dumps({
            "window": {"start": str(start), "end": str(end), "n": args.n},
            "store_bounds": [str(bounds[0]), str(bounds[1])],
            "sector_coverage": sector_cov,
            "books": [asdict(r) for r in results],
            "momentum_dd_window": ([str(mom_dd[0].date()), str(mom_dd[1].date())] if mom_dd else None),
            "pairs": pairs,
            "diversification_score": div_score,
        }, indent=2, default=str), encoding="utf-8")

        lines = [
            "# FI-001 Phase 1 — Measurement\n",
            f"Universe {args.n} - {start}..{end} - store {bounds[0]}..{bounds[1]}. "
            "Books built with identical construction (weekly, long-only, equal-weight, "
            "survivorship-free); only the score function varies.\n",
            "## Books",
            "| book | rebalances | CAGR | Sharpe | MaxDD |",
            "|---|---|---|---|---|",
        ]
        for r in results:
            cg = f"{r.cagr*100:.1f}%" if r.cagr is not None else "n/a"
            dd = f"{r.max_drawdown*100:.1f}%" if r.max_drawdown is not None else "n/a"
            lines.append(f"| {r.book} | {r.n_rebalances} | {cg} | {r.sharpe} | {dd} |")
        lines += [
            f"\n**Diversification score:** {div_score} / 100 (100 = well diversified; higher = better; "
            "uses avg *positive* pairwise correlation).",
            (f"\n**Stress window** = momentum's worst drawdown "
             f"({mom_dd[0].date()}..{mom_dd[1].date()})." if mom_dd else ""),
            "\n## Pairwise interaction\n",
            "| pair | full corr | stress corr (mom DD) | rolling-63 mean | rolling-63 min..max | holdings overlap |",
            "|---|---|---|---|---|---|",
        ]
        for p in pairs:
            r63 = p["roll63"]
            rng = (f"{r63['min']}..{r63['max']}" if r63["min"] is not None else "n/a")
            lines.append(f"| {p['pair']} | {p['corr_full']} | {p['corr_stress_momDD']} "
                         f"| {r63['mean']} | {rng} | {p['holdings_overlap']} |")
        lines += ["\n## Reading (against the frozen H1/H3 priors)\n",
                  "- H1 priors: MOM<->LOW ~ -0.15 (real diversifier), MOM<->SEC ~ +0.38, "
                  "MOM<->TREND ~ +0.87 (redundant). Compare `full corr` above.",
                  "- H3: `stress corr` vs `full corr` shows whether diversification SURVIVES "
                  "momentum's worst drawdown (a pair whose stress corr jumps toward +1 diversifies "
                  "least when it matters most)."]
        if sector_note:
            lines.append(f"\n> {sector_note}")
        (d / "fi001_phase1_report.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"\nWrote {d / 'fi001_phase1_report.md'} and fi001_phase1_results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
