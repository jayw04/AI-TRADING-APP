"""[NOT deprecated — distinct from the Factor Lab; ADR 0026 §5]

Unlike the LOW/SEC/TREND *verdict* harnesses (now superseded by
``app.research.factor_lab.run_program``), this is the IC / long-short factor-**measurement** study —
a different capability that ``run_program`` does not reproduce, and an active Research-Engine
dependency (``app.research.engine.runners`` imports its ``run_study``). It remains the canonical
entry point for "which factors work on our universe." Keep it.

Factor research engine (P10) — measure which factors actually work on OUR
Sharadar universe, before building a strategy around them.

"Measure first, build second." Reuses the survivorship-free price store
(``FactorDataStore``) and the §5c/OOS discipline: every factor is scored
in-sample AND out-of-sample, so a factor that only works on the fit window is
exposed (exactly what killed RangeTrader).

For each factor it computes, at a monthly rebalance cadence:
  - **IC** — cross-sectional Spearman rank correlation between the factor and the
    next-month forward return. Reports mean IC, IC-IR (mean/std), t-stat, % > 0.
  - **Long-short return** — top-quintile minus bottom-quintile forward return per
    month; reports annualized return, vol, Sharpe, hit-rate.
  - **Decay** — mean IC at 1 / 3 / 6 / 12-month forward horizons.
  - **Correlation** — pairwise correlation of the factors' LS return series
    (diversification — do they add independent information?).
All split IS vs OOS at ``--split`` (default 2023-01-01).

Factors implemented now are **price-based** (momentum 12-1 / 6-1 / 12m, low-vol,
short-term reversal). Value/Quality plug in once SF1 fundamentals are ingested —
a factor is just ``(close_matrix, as_of) -> Series[ticker -> value]``.

    cd apps/backend
    .venv/Scripts/python.exe scripts/factor_research.py --n 200 --start 2016-01-01 \
        --split 2023-01-01 --report-dir research/

Outputs a console table + (with --report-dir) factor_report.md + factor_rankings.json.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

TRADING_DAYS_YR = 252
MONTHS_YR = 12


# ---- pure metrics (no I/O; unit-tested) ----


def spearman_ic(factor: pd.Series, fwd_ret: pd.Series) -> float | None:
    """Cross-sectional Spearman rank correlation (factor vs forward return).
    Spearman = Pearson of ranks (no scipy dependency)."""
    df = pd.concat([factor, fwd_ret], axis=1, keys=["f", "r"]).dropna()
    if len(df) < 5 or df["f"].nunique() < 3 or df["r"].nunique() < 3:
        return None
    rf, rr = df["f"].rank().to_numpy(), df["r"].rank().to_numpy()
    c = np.corrcoef(rf, rr)[0, 1]
    return float(c) if np.isfinite(c) else None


def quintile_ls(factor: pd.Series, fwd_ret: pd.Series, *, q: int = 5) -> float | None:
    """Top-quintile minus bottom-quintile mean forward return (long-short)."""
    df = pd.concat([factor, fwd_ret], axis=1, keys=["f", "r"]).dropna()
    if len(df) < q * 2:
        return None
    try:
        buckets = pd.qcut(df["f"].rank(method="first"), q, labels=False)
    except ValueError:
        return None
    top = df["r"][buckets == q - 1].mean()
    bot = df["r"][buckets == 0].mean()
    if pd.isna(top) or pd.isna(bot):
        return None
    return float(top - bot)


@dataclass
class FactorResult:
    factor: str
    window: str  # 'IS' | 'OOS'
    n_periods: int
    mean_ic: float | None
    ic_ir: float | None        # mean IC / std IC
    ic_tstat: float | None
    ic_hit: float | None       # fraction of periods with IC > 0
    ls_ann_return: float | None
    ls_ann_vol: float | None
    ls_sharpe: float | None
    ls_hit: float | None
    decay_ic: dict[str, float | None]  # horizon(months) -> mean IC


def _summary(ics: list[float], ls: list[float], decay: dict[str, list[float]]) -> dict:
    def stats(xs):
        a = np.array([x for x in xs if x is not None], dtype=float)
        return a if len(a) else np.array([])
    ica, lsa = stats(ics), stats(ls)
    out: dict = {
        "n_periods": int(len(ica)),
        "mean_ic": float(ica.mean()) if len(ica) else None,
        "ic_ir": float(ica.mean() / ica.std(ddof=1)) if len(ica) > 1 and ica.std(ddof=1) > 0 else None,
        "ic_tstat": float(ica.mean() / ica.std(ddof=1) * np.sqrt(len(ica))) if len(ica) > 1 and ica.std(ddof=1) > 0 else None,
        "ic_hit": float((ica > 0).mean()) if len(ica) else None,
        "ls_ann_return": float(lsa.mean() * MONTHS_YR) if len(lsa) else None,
        "ls_ann_vol": float(lsa.std(ddof=1) * np.sqrt(MONTHS_YR)) if len(lsa) > 1 else None,
        "ls_sharpe": float(lsa.mean() / lsa.std(ddof=1) * np.sqrt(MONTHS_YR)) if len(lsa) > 1 and lsa.std(ddof=1) > 0 else None,
        "ls_hit": float((lsa > 0).mean()) if len(lsa) else None,
    }
    out["decay_ic"] = {h: (float(np.mean([x for x in v if x is not None])) if any(x is not None for x in v) else None)
                       for h, v in decay.items()}
    return out


# ---- factor definitions (price-based; date×ticker close matrix in trading days) ----


def _factor_matrices(close: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Each factor as a (date × ticker) matrix aligned to ``close``'s daily index.
    Higher = more attractive (long) by convention."""
    rets = close.pct_change(fill_method=None)
    mom_12_1 = close.shift(21) / close.shift(252) - 1.0           # 12-1 momentum
    mom_6_1 = close.shift(21) / close.shift(126) - 1.0            # 6-1 momentum
    mom_12 = close / close.shift(252) - 1.0                       # 12m momentum
    lowvol = -rets.rolling(126).std()                            # low realized vol (negated)
    reversal_1m = -(close / close.shift(21) - 1.0)               # short-term reversal (negated)
    return {
        "mom_12_1": mom_12_1, "mom_6_1": mom_6_1, "mom_12": mom_12,
        "lowvol_6m": lowvol, "reversal_1m": reversal_1m,
    }


