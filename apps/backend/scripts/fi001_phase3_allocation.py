"""FI-001 Phase 3 — Allocation.

Third executable of the FI-001 charter. Phase 2 showed equal-weight blending banks a
~6-8pp drawdown reduction but leaves the Sharpe gate uncleared. Phase 3 asks whether a
PRINCIPLED weighting across the validated books does better than naive equal weight and
than standalone momentum, on the pre-registered H4 gate.

Allocation methods (all weights estimated from a TRAILING window ending strictly before
each monthly rebalance -> no look-ahead):
  - equal_weight        : 1/N static (the Phase 2 control)
  - inverse_vol         : w_i proportional 1/sigma_i (diagonal risk parity)
  - erc                 : equal risk contribution on the full covariance (PORT-001 engine)
  - min_variance        : correlation-aware -- long-only min-variance (clip inv(cov).1)
  - erc_voltarget       : ERC book, then a daily EWMA vol-target gross-exposure overlay

Each combined book is judged vs BOTH standalone momentum (the incumbent) AND equal-weight
(the naive allocation control), with paired Sharpe-diff bootstrap CIs. Books are built
identically (weekly, long-only, equal-weight, survivorship-free); no factor re-optimized.
Sector arm skipped when the store has no `tickers.sector` (run on the box).

    cd apps/backend
    .venv/Scripts/python.exe scripts/fi001_phase3_allocation.py \
        --start 2019-01-01 --end 2026-06-13 --n 150 --report-dir research/fi001/phase3/

Outputs a console summary + (with --report-dir) fi001_phase3_report.md + _results.json.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.factor_data import evidence as ev  # noqa: E402
from app.factor_data.backtest import _vol_target_overlay, run_momentum_backtest  # noqa: E402
from app.factor_data.evidence import paired_sharpe_diff_ci  # noqa: E402
from app.factor_data.factors.low_vol import low_vol_scores  # noqa: E402
from app.factor_data.factors.sector import sector_scores  # noqa: E402
from app.factor_data.factors.trend import trend_scores  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402
from app.research.factor_lab.erc import erc_weights  # noqa: E402

BOOKS = ["momentum", "low_vol", "trend", "sector"]
INITIAL = 100_000.0
LOOKBACK = 126   # trailing trading days for weight estimation
MIN_WINDOW = 60  # need at least this many trailing days or fall back to equal weight


def _score_fn(book: str, n: int):
    if book == "momentum":
        return None
    return {"low_vol": lambda s, d: low_vol_scores(s, d, n=n),
            "trend": lambda s, d: trend_scores(s, d, n=n),
            "sector": lambda s, d: sector_scores(s, d, n=n)}[book]


def _returns(curve: list[tuple[date, float]]) -> pd.Series:
    s = pd.Series({pd.Timestamp(d): eq for d, eq in curve}).sort_index()
    return s.pct_change().dropna()


def _curve_from_returns(ret: pd.Series, initial: float = INITIAL) -> list[tuple[date, float]]:
    eq, out = initial, []
    for ts, r in ret.items():
        eq *= 1.0 + float(r)
        out.append((ts.date(), eq))
    return out


# ---- weight functions (trailing window -> long-only weights summing to 1) ----


def _w_equal(win: pd.DataFrame) -> np.ndarray:
    n = win.shape[1]
    return np.ones(n) / n


def _w_inverse_vol(win: pd.DataFrame) -> np.ndarray:
    sig = win.std().to_numpy()
    sig = np.where(sig > 0, sig, np.nan)
    inv = np.where(np.isfinite(sig), 1.0 / sig, 0.0)
    return inv / inv.sum() if inv.sum() > 0 else _w_equal(win)


def _w_erc(win: pd.DataFrame) -> np.ndarray:
    cov = win.cov().to_numpy()
    try:
        return np.asarray(erc_weights(cov), dtype=float)
    except Exception:  # noqa: BLE001 — degenerate cov -> fall back
        return _w_equal(win)


def _w_min_variance(win: pd.DataFrame) -> np.ndarray:
    """Long-only minimum-variance (correlation-aware): clip inv(cov)·1 to >=0, renorm."""
    cov = win.cov().to_numpy()
    try:
        raw = np.linalg.solve(cov, np.ones(cov.shape[0]))
    except np.linalg.LinAlgError:
        return _w_equal(win)
    raw = np.clip(raw, 0.0, None)
    return raw / raw.sum() if raw.sum() > 0 else _w_equal(win)


WEIGHT_FNS = {
    "equal_weight": _w_equal,
    "inverse_vol": _w_inverse_vol,
    "erc": _w_erc,
    "min_variance": _w_min_variance,
}


def _combined_returns(R: pd.DataFrame, weight_fn) -> pd.Series:
    """Combined-book daily returns under a monthly-rebalanced, trailing-estimated weight.
    Weights at month M use only returns STRICTLY BEFORE M (no look-ahead)."""
    months = sorted({(ts.year, ts.month) for ts in R.index})
    pieces: list[pd.Series] = []
    for (y, m) in months:
        month_mask = (R.index.year == y) & (R.index.month == m)
        month_rows = R.loc[month_mask]
        if month_rows.empty:
            continue
        first_ts = month_rows.index[0]
        trailing = R.loc[R.index < first_ts].tail(LOOKBACK)
        w = weight_fn(trailing) if len(trailing) >= MIN_WINDOW else _w_equal(R)
        pieces.append(pd.Series(month_rows.to_numpy() @ w, index=month_rows.index))
    return pd.concat(pieces).sort_index() if pieces else pd.Series(dtype=float)


def _calmar(cagr: float, mdd: float) -> float | None:
    return None if mdd == 0 else abs(cagr / mdd)


@dataclass
class AllocResult:
    method: str
    cagr: float | None
    sharpe: float | None
    max_drawdown: float | None
    calmar: float | None
    # vs standalone momentum
    dS_vs_mom: float | None
    ci_mom: list | None
    improves_vs_mom: bool
    # vs equal-weight (the naive-allocation control)
    dS_vs_eqw: float | None
    ci_eqw: list | None
    improves_vs_eqw: bool
    dMaxDD_vs_mom_pp: float | None


def _metrics(ret: pd.Series) -> tuple[float, float, float, float | None]:
    curve = _curve_from_returns(ret)
    cg, mdd = ev.cagr(curve), ev.max_drawdown(curve)
    return round(cg, 4), round(ev.sharpe(ret.tolist()), 3), round(mdd, 4), (
        round(_calmar(cg, mdd), 3) if _calmar(cg, mdd) is not None else None)


def main() -> int:
    ap = argparse.ArgumentParser(description="FI-001 Phase 3 allocation.")
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2026-06-13")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--vol-target", type=float, default=0.12, help="annual vol target for the overlay arm.")
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    store = FactorDataStore(read_only=True)
    bounds = store.price_date_bounds()
    sector_cov = store.con.execute("SELECT count(*) FROM tickers WHERE sector IS NOT NULL").fetchone()[0]
    books = [b for b in BOOKS if b != "sector" or sector_cov > 0]
    sector_note = None if sector_cov > 0 else "Sector arm SKIPPED: store has no sector data (run on the box)."

    print(f"FI-001 Phase 3 Allocation -- universe {args.n}, {start}..{end}, vol-target {args.vol_target}")
    print(f"Store bounds {bounds[0]}..{bounds[1]}; sector coverage {sector_cov}")
    if sector_note:
        print("NOTE: " + sector_note)

    ret: dict[str, pd.Series] = {}
    for book in books:
        print(f"running {book} ...", flush=True)
        rep = run_momentum_backtest(store, start, end, n=args.n, score_fn=_score_fn(book, args.n))
        ret[book] = _returns(rep.equity_curve)
    store.close()

    R = pd.DataFrame(ret).dropna()
    mom = R["momentum"]

    # the base combined books
    combined: dict[str, pd.Series] = {name: _combined_returns(R, fn) for name, fn in WEIGHT_FNS.items()}
    # vol-target overlay on the ERC book
    erc_curve = _curve_from_returns(combined["erc"])
    vt_curve = _vol_target_overlay(erc_curve, vol_target_annual=args.vol_target, span=20, initial_equity=INITIAL)
    vt_ret = pd.Series({pd.Timestamp(d): eq for d, eq in vt_curve}).sort_index().pct_change().dropna()
    combined["erc_voltarget"] = vt_ret

    eqw = combined["equal_weight"]
    results: list[AllocResult] = []
    for method, cret in combined.items():
        cg, sh, mdd, cal = _metrics(cret)
        # align each comparison independently
        a = pd.concat([cret, mom], axis=1, keys=["c", "m"]).dropna()
        ci_m = paired_sharpe_diff_ci(a["c"].tolist(), a["m"].tolist())
        b = pd.concat([cret, eqw], axis=1, keys=["c", "e"]).dropna()
        ci_e = paired_sharpe_diff_ci(b["c"].tolist(), b["e"].tolist())
        _, _, mom_mdd, _ = _metrics(mom)
        results.append(AllocResult(
            method=method, cagr=cg, sharpe=sh, max_drawdown=mdd, calmar=cal,
            dS_vs_mom=ci_m.delta, ci_mom=[_nan(ci_m.ci_low), _nan(ci_m.ci_high)],
            improves_vs_mom=ci_m.excludes_zero_positive(),
            dS_vs_eqw=ci_e.delta, ci_eqw=[_nan(ci_e.ci_low), _nan(ci_e.ci_high)],
            improves_vs_eqw=ci_e.excludes_zero_positive(),
            dMaxDD_vs_mom_pp=round((abs(mom_mdd) - abs(mdd)) * 100, 2)))

    # ---- console ----
    print(f"\n{'method':16}{'CAGR':>8}{'Sharpe':>8}{'MaxDD':>8}{'Calmar':>8}"
          f"{'dS vs mom [CI]':>24}{'dS vs eqw [CI]':>24}{'dDD pp':>8}")
    for r in results:
        cg = f"{r.cagr*100:.1f}%" if r.cagr is not None else "n/a"
        dd = f"{r.max_drawdown*100:.1f}%" if r.max_drawdown is not None else "n/a"
        cim = f"{r.dS_vs_mom} {r.ci_mom}"
        cie = f"{r.dS_vs_eqw} {r.ci_eqw}"
        flag = "  <== beats mom" if r.improves_vs_mom else ("  (beats eqw)" if r.improves_vs_eqw else "")
        print(f"{r.method:16}{cg:>8}{str(r.sharpe):>8}{dd:>8}{str(r.calmar):>8}"
              f"{cim:>24}{cie:>24}{str(r.dMaxDD_vs_mom_pp):>8}{flag}")

    # ---- report ----
    if args.report_dir:
        import json
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "fi001_phase3_results.json").write_text(json.dumps({
            "window": {"start": str(start), "end": str(end), "n": args.n, "vol_target": args.vol_target},
            "sector_coverage": sector_cov,
            "results": [asdict(r) for r in results],
        }, indent=2, default=str), encoding="utf-8")
        lines = [
            "# FI-001 Phase 3 — Allocation\n",
            f"Universe {args.n} - {start}..{end} - store {bounds[0]}..{bounds[1]}. Weights estimated from "
            f"a trailing {LOOKBACK}d window, monthly rebalance, no look-ahead. Books: {', '.join(books)}. "
            f"Vol-target overlay = {args.vol_target:.0%} annual on the ERC book.\n",
            "| method | CAGR | Sharpe | MaxDD | Calmar | dSharpe vs mom [95% CI] | dSharpe vs eqw [95% CI] | dMaxDD vs mom (pp) |",
            "|---|---|---|---|---|---|---|---|"]
        for r in results:
            cg = f"{r.cagr*100:.1f}%" if r.cagr is not None else "n/a"
            dd = f"{r.max_drawdown*100:.1f}%" if r.max_drawdown is not None else "n/a"
            lines.append(f"| {r.method} | {cg} | {r.sharpe} | {dd} | {r.calmar} "
                         f"| {r.dS_vs_mom} {r.ci_mom} | {r.dS_vs_eqw} {r.ci_eqw} | {r.dMaxDD_vs_mom_pp} |")
        lines += ["\n## Reading (H4)\n",
                  "- **Beats momentum** = dSharpe-vs-mom CI excludes zero (a real risk-adjusted edge over "
                  "the incumbent). **Beats eqw** = dSharpe-vs-equal-weight CI excludes zero (the principled "
                  "weight is worth its complexity over naive 1/N).",
                  "- Weights are trailing-estimated (no look-ahead); `erc_voltarget` adds a daily EWMA "
                  "vol-target gross-exposure overlay on the ERC book."]
        if sector_note:
            lines.append(f"\n> {sector_note}")
        (d / "fi001_phase3_report.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"\nWrote {d / 'fi001_phase3_report.md'} and fi001_phase3_results.json")
    return 0


def _nan(x: float) -> float | None:
    return None if x != x else x


if __name__ == "__main__":
    raise SystemExit(main())
