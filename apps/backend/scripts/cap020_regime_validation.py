"""CAP-020 Regime-Overlay Validation (FI-001 Phase 4 follow-on; owner priority #4).

Validates the `regime_gross` rule from FI-001 Phase 4 — equal-weight the validated factor books,
then scale gross to `g` (default 0.5) when a market proxy is below its N-day SMA (default 200) — to the
owner-defined bar (design doc `TradingWorkbench_FI001_CAP020_RegimeOverlayValidation_v0.2.md`):

  PRIMARY decision rule : Calmar improvement vs the equal-weight, overlay-OFF benchmark
  SUPPORTING evidence   : Max-Drawdown reduction (required corroborant)
  GUARDRAILS            : Sharpe / CAGR must not decline materially
  VALIDATION CHECKS     : paired-bootstrap CIs exclude zero; >= 2/3 of the SMA x gross grid passes;
                          OOS + per-environment consistency; economic-significance floor

All net of a transaction-cost sweep (5/10/20/50 bps), evaluated OUT-OF-SAMPLE, with a deployment
decision matrix (Validated / Conditionally Promising / Rejected-Evidenced). This is offline research —
no live book, no order path. Reuses the *validated* pieces from FI-001 Phase 4 (the momentum backtest
engine, the factor score fns, and the seeded circular-block bootstrap in `app/factor_data/evidence.py`);
only the trivial parameterized glue (regime gate, gross overlay, cost) is reimplemented here.

    cd apps/backend
    .venv/Scripts/python.exe scripts/cap020_regime_validation.py --report-dir research/cap020/
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.factor_data import evidence as ev  # noqa: E402

# --- study configuration (the sweep grid + acceptance thresholds) -----------

SMA_GRID = [150, 200, 250]
GROSS_GRID = [0.3, 0.5, 0.7]
COST_SWEEP_BPS = [5, 10, 20, 50]
HEADLINE_SMA, HEADLINE_GROSS = 200, 0.5      # the FI-001 Phase 4 point
DEFAULT_COST_BPS = 10                          # cost level the pass/fail call is made at
BOOTSTRAP_SEED = 17                            # fixed → reproducible CIs (evidence.py convention)

# Economic-significance floor (design §4; owner-reviewed material thresholds).
MIN_CALMAR_GAIN = 0.10       # ΔCalmar >= +0.10 (primary)
MIN_MAXDD_REDUCTION_PP = 5.0  # ΔMaxDD >= 5pp reduction (supporting)
SHARPE_GUARDRAIL = -0.05     # ΔSharpe >= -0.05
CAGR_GUARDRAIL_PP = -2.0     # ΔCAGR >= -2.0pp
ROBUSTNESS_FRACTION = 2 / 3  # >= 2/3 of the grid must pass primary + guardrails

# Data-sufficiency gate — a REGIME overlay is meaningless without regime variation. If the usable
# (all-book-overlapping) window is too short, has too few regime flips, or contains no drawdown
# environment, the study is reported "Inconclusive (data-gated)" — NOT one of the three deployment
# labels. This guards against a false verdict on a bull-only sliver of history (design §5.5 power caveat).
MIN_WINDOW_YEARS = 4.0
MIN_OOS_FLIPS = 4
BEAR_ENVIRONMENTS = ("covid_2020", "bear_2022")

# Market environments for the per-environment (not just pooled) read (design §7 risk row).
ENVIRONMENTS = {
    "covid_2020": ("2020-02-01", "2020-06-30"),
    "bear_2022": ("2022-01-01", "2022-12-31"),
    "bull_2023_24": ("2023-01-01", "2024-12-31"),
}


# --- pure, offline-testable core -------------------------------------------

def regime_riskon(proxy_px: pd.Series, sma_days: int) -> pd.Series:
    """Boolean risk-ON series: proxy above its N-day SMA, shifted 1 day (NO look-ahead). Warm-up
    (pre-SMA) fails open to risk-ON. Parameterized generalization of FI-001 Phase 4's `_regime_riskon`."""
    sma = proxy_px.rolling(sma_days).mean()
    return (proxy_px > sma).shift(1, fill_value=True).astype(bool)


