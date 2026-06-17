"""R3 — momentum-crash study: pre-live risk evidence for the 12m momentum book.

The reviewer's pre-live deliverable. Runs the validated 12-month book over the
full sample and characterizes its DOWNSIDE: worst drawdowns (depth + recovery),
worst rolling 1/3/6-month returns, correlation to SPY/QQQ, sector concentration
during the deepest drawdowns, and the effect of the vol-target overlay (R3).

SPY/QQQ and sectors are not in the Sharadar SEP store, so they are pulled from FMP
(prices via `historical_prices`, sector via `profile`); the study degrades
gracefully (skips a section, logs why) if FMP is unavailable.

    cd apps/backend
    .venv/Scripts/python.exe scripts/momentum_crash_study.py \
        --start 2016-01-01 --report-dir ../../research/
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

MOM12_LOOKBACK, MOM12_SKIP = 252, 0


# ---- pure analysis (no I/O; unit-tested) ----


@dataclass
class Drawdown:
    peak_date: date
    trough_date: date
    recovery_date: date | None  # None = still underwater at the end of the sample
    depth: float                # peak→trough return (negative)
    days_to_trough: int
    days_underwater: int | None  # peak→recovery; None if unrecovered


def drawdown_episodes(curve: list[tuple[date, float]]) -> list[Drawdown]:
    """All peak→trough→recovery drawdown episodes in a (date, equity) curve.

    A new episode opens when equity first falls below the running peak and closes
    when equity regains that peak (recovery). The final episode may be unrecovered
    (recovery_date None). Depth is the trough's return from the episode's peak."""
    if not curve:
        return []
    episodes: list[Drawdown] = []
    peak_date, peak = curve[0]
    in_dd = False
    trough = peak
    trough_date = peak_date
    for d, eq in curve:
        if eq >= peak:
            if in_dd:
                episodes.append(Drawdown(
                    peak_date, trough_date, d, trough / peak - 1.0,
                    (trough_date - peak_date).days, (d - peak_date).days,
                ))
                in_dd = False
            peak, peak_date = eq, d
        else:
            if not in_dd:
                in_dd, trough, trough_date = True, eq, d
            elif eq < trough:
                trough, trough_date = eq, d
    if in_dd:
        episodes.append(Drawdown(
            peak_date, trough_date, None, trough / peak - 1.0,
            (trough_date - peak_date).days, None,
        ))
    return episodes


def worst_drawdowns(curve: list[tuple[date, float]], n: int = 20) -> list[Drawdown]:
    """The `n` deepest drawdown episodes, deepest first."""
    return sorted(drawdown_episodes(curve), key=lambda e: e.depth)[:n]


def worst_rolling_returns(monthly: list[tuple[date, float]], months: int) -> float | None:
    """Worst `months`-month return over a month-end (date, equity) series."""
    if len(monthly) <= months:
        return None
    eqs = [e for _, e in monthly]
    rets = [eqs[i] / eqs[i - months] - 1.0 for i in range(months, len(eqs)) if eqs[i - months] > 0]
    return min(rets) if rets else None


def _to_month_end(curve: list[tuple[date, float]]) -> list[tuple[date, float]]:
    """Last observation of each (year, month) in the daily curve."""
    last: dict[tuple[int, int], tuple[date, float]] = {}
    for d, eq in curve:
        last[(d.year, d.month)] = (d, eq)
    return [last[k] for k in sorted(last)]


def _monthly_returns(curve: list[tuple[date, float]]) -> dict[tuple[int,int], float]:
    me = _to_month_end(curve)
    out: dict[tuple[int, int], float] = {}
    for (_, prev), (d, cur) in zip(me[:-1], me[1:], strict=False):
        if prev > 0:
            out[(d.year, d.month)] = cur / prev - 1.0
    return out


# ---- I/O (CLI) ----


def _fmp_monthly_returns(symbol: str, start: str, end: str):
    """Month-end-return series for a benchmark from FMP; None if unavailable."""
    try:
        from app.factor_data.providers.fmp import FMPProvider
        with FMPProvider() as p:
            df = p.historical_prices(symbol, from_date=start, to_date=end)
    except Exception as e:  # noqa: BLE001 — degrade gracefully
        print(f"  (SPY/QQQ fetch failed for {symbol}: {e!r})", file=sys.stderr)
        return None
    if df.empty or "close" not in df.columns:
        return None
    import pandas as pd
    df = df.copy()
    df["d"] = pd.to_datetime(df["date"]).dt.date
    curve = [(r.d, float(r.close)) for r in df.sort_values("d").itertuples()]
    return _monthly_returns(curve)


def _corr(a: dict[tuple[int,int],float], b: dict[tuple[int,int],float]) -> float | None:
    import numpy as np
    keys = sorted(set(a) & set(b))
    if len(keys) < 6:
        return None
    x = np.array([a[k] for k in keys])
    y = np.array([b[k] for k in keys])
    c = np.corrcoef(x, y)[0, 1]
    return float(c) if np.isfinite(c) else None


def _sector_map(tickers: list[str]):
    """ticker -> sector via FMP profile; {} if unavailable."""
    out: dict[str, str] = {}
    try:
        from app.factor_data.providers.fmp import FMPProvider
        with FMPProvider() as p:
            for t in tickers:
                df = p.profile(t)
                if not df.empty and "sector" in df.columns:
                    sec = df.iloc[0]["sector"]
                    if isinstance(sec, str) and sec:
                        out[t] = sec
    except Exception as e:  # noqa: BLE001
        print(f"  (sector fetch failed: {e!r})", file=sys.stderr)
    return out


def _holdings_at(report, when: date) -> list[str]:
    """The book's holdings from the last rebalance on/before `when`."""
    picks = [h for h in report.holdings if h.rebalance_date <= when]
    return picks[-1].tickers if picks else []


