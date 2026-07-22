"""momentum-daily — WEIGHTING-DEFECT IMPACT STUDY (PREREG v1.1, RATIFIED 2026-07-22).

Quantifies the historical effect of replacing the Stage-3 harness's DEFECTIVE truncated-clamp
weights with the cap-feasible equal weights that production implements.

THE DEFECT. `backtest_momentum_stage3.py::weigh` bounds n=5 weights by (lo=0.0, hi=0.20) using an
iterative clamp-and-renormalize capped at 8 iterations. At n=5, hi == 1/n, so
    Sum(w) = 1  and  w_i <= 0.20 over 5 names   =>   w_i = 0.20 for all i
i.e. the feasible capped simplex contains ONLY the uniform portfolio. The loop is a fixed-point
iteration whose sole fixed point is uniform; it therefore exits on the iteration counter, never on
the convergence break, and returns a vector that violates its own cap (>=1 name above 0.20 on
5,393/5,393 five-name sessions; max 20.594%). Any non-uniform output is INFEASIBLE.

WHAT THIS IS NOT: strategy discovery, retuning, re-selection among Stage-3 arms, or a re-run of the
Section 8 census. It is a correction-impact analysis for a defective sizing implementation.

Arms (all N=5, no sector cap, graduated regime = variant C unless --variant says otherwise):
    A        sizing=hybrid_50_50   the defective reference; must reproduce the committed artifact
    B-pinned sizing=equal_weight   PRIMARY  - trade-date schedule pinned to A's
    B-free   sizing=equal_weight   DIAGNOSTIC - rebalance gate free-running

`select_n`, `weigh`, `compute_day`, `build_market_proxy`, `gross_series`, `_CachedPriceStore` and
`_summary` are IMPORTED from the validated harness. `simulate_arm` below is a disclosed
transcription of `backtest_momentum_stage4.py::simulate` (lines 168-258) with the sizing call
parameterized, an optional pinned trade-date schedule, and per-rebalance instrumentation added.
The mark-to-market, trade gate, turnover cost and same-day-close rebalance are unchanged.

    WORKBENCH_FACTOR_DATA_DB_PATH=/path/to/factor_data_full.duckdb \\
        python scripts/weighting_defect_impact_study.py --report-dir <dir> [--with-control]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time as _time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (str(BACKEND_ROOT), str(SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backtest_momentum_stage2 import (  # noqa: E402
    BACKSTOP_DAYS,
    CRASH_WINDOWS,
    INITIAL_EQUITY,
    TURNOVER_COST_BPS,
    WEIGHT_DRIFT_PCT,
    DayScores,
    compute_day,
)
from backtest_momentum_stage3 import select_n, weigh  # noqa: E402
from backtest_momentum_stage4 import (  # noqa: E402
    CAP_ON,
    N,
    build_market_proxy,
    gross_series,
)

from app.factor_data.backtest import _CachedPriceStore, _summary  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402

MAX_POSITION_PCT = 0.20      # the registered production per-name cap (unchanged, adjudication 2026-07-22)
PRODUCTION_SIZING = "production_capped_equal"
FEASIBILITY_EPS = 1e-9
ROLL_WINDOWS = {"1m": 21, "3m": 63, "12m": 252}   # trading days

# Reproduction-gate reference (PREREG v1.1 §2), READ FROM the committed artifact — never
# hand-transcribed. An earlier revision hardcoded these constants; four of the five variant-C
# values were typed from a 6-decimal console echo with the trailing digits invented, and the
# variant-D values were lifted from the Stage-3 artifact instead of the Stage-4 one. The gate
# then failed a run that had in fact reproduced exactly. Reference values are evidence: they get
# loaded from the evidence file, so a transcription error is not expressible.
STAGE4_REFERENCE_ARTIFACT = (
    BACKEND_ROOT.parent.parent
    / "docs/implementation/evidence/momentum_daily_stage2_4/MR_MomentumDaily_Stage4_full.json"
)
REPRO_METRICS = ("cagr", "sharpe", "calmar", "max_drawdown")


def production_weights(target: list[str]) -> dict[str, float]:
    """Pre-gross per-name weights from the EXACT production sizing seam (POST-HOC
    PRODUCTION-FAITHFUL CORRECTION, owner ruling 2026-07-22 §5.2).

    Calls ``MomentumDaily._per_name_notional`` itself rather than restating its rule, so this
    arm cannot drift from what the order path sizes. Evaluated at unit equity, so the result is
    a fraction of gross-scaled investable equity; the caller multiplies by gross exactly as
    ``_apply_targets`` applies it via ``_investable_equity``.

    At k=5 this equals 0.20/name (fully invested). At k<5 the cap binds: 4 names size 0.20 each
    and the remaining 0.20 of gross STAYS IN CASH — production never concentrates past the cap.

    NOTE on the ruling's shorthand: it wrote ``min(gross/k, 0.20)``, which caps the total-equity
    weight at a flat 20%. The production seam is ``min(1/k, 0.20) x gross`` — the cap scales with
    gross. Identical at k=5; they differ only on underfilled sessions (k=4, gross 0.98: 0.200 vs
    0.196). The ruling directed use of "the exact production _per_name_notional() seam", so the
    seam governs and the shorthand is treated as descriptive.
    """
    from types import SimpleNamespace

    from strategies_user.templates.momentum_daily import MomentumDaily

    shim = SimpleNamespace(params={"max_position_pct": MAX_POSITION_PCT})
    unit = float(MomentumDaily._per_name_notional(shim, Decimal(1), len(target)))
    return {t: unit for t in target}


def load_stage4_reference(variant: str, path: Path | None = None) -> dict:
    """Load the committed Stage-4 endpoints for ``variant``. Fail-closed: a missing file or
    absent variant raises rather than silently degrading the reproduction gate."""
    p = path or STAGE4_REFERENCE_ARTIFACT
    if not p.exists():
        raise FileNotFoundError(f"Stage-4 reference artifact not found: {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))
    for v in payload["variants"]:
        if v["variant"] == variant:
            return {k: v[k] for k in (*REPRO_METRICS, "trades")}
    raise KeyError(f"variant {variant!r} absent from {p}")


# ---- arm simulation -------------------------------------------------------------

def simulate_arm(store, trading_days: list[date], day_scores: dict[date, DayScores],
                 sectors: dict[str, str | None], gross: dict[date, float], *,
                 sizing: str, pinned_dates: set[date] | None = None) -> dict:
    """Transcription of stage4 `simulate` with parameterized sizing + optional pinned schedule.

    ``pinned_dates`` replaces the rebalance gate outright: the arm trades on exactly those
    sessions. Selection is sizing-independent, so a pinned arm reproduces the reference arm's
    target-name sequence and holdings path exactly, isolating the weight vector as the only
    difference (asserted downstream, not assumed).
    """
    ws, we = trading_days[0], trading_days[-1]
    pxcache: dict[str, dict[date, float]] = {}

    def pxmap(t: str) -> dict[date, float]:
        if t not in pxcache:
            df = store.get_prices(t, ws, we, adjusted=True)
            pxcache[t] = {dt.date(): float(c) for dt, c in zip(df["date"], df["close"], strict=False)
                          if c is not None and float(c) > 0}
        return pxcache[t]

    equity = INITIAL_EQUITY
    sleeves: dict[str, float] = {}
    cash = 0.0
    target_w: dict[str, float] = {}
    last_px: dict[str, float] = {}
    held: set[str] = set()
    entry_date: dict[str, date] = {}
    curve: list[tuple[date, float]] = []
    holding_periods: list[int] = []
    total_turnover = 0.0
    worst_gap = 0.0
    trades = 0
    since = 0
    risk_off_days = 0
    prev_rank: dict[str, int] | None = None
    applied_gross = 1.0

    trade_dates: list[date] = []
    rebalance_cost_bps: dict[date, float] = {}       # per-rebalance cost, bps of NAV
    target_seq: list[tuple[date, tuple[str, ...]]] = []
    cap_violations: list[dict] = []
    total_cost_frac = 0.0

    for d in trading_days:
        if held:
            for tk in held:
                p = pxmap(tk).get(d)
                if p is not None:
                    lp = last_px.get(tk, 0.0)
                    if lp > 0:
                        r = p / lp - 1.0
                        sleeves[tk] *= 1.0 + r
                        if r < worst_gap:
                            worst_gap = r
                    last_px[tk] = p
            equity = sum(sleeves.values()) + cash
        curve.append((d, equity))
        g = gross.get(d, 1.0)
        if g < 1.0:
            risk_off_days += 1

        ds = day_scores.get(d)
        if ds is None:
            since += 1
            continue

        target = select_n(ds, held, prev_rank, N, sectors, CAP_ON)
        prev_rank = ds.rank
        target_seq.append((d, tuple(target)))
        changed = set(target) != held
        regime_flip = abs(g - applied_gross) > 1e-9
        drift = False
        if held and equity > 0 and target_w:
            drift = max(abs(sleeves.get(tk, 0.0) / equity - target_w.get(tk, 0.0))
                        for tk in held) > WEIGHT_DRIFT_PCT
        if pinned_dates is None:
            do_trade = bool(changed or regime_flip or drift or since >= BACKSTOP_DAYS)
        else:
            do_trade = d in pinned_dates
        if not do_trade:
            since += 1
            continue

        if g <= 0.0 or not target:
            neww = {}
        else:
            base = (production_weights(target) if sizing == PRODUCTION_SIZING
                    else weigh(store, target, d, sizing=sizing, n=N, cap_on=CAP_ON,
                               sectors=sectors))
            over = {t: w for t, w in base.items() if w > MAX_POSITION_PCT + FEASIBILITY_EPS}
            if over:
                cap_violations.append({"date": d.isoformat(), "max_weight": max(over.values()),
                                       "n_over": len(over)})
            neww = {tk: w * g for tk, w in base.items()}
        cash_w = 1.0 - sum(neww.values())

        curw = {tk: (sleeves.get(tk, 0.0) / equity if equity > 0 else 0.0)
                for tk in set(sleeves) | set(neww)}
        cur_cash_w = cash / equity if equity > 0 else 0.0
        turnover = 0.5 * (sum(abs(neww.get(k, 0.0) - curw.get(k, 0.0))
                              for k in set(neww) | set(curw)) + abs(cash_w - cur_cash_w))
        total_turnover += turnover
        cost_frac = (TURNOVER_COST_BPS / 1e4) * turnover
        total_cost_frac += cost_frac
        rebalance_cost_bps[d] = cost_frac * 1e4
        equity *= 1.0 - cost_frac

        for tk in held - set(neww):
            if tk in entry_date:
                holding_periods.append((d - entry_date[tk]).days)
        for tk in set(neww) - held:
            entry_date[tk] = d

        sleeves = {tk: w * equity for tk, w in neww.items()}
        cash = cash_w * equity
        last_px = {tk: (pxmap(tk).get(d) or 0.0) for tk in neww}
        target_w = dict(neww)
        held = set(neww)
        applied_gross = g
        trades += 1
        trade_dates.append(d)
        since = 0

    summ = _summary(curve, INITIAL_EQUITY)
    years = (curve[-1][0] - curve[0][0]).days / 365.25 if len(curve) > 1 else 0.0
    for tk in held:
        if tk in entry_date:
            holding_periods.append((curve[-1][0] - entry_date[tk]).days)
    ann_turnover = (total_turnover / years if years > 0 else 0.0)
    crash = {}
    for name, (cs, ce) in CRASH_WINDOWS.items():
        seg = [(dd, e) for dd, e in curve if cs <= dd <= ce]
        crash[name] = (seg[-1][1] / seg[0][1] - 1.0) if len(seg) >= 2 else 0.0

    return {
        "sizing": sizing, "pinned": pinned_dates is not None,
        "cagr": summ.cagr, "total_return": summ.total_return, "sharpe": summ.sharpe,
        "max_drawdown": summ.max_drawdown,
        "calmar": (summ.cagr / abs(summ.max_drawdown)) if summ.max_drawdown else 0.0,
        "annualized_volatility": _ann_vol(curve),
        "annualized_turnover": ann_turnover,
        "annualized_cost_bps": TURNOVER_COST_BPS * ann_turnover,
        "total_cost_frac": total_cost_frac,
        "avg_holding_days": (statistics.mean(holding_periods) if holding_periods else 0.0),
        "worst_single_name_gap": worst_gap, "trades": trades,
        "pct_days_risk_off": risk_off_days / max(len(trading_days), 1),
        "final_equity": curve[-1][1] if curve else INITIAL_EQUITY,
        "crash_windows": crash,
        "cap_violation_rebalances": len(cap_violations),
        "cap_violation_max_weight": (max(v["max_weight"] for v in cap_violations)
                                     if cap_violations else 0.0),
        "_curve": curve, "_trade_dates": trade_dates,
        "_rebalance_cost_bps": rebalance_cost_bps, "_target_seq": target_seq,
    }


def _ann_vol(curve: list[tuple[date, float]]) -> float:
    """Annualized volatility of daily LOG returns at sqrt(252) (PREREG v1.1 §4)."""
    rets = [math.log(curve[i][1] / curve[i - 1][1])
            for i in range(1, len(curve)) if curve[i - 1][1] > 0 and curve[i][1] > 0]
    return statistics.stdev(rets) * math.sqrt(252) if len(rets) > 1 else 0.0


# ---- comparison -----------------------------------------------------------------

def _rolling(curve: list[tuple[date, float]], w: int) -> dict[date, float]:
    return {curve[i][0]: curve[i][1] / curve[i - w][1] - 1.0
            for i in range(w, len(curve)) if curve[i - w][1] > 0}


def _pctile(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    return s[min(len(s) - 1, int(q * len(s)))]


def compare(a: dict, b: dict) -> dict:
    """Tier-2 quantities for the pinned comparison B - A, plus per-segment diagnostics."""
    out: dict = {"delta_annualized_volatility_bps": (b["annualized_volatility"]
                                                     - a["annualized_volatility"]) * 1e4,
                 "delta_annualized_cost_bps": b["annualized_cost_bps"] - a["annualized_cost_bps"]}

    for label, w in ROLL_WINDOWS.items():
        ra, rb = _rolling(a["_curve"], w), _rolling(b["_curve"], w)
        common = sorted(set(ra) & set(rb))
        diffs = [abs(rb[d] - ra[d]) * 1e4 for d in common]          # bps
        signed = [(rb[d] - ra[d]) * 1e4 for d in common]
        out[f"rolling_{label}"] = {
            "n": len(common),
            "median_abs_bps": statistics.median(diffs) if diffs else 0.0,
            "p95_abs_bps": _pctile(diffs, 0.95),
            "max_abs_bps": max(diffs) if diffs else 0.0,
            "median_signed_bps": statistics.median(signed) if signed else 0.0,
            "pct_positive": (sum(1 for x in signed if x > 0) / len(signed)) if signed else 0.0,
        }

    da, db = a["_rebalance_cost_bps"], b["_rebalance_cost_bps"]
    common_d = sorted(set(da) & set(db))
    per_reb = [abs(db[d] - da[d]) for d in common_d]
    out["max_single_rebalance_cost_diff_bps"] = max(per_reb) if per_reb else 0.0
    out["median_single_rebalance_cost_diff_bps"] = statistics.median(per_reb) if per_reb else 0.0

    out["trade_dates_identical"] = a["_trade_dates"] == b["_trade_dates"]
    out["trade_date_overlap"] = (len(set(a["_trade_dates"]) & set(b["_trade_dates"]))
                                 / max(len(set(a["_trade_dates"]) | set(b["_trade_dates"])), 1))
    out["target_sequence_identical"] = a["_target_seq"] == b["_target_seq"]

    # T12 — persistence by calendar year (signed annual return difference, bps)
    ca = {d: e for d, e in a["_curve"]}
    cb = {d: e for d, e in b["_curve"]}
    years = sorted({d.year for d in ca})
    per_year = {}
    for y in years:
        ds = [d for d in sorted(ca) if d.year == y]
        if len(ds) < 2:
            continue
        ra = ca[ds[-1]] / ca[ds[0]] - 1.0
        rb = cb[ds[-1]] / cb[ds[0]] - 1.0
        per_year[str(y)] = (rb - ra) * 1e4
    out["per_year_return_diff_bps"] = per_year
    signs = [v for v in per_year.values() if abs(v) > 1e-9]
    out["per_year_same_sign_share"] = (max(sum(1 for v in signs if v > 0),
                                           sum(1 for v in signs if v < 0)) / len(signs)
                                       if signs else 0.0)
    out["per_year_max_abs_bps"] = max((abs(v) for v in per_year.values()), default=0.0)
    return out


def evaluate_gates(cmp_: dict, b: dict) -> dict:
    """PREREG v1.1 §4. Every gate reported individually; no composite, no averaging."""
    g = [
        ("T1  annualized volatility |d|", abs(cmp_["delta_annualized_volatility_bps"]), 25.0, "bps"),
        ("T2  rolling 1m median |d|", cmp_["rolling_1m"]["median_abs_bps"], 10.0, "bps"),
        ("T3  rolling 1m p95 |d|", cmp_["rolling_1m"]["p95_abs_bps"], 50.0, "bps"),
        ("T4  rolling 3m median |d|", cmp_["rolling_3m"]["median_abs_bps"], 20.0, "bps"),
        ("T5  rolling 3m p95 |d|", cmp_["rolling_3m"]["p95_abs_bps"], 75.0, "bps"),
        ("T6  rolling 12m median |d|", cmp_["rolling_12m"]["median_abs_bps"], 35.0, "bps"),
        ("T7  rolling 12m p95 |d|", cmp_["rolling_12m"]["p95_abs_bps"], 125.0, "bps"),
        ("T8  annualized cost |d|", abs(cmp_["delta_annualized_cost_bps"]), 10.0, "bps"),
        ("T9  max single-rebalance cost |d|", cmp_["max_single_rebalance_cost_diff_bps"], 2.0, "bps"),
    ]
    results = [{"gate": name, "value": val, "threshold": thr, "unit": unit,
                "pass": val <= thr, "ratio": (val / thr if thr else 0.0)} for name, val, thr, unit in g]
    results.append({"gate": "T10 trade-date alignment", "value": float(cmp_["trade_dates_identical"]),
                    "threshold": 1.0, "unit": "identical", "pass": bool(cmp_["trade_dates_identical"]),
                    "ratio": 0.0 if cmp_["trade_dates_identical"] else 99.0})
    results.append({"gate": "T11 cap violations (equal arm)", "value": float(b["cap_violation_rebalances"]),
                    "threshold": 0.0, "unit": "rebalances", "pass": b["cap_violation_rebalances"] == 0,
                    "ratio": 0.0 if b["cap_violation_rebalances"] == 0 else 99.0})
    results.append({"gate": "T13 target/holdings path identical",
                    "value": float(cmp_["target_sequence_identical"]), "threshold": 1.0,
                    "unit": "identical", "pass": bool(cmp_["target_sequence_identical"]),
                    "ratio": 0.0 if cmp_["target_sequence_identical"] else 99.0})

    failures = [r for r in results if not r["pass"]]
    if not failures:
        verdict = "PRACTICALLY_EQUIVALENT"
    elif all(r["ratio"] <= 2.0 for r in failures):
        verdict = "MINOR_BUT_MEASURABLE"
    else:
        verdict = "MATERIALLY_DIFFERENT"
    return {"gates": results, "failures": [r["gate"] for r in failures], "verdict": verdict}


def _adjudicate_production(cmp_: dict, b: dict) -> dict:
    """Owner-specified bands for the production-faithful arm (2026-07-22). Thresholds unchanged;
    only the CLASSIFICATION of a T7 failure is banded.

      T7 > 250 bps                -> MATERIALLY_DIFFERENT
      125 < T7 <= 250 bps         -> MINOR_BUT_MEASURABLE
      T7 <= 125 bps + others pass -> the registered mechanical rule
      T11 != 0                    -> STOP, implementation defect (must be zero BY CONSTRUCTION)
    """
    t7 = cmp_["rolling_12m"]["p95_abs_bps"]
    if b["cap_violation_rebalances"] != 0:
        return {"t7_p95_bps": t7, "cap_violations": b["cap_violation_rebalances"],
                "classification": "STOP_IMPLEMENTATION_DEFECT",
                "note": ("T11 must be zero BY CONSTRUCTION for the production arm — the seam caps "
                         "at max_position_pct. A non-zero count means the arm is not calling the "
                         "production seam.")}
    if t7 > 250.0:
        cls = "MATERIALLY_DIFFERENT"
    elif t7 > 125.0:
        cls = "MINOR_BUT_MEASURABLE"
    else:
        cls = "PER_REGISTERED_MECHANICAL_RULE"
    return {"t7_p95_bps": t7, "cap_violations": 0, "classification": cls}


def check_reproduction(a: dict, variant: str, ref: dict | None = None) -> dict:
    ref = ref if ref is not None else load_stage4_reference(variant)
    checks = {}
    for k in REPRO_METRICS:
        rel = abs(a[k] - ref[k]) / max(abs(ref[k]), 1e-12)
        checks[k] = {"observed": a[k], "reference": ref[k], "rel_diff": rel, "pass": rel <= 1e-9}
    checks["trades"] = {"observed": a["trades"], "reference": ref["trades"],
                        "rel_diff": 0.0, "pass": a["trades"] == ref["trades"]}
    return {"checks": checks, "pass": all(c["pass"] for c in checks.values())}


def _strip(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2005-01-01")
    ap.add_argument("--end", default="2026-06-13")
    ap.add_argument("--report-dir", required=True)
    ap.add_argument("--with-control", action="store_true",
                    help="also run variant D (NON-GOVERNING regime-free reproduction control)")
    args = ap.parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    db_path = os.environ["WORKBENCH_FACTOR_DATA_DB_PATH"]

    store = FactorDataStore(read_only=True)
    trading_days = store.trading_days(start, end)
    cached = _CachedPriceStore(store)
    t0 = _time.perf_counter()
    print(f"[impact] window {trading_days[0]}..{trading_days[-1]} {len(trading_days)} days", flush=True)

    proxy = build_market_proxy(store, trading_days, db_path)
    print(f"[impact] proxy built ({(_time.perf_counter()-t0)/60:.1f}m)", flush=True)

    day_scores: dict[date, DayScores] = {}
    for i, d in enumerate(trading_days):
        ds = compute_day(cached, d)
        if ds is not None:
            day_scores[d] = ds
        if (i + 1) % 1000 == 0:
            print(f"[impact] scored {i+1}/{len(trading_days)} ({(_time.perf_counter()-t0)/60:.1f}m)",
                  flush=True)
    all_tk = sorted({t for ds in day_scores.values() for t in ds.ranked})
    sectors = store.get_sectors(all_tk)
    print(f"[impact] scores done: {len(day_scores)} usable ({(_time.perf_counter()-t0)/60:.1f}m)",
          flush=True)

    payload: dict = {
        "schema": "mr_momentum_daily.weighting_defect_impact.v1",
        "prereg": "PREREG_weighting_defect_impact_study_v1.1.md",
        "window": {"start": str(trading_days[0]), "end": str(trading_days[-1]),
                   "trading_days": len(trading_days)},
        "constants": {"N": N, "cap_on": CAP_ON, "max_position_pct": MAX_POSITION_PCT,
                      "initial_equity": INITIAL_EQUITY, "turnover_cost_bps": TURNOVER_COST_BPS,
                      "weight_drift_pct": WEIGHT_DRIFT_PCT, "backstop_days": BACKSTOP_DAYS},
        "arms": {},
    }

    variants = [("C", "GOVERNING")] + ([("D", "NON-GOVERNING REGIME-FREE REPRODUCTION CONTROL")]
                                       if args.with_control else [])
    for variant, role in variants:
        g = gross_series(proxy, variant)
        print(f"[impact] --- variant {variant} ({role}) ---", flush=True)
        a = simulate_arm(cached, trading_days, day_scores, sectors, g, sizing="hybrid_50_50")
        repro = check_reproduction(a, variant)
        print(f"[impact] A defective: CAGR {a['cagr']:.4%} Sharpe {a['sharpe']:.4f} "
              f"trades {a['trades']} | reproduction {'PASS' if repro['pass'] else 'FAIL'}", flush=True)
        if not repro["pass"] and variant == "C":
            payload["arms"][variant] = {"role": role, "reproduction": repro,
                                        "STOPPED": "Arm A failed the reproduction gate (PREREG v1.1 §2)"}
            print("[impact] STOP — reproduction gate failed on the governing variant", flush=True)
            break

        pinned = set(a["_trade_dates"])
        b_pin = simulate_arm(cached, trading_days, day_scores, sectors, g,
                             sizing="equal_weight", pinned_dates=pinned)
        b_free = simulate_arm(cached, trading_days, day_scores, sectors, g, sizing="equal_weight")
        cmp_pin = compare(a, b_pin)
        gates = evaluate_gates(cmp_pin, b_pin)
        cmp_free = compare(a, b_free)

        # POST-HOC PRODUCTION-FAITHFUL CORRECTION (owner ruling 2026-07-22 §5.2): the
        # preregistered arm allocated 25%/name on two underfilled (4-name) rebalances because the
        # harness equal_weight applies no cap; production caps at 20% and holds the rest in cash.
        # Same regime path, same pinned trade dates, same Tier-2 maths, unchanged thresholds.
        b_prod = simulate_arm(cached, trading_days, day_scores, sectors, g,
                              sizing=PRODUCTION_SIZING, pinned_dates=pinned)
        cmp_prod = compare(a, b_prod)
        gates_prod = evaluate_gates(cmp_prod, b_prod)
        gates_prod["adjudication_bands"] = _adjudicate_production(cmp_prod, b_prod)
        print(f"[impact] B-pinned: CAGR {b_pin['cagr']:.4%} Sharpe {b_pin['sharpe']:.4f} "
              f"trades {b_pin['trades']} | VERDICT {gates['verdict']}", flush=True)
        for r in gates["gates"]:
            print(f"[impact]   {'PASS' if r['pass'] else 'FAIL'} {r['gate']:38} "
                  f"{r['value']:.4f} / {r['threshold']:.2f} {r['unit']}", flush=True)

        print(f"[impact] B-prod (production-faithful): CAGR {b_prod['cagr']:.4%} "
              f"Sharpe {b_prod['sharpe']:.4f} trades {b_prod['trades']} | "
              f"T7 {cmp_prod['rolling_12m']['p95_abs_bps']:.2f}bps "
              f"capviol {b_prod['cap_violation_rebalances']} | "
              f"CLASS {gates_prod['adjudication_bands']['classification']}", flush=True)
        for r in gates_prod["gates"]:
            print(f"[impact]   {'PASS' if r['pass'] else 'FAIL'} prod {r['gate']:38} "
                  f"{r['value']:.4f} / {r['threshold']:.2f} {r['unit']}", flush=True)

        payload["arms"][variant] = {
            "role": role, "reproduction": repro,
            "A_defective_hybrid": _strip(a), "B_pinned_equal": _strip(b_pin),
            "B_free_equal": _strip(b_free),
            "B_pinned_production": _strip(b_prod),
            "primary_comparison_pinned": cmp_pin,
            "diagnostic_comparison_free": cmp_free,
            "production_faithful_comparison_pinned": cmp_prod,
            "gate_evaluation": gates,
            "gate_evaluation_production": gates_prod,
            "arm_labels": {
                "B_pinned_equal": "PREREGISTERED ARM — harness equal_weight, uncapped",
                "B_pinned_production": ("POST-HOC PRODUCTION-FAITHFUL CORRECTION — required "
                                        "because the preregistered arm did not reproduce "
                                        "production on two underfilled rebalances"),
            },
        }

    rd = Path(args.report_dir)
    rd.mkdir(parents=True, exist_ok=True)
    out = rd / "weighting_defect_impact_v1.0.json"
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"[impact] wrote {out} ({(_time.perf_counter()-t0)/60:.1f}m)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