def gross_series(riskon: pd.Series, risk_off_gross: float) -> pd.Series:
    """Gross-exposure series: 1.0 in risk-ON, `risk_off_gross` in risk-OFF."""
    return pd.Series(1.0, index=riskon.index).mask(~riskon.astype(bool), float(risk_off_gross))


def overlay_returns(
    eqw_ret: pd.Series, riskon: pd.Series, risk_off_gross: float, cost_bps: float
) -> pd.Series:
    """Net-of-cost daily returns of the gross overlay applied to the equal-weight book.

    return_t = gross_t * eqw_ret_t - turnover_t * (cost_bps / 1e4), where turnover_t = |gross_t -
    gross_{t-1}| is the *incremental* trading the overlay introduces on a regime flip (the benchmark
    holds gross 1.0, so its overlay turnover is zero and the base-book turnover cancels in the delta).
    Starts fully invested (gross_{-1} = 1.0)."""
    g = gross_series(riskon.reindex(eqw_ret.index).fillna(True), risk_off_gross)
    turnover = g.diff().abs()
    turnover.iloc[0] = abs(g.iloc[0] - 1.0)
    return g * eqw_ret - turnover * (float(cost_bps) / 1e4)


# metric helpers — returns-based, annualization 252/n, used consistently for BOTH the point deltas
# and the bootstrap so the point estimate and its CI use one estimator.
def _mdd(rets: list[float]) -> float:
    eq, peak, worst = 1.0, 1.0, 0.0
    for r in rets:
        eq *= 1.0 + r
        peak = max(peak, eq)
        worst = min(worst, eq / peak - 1.0)
    return worst  # <= 0


def _cagr(rets: list[float]) -> float:
    n = len(rets)
    if n == 0:
        return 0.0
    eq = 1.0
    for r in rets:
        eq *= 1.0 + r
    return eq ** (252.0 / n) - 1.0 if eq > 0 else -1.0


def _calmar(rets: list[float]) -> float:
    m = _mdd(rets)
    return _cagr(rets) / abs(m) if m < 0 else float("nan")


def metrics_row(rets: list[float]) -> dict:
    """Descriptive metrics for one return series (Sharpe from evidence.py; the rest returns-based)."""
    s = pd.Series(rets, dtype="float64")
    worst_month = float((s.rolling(21).apply(lambda w: (1 + w).prod() - 1.0, raw=True)).min())
    k = max(1, int(0.05 * len(s)))
    cvar5 = float(s.nsmallest(k).mean()) if len(s) else float("nan")
    return {
        "cagr": round(_cagr(rets), 4), "sharpe": round(ev.sharpe(rets), 3),
        "maxdd": round(_mdd(rets), 4), "calmar": round(_calmar(rets), 3),
        "worst_month": round(worst_month, 4), "cvar5": round(cvar5, 4),
    }


def paired_diff_ci(a: list[float], b: list[float], stat, *, seed: int = BOOTSTRAP_SEED,
                   block: int = 21, n_resamples: int = 2000) -> tuple[float, float, float]:
    """Circular-block PAIRED bootstrap of ``stat(a) - stat(b)`` (a = overlay, b = benchmark). Same
    resampled day-indices applied to both series each draw (controls for shared market days). Mirrors
    ``evidence.paired_sharpe_diff_ci`` but for any path-dependent statistic (MaxDD / Calmar). Returns
    (delta, ci_low, ci_high); CIs are NaN when the series is too short."""
    import random

    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    point = stat(a) - stat(b)
    if n < block * 2:
        return round(point, 4), float("nan"), float("nan")
    rng = random.Random(seed)
    diffs: list[float] = []
    for _ in range(n_resamples):
        idx: list[int] = []
        while len(idx) < n:
            s0 = rng.randrange(n)
            idx.extend((s0 + k) % n for k in range(block))
        idx = idx[:n]
        ra = [a[i] for i in idx]
        rb = [b[i] for i in idx]
        diffs.append(stat(ra) - stat(rb))
    diffs.sort()
    return (round(point, 4), round(diffs[int(0.025 * n_resamples)], 4),
            round(diffs[min(int(0.975 * n_resamples), n_resamples - 1)], 4))


def _ci_excludes_zero(lo: float, hi: float, *, positive: bool) -> bool:
    """True iff the CI lies strictly on the required side of zero (NaN-safe)."""
    if lo != lo or hi != hi:  # NaN
        return False
    return lo > 0 if positive else hi < 0


