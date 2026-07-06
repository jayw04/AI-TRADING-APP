"""[DEPRECATED 2026-06-25 — superseded by the Factor Lab, ADR 0026]

Author new work as a ``ProgramSpec`` and run it through
``app.research.factor_lab.runner.run_program(app.research.factor_lab.configs.TREND_001, store=…)``
instead. ``run_program`` reproduces this harness's committed evidence package byte-for-byte —
**55/55 fields matched** on the full 2000–2026 window (equivalence proven 2026-06-25; ADR 0026 §5).
This bespoke script is **retained, not deleted**, as the immutable scientific record — its tests stay
green and its evidence package stands. Do not add new programs here.

TREND-001 Trend Following research harness (pre-registered, read-only).

Frozen plan v0.2 (`docs/implementation/TradingWorkbench_TREND001_TrendFollowing_Plan_v0.1.md`):
signal = **per-name price > 200-day SMA**, weekly Monday rebalance, **hold all in-trend
names equal-weight (1/N each → gross = #in-trend / N), cash the rest**, top-200 universe.

The question: does a *per-name* time-series trend signal add value to the platform —
standalone risk-adjusted edge (H1), an incremental diversifier of cross-sectional
momentum (H2), or downside/participation protection (H3) — **beyond the portfolio-level
regime filter the platform already runs**?

Why a bespoke simulator: trend following's defining property is that gross exposure
*falls* in downtrends (cash when few names are in-trend). The shared
``run_momentum_backtest`` is always fully invested (it drops, not banks, any
sub-1.0 weight — see ``backtest._simulate``), so it cannot model participation. We
therefore reuse ``run_momentum_backtest`` for the fully-invested benchmarks (momentum,
equal-weight) and use a cash-aware sim — mirroring ``_simulate``'s daily closeadj
marking, with an explicit constant cash sleeve and one-way turnover charged on the
stock legs only — for the trend book and the regime-filter control.

Read-only research (ADR 0019); no order path, no broker, no DB session, no LLM. Output:
script → JSON → Markdown evidence package, seeded/deterministic.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import random
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pandas as pd  # noqa: E402

from app.factor_data import evidence as ev  # noqa: E402
from app.factor_data.backtest import (  # noqa: E402
    _CachedPriceStore,
    _iso_week_last_trading_days,
    run_momentum_backtest,
    simulate_cash_book,
)
from app.factor_data.regime import market_breadth  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402
from app.factor_data.universe import universe_asof  # noqa: E402

SMA_DAYS = 200       # frozen trend window (= the platform's regime-filter window)
BREADTH_MA_DAYS = 200  # the regime-control market proxy (ADR 0022, vendor-free breadth)


def in_trend_names(store: Any, as_of: date, *, n: int, sma_days: int = SMA_DAYS) -> tuple[list[str], list[str]]:
    """(universe, in-trend subset) as of `as_of`: in-trend iff last close (strictly
    before `as_of`) > its `sma_days`-day SMA. Point-in-time, no look-ahead."""
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
            if c is not None and float(c) > 0 and dt.date() < as_of  # strictly before
        ]
        closes = closes[-sma_days:]
        if len(closes) < sma_days:
            continue
        sma = sum(closes) / len(closes)
        if closes[-1] > sma:
            in_trend.append(t)
    return universe, in_trend


def _trend_select(store: Any, as_of: date, *, n: int, sma_days: int = SMA_DAYS) -> dict[str, float]:
    """Equal-weight the in-trend names at 1/|universe| each → gross = #in-trend/N,
    the remainder is cash (the participation mechanism)."""
    universe, in_trend = in_trend_names(store, as_of, n=n, sma_days=sma_days)
    if not universe:
        return {}
    w = 1.0 / len(universe)
    return {t: w for t in in_trend}


def _regime_eqw_select(store: Any, as_of: date, *, n: int, ma_days: int = BREADTH_MA_DAYS) -> dict[str, float]:
    """The competing-explanation control: hold the equal-weight universe fully when
    market breadth ≥ 0.5 (the portfolio-level regime filter), else all cash. Tests
    whether per-name trend beats the market-level timing the platform already has."""
    universe = universe_asof(store, as_of, n=n)
    if not universe:
        return {}
    breadth = market_breadth(store, as_of, n=n, ma_days=ma_days)
    if breadth is None or breadth < 0.5:
        return {}  # risk-off → cash
    w = 1.0 / len(universe)
    return {t: w for t in universe}


def _curve_stats(curve: list[tuple[date, float]]) -> dict[str, float]:
    r = ev.daily_returns(curve)
    c = ev.cagr(curve)
    dd = ev.max_drawdown(curve)
    return {"cagr": c, "sharpe": ev.sharpe(r), "max_drawdown": dd, "calmar": ev.calmar(c, dd)}


def _paired_sharpe_diff_ci(a_r: list[float], b_r: list[float], *, n_resamples: int, seed: int,
                           block: int = 21) -> dict[str, float]:
    """Circular-block paired bootstrap of Sharpe(a) - Sharpe(b) (a=strategy, b=benchmark)."""
    n = min(len(a_r), len(b_r))
    point = ev.sharpe(a_r[:n]) - ev.sharpe(b_r[:n])
    if n < block * 2:
        return {"delta": round(point, 3), "ci_low": float("nan"), "ci_high": float("nan")}
    rng = random.Random(seed)
    diffs: list[float] = []
    for _ in range(n_resamples):
        idx: list[int] = []
        while len(idx) < n:
            s0 = rng.randrange(n)
            idx.extend((s0 + k) % n for k in range(block))
        idx = idx[:n]
        diffs.append(ev.sharpe([a_r[i] for i in idx]) - ev.sharpe([b_r[i] for i in idx]))
    diffs.sort()
    return {"delta": round(point, 3), "ci_low": round(diffs[int(0.025 * n_resamples)], 3),
            "ci_high": round(diffs[min(int(0.975 * n_resamples), n_resamples - 1)], 3)}


def _returns_corr(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 30:
        return None
    s = pd.concat([pd.Series(a[:n]), pd.Series(b[:n])], axis=1)
    c = float(s.corr().iloc[0, 1])
    return round(c, 3) if c == c else None  # NaN-safe


def _blend_curve(a: list[tuple[date, float]], b: list[tuple[date, float]],
                 *, initial_equity: float = 100_000.0) -> list[tuple[date, float]]:
    """A 50/50 daily-rebalanced blend of two equity curves (returns-averaged)."""
    ar, br = ev.daily_returns(a), ev.daily_returns(b)
    dates = [d for d, _ in a][1:]  # daily_returns drops the first point
    n = min(len(ar), len(br), len(dates))
    eq = initial_equity
    out: list[tuple[date, float]] = []
    for i in range(n):
        eq *= 1.0 + 0.5 * (ar[i] + br[i])
        out.append((dates[i], eq))
    return out


def _windows(start: date, end: date, k: int) -> list[tuple[date, date]]:
    step = max(1, (end - start).days // k)
    out = []
    for i in range(k):
        ws = date.fromordinal(start.toordinal() + i * step)
        we = end if i == k - 1 else date.fromordinal(start.toordinal() + (i + 1) * step)
        out.append((ws, we))
    return out


def _excludes_zero_pos(ci: dict[str, float]) -> bool:
    lo = ci["ci_low"]
    return lo == lo and lo > 0  # NaN-safe


def classify_outcome(
    *, h1_real: bool, consistent: bool, blend_helps: bool,
    dd_vs_mom: float, dd_vs_eqw: float, beats_regime: bool, h1_ci_high: float,
) -> tuple[str, str, dict[str, bool]]:
    """The frozen TREND-001 verdict tree (plan v0.2 §4), as a pure function.

    Faithful to the pre-registered triggers (no extra gates):
      - **A — Validated**: H1 clears (standalone risk-adjusted edge) and is consistent.
      - **B — Diversifier / Defensive**: H1 fails, but **H2 *or* H3 clears _beyond the
        existing regime filter_**. H2 = the blend statistically helps; H3 = trend
        drawdown materially shallower than BOTH momentum and equal-weight AND it beats
        the portfolio-level regime-filter control (``beats_regime``).
      - **C — Rejected**: H1, H2, H3 all fail, OR the benefit is fully subsumed by the
        regime filter (``not beats_regime``).
      - **D — Inconclusive**: anything else (borderline / wide CI).

    NB correlation is descriptive only — the plan triggers B on H2 *or* H3, so a high
    trend↔momentum correlation does NOT block a B verdict earned on the H3 axis.
    """
    h2_clears = blend_helps
    h3_clears = dd_vs_mom > 0.0 and dd_vs_eqw > 0.0 and beats_regime
    subsumed = not beats_regime
    flags = {"h2_clears": h2_clears, "h3_clears": h3_clears, "subsumed": subsumed}

    if h1_real and consistent:
        return ("A - Validated",
                "standalone trend book candidate -> governance -> paper", flags)
    if (h2_clears or h3_clears) and not subsumed:
        return ("B - Diversifier / Defensive",
                "participation sleeve / momentum+trend blend candidate (evidence-gated)", flags)
    all_fail = not (h2_clears or h3_clears) and (h1_ci_high == h1_ci_high and h1_ci_high < 0)
    if subsumed or all_fail:
        return ("C - Rejected",
                "benefit subsumed by the existing portfolio-level regime filter; per-name "
                "trend adds nothing here -> knowledge base (validates existing machinery)", flags)
    return ("D - Inconclusive",
            "research debt -> inverse-vol / multi-window V2", flags)


def _git_sha() -> str:
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def _run_trend(store: Any, start: date, end: date, *, n: int, cost_bps: float = 10.0
               ) -> tuple[list[tuple[date, float]], list[tuple[date, float]]]:
    """Trend book over [start, end] on a per-run price cache. Returns (curve, gross_series)."""
    cached = _CachedPriceStore(store)
    days = cached.trading_days(start, end)
    rebs = _iso_week_last_trading_days(days)
    return simulate_cash_book(cached, rebs, days, lambda d: _trend_select(cached, d, n=n),
                              turnover_cost_bps=cost_bps)


def _run_regime_eqw(store: Any, start: date, end: date, *, n: int
                    ) -> list[tuple[date, float]]:
    cached = _CachedPriceStore(store)
    days = cached.trading_days(start, end)
    rebs = _iso_week_last_trading_days(days)
    curve, _ = simulate_cash_book(cached, rebs, days, lambda d: _regime_eqw_select(cached, d, n=n))
    return curve


def main() -> int:
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(description="TREND-001 Trend Following research")
    ap.add_argument("--store", default=None)
    ap.add_argument("--start", default="2000-01-01")
    ap.add_argument("--end", default="2026-06-12")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--windows", type=int, default=5)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    started = time.monotonic()
    exp_id = f"EXP-{datetime.now(UTC):%Y%m%d-%H%M%S}-trend001"

    store = FactorDataStore(db_path=args.store, read_only=True)
    try:
        n = args.n
        mom_rep = run_momentum_backtest(store, start, end, n=n)
        eq_curve = mom_rep.baseline_curve
        trend_curve, gross = _run_trend(store, start, end, n=n)
        regime_curve = _run_regime_eqw(store, start, end, n=n)
        blend_curve = _blend_curve(trend_curve, mom_rep.equity_curve)

        mom, eqw = _curve_stats(mom_rep.equity_curve), _curve_stats(eq_curve)
        trend, regime, blend = (_curve_stats(trend_curve), _curve_stats(regime_curve),
                                _curve_stats(blend_curve))

        tr, mr, er = (ev.daily_returns(trend_curve), ev.daily_returns(mom_rep.equity_curve),
                      ev.daily_returns(eq_curve))
        # H1: trend vs equal-weight (standalone risk-adjusted)
        h1 = _paired_sharpe_diff_ci(tr, er, n_resamples=args.bootstrap, seed=args.seed)
        # H2: corr(trend, momentum) + blend vs momentum-alone
        corr = _returns_corr(tr, mr)
        h2_blend = _paired_sharpe_diff_ci(ev.daily_returns(blend_curve), mr,
                                          n_resamples=args.bootstrap, seed=args.seed)
        # H3: downside + the competing-explanation A/B vs the regime filter
        dd_vs_mom = round(trend["max_drawdown"] - mom["max_drawdown"], 4)      # >0 ⇒ shallower
        dd_vs_eqw = round(trend["max_drawdown"] - eqw["max_drawdown"], 4)
        dd_vs_regime = round(trend["max_drawdown"] - regime["max_drawdown"], 4)
        sharpe_vs_regime = round(trend["sharpe"] - regime["sharpe"], 3)
        gross_vals = [g for _, g in gross]
        gross_mean = round(sum(gross_vals) / len(gross_vals), 3) if gross_vals else None
        gross_min = round(min(gross_vals), 3) if gross_vals else None

        # walk-forward (trend vs equal-weight): Sharpe delta + drawdown
        wf, n_pos, n_dd_better = [], 0, 0
        for ws, we in _windows(start, end, args.windows):
            try:
                w_trend_curve, _ = _run_trend(store, ws, we, n=n)
                w_rep = run_momentum_backtest(store, ws, we, n=n)
                w_eqw = _curve_stats(w_rep.baseline_curve)
                w_tr = _curve_stats(w_trend_curve)
                wf.append({"window": [str(ws), str(we)], "trend_sharpe": round(w_tr["sharpe"], 2),
                           "eqw_sharpe": round(w_eqw["sharpe"], 2),
                           "delta": round(w_tr["sharpe"] - w_eqw["sharpe"], 2),
                           "trend_maxdd": round(w_tr["max_drawdown"], 3),
                           "eqw_maxdd": round(w_eqw["max_drawdown"], 3)})
                if w_tr["sharpe"] - w_eqw["sharpe"] > 0:
                    n_pos += 1
                if w_tr["max_drawdown"] > w_eqw["max_drawdown"]:  # shallower
                    n_dd_better += 1
            except Exception as exc:  # noqa: BLE001
                wf.append({"window": [str(ws), str(we)], "error": repr(exc)})

        # cost sweep (trend book)
        costs = {}
        for bps in (5.0, 10.0, 20.0, 50.0):
            cc, _ = _run_trend(store, start, end, n=n, cost_bps=bps)
            costs[f"{int(bps)}bps"] = round(_curve_stats(cc)["sharpe"], 2)

        # verdict (A/B/C/D per the frozen plan §4) — pure, testable
        h1_real = _excludes_zero_pos(h1)
        consistent = bool([w for w in wf if "delta" in w]) and n_pos >= (args.windows + 1) // 2 + 1
        blend_helps = _excludes_zero_pos(h2_blend)
        beats_regime = sharpe_vs_regime > 0.0 or dd_vs_regime > 0.0
        outcome, action, verdict_flags = classify_outcome(
            h1_real=h1_real, consistent=consistent, blend_helps=blend_helps,
            dd_vs_mom=dd_vs_mom, dd_vs_eqw=dd_vs_eqw, beats_regime=beats_regime,
            h1_ci_high=h1["ci_high"],
        )
        subsumed = verdict_flags["subsumed"]

        result: dict[str, Any] = {
            "program": "TREND-001", "experiment_id": exp_id, "git_sha": _git_sha(),
            "data": "SEP survivorship-free (full-cycle 2000-2026)",
            "window": [str(start), str(end)], "n": n,
            "construction": "V1 per-name close>200d SMA, in-trend equal-weight (1/N), cash rest",
            "books": {"momentum": mom, "trend": trend, "blend": blend,
                      "equal_weight": eqw, "regime_eqw": regime},
            "H1_trend_vs_eqw_sharpe_ci": h1,
            "H2_corr_trend_momentum": corr, "H2_blend_vs_momentum_sharpe_ci": h2_blend,
            "H3_maxdd_vs_momentum": dd_vs_mom, "H3_maxdd_vs_eqw": dd_vs_eqw,
            "H3_maxdd_vs_regime_filter": dd_vs_regime, "H3_sharpe_vs_regime_filter": sharpe_vs_regime,
            "H3_windows_trend_shallower_dd": f"{n_dd_better}/{args.windows}",
            "participation_gross_mean": gross_mean, "participation_gross_min": gross_min,
            "walk_forward": wf, "n_windows_trend_beats_eqw": f"{n_pos}/{args.windows}",
            "cost_sweep_trend_sharpe": costs,
            "beats_regime_filter": beats_regime, "subsumed_by_regime_filter": subsumed,
            "outcome": outcome, "action": action,
            "duration_s": round(time.monotonic() - started, 1),
        }
    finally:
        store.close()

    b = result["books"]
    print(f"[{exp_id}] TREND-001 Trend Following  {start}..{end} n={n}")
    print(f"  momentum    Sharpe {b['momentum']['sharpe']:.2f} maxDD {b['momentum']['max_drawdown']:.1%}")
    print(f"  trend       Sharpe {b['trend']['sharpe']:.2f} maxDD {b['trend']['max_drawdown']:.1%}  "
          f"(gross mean {gross_mean}, min {gross_min})")
    print(f"  regime-eqw  Sharpe {b['regime_eqw']['sharpe']:.2f} maxDD {b['regime_eqw']['max_drawdown']:.1%}  "
          f"(the competing explanation)")
    print(f"  H1 trend-vs-eqw dSharpe {h1['delta']:+.2f} CI [{h1['ci_low']}, {h1['ci_high']}]; "
          f"windows won {result['n_windows_trend_beats_eqw']}")
    print(f"  H2 corr(trend,mom)={corr}  blend-vs-mom dSharpe {h2_blend['delta']:+.2f} "
          f"CI [{h2_blend['ci_low']}, {h2_blend['ci_high']}]")
    print(f"  H3 maxDD vs mom {dd_vs_mom:+.1%} vs eqw {dd_vs_eqw:+.1%} vs regime {dd_vs_regime:+.1%}; "
          f"beats regime filter: {result['beats_regime_filter']}")
    print(f"  -> OUTCOME: {outcome}: {action}  ({result['duration_s']}s)")

    if args.report_dir:
        outdir = Path(args.report_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "trend_following.json").write_text(json.dumps(result, indent=2, default=str),
                                                     encoding="utf-8")
        (outdir / "trend_following.md").write_text(_render(result), encoding="utf-8")
        print(f"  wrote {outdir / 'trend_following.json'} + trend_following.md")
    return 0


def _render(r: dict[str, Any]) -> str:
    b = r["books"]
    h1, h2 = r["H1_trend_vs_eqw_sharpe_ci"], r["H2_blend_vs_momentum_sharpe_ci"]

    def row(label: str, key: str) -> str:
        s = b[key]
        return (f"| {label} | {s['cagr']:+.2%} | {s['sharpe']:.2f} | {s['max_drawdown']:.1%} | "
                f"{s['calmar']:.2f} |")

    lines = [
        f"# TREND-001 Trend Following — Evidence ({r['outcome']})",
        "",
        f"_git {r['git_sha']} · {r['experiment_id']} · {r['data']} · {r['window'][0]}..{r['window'][1]} · "
        f"n={r['n']} · {r['construction']} · {r['duration_s']}s_",
        "",
        "> Pre-registered (TREND-001 plan v0.2). The question: *does a per-name time-series trend signal "
        "add value beyond the portfolio-level regime filter the platform already runs?* — standalone edge "
        "(H1), incremental diversifier (H2), or downside/participation (H3). Honest prior: the existing "
        "SPY-regime filter already de-risks the book, so Rejected (40%) was the modal pre-registered outcome.",
        "",
        "## Books",
        "",
        "| Book | CAGR | Sharpe | maxDD | Calmar |",
        "|---|---|---|---|---|",
        row("Equal-weight (benchmark)", "equal_weight"),
        row("Momentum (v1.1)", "momentum"),
        row("**Trend Following**", "trend"),
        row("Momentum+Trend blend", "blend"),
        row("Regime-filter eqw (control)", "regime_eqw"),
        "",
        f"Participation: trend gross exposure mean **{r['participation_gross_mean']}**, "
        f"min **{r['participation_gross_min']}** (falls in downtrends = the mechanism).",
        "",
        "## H1 — standalone risk-adjusted edge (trend vs equal-weight)",
        f"- **dSharpe {h1['delta']:+.2f}, paired 95% CI [{h1['ci_low']}, {h1['ci_high']}]** — "
        f"{'EXCLUDES zero (edge)' if _excludes_zero_pos(h1) else 'includes zero -> no standalone edge'}.",
        f"- Walk-forward: trend beats equal-weight in **{r['n_windows_trend_beats_eqw']}** windows.",
        "",
        "## H2 — diversifier (correlation / blend)",
        f"- corr(momentum, trend) = **{r['H2_corr_trend_momentum']}**.",
        f"- blend vs momentum-alone dSharpe {h2['delta']:+.2f}, CI [{h2['ci_low']}, {h2['ci_high']}].",
        "",
        "## H3 — downside protection & the competing-explanation A/B",
        f"- trend maxDD vs momentum: **{r['H3_maxdd_vs_momentum']:+.1%}** (positive = shallower).",
        f"- trend maxDD vs equal-weight: **{r['H3_maxdd_vs_eqw']:+.1%}**.",
        f"- **vs the existing regime filter** — maxDD {r['H3_maxdd_vs_regime_filter']:+.1%}, "
        f"Sharpe {r['H3_sharpe_vs_regime_filter']:+.2f}: per-name trend "
        f"{'BEATS' if r['beats_regime_filter'] else 'does NOT beat'} the portfolio-level filter.",
        f"- shallower drawdown than equal-weight in **{r['H3_windows_trend_shallower_dd']}** windows.",
        "",
        "## Cost sweep (trend Sharpe)",
        "  " + " · ".join(f"{k} {v}" for k, v in r["cost_sweep_trend_sharpe"].items()),
        "",
        f"## Outcome: **{r['outcome']}** → {r['action']}",
        "",
        "_Per ADR 0014 + the TREND-001 gate. 200-day SMA frozen (no optimization). No parameter "
        "introduced solely to improve historical performance. The evidence package is the deliverable._",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
