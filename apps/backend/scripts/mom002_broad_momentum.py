"""MOM-002 — Broad Momentum: does Top-20 beat Top-5 on a risk-adjusted basis?

Research program launched from the 2026-07-02 daily-report review, which observed
that the live Top-5 momentum book is effectively "one macro theme" (semis / storage
/ AI infrastructure) rather than five independent bets, and asked the ★★★★★ question:

    Does Top-20 Momentum outperform Top-5 on a risk-adjusted basis?

This is a MEASUREMENT study, not a strategy change. It reuses the survivorship-free
`run_momentum_backtest` framework (`app.factor_data.backtest`) — the SAME construction
rules as the live book (weekly rebalance, long-only, equal-weight, last-price-to-cash
delisting) — and sweeps the book breadth N ∈ {5, 10, 15, 20} via the new absolute
`top_n` override. For each config it reports the full-window AND out-of-sample
(post-`--split`) risk-adjusted metrics, plus the cross-config monthly-return
correlation (how much independent information a broader book actually adds).

Sector-cap arm: the review also asked for a sector cap. `run_momentum_backtest`
supports `max_sector_pct`, but it needs a sector-populated factor store
(`tickers.sector`). A store without sector data FAILS OPEN (no cap) — so this script
only runs the sector-cap arm when `--max-sector-pct` is given AND the store has
sector coverage; otherwise it prints a notice and runs breadth-only.

    cd apps/backend
    .venv/Scripts/python.exe scripts/mom002_broad_momentum.py \
        --start 2019-01-01 --end 2026-06-13 --n 150 --split 2023-01-01 \
        --report-dir research/mom002/

Outputs a console table + (with --report-dir) mom002_report.md + mom002_results.json.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.factor_data.backtest import run_momentum_backtest  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402
from app.strategies import metrics  # noqa: E402

DEFAULT_TOP_NS = (5, 10, 15, 20)


# ---- pure metric helpers (reuse the shared formulas; no I/O) ----


def _dt_curve(curve: list[tuple[date, float]]) -> list[tuple[datetime, float]]:
    return [(datetime.combine(d, time()), eq) for d, eq in curve]


def _slice_from(curve: list[tuple[date, float]], split: date) -> list[tuple[date, float]]:
    """Sub-curve on/after ``split`` — for the out-of-sample metrics."""
    return [(d, eq) for d, eq in curve if d >= split]


def _calmar(cagr: float, max_dd: float) -> float | None:
    return None if max_dd == 0 else abs(cagr / max_dd)


def _window_metrics(curve: list[tuple[date, float]]) -> dict:
    """CAGR / Sharpe / MaxDD / Calmar / total-return for a (date, equity) curve,
    re-anchored to its own first point so sub-period returns are self-consistent."""
    if len(curve) < 2:
        return {"cagr": None, "sharpe": None, "max_drawdown": None,
                "calmar": None, "total_return": None}
    dtc = _dt_curve(curve)
    init = curve[0][1]
    final = curve[-1][1]
    days = (curve[-1][0] - curve[0][0]).days
    years = days / 365.25 if days > 0 else 0.0
    cagr = (final / init) ** (1.0 / years) - 1.0 if years > 0 and init > 0 else 0.0
    mdd = metrics.max_drawdown(dtc)
    return {
        "cagr": cagr,
        "sharpe": metrics.sharpe_ratio(dtc),
        "max_drawdown": mdd,
        "calmar": _calmar(cagr, mdd),
        "total_return": final / init - 1.0 if init > 0 else 0.0,
    }


def _avg_turnover(holdings) -> float | None:
    """Mean one-way name turnover between consecutive rebalances — the fraction of
    the prior book replaced. A breadth/stability proxy (not $-weighted)."""
    prev: set[str] | None = None
    churn: list[float] = []
    for h in holdings:
        cur = set(h.tickers)
        if prev is not None and prev:
            churn.append(len(prev - cur) / len(prev))
        prev = cur
    return sum(churn) / len(churn) if churn else None


def _monthly_returns(curve: list[tuple[date, float]]) -> pd.Series:
    """Month-end equity -> monthly simple returns (for cross-config correlation)."""
    if len(curve) < 2:
        return pd.Series(dtype=float)
    s = pd.Series({pd.Timestamp(d): eq for d, eq in curve}).sort_index()
    return s.resample("ME").last().pct_change().dropna()


@dataclass
class ConfigResult:
    top_n: int
    max_sector_pct: float | None
    n_rebalances: int
    avg_names: float
    avg_turnover: float | None
    full: dict          # window metrics over the whole run
    oos: dict           # window metrics on/after split
    baseline_sharpe: float | None


def run_config(store, *, start, end, n, top_n, split, max_sector_pct) -> tuple[ConfigResult, pd.Series]:
    rep = run_momentum_backtest(
        store, start, end, n=n, top_n=top_n, max_sector_pct=max_sector_pct,
    )
    holds = rep.holdings
    avg_names = (sum(len(h.tickers) for h in holds) / len(holds)) if holds else 0.0
    res = ConfigResult(
        top_n=top_n,
        max_sector_pct=max_sector_pct,
        n_rebalances=len(rep.rebalances),
        avg_names=avg_names,
        avg_turnover=_avg_turnover(holds),
        full=_window_metrics(rep.equity_curve),
        oos=_window_metrics(_slice_from(rep.equity_curve, split)),
        baseline_sharpe=rep.baseline_metrics.sharpe,
    )
    return res, _monthly_returns(rep.equity_curve)


def _fmt(x, p=2, pct=False):
    if x is None:
        return "n/a"
    return f"{x * 100:.{p}f}%" if pct else f"{x:.{p}f}"


def _verdict(results: list[ConfigResult]) -> list[str]:
    """Compare the breadth extremes (Top-5 vs Top-20) on the risk-adjusted metrics
    the review asked about. Evidence-first: state what the numbers say, no promotion."""
    by_n = {r.top_n: r for r in results if r.max_sector_pct is None}
    lo, hi = min(by_n), max(by_n)
    if lo not in by_n or hi not in by_n:
        return ["Insufficient configs for a Top-N comparison."]
    a, b = by_n[lo], by_n[hi]
    out = [f"**Breadth comparison — Top-{lo} vs Top-{hi} (full window):**"]

    def line(label, va, vb, higher_better=True, pct=False):
        if va is None or vb is None:
            out.append(f"- {label}: n/a")
            return
        better = (vb > va) if higher_better else (vb < va)
        arrow = "improves" if better else "worsens"
        out.append(f"- {label}: Top-{lo} {_fmt(va, pct=pct)} -> Top-{hi} {_fmt(vb, pct=pct)} "
                   f"({arrow} with breadth)")

    line("Sharpe", a.full["sharpe"], b.full["sharpe"], higher_better=True)
    # max_drawdown is negative; a shallower (less-negative, i.e. larger) value is better.
    line("Max drawdown", a.full["max_drawdown"], b.full["max_drawdown"],
         higher_better=True, pct=True)
    line("Calmar", a.full["calmar"], b.full["calmar"], higher_better=True)
    line("CAGR", a.full["cagr"], b.full["cagr"], higher_better=True, pct=True)
    line("OOS Sharpe", a.oos["sharpe"], b.oos["sharpe"], higher_better=True)

    # Headline call: risk-adjusted = Sharpe first, corroborated by Calmar.
    sa, sb = a.full["sharpe"], b.full["sharpe"]
    if sa is not None and sb is not None:
        if sb > sa:
            out.append(f"\n=> On this window, **Top-{hi} is the stronger risk-adjusted book** "
                       f"(higher Sharpe). Broadening the book helped.")
        elif sb < sa:
            out.append(f"\n=> On this window, **Top-{lo} is the stronger risk-adjusted book** "
                       f"(higher Sharpe). Concentration was not penalised — the review's "
                       f"diversification concern is about *portfolio correlation*, not single-book Sharpe.")
        else:
            out.append(f"\n=> Top-{lo} and Top-{hi} are indistinguishable on Sharpe over this window.")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="MOM-002 Broad Momentum breadth sweep.")
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2026-06-13")
    ap.add_argument("--n", type=int, default=150, help="momentum universe size (top-N by dollar volume).")
    ap.add_argument("--split", default="2023-01-01", help="in-sample/out-of-sample boundary (YYYY-MM-DD).")
    ap.add_argument("--top-ns", default=",".join(map(str, DEFAULT_TOP_NS)),
                    help="comma-separated absolute book sizes to sweep.")
    ap.add_argument("--max-sector-pct", type=float, default=None,
                    help="also run each config with this per-sector cap (needs a sector-populated store).")
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    split = date.fromisoformat(args.split)
    top_ns = [int(x) for x in args.top_ns.split(",") if x.strip()]

    store = FactorDataStore(read_only=True)
    try:
        bounds = store.price_date_bounds()
        sector_cov = store.con.execute(
            "SELECT count(*) FROM tickers WHERE sector IS NOT NULL"
        ).fetchone()[0]
    finally:
        pass  # keep open; the backtest reads from it

    print(f"MOM-002 Broad Momentum — universe {args.n}, {start}..{end}, IS/OOS split {split}")
    print(f"Store price bounds {bounds[0]}..{bounds[1]}; tickers with sector = {sector_cov}\n")

    arms: list[tuple[int, float | None]] = [(k, None) for k in top_ns]
    if args.max_sector_pct is not None:
        if sector_cov > 0:
            arms += [(k, args.max_sector_pct) for k in top_ns]
        else:
            print(f"NOTE: --max-sector-pct {args.max_sector_pct} requested but the store has 0 "
                  f"tickers with sector data -> sector-cap arm SKIPPED (would fail open). "
                  f"Run against the sector-populated store (box / post TICKERS re-ingest).\n")

    results: list[ConfigResult] = []
    monthly: dict[str, pd.Series] = {}
    for top_n, msp in arms:
        label = f"Top-{top_n}" + (f"+sec{int(msp * 100)}" if msp is not None else "")
        print(f"running {label} ...", flush=True)
        res, mret = run_config(store, start=start, end=end, n=args.n,
                               top_n=top_n, split=split, max_sector_pct=msp)
        results.append(res)
        monthly[label] = mret
    store.close()

    # cross-config monthly-return correlation
    corr = pd.DataFrame(monthly).corr() if len(monthly) > 1 else pd.DataFrame()

    # ---- console output ----
    hdr = f"{'config':16}{'rebs':>6}{'avgN':>7}{'CAGR':>8}{'Sharpe':>8}{'MaxDD':>8}{'Calmar':>8}{'OOS-Shrp':>10}{'turn':>7}"
    print("\n" + hdr)
    print("-" * len(hdr))
    for r in results:
        label = f"Top-{r.top_n}" + (f"+sec{int(r.max_sector_pct * 100)}" if r.max_sector_pct else "")
        print(f"{label:16}{r.n_rebalances:>6}{r.avg_names:>7.1f}"
              f"{_fmt(r.full['cagr'], pct=True):>8}{_fmt(r.full['sharpe']):>8}"
              f"{_fmt(r.full['max_drawdown'], pct=True):>8}{_fmt(r.full['calmar']):>8}"
              f"{_fmt(r.oos['sharpe']):>10}{_fmt(r.avg_turnover, pct=True):>7}")
    if not corr.empty:
        print("\nCross-config monthly-return correlation:")
        print(corr.round(2).to_string())
    print("\n" + "\n".join(_verdict(results)))

    # ---- evidence report ----
    if args.report_dir:
        import json
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "mom002_results.json").write_text(json.dumps({
            "window": {"start": str(start), "end": str(end), "split": str(split), "n": args.n},
            "store_bounds": [str(bounds[0]), str(bounds[1])],
            "sector_coverage": sector_cov,
            "configs": [asdict(r) for r in results],
            "monthly_return_correlation": (corr.round(4).to_dict() if not corr.empty else {}),
        }, indent=2, default=str), encoding="utf-8")

        lines = [
            "# MOM-002 Broad Momentum — breadth sweep\n",
            f"Universe {args.n} · window {start}..{end} · IS/OOS split {split} · "
            f"store {bounds[0]}..{bounds[1]}\n",
            "Same construction as the live book: weekly rebalance, long-only, equal-weight, "
            "survivorship-free, last-price-to-cash delisting. Breadth N is the only variable.\n",
            "| config | rebs | avg N | CAGR | Sharpe | MaxDD | Calmar | OOS Sharpe | avg turnover |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for r in results:
            label = f"Top-{r.top_n}" + (f" +sec{int(r.max_sector_pct * 100)}" if r.max_sector_pct else "")
            lines.append(
                f"| {label} | {r.n_rebalances} | {r.avg_names:.1f} | {_fmt(r.full['cagr'], pct=True)} "
                f"| {_fmt(r.full['sharpe'])} | {_fmt(r.full['max_drawdown'], pct=True)} "
                f"| {_fmt(r.full['calmar'])} | {_fmt(r.oos['sharpe'])} | {_fmt(r.avg_turnover, pct=True)} |")
        if not corr.empty:
            lines += ["\n## Cross-config monthly-return correlation\n", "```",
                      corr.round(2).to_string(), "```"]
        lines += ["\n## Reading\n", *[f"{ln}" for ln in _verdict(results)]]
        if args.max_sector_pct is not None and sector_cov == 0:
            lines.append(f"\n> Sector-cap arm (--max-sector-pct {args.max_sector_pct}) was SKIPPED: "
                         f"the local store has no sector data. Re-run on the sector-populated store.")
        (d / "mom002_report.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"\nWrote {d / 'mom002_report.md'} and mom002_results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