@dataclass
class CellResult:
    sma: int
    gross: float
    cost_bps: float
    d_calmar: float
    calmar_ci: list
    d_maxdd_pp: float          # positive = reduction (benchmark worse)
    maxdd_ci_pp: list
    d_sharpe: float
    d_cagr_pp: float
    n_flips: int
    turnover: float
    passes_primary: bool       # ΔCalmar material + CI>0
    passes_supporting: bool    # ΔMaxDD material + CI (reduction) significant
    passes_guardrails: bool    # Sharpe + CAGR guardrails hold
    passes: bool               # all of the above


def evaluate_cell(eqw_ret: pd.Series, proxy_px: pd.Series, sma: int, gross: float,
                  cost_bps: float) -> CellResult:
    """One (SMA, gross, cost) cell: overlay vs eqw-overlay-OFF benchmark, with paired ΔCalmar/ΔMaxDD
    CIs and the pass flags for the acceptance hierarchy."""
    riskon = regime_riskon(proxy_px, sma).reindex(eqw_ret.index).fillna(True)
    ov = overlay_returns(eqw_ret, riskon, gross, cost_bps)
    a, b = ov.tolist(), eqw_ret.tolist()

    d_cal, cal_lo, cal_hi = paired_diff_ci(a, b, _calmar)
    d_mdd, mdd_lo, mdd_hi = paired_diff_ci(a, b, _mdd)  # overlay maxdd - benchmark maxdd (both <= 0)
    d_sharpe = round(ev.sharpe(a) - ev.sharpe(b), 3)
    d_cagr_pp = round((_cagr(a) - _cagr(b)) * 100, 2)
    g = gross_series(riskon, gross)
    turnover = float(g.diff().abs().fillna(abs(g.iloc[0] - 1.0)).sum())
    n_flips = int((g.diff().fillna(0) != 0).sum())

    # ΔMaxDD as a positive "pp reduced" (overlay less negative than benchmark => reduction).
    d_maxdd_pp = round((d_mdd) * 100, 2)  # overlay_mdd - bench_mdd; positive => overlay less deep
    maxdd_ci_pp = [round(mdd_lo * 100, 2), round(mdd_hi * 100, 2)]

    passes_primary = (d_cal >= MIN_CALMAR_GAIN) and _ci_excludes_zero(cal_lo, cal_hi, positive=True)
    passes_supporting = (d_maxdd_pp >= MIN_MAXDD_REDUCTION_PP) and _ci_excludes_zero(
        mdd_lo, mdd_hi, positive=True)
    passes_guardrails = (d_sharpe >= SHARPE_GUARDRAIL) and (d_cagr_pp >= CAGR_GUARDRAIL_PP)
    return CellResult(
        sma=sma, gross=gross, cost_bps=cost_bps, d_calmar=d_cal, calmar_ci=[cal_lo, cal_hi],
        d_maxdd_pp=d_maxdd_pp, maxdd_ci_pp=maxdd_ci_pp, d_sharpe=d_sharpe, d_cagr_pp=d_cagr_pp,
        n_flips=n_flips, turnover=round(turnover, 3),
        passes_primary=passes_primary, passes_supporting=passes_supporting,
        passes_guardrails=passes_guardrails,
        passes=passes_primary and passes_supporting and passes_guardrails)


def data_sufficiency(window_years: float, oos_flips: int, environments_present: list[str]) -> list[str]:
    """Return the reasons the sample is insufficient to validate a regime overlay (empty ⇒ sufficient)."""
    reasons: list[str] = []
    if window_years < MIN_WINDOW_YEARS:
        reasons.append(f"usable window {window_years:.1f}y < {MIN_WINDOW_YEARS:.0f}y "
                       "(all-book-overlapping history too short)")
    if oos_flips < MIN_OOS_FLIPS:
        reasons.append(f"only {oos_flips} OOS regime flip(s) < {MIN_OOS_FLIPS} "
                       "(the overlay barely acts)")
    if not any(e in environments_present for e in BEAR_ENVIRONMENTS):
        reasons.append("no drawdown/bear environment in the window (cannot test the overlay's purpose)")
    return reasons


