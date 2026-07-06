"""FI-001 Phase 4 — Adaptive Portfolio (v1).

Fourth and final arm of the FI-001 charter, gated by Phases 1-3. Those found: combining
the validated books reduces drawdown but never clears the Sharpe gate; naive equal-weight
beats sophisticated STATIC allocation; the vol-target overlay is the drawdown lever; and
(Phase 1) cross-book correlation is REGIME-DEPENDENT. Phase 4 asks the natural next
question: does an allocation that ADAPTS to the market regime / correlation state do
better than the static equal-weight book?

Adaptive rules (all no look-ahead -- the regime at day t uses only data through t-1):
  - static_eqw     : equal-weight, full gross (the Phase 3 winner -- the control)
  - regime_gross   : equal-weight book, gross 1.0 in risk-ON / `--risk-off-gross` in
                     risk-OFF, where regime = market proxy above/below its 200d SMA.
                     A discrete cousin of the vol-target overlay.
  - regime_tilt    : risk-ON -> overweight momentum; risk-OFF -> overweight the defensive
                     books (low-vol / trend). Same gross, different weights by regime.
  - corr_adaptive  : equal-weight book, de-risk gross when the trailing 63d average
                     pairwise book-correlation exceeds `--corr-threshold` (diversification
                     has vanished -> reduce exposure). Motivated directly by Phase 1.

The market proxy is the equal-weight-universe baseline from the momentum backtest (no
extra data). Each adaptive book is judged vs static equal-weight AND vs standalone
momentum on the paired Sharpe-diff bootstrap CI. No factor re-optimized.

    cd apps/backend
    .venv/Scripts/python.exe scripts/fi001_phase4_adaptive.py \
        --start 2019-01-01 --end 2026-06-13 --n 150 --report-dir research/fi001/phase4/

Outputs a console summary + (with --report-dir) fi001_phase4_report.md + _results.json.
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

from app.factor_data import evidence as ev  # noqa: E402
from app.factor_data.backtest import run_momentum_backtest  # noqa: E402
from app.factor_data.evidence import paired_sharpe_diff_ci  # noqa: E402
from app.factor_data.factors.low_vol import low_vol_scores  # noqa: E402
from app.factor_data.factors.sector import sector_scores  # noqa: E402
from app.factor_data.factors.trend import trend_scores  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402

BOOKS = ["momentum", "low_vol", "trend", "sector"]
INITIAL = 100_000.0
SMA_DAYS = 200
CORR_WINDOW = 63


def _score_fn(book: str, n: int):
    if book == "momentum":
        return None
    return {"low_vol": lambda s, d: low_vol_scores(s, d, n=n),
            "trend": lambda s, d: trend_scores(s, d, n=n),
            "sector": lambda s, d: sector_scores(s, d, n=n)}[book]


def _returns(curve: list[tuple[date, float]]) -> pd.Series:
    s = pd.Series({pd.Timestamp(d): eq for d, eq in curve}).sort_index()
    return s.pct_change().dropna()


def _prices(curve: list[tuple[date, float]]) -> pd.Series:
    return pd.Series({pd.Timestamp(d): eq for d, eq in curve}).sort_index()


def _curve_from_returns(ret: pd.Series, initial: float = INITIAL) -> list[tuple[date, float]]:
    eq, out = initial, []
    for ts, r in ret.items():
        eq *= 1.0 + float(r)
        out.append((ts.date(), eq))
    return out


def _calmar(cagr: float, mdd: float) -> float | None:
    return None if mdd == 0 else abs(cagr / mdd)


def _regime_riskon(proxy_px: pd.Series) -> pd.Series:
    """Boolean risk-ON series: proxy above its 200d SMA, shifted 1 day (no look-ahead)."""
    sma = proxy_px.rolling(SMA_DAYS).mean()
    # warm-up (pre-SMA) defaults risk-ON (fail open); shift 1 day = no look-ahead
    return (proxy_px > sma).shift(1, fill_value=True).astype(bool)


def _trailing_avg_corr(R: pd.DataFrame, window: int = CORR_WINDOW) -> pd.Series:
    """Rolling average pairwise correlation across the books (t uses data through t-1)."""
    cols = list(R.columns)
    pair_series = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            pair_series.append(R[cols[i]].rolling(window).corr(R[cols[j]]))
    if not pair_series:
        return pd.Series(0.0, index=R.index)
    avg = pd.concat(pair_series, axis=1).mean(axis=1)
    return avg.shift(1)  # decide today's gross from yesterday's correlation state


@dataclass
class AdaptResult:
    strategy: str
    cagr: float | None
    sharpe: float | None
    max_drawdown: float | None
    calmar: float | None
    dS_vs_eqw: float | None
    ci_eqw: list | None
    improves_vs_eqw: bool
    dS_vs_mom: float | None
    ci_mom: list | None
    improves_vs_mom: bool
    dMaxDD_vs_eqw_pp: float | None


def _metrics(ret: pd.Series):
    curve = _curve_from_returns(ret)
    cg, mdd = ev.cagr(curve), ev.max_drawdown(curve)
    return round(cg, 4), round(ev.sharpe(ret.tolist()), 3), round(mdd, 4), (
        round(_calmar(cg, mdd), 3) if _calmar(cg, mdd) is not None else None)


def _nan(x: float) -> float | None:
    return None if x != x else x


def main() -> int:
    ap = argparse.ArgumentParser(description="FI-001 Phase 4 adaptive portfolio.")
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2026-06-13")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--risk-off-gross", type=float, default=0.5, help="gross exposure in risk-off.")
    ap.add_argument("--corr-threshold", type=float, default=0.6, help="de-risk when trailing avg corr exceeds.")
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    store = FactorDataStore(read_only=True)
    bounds = store.price_date_bounds()
    sector_cov = store.con.execute("SELECT count(*) FROM tickers WHERE sector IS NOT NULL").fetchone()[0]
    books = [b for b in BOOKS if b != "sector" or sector_cov > 0]
    sector_note = None if sector_cov > 0 else "Sector arm SKIPPED: store has no sector data (run on the box)."

    print(f"FI-001 Phase 4 Adaptive -- universe {args.n}, {start}..{end}, "
          f"risk-off gross {args.risk_off_gross}, corr-threshold {args.corr_threshold}")
    print(f"Store bounds {bounds[0]}..{bounds[1]}; sector coverage {sector_cov}")
    if sector_note:
        print("NOTE: " + sector_note)

    ret: dict[str, pd.Series] = {}
    proxy_px: pd.Series | None = None
    for book in books:
        print(f"running {book} ...", flush=True)
        rep = run_momentum_backtest(store, start, end, n=args.n, score_fn=_score_fn(book, args.n))
        ret[book] = _returns(rep.equity_curve)
        if book == "momentum":
            proxy_px = _prices(rep.baseline_curve)  # equal-weight universe = market proxy
    store.close()

    R = pd.DataFrame(ret).dropna()
    mom = R["momentum"]
    eqw = R.mean(axis=1)  # static equal-weight (Phase 3 winner)

    riskon = _regime_riskon(proxy_px).reindex(R.index).fillna(True)
    avg_corr = _trailing_avg_corr(R).reindex(R.index)

    # --- adaptive strategies ---
    def gross_series(mask_riskoff: pd.Series) -> pd.Series:
        return pd.Series(1.0, index=R.index).mask(mask_riskoff, args.risk_off_gross)

    strategies: dict[str, pd.Series] = {}
    strategies["static_eqw"] = eqw
    strategies["regime_gross"] = eqw * gross_series(~riskon)
    # regime_tilt: risk-on overweight momentum; risk-off overweight defense
    on_w = {"momentum": 0.5, "low_vol": 0.25, "trend": 0.25, "sector": 0.25}
    off_w = {"momentum": 0.2, "low_vol": 0.45, "trend": 0.35, "sector": 0.25}
    on_v = pd.Series([on_w[b] for b in books])
    on_v /= on_v.sum()
    off_v = pd.Series([off_w[b] for b in books])
    off_v /= off_v.sum()
    tilt = pd.Series(0.0, index=R.index)
    tilt_on = R.to_numpy() @ on_v.to_numpy()
    tilt_off = R.to_numpy() @ off_v.to_numpy()
    tilt = pd.Series(pd.Series(tilt_on, index=R.index).where(riskon, pd.Series(tilt_off, index=R.index)))
    strategies["regime_tilt"] = tilt
    # corr_adaptive: de-risk when trailing avg corr exceeds threshold
    hi_corr = (avg_corr > args.corr_threshold).fillna(False)
    strategies["corr_adaptive"] = eqw * gross_series(hi_corr)

    _, _, eqw_mdd, _ = _metrics(eqw)
    results: list[AdaptResult] = []
    for name, sret in strategies.items():
        cg, sh, mdd, cal = _metrics(sret)
        a = pd.concat([sret, eqw], axis=1, keys=["s", "e"]).dropna()
        ci_e = paired_sharpe_diff_ci(a["s"].tolist(), a["e"].tolist())
        b = pd.concat([sret, mom], axis=1, keys=["s", "m"]).dropna()
        ci_m = paired_sharpe_diff_ci(b["s"].tolist(), b["m"].tolist())
        results.append(AdaptResult(
            strategy=name, cagr=cg, sharpe=sh, max_drawdown=mdd, calmar=cal,
            dS_vs_eqw=ci_e.delta, ci_eqw=[_nan(ci_e.ci_low), _nan(ci_e.ci_high)],
            improves_vs_eqw=ci_e.excludes_zero_positive(),
            dS_vs_mom=ci_m.delta, ci_mom=[_nan(ci_m.ci_low), _nan(ci_m.ci_high)],
            improves_vs_mom=ci_m.excludes_zero_positive(),
            dMaxDD_vs_eqw_pp=round((abs(eqw_mdd) - abs(mdd)) * 100, 2)))

    # --- console ---
    print(f"\n{'strategy':15}{'CAGR':>8}{'Sharpe':>8}{'MaxDD':>8}{'Calmar':>8}"
          f"{'dS vs eqw [CI]':>24}{'dS vs mom [CI]':>24}{'dDD vs eqw':>11}")
    for r in results:
        cg = f"{r.cagr*100:.1f}%" if r.cagr is not None else "n/a"
        dd = f"{r.max_drawdown*100:.1f}%" if r.max_drawdown is not None else "n/a"
        flag = "  <== beats eqw" if r.improves_vs_eqw else ("  (beats mom)" if r.improves_vs_mom else "")
        print(f"{r.strategy:15}{cg:>8}{str(r.sharpe):>8}{dd:>8}{str(r.calmar):>8}"
              f"{str(r.dS_vs_eqw)+' '+str(r.ci_eqw):>24}{str(r.dS_vs_mom)+' '+str(r.ci_mom):>24}"
              f"{str(r.dMaxDD_vs_eqw_pp):>11}{flag}")

    # --- report ---
    if args.report_dir:
        import json
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "fi001_phase4_results.json").write_text(json.dumps({
            "window": {"start": str(start), "end": str(end), "n": args.n,
                       "risk_off_gross": args.risk_off_gross, "corr_threshold": args.corr_threshold},
            "sector_coverage": sector_cov,
            "pct_risk_off_days": round(float((~riskon).mean()), 3),
            "results": [asdict(r) for r in results],
        }, indent=2, default=str), encoding="utf-8")
        lines = [
            "# FI-001 Phase 4 — Adaptive Portfolio (v1)\n",
            f"Universe {args.n} - {start}..{end} - store {bounds[0]}..{bounds[1]}. Regime = equal-weight "
            f"universe vs its {SMA_DAYS}d SMA (no look-ahead); risk-off gross {args.risk_off_gross}; "
            f"corr de-risk threshold {args.corr_threshold} (trailing {CORR_WINDOW}d). Books: {', '.join(books)}.\n",
            "| strategy | CAGR | Sharpe | MaxDD | Calmar | dSharpe vs eqw [95% CI] | dSharpe vs mom [95% CI] | dMaxDD vs eqw (pp) |",
            "|---|---|---|---|---|---|---|---|"]
        for r in results:
            cg = f"{r.cagr*100:.1f}%" if r.cagr is not None else "n/a"
            dd = f"{r.max_drawdown*100:.1f}%" if r.max_drawdown is not None else "n/a"
            lines.append(f"| {r.strategy} | {cg} | {r.sharpe} | {dd} | {r.calmar} "
                         f"| {r.dS_vs_eqw} {r.ci_eqw} | {r.dS_vs_mom} {r.ci_mom} | {r.dMaxDD_vs_eqw_pp} |")
        lines += ["\n## Reading (H4 adaptive)\n",
                  "- **beats eqw** = dSharpe-vs-equal-weight CI excludes zero (adaptation earns its keep "
                  "over the static Phase 3 winner). **beats mom** = same vs standalone momentum.",
                  "- All regime signals use only past data (200d SMA / trailing corr, shifted 1 day)."]
        if sector_note:
            lines.append(f"\n> {sector_note}")
        (d / "fi001_phase4_report.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"\nWrote {d / 'fi001_phase4_report.md'} and fi001_phase4_results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
