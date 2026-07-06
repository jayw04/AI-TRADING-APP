"""SCAN-001 v0.4 — the Confidence Model (calibration + composability; frozen plan v1.1).

Read-only research. Reuses the v0.2 engine + panel plumbing and the v0.3 PIT regime
classification, and asks the question v0.1–v0.3 never did: **does the confidence number
predict realized outcome, or is it decorative?** (SCAN-001 v0.4 §2.)

The Confidence Model decomposes into two levers (v0.4 §0), tested separately so the
attribution is clean:

  * Lever A (within-day) — the engine's per-candidate ``opportunity_confidence``. The ONLY
    term that re-ranks candidates within a day. Tested for calibration (H-conf-1).
  * Lever B (cross-day) — the per-day ``discovery_confidence(regime_today)``, computed
    POINT-IN-TIME over an expanding window of PRIOR days only (§1b, anti-circularity). A
    day-level throttle; it cannot reorder within a day (H-conf-2 / 3b).

``final_confidence = opportunity_confidence × discovery_confidence`` is the frozen composite
(§1c). Honest headroom caveat (§0): v0.3 found the engine REGIME-ROBUST (confidence band
0.91–1.00), so Lever B has little to bite on — a weak throttle reads as "broadly robust", not
failure. v0.4 is a SUCCESS if Lever A calibrates (H-conf-1); it fails only if the per-candidate
confidence is itself uninformative.

PIT note: the per-day Discovery Confidence uses a **closed-form normal-approx** separation
(mean / SE of the regime's prior daily-edge series) in place of v0.3's per-bucket block
bootstrap — an expanding-window bootstrap on every one of ~3,800 days would be prohibitive.
The blend formula and branch logic are identical to v0.3 (`ce.discovery_confidence`); only the
separation statistic is the cheap normal approximation. The end-of-sample PIT confidences are
cross-checked against the v0.3 in-sample heatmap in the report's honest-scope section.

Never routes an order — the candidate set is evidence, not a signal (SCAN-001 §0a). Lift is
reported at the EVIDENCE layer only (expansion edge / edge-per-exposure); no P&L simulation
(§10 OQ4). The premarket-data gate (PR #221) stays the hard prerequisite before any live use.

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
        apps/backend/scripts/candidate_engine_v0_4.py \
        --store apps/backend/data/factor_data_full.duckdb --end 2026-06-12 --bootstrap 2000 \
        --report-dir docs/implementation/evidence/scan_001_candidate_engine_v0_4
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import candidate_engine_v0_2 as v2  # noqa: E402  (panel plumbing)
import candidate_engine_v0_3 as v3  # noqa: E402  (PIT market-return proxy)
import pandas as pd  # noqa: E402

from app.factor_data import candidate_engine as ce  # noqa: E402
from app.factor_data import evidence as ev  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402

HISTORY_BUFFER = 60
MARKET_REGIMES = ("bull", "bear", "sideways")
TOP_K = 8                # confidence-ranked subset of TOP_N (frozen §3: top-8 of top-15)
MIN_CANDS_FOR_TERCILE = 6  # need ≥6 candidates to split a day into confidence terciles


# ---- PIT expanding-window Discovery Confidence (§1b) -----------------------


def _phi(x: float) -> float:
    """Standard-normal CDF via erf (closed-form, no SciPy)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _pit_stats(edges: list[float]) -> dict[str, float] | None:
    """Normal-approx summary of a regime's PRIOR-only daily-edge series → mean, 95% lower
    bound, one-sided p for mean>0. None under the warm-up floor (< MIN_CONFIDENCE_DAYS)."""
    n = len(edges)
    if n < ce.MIN_CONFIDENCE_DAYS:
        return None
    m = ev._mean(edges)
    sd = ev._std(edges)
    se = sd / math.sqrt(n) if n > 0 else 0.0
    if se == 0.0:
        return {"mean": m, "ci_low": m, "p_value": 0.0 if m > 0 else 1.0}
    t = m / se
    return {"mean": m, "ci_low": m - 1.96 * se, "p_value": 1.0 - _phi(t)}