def classify(headline: CellResult, robustness_frac: float) -> str:
    """Deployment decision matrix (design §4). Calmar is the primary rule; MaxDD corroborates;
    Sharpe/CAGR are guardrails; robustness (>= 2/3 grid) is the trust check."""
    if headline.passes and robustness_frac >= ROBUSTNESS_FRACTION:
        return "Validated"
    # any genuine drawdown/Calmar improvement but a failed guardrail / CI / robustness / floor
    improved = headline.d_calmar > 0 or headline.d_maxdd_pp > 0
    if improved and not (headline.d_calmar <= 0 and headline.d_maxdd_pp <= 0):
        return "Conditionally Promising"
    return "Rejected (Evidenced)"


def robustness_fraction(cells: list[CellResult]) -> float:
    """Fraction of grid cells (at the default cost) that pass primary + supporting + guardrails."""
    if not cells:
        return 0.0
    return sum(1 for c in cells if c.passes) / len(cells)


# --- data-dependent driver (runs where the FI-001 factor store lives) -------

def _git_commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(BACKEND_ROOT),
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _pkg_versions() -> dict:
    out = {"python": sys.version.split()[0]}
    for mod in ("numpy", "pandas", "scipy"):
        try:
            out[mod] = __import__(mod).__version__
        except Exception:
            out[mod] = "n/a"
    return out


@dataclass
class Reproducibility:
    git_commit: str
    packages: dict
    bootstrap_seed: int
    dataset: dict = field(default_factory=dict)


def _build_books(store, start: date, end: date, n: int):
    """Reuse FI-001 Phase 4's book construction: momentum/low_vol/trend/sector equity curves +
    the equal-weight-universe market proxy. Returns (R DataFrame of book returns, proxy_px)."""
    from app.factor_data.backtest import run_momentum_backtest
    from app.factor_data.factors.low_vol import low_vol_scores
    from app.factor_data.factors.sector import sector_scores
    from app.factor_data.factors.trend import trend_scores

    score_fns = {
        "momentum": None,
        "low_vol": lambda s, d: low_vol_scores(s, d, n=n),
        "trend": lambda s, d: trend_scores(s, d, n=n),
        "sector": lambda s, d: sector_scores(s, d, n=n),
    }
    sector_cov = store.con.execute(
        "SELECT count(*) FROM tickers WHERE sector IS NOT NULL").fetchone()[0]
    books = [b for b in ["momentum", "low_vol", "trend", "sector"] if b != "sector" or sector_cov > 0]
    ret: dict[str, pd.Series] = {}
    proxy_px: pd.Series | None = None
    for book in books:
        print(f"  running {book} ...", flush=True)
        rep = run_momentum_backtest(store, start, end, n=n, score_fn=score_fns[book])
        s = pd.Series({pd.Timestamp(d): eq for d, eq in rep.equity_curve}).sort_index()
        ret[book] = s.pct_change().dropna()
        if book == "momentum":
            proxy_px = pd.Series(
                {pd.Timestamp(d): eq for d, eq in rep.baseline_curve}).sort_index()
    return pd.DataFrame(ret).dropna(), proxy_px, books, sector_cov


