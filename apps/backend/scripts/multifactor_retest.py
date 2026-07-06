"""P14 Factor Lab — the SF1 multi-factor re-test (ADR 0023).

The decisive follow-on to P12 §3 (which was EXPLORATORY/Inconclusive on thin FMP data). Re-runs the
question — does momentum + SF1 value + SF1 quality beat momentum-only out-of-sample? — on the
survivorship-free, point-in-time **SF1** store (2016+, ~thousands of names). Read-only research.

Three artifacts:
1. **Factor-correlation matrix** — momentum × SF1-value × SF1-quality × multifactor (avg cross-section):
   are value/quality genuine diversifiers of momentum on SF1 data?
2. **Full-window backtest + paired Sharpe-difference bootstrap** — momentum vs multifactor through the
   §1 harness; the DECISIVE statistic is whether the 95% CI of (multifactor - momentum) Sharpe
   excludes zero.
3. **Walk-forward sub-windows** — per-window ΔSharpe + the fraction the multifactor wins (consistency,
   not one lucky window).

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe apps/backend/scripts/multifactor_retest.py \
        --store apps/backend/data/factor_data_full.duckdb --start 2017-01-01 --end 2026-03-31 \
        --n 200 --windows 5 --report-dir docs/implementation/evidence/p14_s1_multifactor
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pandas as pd  # noqa: E402

from app.factor_data import evidence as ev  # noqa: E402
from app.factor_data.backtest import run_momentum_backtest  # noqa: E402
from app.factor_data.factors.composite import composite_scores, factor_zscores  # noqa: E402
from app.factor_data.factors.engine import FactorUnavailable  # noqa: E402
from app.factor_data.factors.sf1 import SF1_QUALITY_FACTORS, SF1_VALUE_FACTORS  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402

VALUE = list(SF1_VALUE_FACTORS)
QUALITY = list(SF1_QUALITY_FACTORS)
ALL = ["momentum", *VALUE, *QUALITY]


def _comp_score(n: int):
    def score(s: FactorDataStore, d: date) -> pd.DataFrame:
        return composite_scores(s, d, factors=ALL, n=n, missing="impute")
    return score


def _curve_stats(curve: list[tuple[date, float]]) -> dict[str, float]:
    r = ev.daily_returns(curve)
    c = ev.cagr(curve)
    dd = ev.max_drawdown(curve)
    return {"cagr": c, "sharpe": ev.sharpe(r), "max_drawdown": dd, "calmar": ev.calmar(c, dd)}


def _paired_sharpe_diff_ci(
    mom_r: list[float], mf_r: list[float], *, n_resamples: int, seed: int, block: int = 21
) -> dict[str, float]:
    """Circular-block paired bootstrap of (Sharpe(multifactor) - Sharpe(momentum)).

    Resamples the SAME block indices for both aligned daily-return series, so the pairing (and thus
    the common market move) is preserved. Returns the point estimate + 95% percentile CI; a CI that
    excludes 0 is the decisive 'the multifactor edge is real' signal."""
    n = min(len(mom_r), len(mf_r))
    point = ev.sharpe(mf_r[:n]) - ev.sharpe(mom_r[:n])
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
        m = [mom_r[i] for i in idx]
        f = [mf_r[i] for i in idx]
        diffs.append(ev.sharpe(f) - ev.sharpe(m))
    diffs.sort()
    lo = diffs[int(0.025 * n_resamples)]
    hi = diffs[min(int(0.975 * n_resamples), n_resamples - 1)]
    return {"delta": round(point, 3), "ci_low": round(lo, 3), "ci_high": round(hi, 3)}


def _window_bounds(start: date, end: date, k: int) -> list[tuple[date, date]]:
    """Split [start, end] into k contiguous equal sub-windows (walk-forward consistency check)."""
    days = (end - start).days
    step = days // k
    out = []
    for i in range(k):
        ws = start + pd.Timedelta(days=i * step)
        we = end if i == k - 1 else start + pd.Timedelta(days=(i + 1) * step)
        out.append((ws.date() if hasattr(ws, "date") else ws,
                    we.date() if hasattr(we, "date") else we))
    return out


def _backtest_pair(store: FactorDataStore, s: date, e: date, n: int) -> dict[str, Any]:
    mom = run_momentum_backtest(store, s, e, n=n)
    mf = run_momentum_backtest(store, s, e, n=n, score_fn=_comp_score(n))
    ms, fs = _curve_stats(mom.equity_curve), _curve_stats(mf.equity_curve)
    return {"momentum": ms, "multifactor": fs, "delta_sharpe": round(fs["sharpe"] - ms["sharpe"], 3),
            "_mom_r": ev.daily_returns(mom.equity_curve), "_mf_r": ev.daily_returns(mf.equity_curve)}


def main() -> int:
    ap = argparse.ArgumentParser(description="P14 SF1 multi-factor re-test")
    ap.add_argument("--store", default=None)
    ap.add_argument("--start", default="2017-01-01")
    ap.add_argument("--end", default="2026-03-31")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--windows", type=int, default=5)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    started = time.monotonic()
    exp_id = f"EXP-{datetime.now(UTC):%Y%m%d-%H%M%S}-sf1mf"

    store = FactorDataStore(db_path=args.store, read_only=True)
    try:
        health = ev.dataset_health(store, start, end)

        # 1) factor-correlation matrix (monthly cross-sections)
        corr_sum: pd.DataFrame | None = None
        n_corr = 0
        for d in (x.date() for x in pd.date_range(start, end, freq="MS")):
            try:
                z = factor_zscores(store, d, factors=ALL, n=args.n)
            except FactorUnavailable:
                continue
            g = pd.DataFrame({"momentum": z["momentum"], "value": z[VALUE].mean(axis=1),
                              "quality": z[QUALITY].mean(axis=1), "multifactor": z.mean(axis=1)})
            g = g.dropna(how="any")
            if len(g) < 20:
                continue
            corr_sum = g.corr() if corr_sum is None else corr_sum + g.corr()
            n_corr += 1
        corr = (corr_sum / n_corr) if corr_sum is not None else pd.DataFrame()
        mom_value = float(corr.at["momentum", "value"]) if n_corr else float("nan")
        mom_quality = float(corr.at["momentum", "quality"]) if n_corr else float("nan")

        # 2) full-window backtest + paired Sharpe-difference bootstrap (the decisive test)
        full = _backtest_pair(store, start, end, args.n)
        diff_ci = _paired_sharpe_diff_ci(full["_mom_r"], full["_mf_r"],
                                         n_resamples=args.bootstrap, seed=args.seed)

        # 3) walk-forward sub-windows (consistency)
        windows = []
        for ws, we in _window_bounds(start, end, args.windows):
            try:
                wp = _backtest_pair(store, ws, we, args.n)
                windows.append({"window": [str(ws), str(we)],
                                "momentum_sharpe": round(wp["momentum"]["sharpe"], 2),
                                "multifactor_sharpe": round(wp["multifactor"]["sharpe"], 2),
                                "delta_sharpe": wp["delta_sharpe"]})
            except Exception as exc:  # a thin window must not kill the sweep
                windows.append({"window": [str(ws), str(we)], "error": repr(exc)})
        wins = [w for w in windows if "delta_sharpe" in w]
        n_win_pos = sum(1 for w in wins if w["delta_sharpe"] > 0)

        # verdict: decisive only if the paired ΔSharpe CI excludes 0 AND most windows agree
        ci_excludes_zero = (diff_ci["ci_low"] == diff_ci["ci_low"]  # not NaN
                            and diff_ci["ci_low"] > 0)
        consistent = bool(wins) and n_win_pos >= (len(wins) + 1) // 2 + 1
        if ci_excludes_zero and consistent:
            state, action = "Validated", "multi-factor v2.0 candidate (SF1)"
        elif diff_ci["ci_high"] < 0:
            state, action = "Rejected", "momentum stands alone — keep v1.1"
        else:
            state, action = "Inconclusive", "keep v1.1; dSharpe CI spans 0"

        result: dict[str, Any] = {
            "experiment_id": exp_id, "git_sha": _git_sha(),
            "data": "SF1 survivorship-free PIT, 2016+ (ADR 0023)",
            "window": [str(start), str(end)], "n": args.n, "windows": args.windows,
            "dataset_health_ok": health["ok"],
            "factors": {"value": VALUE, "quality": QUALITY},
            "correlation_matrix": corr.round(3).to_dict() if n_corr else {},
            "n_correlation_samples": n_corr,
            "momentum_value_corr": round(mom_value, 3), "momentum_quality_corr": round(mom_quality, 3),
            "momentum_book": full["momentum"], "multifactor_book": full["multifactor"],
            "delta_sharpe": full["delta_sharpe"], "paired_delta_sharpe_ci": diff_ci,
            "walk_forward": wins, "n_windows_multifactor_wins": f"{n_win_pos}/{len(wins)}",
            "research_state": state, "action": action,
            "duration_s": round(time.monotonic() - started, 2),
        }
    finally:
        store.close()

    mom, mf = result["momentum_book"], result["multifactor_book"]
    print(f"[{exp_id}] SF1 multi-factor re-test  {start}..{end} n={args.n}")
    print(f"  corr(mom,value)={result['momentum_value_corr']} corr(mom,quality)="
          f"{result['momentum_quality_corr']} (n={n_corr})")
    print(f"  momentum   : CAGR {mom['cagr']:+.2%} Sharpe {mom['sharpe']:.2f} maxDD {mom['max_drawdown']:.1%}")
    print(f"  multifactor: CAGR {mf['cagr']:+.2%} Sharpe {mf['sharpe']:.2f} maxDD {mf['max_drawdown']:.1%}")
    print(f"  dSharpe {result['delta_sharpe']:+.2f}  paired 95% CI "
          f"[{diff_ci['ci_low']}, {diff_ci['ci_high']}]  windows won {result['n_windows_multifactor_wins']}")
    print(f"  -> {state}: {action}  ({result['duration_s']}s)")

    if args.report_dir:
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "multifactor_retest.json").write_text(json.dumps(result, indent=2, default=str),
                                                   encoding="utf-8")
        (d / "multifactor_retest.md").write_text(_render(result), encoding="utf-8")
        print(f"  wrote {d / 'multifactor_retest.json'} + .md")
    return 0


def _git_sha() -> str:
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def _render(r: dict[str, Any]) -> str:
    mom, mf, ci = r["momentum_book"], r["multifactor_book"], r["paired_delta_sharpe_ci"]
    lines = [
        f"# P14 Factor Lab — SF1 multi-factor re-test ({r['experiment_id']})",
        "",
        f"_git {r['git_sha']} · {r['data']} · window {r['window'][0]}..{r['window'][1]} · n={r['n']} · "
        f"{r['duration_s']}s_",
        "",
        "> The decisive re-run of the P12 §3 question on survivorship-free point-in-time SF1 "
        "fundamentals (2016+), which the thin FMP data could not settle.",
        "",
        "## 1. Factor-correlation matrix (avg cross-section)",
        "",
        f"- corr(momentum, SF1-value) = **{r['momentum_value_corr']}**",
        f"- corr(momentum, SF1-quality) = **{r['momentum_quality_corr']}**",
        f"- (averaged over {r['n_correlation_samples']} monthly cross-sections)",
        "",
        "_Near-zero/low correlation = genuine diversifier; strongly negative = momentum's opposite._",
        "",
        "## 2. Full-window backtest + paired Sharpe-difference bootstrap (decisive)",
        "",
        "| Book | CAGR | Sharpe | maxDD | Calmar |",
        "|---|---|---|---|---|",
        f"| Momentum (v1.1 base) | {mom['cagr']:+.2%} | {mom['sharpe']:.2f} | {mom['max_drawdown']:.1%} | {mom['calmar']:.2f} |",
        f"| Multi-factor (mom+SF1 value+quality) | {mf['cagr']:+.2%} | {mf['sharpe']:.2f} | {mf['max_drawdown']:.1%} | {mf['calmar']:.2f} |",
        "",
        f"**ΔSharpe = {r['delta_sharpe']:+.2f}; paired 95% CI [{ci['ci_low']}, {ci['ci_high']}].** "
        "A CI excluding 0 is the real-edge signal.",
        "",
        "## 3. Walk-forward consistency",
        "",
        f"Multi-factor beat momentum in **{r['n_windows_multifactor_wins']}** sub-windows.",
        "",
        "| Window | Momentum Sharpe | Multi-factor Sharpe | ΔSharpe |",
        "|---|---|---|---|",
        *[f"| {w['window'][0]}..{w['window'][1]} | {w['momentum_sharpe']} | "
          f"{w['multifactor_sharpe']} | {w['delta_sharpe']:+.2f} |" for w in r["walk_forward"]],
        "",
        f"## Verdict: **{r['research_state']}** → {r['action']}",
        "",
        "_Per ADR 0014/0023, either outcome is a win: a real edge → a v2.0 multi-factor candidate; "
        "momentum stands → keep v1.1, the SF1 spend bought an honest answer. ~10-year SF1 depth "
        "(2016+) is the standing caveat (ADR 0023)._",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