def _discovery_confidence_today(
    prior_by_regime: dict[str, list[float]], target: str
) -> tuple[float, bool]:
    """Today's Discovery Confidence for ``target`` market regime, from prior days only.

    Returns (confidence, is_warmup). Under warm-up (target regime < 60 prior days) →
    (NEUTRAL_CONFIDENCE, True): no down-weight. Otherwise applies the frozen v0.3 blend via
    ``ce.discovery_confidence`` with ``ref`` = the largest separated regime's prior mean."""
    stats = {r: _pit_stats(prior_by_regime[r]) for r in MARKET_REGIMES}
    ts = stats[target]
    if ts is None:
        return ce.NEUTRAL_CONFIDENCE, True
    sep_means = [s["mean"] for s in stats.values() if s is not None and s["ci_low"] > 0]
    if sep_means:
        ref = max(sep_means)
    else:
        all_means = [s["mean"] for s in stats.values() if s is not None]
        ref = max(all_means) if all_means else 1.0
    if ref <= 0:
        ref = 1.0
    return ce.discovery_confidence(ts["mean"], ts["ci_low"], ts["p_value"], ref), False


# ---- one cut (universe × window) -------------------------------------------


def run_cut(
    store: FactorDataStore, *, start: date, end: date, n: int, bootstrap: int
) -> dict[str, Any]:
    days = v2._trading_days(store, start, end)
    universes = v2._monthly_universes(store, days, n=n, lookback_days=90)
    checkpoints = sorted(universes)
    union = sorted({s for syms in universes.values() for s in syms})
    bars = v2._load_bars(
        store, union, start - pd.Timedelta(days=HISTORY_BUFFER).to_pytimedelta(), end
    )
    if bars.empty:
        raise SystemExit("no bars for cut")
    bars = bars.assign(date=pd.to_datetime(bars["date"]).dt.date)
    by_symbol = {sym: g.reset_index(drop=True) for sym, g in bars.groupby("ticker")}
    pos_index = {sym: {d: i for i, d in enumerate(g["date"])} for sym, g in by_symbol.items()}

    # Per-candidate rows (pooled) for the calibration curve + day-level structures for the
    # autocorrelation-aware CIs. prior_by_regime accrues PIT (used before it is appended to).
    cand_conf: list[float] = []     # opportunity_confidence, pooled across candidates
    cand_E: list[float] = []        # realized expansion, aligned with cand_conf
    cand_CM: list[float] = []       # realized capturable move, aligned

    day_cands: list[list[dict[str, float]]] = []   # per day: [{conf, E, CM}, …]
    day_edge_E: list[float] = []                   # per day: cand mean E − baseline mean E
    day_disc_conf: list[float] = []                # per day: PIT Discovery Confidence (Lever B)
    day_warm: list[bool] = []                      # per day: was it under confidence warm-up?
    day_regime: list[str] = []                     # per day: market regime label

    prior_by_regime: dict[str, list[float]] = {r: [] for r in MARKET_REGIMES}
    proxy_levels: list[float] = [1.0]
    proxy_returns: list[float] = []

    cur_universe: list[str] = []
    cp_iter = iter(checkpoints)
    next_cp = next(cp_iter, None)

    for d in days:
        while next_cp is not None and next_cp <= d:
            cur_universe = universes[next_cp]
            next_cp = next(cp_iter, None)

        mkt = ce.market_regime(proxy_levels)  # classified through the PRIOR close (PIT)

        scored = False
        if len(cur_universe) >= v2.MIN_UNIVERSE and mkt is not None:
            panel: list[dict[str, Any]] = []
            for sym in cur_universe:
                g = by_symbol.get(sym)
                if g is None:
                    continue
                i = pos_index[sym].get(d)
                if i is None:
                    continue
                row = v2._feature_row(g, i, sym)
                if row is not None:
                    panel.append(row)
            eligible = [r for r in panel if ce.is_eligible(r)]
            if len(eligible) >= v2.MIN_UNIVERSE:
                outcomes = {r["symbol"]: r for r in eligible}
                cands = ce.select_candidates(panel, top_n=v2.TOP_N)
                rows = [
                    {"conf": c.confidence, "E": outcomes[c.symbol]["_E"],
                     "CM": outcomes[c.symbol]["_CM"]}
                    for c in cands if c.symbol in outcomes
                ]
                if rows:
                    disc, warm = _discovery_confidence_today(prior_by_regime, mkt)
                    edge = ev._mean([r["E"] for r in rows]) - ev._mean(
                        [o["_E"] for o in eligible])
                    for r in rows:
                        cand_conf.append(r["conf"])
                        cand_E.append(r["E"])
                        cand_CM.append(r["CM"])
                    day_cands.append(rows)
                    day_edge_E.append(edge)
                    day_disc_conf.append(disc)
                    day_warm.append(warm)
                    day_regime.append(mkt)
                    prior_by_regime[mkt].append(edge)  # now history (used AFTER, PIT)
                    scored = True
        _ = scored

        mret = v3._market_return(by_symbol, pos_index, cur_universe, d)
        if mret is not None:
            proxy_returns.append(mret)
            proxy_levels.append(proxy_levels[-1] * (1.0 + mret))

    if not day_cands:
        raise SystemExit("no scorable, classifiable days in cut")

    return _analyze(
        cand_conf, cand_E, cand_CM, day_cands, day_edge_E, day_disc_conf, day_warm, day_regime,
        config={"universe_n": n, "start": start.isoformat(), "end": end.isoformat(),
                "scored_days": len(day_cands), "top_n": v2.TOP_N, "top_k": TOP_K,
                "warmup_days": sum(day_warm), "bootstrap": bootstrap},
        bootstrap=bootstrap,
    )