def main() -> int:
    ap = argparse.ArgumentParser(description="CAP-020 regime-overlay validation.")
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2026-06-13")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--oos-frac", type=float, default=0.6, help="chronological IS fraction; OOS is the rest.")
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    from app.factor_data.store import FactorDataStore

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    store = FactorDataStore(read_only=True)
    bounds = store.price_date_bounds()
    print(f"CAP-020 validation — universe {args.n}, {start}..{end}; store {bounds[0]}..{bounds[1]}")
    R, proxy_px, books, sector_cov = _build_books(store, start, end, args.n)
    store.close()
    if proxy_px is None or R.empty:
        print("ERROR: no book returns built.")
        return 1

    eqw = R.mean(axis=1)                       # equal-weight combined book (the benchmark, overlay OFF)
    proxy_px = proxy_px.reindex(R.index).ffill()
    split = int(len(eqw) * args.oos_frac)
    oos = eqw.index[split:]
    eqw_oos = eqw.loc[oos]
    proxy_oos = proxy_px.loc[oos]
    print(f"  built {len(eqw)} days; IS {split} / OOS {len(oos)} days; books {', '.join(books)}")

    # Grid at the default cost (OOS) → robustness; headline cell → cost sweep + environments.
    grid = [evaluate_cell(eqw_oos, proxy_oos, sma, g, DEFAULT_COST_BPS)
            for sma in SMA_GRID for g in GROSS_GRID]
    rob = robustness_fraction(grid)
    headline = next(c for c in grid if c.sma == HEADLINE_SMA and c.gross == HEADLINE_GROSS)

    cost_sweep = [asdict(evaluate_cell(eqw_oos, proxy_oos, HEADLINE_SMA, HEADLINE_GROSS, c))
                  for c in COST_SWEEP_BPS]
    envs = {}
    for name, (s0, s1) in ENVIRONMENTS.items():
        m = (R.index >= pd.Timestamp(s0)) & (R.index <= pd.Timestamp(s1))
        if m.sum() < 42:
            continue
        e_eqw, e_proxy = eqw[m], proxy_px[m]
        envs[name] = asdict(evaluate_cell(e_eqw, e_proxy, HEADLINE_SMA, HEADLINE_GROSS, DEFAULT_COST_BPS))

    # Data-sufficiency gate BEFORE any deployment verdict (a regime overlay needs regime variation).
    window_years = (R.index[-1] - R.index[0]).days / 365.25
    insufficiency = data_sufficiency(window_years, headline.n_flips, list(envs))
    verdict = "Inconclusive (data-gated)" if insufficiency else classify(headline, rob)

    repro = Reproducibility(
        git_commit=_git_commit(), packages=_pkg_versions(), bootstrap_seed=BOOTSTRAP_SEED,
        dataset={"store_start": str(bounds[0]), "store_end": str(bounds[1]),
                 "universe_n": args.n, "sector_coverage": sector_cov,
                 "book_days": int(len(eqw)), "books": books})

    bench_oos = metrics_row(eqw_oos.tolist())
    print(f"\nbenchmark (eqw, overlay OFF, OOS): {bench_oos}")
    print(f"headline cell (SMA {HEADLINE_SMA}, gross {HEADLINE_GROSS}, {DEFAULT_COST_BPS}bps, OOS): "
          f"ΔCalmar {headline.d_calmar} {headline.calmar_ci}, ΔMaxDD {headline.d_maxdd_pp}pp "
          f"{headline.maxdd_ci_pp}, ΔSharpe {headline.d_sharpe}, ΔCAGR {headline.d_cagr_pp}pp, "
          f"flips {headline.n_flips}")
    print(f"robustness: {sum(1 for c in grid if c.passes)}/{len(grid)} grid cells pass "
          f"({rob:.0%}; need ≥ {ROBUSTNESS_FRACTION:.0%})")
    print(f"usable window {R.index[0].date()}..{R.index[-1].date()} ({window_years:.1f}y); "
          f"environments present: {list(envs) or 'none'}")
    if insufficiency:
        print("DATA-GATED — insufficient to validate a regime overlay:")
        for r in insufficiency:
            print(f"  - {r}")
    print(f"\n=== VERDICT: {verdict} ===")

    if args.report_dir:
        import json
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        pkg = {
            "study": "CAP-020 regime-overlay validation",
            "window": {"start": str(start), "end": str(end), "n": args.n, "oos_frac": args.oos_frac},
            "benchmark_oos": bench_oos,
            "headline": asdict(headline), "grid": [asdict(c) for c in grid],
            "cost_sweep": cost_sweep, "environments": envs,
            "robustness_fraction": round(rob, 3), "verdict": verdict,
            "usable_window": {"start": str(R.index[0].date()), "end": str(R.index[-1].date()),
                              "years": round(window_years, 2), "days": int(len(eqw)),
                              "oos_flips": headline.n_flips, "environments_present": list(envs)},
            "data_gated_reasons": insufficiency,
            "thresholds": {"min_calmar_gain": MIN_CALMAR_GAIN,
                           "min_maxdd_reduction_pp": MIN_MAXDD_REDUCTION_PP,
                           "sharpe_guardrail": SHARPE_GUARDRAIL, "cagr_guardrail_pp": CAGR_GUARDRAIL_PP,
                           "robustness_fraction": ROBUSTNESS_FRACTION},
            "reproducibility": asdict(repro),
        }
        (d / "cap020_validation_results.json").write_text(
            json.dumps(pkg, indent=2, default=str), encoding="utf-8")
        print(f"\nWrote {d / 'cap020_validation_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