def _month_end_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Last trading day of each month present in the index."""
    s = pd.Series(index, index=index)
    return list(s.groupby([index.year, index.month]).last())


def run_study(close: pd.DataFrame, *, split: pd.Timestamp,
              horizons=(1, 3, 6, 12),
              extra_matrices: dict[str, pd.DataFrame] | None = None,
              ) -> tuple[list[FactorResult], pd.DataFrame]:
    """Compute IS/OOS IC, long-short, decay, and the LS-return panel for
    correlation. ``close`` is a daily (date × ticker) adjusted-close matrix.

    ``extra_matrices`` (optional) are additional (date × ticker) factor matrices —
    e.g. the Value/Quality fundamental factors — already aligned to the month-end
    rebalance dates; they are studied alongside the price factors."""
    close = close.sort_index()
    fmats = _factor_matrices(close)
    if extra_matrices:
        fmats = {**fmats, **extra_matrices}
    rebal = _month_end_dates(close.index)
    px = close.reindex(rebal)  # month-end prices
    # forward h-month returns at each rebalance date
    fwd = {h: px.shift(-h) / px - 1.0 for h in horizons}

    results: list[FactorResult] = []
    ls_series: dict[str, pd.Series] = {}
    for fname, fmat in fmats.items():
        fr = fmat.reindex(rebal)  # factor at each rebalance date
        per_ic: dict[int, list] = {h: [] for h in horizons}
        ls_by_date: dict = {}
        windows: dict[str, list] = {"IS": [], "OOS": [], "IS_ls": [], "OOS_ls": []}
        for dt in rebal:
            f_row = fr.loc[dt]
            ic1 = spearman_ic(f_row, fwd[1].loc[dt])
            ls1 = quintile_ls(f_row, fwd[1].loc[dt])
            for h in horizons:
                per_ic[h].append(spearman_ic(f_row, fwd[h].loc[dt]))
            if ls1 is not None:
                ls_by_date[dt] = ls1
            tag = "IS" if dt < split else "OOS"
            windows[tag].append(ic1)
            windows[f"{tag}_ls"].append(ls1)
        ls_series[fname] = pd.Series(ls_by_date)
        for tag in ("IS", "OOS"):
            mask = [dt < split if tag == "IS" else dt >= split for dt in rebal]
            decay = {f"{h}m": [per_ic[h][i] for i in range(len(rebal)) if mask[i]] for h in horizons}
            s = _summary(windows[tag], windows[f"{tag}_ls"], decay)
            results.append(FactorResult(factor=fname, window=tag, **s))
    ls_panel = pd.DataFrame(ls_series)
    return results, ls_panel


# ---- I/O (CLI only) ----


def _load_close(n: int, start: str) -> pd.DataFrame:
    from datetime import date, timedelta

    from app.factor_data.store import FactorDataStore
    store = FactorDataStore(read_only=True)
    try:
        end = store.price_date_bounds()[1] or date.today()
        # Universe directly from SEP (top-N by recent median dollar volume) — avoids
        # the tickers-table PIT join, whose lastpricedate can lag a fresh SEP backfill.
        recent = (pd.Timestamp(end) - timedelta(days=180)).date()
        uni = [r[0] for r in store.con.execute(
            "SELECT ticker FROM sep WHERE date >= ? GROUP BY ticker HAVING count(*) > 60 "
            "ORDER BY median(closeadj * volume) DESC LIMIT ?",
            [recent, n],
        ).fetchall()]
        if not uni:
            return pd.DataFrame()
        ph = ",".join("?" * len(uni))
        df = store.con.execute(
            f"SELECT ticker, date, closeadj FROM sep WHERE ticker IN ({ph}) "
            f"AND date >= ? AND closeadj > 0 ORDER BY date",
            [*uni, start],
        ).df()
    finally:
        store.close()
    if df.empty:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"])
    return df.pivot_table(index="date", columns="ticker", values="closeadj")


def _load_fundamentals(tickers: list[str]) -> pd.DataFrame:
    """Annual (FY) fundamentals for ``tickers`` from the store, for the PIT factor
    build. Returns ticker/accepted_date/period_end + the raw fields; empty if the
    fundamentals table is empty (ingest_fmp.py not run)."""
    from app.factor_data.store import FactorDataStore
    store = FactorDataStore(read_only=True)
    try:
        if store.row_count("fundamentals") == 0 or not tickers:
            return pd.DataFrame()
        ph = ",".join("?" * len(tickers))
        return store.con.execute(
            f"SELECT ticker, accepted_date, filing_date, period_end, revenue, "
            f"gross_profit, operating_income, ebitda, net_income, free_cash_flow, "
            f"total_debt, total_equity, total_assets, shares_diluted, enterprise_value "
            f"FROM fundamentals WHERE period = 'FY' AND ticker IN ({ph})",
            tickers,
        ).df()
    finally:
        store.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Factor research engine (IS/OOS IC + long-short).")
    ap.add_argument("--n", type=int, default=200, help="universe size (top-N by dollar volume).")
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--split", default="2023-01-01", help="IS/OOS boundary (YYYY-MM-DD).")
    ap.add_argument("--report-dir", default=None)
    ap.add_argument("--with-fundamentals", action="store_true",
                    help="also study the FMP Value/Quality factors (needs ingest_fmp run first).")
    args = ap.parse_args()

    close = _load_close(args.n, args.start)
    if close.empty:
        print("No price data — check the factor store / backfill.", file=sys.stderr)
        return 1
    print(f"Universe {close.shape[1]} names, {close.index.min().date()}..{close.index.max().date()} "
          f"({close.shape[0]} days). IS/OOS split {args.split}.\n")

    extra: dict[str, pd.DataFrame] | None = None
    if args.with_fundamentals:
        from app.factor_data.factors.fundamental import build_fundamental_factor_matrices
        fund = _load_fundamentals(list(close.columns))
        if fund.empty:
            print("--with-fundamentals: no fundamentals in store; run ingest_fmp.py first.", file=sys.stderr)
        else:
            rebal = _month_end_dates(close.index)
            extra = build_fundamental_factor_matrices(fund, close, rebal)
            print(f"Fundamentals: {fund['ticker'].nunique()} names, {len(fund)} statements "
                  f"-> {len([m for m in extra.values() if not m.empty])} factor matrices.\n")
    results, ls_panel = run_study(close, split=pd.Timestamp(args.split), extra_matrices=extra)

    def fmt(x, p=2):
        return "n/a" if x is None else f"{x:.{p}f}"
    print(f"{'factor':12}{'win':5}{'meanIC':>8}{'IC-IR':>7}{'tstat':>7}{'IC>0':>6}{'LS-Shrp':>8}{'LS-ret':>8}")
    for r in results:
        print(f"{r.factor:12}{r.window:5}{fmt(r.mean_ic,3):>8}{fmt(r.ic_ir):>7}{fmt(r.ic_tstat):>7}"
              f"{fmt(r.ic_hit):>6}{fmt(r.ls_sharpe):>8}{fmt(r.ls_ann_return):>8}")
    corr = ls_panel.corr()
    print("\nLong-short return correlation (diversification):")
    print(corr.round(2).to_string())

    if args.report_dir:
        import json
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "factor_rankings.json").write_text(
            json.dumps([asdict(r) for r in results], indent=2, default=str), encoding="utf-8")
        lines = [f"# Factor research — {close.index.min().date()}..{close.index.max().date()} "
                 f"({close.shape[1]} names, IS/OOS split {args.split})\n",
                 "| factor | win | mean IC | IC-IR | t | IC>0 | LS Sharpe | LS ann.ret |",
                 "|---|---|---|---|---|---|---|---|"]
        for r in results:
            lines.append(f"| {r.factor} | {r.window} | {fmt(r.mean_ic,3)} | {fmt(r.ic_ir)} | {fmt(r.ic_tstat)} "
                         f"| {fmt(r.ic_hit)} | {fmt(r.ls_sharpe)} | {fmt(r.ls_ann_return)} |")
        lines += ["\n## Long-short return correlation\n", "```", corr.round(2).to_string(), "```"]
        (d / "factor_report.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"\nWrote {d/'factor_report.md'} and factor_rankings.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