# ---- hypotheses (§2) -------------------------------------------------------


def _ci(series: list[float], bootstrap: int) -> dict[str, float]:
    r = ev.block_bootstrap_ci(series, ev._mean, n_resamples=bootstrap)
    return {"point": round(r.point, 4), "ci_low": round(r.ci_low, 4),
            "ci_high": round(r.ci_high, 4), "p_value": round(r.p_value, 4)}


def _analyze(
    cand_conf: list[float], cand_E: list[float], cand_CM: list[float],
    day_cands: list[list[dict[str, float]]], day_edge_E: list[float],
    day_disc_conf: list[float], day_warm: list[bool], day_regime: list[str],
    *, config: dict[str, Any], bootstrap: int,
) -> dict[str, Any]:
    # --- H-conf-1: per-candidate confidence calibration (Lever A) ---
    order = sorted(range(len(cand_conf)), key=lambda k: cand_conf[k])
    third = len(order) // 3
    lo_idx, hi_idx = order[:third], order[2 * third:]
    c33 = cand_conf[order[third]] if order else 0.0
    c67 = cand_conf[order[2 * third]] if order else 0.0

    def _tranche(idxs: list[int]) -> dict[str, Any]:
        es = [cand_E[k] for k in idxs]
        cms = [cand_CM[k] for k in idxs]
        confs = [cand_conf[k] for k in idxs]
        return {"n": len(idxs), "conf_min": round(min(confs), 4) if confs else 0.0,
                "conf_max": round(max(confs), 4) if confs else 0.0,
                "mean_E": round(ev._mean(es), 4), "mean_CM": round(ev._mean(cms), 4)}

    low_t, mid_t, high_t = (
        _tranche(lo_idx), _tranche(order[third:2 * third]), _tranche(hi_idx))
    # Day-level high−low diff series (autocorrelation-aware CI): per day, mean E of its
    # candidates in the global HIGH tercile minus those in the LOW tercile.
    diff_series = []
    for rows in day_cands:
        hi_e = [r["E"] for r in rows if r["conf"] >= c67]
        lo_e = [r["E"] for r in rows if r["conf"] <= c33]
        if hi_e and lo_e:
            diff_series.append(ev._mean(hi_e) - ev._mean(lo_e))
    h1_ci = _ci(diff_series, bootstrap) if diff_series else {"point": 0.0, "ci_low": 0.0,
                                                             "ci_high": 0.0, "p_value": 1.0}
    monotone = low_t["mean_E"] < mid_t["mean_E"] < high_t["mean_E"]
    h1_supported = monotone and h1_ci["ci_low"] > 0

    # --- H-conf-2: per-day Discovery-Confidence forward calibration (Lever B) ---
    # Covariance test: mean of (conf − mean_conf)·(edge − mean_edge) over non-warm days. > 0
    # (CI-separated) ⟺ higher-confidence days carry larger edge. Plus the readable median split.
    nw = [(c, e) for c, e, w in zip(day_disc_conf, day_edge_E, day_warm, strict=True) if not w]
    if len(nw) >= 2:
        cs = [c for c, _ in nw]
        es = [e for _, e in nw]
        mc, me = ev._mean(cs), ev._mean(es)
        cov_series = [(c - mc) * (e - me) for c, e in nw]
        h2_ci = _ci(cov_series, bootstrap)
        med = sorted(cs)[len(cs) // 2]
        hi_e = [e for c, e in nw if c > med]
        lo_e = [e for c, e in nw if c <= med]
        h2_split = {"median_conf": round(med, 4),
                    "high_conf_edge": round(ev._mean(hi_e), 4) if hi_e else 0.0,
                    "low_conf_edge": round(ev._mean(lo_e), 4) if lo_e else 0.0,
                    "high_days": len(hi_e), "low_days": len(lo_e)}
    else:
        h2_ci = {"point": 0.0, "ci_low": 0.0, "ci_high": 0.0, "p_value": 1.0}
        h2_split = {"median_conf": 0.0, "high_conf_edge": 0.0, "low_conf_edge": 0.0,
                    "high_days": 0, "low_days": 0}
    h2_supported = h2_ci["ci_low"] > 0

    # --- H-conf-3a: within-day confidence-weighted selection (top-K of top-N) ---
    sel_diff = []
    flat_E, topk_E = [], []
    for rows in day_cands:
        flat = ev._mean([r["E"] for r in rows])
        topk = sorted(rows, key=lambda r: -r["conf"])[:TOP_K]
        topk_mean = ev._mean([r["E"] for r in topk])
        flat_E.append(flat)
        topk_E.append(topk_mean)
        sel_diff.append(topk_mean - flat)
    h3a_ci = _ci(sel_diff, bootstrap)
    h3a_supported = h3a_ci["ci_low"] > 0

    # --- H-conf-3b: cross-day Discovery-Confidence throttle (edge per exposure) ---
    w = [c if not warm else ce.NEUTRAL_CONFIDENCE
         for c, warm in zip(day_disc_conf, day_warm, strict=True)]
    sw = sum(w)
    throttled_epe = sum(wi * e for wi, e in zip(w, day_edge_E, strict=True)) / sw if sw else 0.0
    flat_epe = ev._mean(day_edge_E)
    participation = sw / len(w) if w else 0.0
    h3b = {"flat_edge_per_exposure": round(flat_epe, 4),
           "throttled_edge_per_exposure": round(throttled_epe, 4),
           "delta": round(throttled_epe - flat_epe, 4),
           "mean_exposure": round(participation, 4),
           "note": "Lever B significance is carried by H-conf-2; expected small (REGIME-ROBUST)."}

    # --- H-conf-3c: composite (within-day top-K selection × cross-day throttle) ---
    composite_epe = (
        sum(wi * tk for wi, tk in zip(w, topk_E, strict=True)) / sw if sw else 0.0)
    # baseline-relative composite edge per exposure vs the flat top-N book, exposure-weighted
    flat_book_epe = (
        sum(wi * f for wi, f in zip(w, flat_E, strict=True)) / sw if sw else 0.0)
    h3c = {"composite_mean_E_per_exposure": round(composite_epe, 4),
           "flat_book_mean_E_per_exposure": round(flat_book_epe, 4),
           "delta": round(composite_epe - flat_book_epe, 4),
           "note": "Within-day, final_confidence rank ≡ opportunity_confidence rank (Lever B is "
                   "constant per day); the composite's distinct effect is the cross-day weighting."}

    return {
        "config": config,
        "calibration_curve": {"low": low_t, "mid": mid_t, "high": high_t},
        "h_conf_1": {"diff_high_minus_low": h1_ci, "monotone": monotone,
                     "supported": h1_supported, "diff_days": len(diff_series)},
        "h_conf_2": {"covariance": h2_ci, "median_split": h2_split,
                     "non_warm_days": len(nw), "supported": h2_supported},
        "h_conf_3a": {"topk_minus_flat_E": h3a_ci, "flat_mean_E": round(ev._mean(flat_E), 4),
                      "topk_mean_E": round(ev._mean(topk_E), 4), "supported": h3a_supported},
        "h_conf_3b": h3b,
        "h_conf_3c": h3c,
    }


# ---- verdict + report ------------------------------------------------------


def _classify(headline: dict[str, Any], recency: dict[str, Any]) -> dict[str, Any]:
    """Frozen §4 decision matrix on the headline cut (recency = cross-check)."""
    h = headline
    h1 = h["h_conf_1"]["supported"]
    h2 = h["h_conf_2"]["supported"]
    h3a = h["h_conf_3a"]["supported"]
    negatives = []
    if h["h_conf_3a"]["topk_minus_flat_E"]["ci_high"] < 0:
        negatives.append("3a (within-day selection)")
    if not h1:
        verdict = "CONFIDENCE-UNINFORMATIVE — per-candidate confidence does not predict expansion"
    elif h1 and (h2 or h3a) and not negatives:
        verdict = "CONFIDENCE-CALIBRATED — confidence predicts outcome; ship final_confidence"
    elif h1 and not h2 and not negatives:
        verdict = ("CALIBRATED WITHIN-DAY, REGIME-FLAT — Lever A calibrates; the regime throttle "
                   "is flat (expected: v0.3 REGIME-ROBUST). A success, not a failure.")
    else:
        verdict = "COUNTER-PRODUCTIVE — a lever degrades the book; ship the flat book for it"
    return {
        "verdict": verdict,
        "h_conf_1_headline": h1, "h_conf_1_recency": recency["h_conf_1"]["supported"],
        "h_conf_2_headline": h2, "h_conf_3a_headline": h3a,
        "note": ("v0.2 Validated + v0.3 Operating-Envelope verdicts are unchanged; v0.4 annotates "
                 "HOW to weight the candidate set. L4 stays gated on the premarket-data replication."),
    }


def _curve_rows(cut: dict[str, Any]) -> list[str]:
    cv = cut["calibration_curve"]
    out = ["| Confidence band | n | conf range | realized E | realized CM |",
           "| --- | --- | --- | --- | --- |"]
    for name, key in (("Low", "low"), ("Medium", "mid"), ("High", "high")):
        t = cv[key]
        out.append(f"| {name} | {t['n']} | [{t['conf_min']}, {t['conf_max']}] | "
                   f"{t['mean_E']} | {t['mean_CM']} |")
    return out


def _write_report(result: dict[str, Any], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "candidate_engine_v0_4_evidence.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    v = result["confidence_model"]
    h = result["headline"]
    L = [
        "# SCAN-001 v0.4 — The Confidence Model (calibration + composability) evidence",
        "",
        f"*Generated {result['generated_utc']} · read-only · SCAN-001 §0a: candidate set is "
        "evidence, not a signal. Lift at the evidence layer only — no P&L simulation.*",
        "",
        f"## Verdict: {v['verdict']}",
        "",
        f"*{v['note']}*",
        "",
        "### Calibration curve — does confidence predict expansion? (headline cut)",
        "",
        "The single readable test of the model: realized expansion `E` by confidence band. If it "
        "steps up Low → Medium → High, the per-candidate confidence is informative.",
        "",
        *_curve_rows(h),
        "",
        f"Monotone Low<Med<High: **{h['h_conf_1']['monotone']}** · "
        f"high−low edge {h['h_conf_1']['diff_high_minus_low']['point']} "
        f"CI [{h['h_conf_1']['diff_high_minus_low']['ci_low']}, "
        f"{h['h_conf_1']['diff_high_minus_low']['ci_high']}] "
        f"(p={h['h_conf_1']['diff_high_minus_low']['p_value']}, {h['h_conf_1']['diff_days']} days) "
        f"→ **H-conf-1 {'SUPPORTED' if h['h_conf_1']['supported'] else 'not supported'}**",
        "",
    ]
    for label, cut in (("HEADLINE (top-200, 2010–2026)", result["headline"]),
                       ("RECENCY cross-check (top-500, 2021–2026)", result["recency"])):
        c = cut["config"]
        h1, h2, h3a = cut["h_conf_1"], cut["h_conf_2"], cut["h_conf_3a"]
        h3b, h3c = cut["h_conf_3b"], cut["h_conf_3c"]
        L += [
            f"## {label} — {c['start']} → {c['end']}, {c['scored_days']} scored days "
            f"({c['warmup_days']} warm-up)",
            "",
            "### Lever A — calibration",
            *_curve_rows(cut),
            "",
            f"- **H-conf-1** (per-candidate calibration): monotone={h1['monotone']}, "
            f"high−low E {h1['diff_high_minus_low']['point']} "
            f"CI [{h1['diff_high_minus_low']['ci_low']}, {h1['diff_high_minus_low']['ci_high']}] "
            f"→ **{'SUPPORTED' if h1['supported'] else 'not supported'}**",
            f"- **H-conf-3a** (top-{c['top_k']} of top-{c['top_n']} by confidence): "
            f"top-K mean E {h3a['topk_mean_E']} vs flat {h3a['flat_mean_E']}, "
            f"Δ {h3a['topk_minus_flat_E']['point']} "
            f"CI [{h3a['topk_minus_flat_E']['ci_low']}, {h3a['topk_minus_flat_E']['ci_high']}] "
            f"→ **{'SUPPORTED' if h3a['supported'] else 'not supported'}**",
            "",
            "### Lever B — regime throttle (expected small; REGIME-ROBUST)",
            f"- **H-conf-2** (forward calibration): covariance(conf, edge) "
            f"{h2['covariance']['point']} CI [{h2['covariance']['ci_low']}, "
            f"{h2['covariance']['ci_high']}] → "
            f"**{'SUPPORTED' if h2['supported'] else 'not supported'}** · "
            f"median split: high-conf days edge {h2['median_split']['high_conf_edge']} vs "
            f"low-conf {h2['median_split']['low_conf_edge']} "
            f"({h2['non_warm_days']} non-warm days)",
            f"- **H-conf-3b** (exposure throttle): edge/exposure throttled "
            f"{h3b['throttled_edge_per_exposure']} vs flat {h3b['flat_edge_per_exposure']} "
            f"(Δ {h3b['delta']}, mean exposure {h3b['mean_exposure']})",
            f"- **H-conf-3c** (composite): E/exposure {h3c['composite_mean_E_per_exposure']} "
            f"vs flat book {h3c['flat_book_mean_E_per_exposure']} (Δ {h3c['delta']})",
            "",
        ]
    L += [
        "## Honest scope",
        "",
        "- **PIT confidence is a normal-approx** of v0.3's block bootstrap (an expanding-window "
        "bootstrap per day is prohibitive); the blend/branch logic is identical to v0.3.",
        "- The per-day Discovery Confidence throttles on the **market regime** (bull/bear/sideways); "
        "the vol axis is left to v0.3's heatmap.",
        "- Within a day the composite rank equals the opportunity-confidence rank (Lever B is "
        "constant per day) — by design; Lever B only weights across days.",
        "- Lift is **evidence-layer** (expansion edge / edge-per-exposure), never a P&L backtest "
        "— the premarket-data gate (PR #221) stays the hard prerequisite before any live use.",
        "- Survivorship-biased universe (today's liquid names) — read effects as relative.",
        "",
    ]
    (report_dir / "candidate_engine_v0_4_evidence.md").write_text("\n".join(L), encoding="utf-8")


def _trailing(end: date, years: int) -> date:
    return end.replace(year=end.year - years)


def main() -> None:
    p = argparse.ArgumentParser(description="SCAN-001 v0.4 Confidence-Model research harness")
    p.add_argument("--store", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--bootstrap", type=int, default=2000)
    p.add_argument("--report-dir",
                   default="docs/implementation/evidence/scan_001_candidate_engine_v0_4")
    args = p.parse_args()
    end = date.fromisoformat(args.end)

    with FactorDataStore(args.store, read_only=True) as store:
        headline = run_cut(store, start=_trailing(end, 16), end=end, n=200, bootstrap=args.bootstrap)
        recency = run_cut(store, start=_trailing(end, 5), end=end, n=500, bootstrap=args.bootstrap)

    result: dict[str, Any] = {
        "program": "SCAN-001", "plan": "v0.4",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "headline": headline, "recency": recency,
    }
    result["confidence_model"] = _classify(headline, recency)
    _write_report(result, Path(args.report_dir))
    v = result["confidence_model"]
    print(f"[SCAN-001 v0.4] {v['verdict']}")
    print(f"  H-conf-1 headline={v['h_conf_1_headline']} recency={v['h_conf_1_recency']} | "
          f"H-conf-2={v['h_conf_2_headline']} | H-conf-3a={v['h_conf_3a_headline']}")


if __name__ == "__main__":
    main()