def main() -> int:
    ap = argparse.ArgumentParser(description="Momentum-crash study (12m book).")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--top-quantile", type=float, default=0.20)
    ap.add_argument("--turnover-cost-bps", type=float, default=10.0)
    ap.add_argument("--initial-equity", type=float, default=100_000.0)
    ap.add_argument("--vol-target", type=float, default=0.15)
    ap.add_argument("--worst", type=int, default=20)
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    from app.factor_data.backtest import _summary, _vol_target_overlay, run_momentum_backtest
    from app.factor_data.store import FactorDataStore

    store = FactorDataStore(read_only=True)
    try:
        floor, latest = store.price_date_bounds()
        if latest is None:
            print("No price data.", file=sys.stderr)
            return 1
        start, end = date.fromisoformat(args.start), (date.fromisoformat(args.end) if args.end else latest)
        rep = run_momentum_backtest(
            store, start, end, n=args.n, lookback_days=MOM12_LOOKBACK, skip_days=MOM12_SKIP,
            top_quantile=args.top_quantile, turnover_cost_bps=args.turnover_cost_bps,
            initial_equity=args.initial_equity,
        )
        curve = rep.equity_curve
        if not curve:
            print("Empty book curve.", file=sys.stderr)
            return 1
        worst = worst_drawdowns(curve, args.worst)
        rolling = {m: worst_rolling_returns(_to_month_end(curve), m) for m in (1, 3, 6)}
        book_m = _monthly_returns(curve)
        vol_curve = _vol_target_overlay(curve, vol_target_annual=args.vol_target, span=20,
                                        initial_equity=args.initial_equity)
        base_m = _monthly_returns(rep.baseline_curve)

        # Benchmarks + sectors from FMP (degrade gracefully).
        spy_m = _fmp_monthly_returns("SPY", args.start, end.isoformat())
        qqq_m = _fmp_monthly_returns("QQQ", args.start, end.isoformat())
        # Sector concentration in the 5 deepest drawdowns: holdings at each trough.
        crash_tickers = sorted({t for dd in worst[:5] for t in _holdings_at(rep, dd.trough_date)})
        sectors = _sector_map(crash_tickers) if crash_tickers else {}
    finally:
        store.close()

    raw = _summary(curve, args.initial_equity)
    vol = _summary(vol_curve, args.initial_equity)

    def pct(x):
        return "n/a" if x is None else f"{x:.2%}"

    lines = [
        "# Momentum-crash study — 12m book (R3, pre-live risk evidence)\n",
        f"Store `{floor}..{latest}`; 12m book (lookback {MOM12_LOOKBACK}/skip {MOM12_SKIP}); "
        f"`[{start}..{end}]`; n={args.n}, turnover {args.turnover_cost_bps}bps. "
        f"Full-sample maxDD {pct(raw.max_drawdown)}, Sharpe {raw.sharpe:.2f}.\n",
        "> Winner-biased liquid universe + a momentum-friendly sample — read the **shape** "
        "of the downside (depth, recovery, concentration), not the absolute levels.\n",
        f"## Worst {len(worst)} drawdowns\n",
        "| # | peak | trough | recovery | depth | days→trough | days underwater |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, dd in enumerate(worst, 1):
        rec = dd.recovery_date.isoformat() if dd.recovery_date else "**unrecovered**"
        uw = "n/a" if dd.days_underwater is None else str(dd.days_underwater)
        lines.append(f"| {i} | {dd.peak_date} | {dd.trough_date} | {rec} | {dd.depth:.2%} | "
                     f"{dd.days_to_trough} | {uw} |")
    lines += [
        "\n## Worst rolling returns\n",
        "| window | worst return |", "|---|---|",
        f"| 1-month | {pct(rolling[1])} |",
        f"| 3-month | {pct(rolling[3])} |",
        f"| 6-month | {pct(rolling[6])} |",
        "\n## Market correlation (monthly returns)\n",
        "| benchmark | correlation |", "|---|---|",
        f"| SPY | {('n/a' if _corr(book_m, spy_m) is None else f'{_corr(book_m, spy_m):.2f}') if spy_m else 'n/a (FMP unavailable)'} |",
        f"| QQQ | {('n/a' if _corr(book_m, qqq_m) is None else f'{_corr(book_m, qqq_m):.2f}') if qqq_m else 'n/a (FMP unavailable)'} |",
        f"| equal-weight universe | {'n/a' if _corr(book_m, base_m) is None else f'{_corr(book_m, base_m):.2f}'} |",
    ]
    # Sector concentration during the 5 deepest drawdowns.
    lines += ["\n## Sector concentration during the 5 deepest drawdowns\n"]
    if sectors:
        from collections import Counter
        for dd in worst[:5]:
            held = _holdings_at(rep, dd.trough_date)
            secs = Counter(sectors.get(t, "Unknown") for t in held)
            top = secs.most_common(1)[0] if secs else ("n/a", 0)
            share = top[1] / len(held) if held else 0.0
            lines.append(f"- trough {dd.trough_date} ({dd.depth:.1%}): {len(held)} names, "
                         f"top sector **{top[0]} {share:.0%}** ({dict(secs.most_common(4))})")
    else:
        lines.append("- (sector data unavailable — FMP profile fetch returned nothing)")
    lines += [
        "\n## Overlay effect (R3 — vol-targeting)\n",
        f"- raw 12m book: maxDD **{pct(raw.max_drawdown)}**, Sharpe {raw.sharpe:.2f}",
        f"- vol-targeted ({args.vol_target}): maxDD **{pct(vol.max_drawdown)}**, Sharpe {vol.sharpe:.2f}",
        "- See `momentum_overlays_findings.md` — vol-targeting roughly halves drawdown at flat Sharpe; "
        "the recommended pre-live mitigation.",
    ]

    text = "\n".join(lines) + "\n"
    if args.report_dir:  # write the artifact first — never lose it to a console-encoding error
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "momentum_crash_study.md").write_text(text, encoding="utf-8")
    # Console may be cp1252 (Windows) — degrade non-encodable chars rather than crash.
    enc = sys.stdout.encoding or "utf-8"
    sys.stdout.write(text.encode(enc, "replace").decode(enc) + "\n")
    if args.report_dir:
        print(f"Wrote {Path(args.report_dir) / 'momentum_crash_study.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
