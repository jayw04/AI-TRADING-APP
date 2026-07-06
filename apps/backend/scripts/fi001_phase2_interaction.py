"""FI-001 Phase 2 — Interaction.

Second executable of the FI-001 charter. Phase 1 measured how the validated books
CORRELATE; Phase 2 asks whether COMBINING them helps: for each pair (and the 3-way
set), build a 50/50 return-level blend and test it against standalone Momentum on the
platform's pre-registered H2 gate:

  - Delta-Sharpe(blend - momentum) with a paired circular-block bootstrap CI
    (`app.factor_data.evidence.paired_sharpe_diff_ci`) -- the same significance test
    every program uses. "Improves" requires the CI to exclude zero (positive).
  - Drawdown reduction vs standalone momentum.
  - Blend Sharpe / Calmar vs the better standalone component.

Pre-registered H2 prior: blends REDUCE drawdown but the standalone-Sharpe uplift is
modest and may not clear zero (the modal, honest outcome). Momentum+Low-Vol -- the
independent pair from Phase 1 -- is the most likely to clear the bar.

Books are built with identical construction (weekly, long-only, equal-weight,
survivorship-free), varying only the score function; the blend is an aligned 50/50
average of daily returns (byte-equivalent to factor_lab `_returns_blend`). Sector arm
skipped when the store has no `tickers.sector` (run on the box). No factor is re-tuned.

    cd apps/backend
    .venv/Scripts/python.exe scripts/fi001_phase2_interaction.py \
        --start 2019-01-01 --end 2026-06-13 --n 150 --report-dir research/fi001/phase2/

Outputs a console summary + (with --report-dir) fi001_phase2_report.md + _results.json.
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
    """Rebuild a (date, equity) curve from a daily-return series (for DD/CAGR metrics)."""
    eq = initial
    out: list[tuple[date, float]] = []
    for ts, r in ret.items():
        eq *= 1.0 + float(r)
        out.append((ts.date(), eq))
    return out


def _calmar(cagr: float, mdd: float) -> float | None:
    return None if mdd == 0 else abs(cagr / mdd)


@dataclass
class Metrics:
    label: str
    cagr: float | None
    sharpe: float | None
    max_drawdown: float | None
    calmar: float | None


def _metrics(label: str, ret: pd.Series) -> Metrics:
    curve = _curve_from_returns(ret)
    if len(curve) < 2:
        return Metrics(label, None, None, None, None)
    cg = ev.cagr(curve)
    mdd = ev.max_drawdown(curve)
    return Metrics(label, round(cg, 4), round(ev.sharpe(ret.tolist()), 3),
                   round(mdd, 4), (round(_calmar(cg, mdd), 3) if _calmar(cg, mdd) is not None else None))


@dataclass
class BlendResult:
    blend: str
    components: list[str]
    metrics: dict
    # vs standalone momentum (the incumbent)
    delta_sharpe_vs_mom: float | None
    ci_low: float | None
    ci_high: float | None
    improves_sharpe: bool         # CI excludes zero (positive) -> real risk-adjusted uplift
    delta_maxdd_vs_mom_pp: float | None  # positive = shallower (better) than momentum
    verdict: str


def _verdict(improves: bool, dmdd_pp: float | None) -> str:
    if improves:
        return "IMPROVES (Sharpe CI > 0)"
    if dmdd_pp is not None and dmdd_pp >= 3.0:
        return "DIVERSIFIES (DD-only; Sharpe CI spans 0)"
    return "NO HELP"


def main() -> int:
    ap = argparse.ArgumentParser(description="FI-001 Phase 2 interaction (pairwise blends).")
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2026-06-13")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)

    store = FactorDataStore(read_only=True)
    bounds = store.price_date_bounds()
    sector_cov = store.con.execute("SELECT count(*) FROM tickers WHERE sector IS NOT NULL").fetchone()[0]
    books = [b for b in BOOKS if b != "sector" or sector_cov > 0]
    sector_note = None if sector_cov > 0 else ("Sector arm SKIPPED: store has no sector data "
                                               "(run on the box).")

    print(f"FI-001 Phase 2 Interaction -- universe {args.n}, {start}..{end}")
    print(f"Store bounds {bounds[0]}..{bounds[1]}; sector coverage {sector_cov}")
    if sector_note:
        print("NOTE: " + sector_note)

    ret: dict[str, pd.Series] = {}
    for book in books:
        print(f"running {book} ...", flush=True)
        rep = run_momentum_backtest(store, start, end, n=args.n, score_fn=_score_fn(book, args.n))
        ret[book] = _returns(rep.equity_curve)
    store.close()

    # align all books on common dates (paired bootstrap needs positional alignment)
    R = pd.DataFrame(ret).dropna()
    mom = R["momentum"]
    mom_metrics = _metrics("momentum", mom)

    standalone = [_metrics(b, R[b]) for b in books]

    # pairwise (momentum-anchored + low_vol<->trend) + the 3-way equal blend
    combos: list[list[str]] = []
    for b in books:
        if b != "momentum":
            combos.append(["momentum", b])
    if "low_vol" in books and "trend" in books:
        combos.append(["low_vol", "trend"])
    non_mom = [b for b in books if b != "momentum"]
    combos.append(["momentum", *non_mom])  # momentum + all diversifiers, equal weight

    blends: list[BlendResult] = []
    for comp in combos:
        blend_ret = R[comp].mean(axis=1)  # equal-weight daily-return blend
        m = _metrics("+".join(comp), blend_ret)
        ci = paired_sharpe_diff_ci(blend_ret.tolist(), mom.tolist())
        dmdd_pp = (round((abs(mom_metrics.max_drawdown) - abs(m.max_drawdown)) * 100, 2)
                   if m.max_drawdown is not None and mom_metrics.max_drawdown is not None else None)
        improves = ci.excludes_zero_positive()
        blends.append(BlendResult(
            blend="+".join(comp), components=comp, metrics=asdict(m),
            delta_sharpe_vs_mom=ci.delta,
            ci_low=(None if ci.ci_low != ci.ci_low else ci.ci_low),
            ci_high=(None if ci.ci_high != ci.ci_high else ci.ci_high),
            improves_sharpe=improves, delta_maxdd_vs_mom_pp=dmdd_pp,
            verdict=_verdict(improves, dmdd_pp)))

    # ---- console ----
    def _row(m: Metrics) -> str:
        cg = f"{m.cagr*100:.1f}%" if m.cagr is not None else "n/a"
        dd = f"{m.max_drawdown*100:.1f}%" if m.max_drawdown is not None else "n/a"
        return f"{m.label:20}{cg:>9}{str(m.sharpe):>8}{dd:>9}{str(m.calmar):>8}"
    print(f"\n{'standalone':20}{'CAGR':>9}{'Sharpe':>8}{'MaxDD':>9}{'Calmar':>8}")
    for m in standalone:
        print(_row(m))
    print(f"\n{'blend (eqw)':20}{'CAGR':>9}{'Sharpe':>8}{'MaxDD':>9}{'Calmar':>8}"
          f"{'dSharpe vs mom [CI]':>26}{'dMaxDD pp':>11}  verdict")
    for b in blends:
        m = Metrics(**b.metrics)
        ci = f"{b.delta_sharpe_vs_mom} [{b.ci_low}, {b.ci_high}]"
        print(f"{_row(m)}{ci:>26}{str(b.delta_maxdd_vs_mom_pp):>11}  {b.verdict}")

    # ---- report ----
    if args.report_dir:
        import json
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "fi001_phase2_results.json").write_text(json.dumps({
            "window": {"start": str(start), "end": str(end), "n": args.n},
            "sector_coverage": sector_cov,
            "standalone": [asdict(m) for m in standalone],
            "blends": [asdict(b) for b in blends],
        }, indent=2, default=str), encoding="utf-8")
        lines = [
            "# FI-001 Phase 2 — Interaction (pairwise blends vs standalone)\n",
            f"Universe {args.n} - {start}..{end} - store {bounds[0]}..{bounds[1]}. Equal-weight "
            "return-level blends; H2 gate = paired Sharpe-diff bootstrap CI vs standalone momentum.\n",
            "## Standalone books",
            "| book | CAGR | Sharpe | MaxDD | Calmar |", "|---|---|---|---|---|"]
        for m in standalone:
            cg = f"{m.cagr*100:.1f}%" if m.cagr is not None else "n/a"
            dd = f"{m.max_drawdown*100:.1f}%" if m.max_drawdown is not None else "n/a"
            lines.append(f"| {m.label} | {cg} | {m.sharpe} | {dd} | {m.calmar} |")
        lines += ["\n## Blends vs standalone momentum\n",
                  "| blend (eqw) | CAGR | Sharpe | MaxDD | Calmar | dSharpe vs mom [95% CI] | dMaxDD (pp) | verdict |",
                  "|---|---|---|---|---|---|---|---|"]
        for b in blends:
            m = Metrics(**b.metrics)
            cg = f"{m.cagr*100:.1f}%" if m.cagr is not None else "n/a"
            dd = f"{m.max_drawdown*100:.1f}%" if m.max_drawdown is not None else "n/a"
            lines.append(f"| {b.blend} | {cg} | {m.sharpe} | {dd} | {m.calmar} "
                         f"| {b.delta_sharpe_vs_mom} [{b.ci_low}, {b.ci_high}] | {b.delta_maxdd_vs_mom_pp} | {b.verdict} |")
        lines += ["\n## Reading (H2)\n",
                  "- **IMPROVES** = the blend's Sharpe-diff CI vs standalone momentum excludes zero "
                  "(a real risk-adjusted uplift).",
                  "- **DIVERSIFIES (DD-only)** = Sharpe CI spans zero but the blend's max drawdown is "
                  ">=3pp shallower than momentum (the modal, pre-registered outcome).",
                  "- **NO HELP** = neither."]
        if sector_note:
            lines.append(f"\n> {sector_note}")
        (d / "fi001_phase2_report.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"\nWrote {d / 'fi001_phase2_report.md'} and fi001_phase2_results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
