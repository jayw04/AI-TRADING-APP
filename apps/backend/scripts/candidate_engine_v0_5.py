"""SCAN-001 v0.5 — the De-Tautologized (ATR-decoupled) Confidence (frozen plan v1.0).

Read-only research. v0.4 found the per-candidate confidence is INVERSE to ATR-normalized
expansion `E` and positive to absolute capturable move `CM` — but `CM` is ATR-coupled
(high-ATR names move more, near-mechanically: the v0.1 tautology), and the full confidence
blends ATR in. So "confidence predicts CM" would re-introduce that tautology.

v0.5 asks the only non-mechanical version of the question (plan §0): is there an
**ATR-decoupled** confidence — `confidence_gr`, built from Gap + RVOL strength ONLY — that
predicts a **de-tautologized** outcome **after controlling for ATR** (tested WITHIN ATR
terciles)? If yes, v0.4's negative was an ATR-poisoning artifact and the decoupled confidence
earns a ranking role; if no, v0.4's negative is robust and final (a confirmed double-negative,
the RNG-001 close).

Frozen (plan §1–§3, owner-approved): confidence under test = `confidence_gr` (Gap+RVOL only);
primary outcome = `E`, companion = ATR-stratified `CM`; ATR control = candidate ATR terciles;
K = top-8 of top-15; HEADLINE top-200 2010–2026, RECENCY top-500 2021–2026; seeded (17)
circular-block bootstrap n=2000. Never routes an order — the candidate set is evidence, not a
signal (SCAN-001 §0a). Lift at the evidence layer only (no P&L). The premarket-data gate
(PR #221) stays the hard prerequisite before any live use.

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
        apps/backend/scripts/candidate_engine_v0_5.py \
        --store apps/backend/data/factor_data_full.duckdb --end 2026-06-12 --bootstrap 2000 \
        --report-dir docs/implementation/evidence/scan_001_candidate_engine_v0_5
"""

from __future__ import annotations

import argparse
import json
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
import pandas as pd  # noqa: E402

from app.factor_data import candidate_engine as ce  # noqa: E402
from app.factor_data import evidence as ev  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402

HISTORY_BUFFER = 60
TOP_K = 8                # confidence-ranked subset of TOP_N (frozen §3)
MIN_BAND_DAYS = 60       # an ATR band needs ≥60 paired days to get a CM verdict (else insufficient)
ATR_BANDS = ("low_atr", "mid_atr", "high_atr")


def _ci(series: list[float], bootstrap: int) -> dict[str, Any]:
    if len(series) < 2:
        return {"point": 0.0, "ci_low": 0.0, "ci_high": 0.0, "p_value": 1.0, "n": len(series)}
    r = ev.block_bootstrap_ci(series, ev._mean, n_resamples=bootstrap)
    return {"point": round(r.point, 4), "ci_low": round(r.ci_low, 4),
            "ci_high": round(r.ci_high, 4), "p_value": round(r.p_value, 4), "n": len(series)}


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

    # Per-candidate rows tagged with their scan-day index (for autocorrelation-aware day-level CIs).
    cands: list[dict[str, float]] = []   # {day, gr, atr, E, CM}
    scored_days = 0

    cur_universe: list[str] = []
    cp_iter = iter(checkpoints)
    next_cp = next(cp_iter, None)

    for d in days:
        while next_cp is not None and next_cp <= d:
            cur_universe = universes[next_cp]
            next_cp = next(cp_iter, None)
        if len(cur_universe) < v2.MIN_UNIVERSE:
            continue
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
        if len(eligible) < v2.MIN_UNIVERSE:
            continue
        by_sym = {r["symbol"]: r for r in eligible}
        selected = ce.select_candidates(panel, top_n=v2.TOP_N)
        rows = [by_sym[c.symbol] for c in selected if c.symbol in by_sym]
        if not rows:
            continue
        for r in rows:
            cands.append({"day": float(scored_days), "gr": ce.confidence_gr(r),
                          "atr": r["atr_pct"], "E": r["_E"], "CM": r["_CM"]})
        scored_days += 1

    if not cands:
        raise SystemExit("no scorable days in cut")

    return _analyze(cands, config={"universe_n": n, "start": start.isoformat(),
                                   "end": end.isoformat(), "scored_days": scored_days,
                                   "candidates": len(cands), "top_n": v2.TOP_N, "top_k": TOP_K,
                                   "bootstrap": bootstrap}, bootstrap=bootstrap)


def _terciles(values: list[float]) -> tuple[float, float]:
    """(c33, c67) index-based tercile cutoffs (handles tie-heavy confidence distributions)."""
    s = sorted(values)
    if not s:
        return 0.0, 0.0
    return s[len(s) // 3], s[2 * len(s) // 3]


def _tranche(rows: list[dict[str, float]], key: str) -> dict[str, Any]:
    es = [r["E"] for r in rows]
    cms = [r["CM"] for r in rows]
    grs = [r[key] for r in rows]
    return {"n": len(rows), "conf_min": round(min(grs), 4) if grs else 0.0,
            "conf_max": round(max(grs), 4) if grs else 0.0,
            "mean_E": round(ev._mean(es), 4), "mean_CM": round(ev._mean(cms), 4)}


def _by_day(rows: list[dict[str, float]]) -> dict[float, list[dict[str, float]]]:
    out: dict[float, list[dict[str, float]]] = {}
    for r in rows:
        out.setdefault(r["day"], []).append(r)
    return out


def _day_high_minus_low(
    rows: list[dict[str, float]], conf_key: str, metric: str, c33: float, c67: float
) -> list[float]:
    """Per-day (mean metric of high-confidence cands) − (mean of low-confidence cands)."""
    series: list[float] = []
    for day_rows in _by_day(rows).values():
        hi = [r[metric] for r in day_rows if r[conf_key] >= c67]
        lo = [r[metric] for r in day_rows if r[conf_key] <= c33]
        if hi and lo:
            series.append(ev._mean(hi) - ev._mean(lo))
    return series


def _distribution(values: list[float]) -> list[dict[str, Any]]:
    """Decile histogram of the Discovery Confidence (confidence_gr) values — the customer
    artifact: where the bounded [0,1] number lands (saturation, low/mid/high mass)."""
    edges = [i / 10 for i in range(11)]
    out: list[dict[str, Any]] = []
    n = len(values) or 1
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        # last bin is closed on the right so confidence == 1.0 is counted
        c = sum(1 for v in values if (lo <= v < hi) or (hi == 1.0 and v == 1.0))
        out.append({"bin": f"[{lo:.1f},{hi:.1f}{']' if hi == 1.0 else ')'}", "count": c,
                    "pct": round(100.0 * c / n, 1)})
    return out


def _analyze(cands: list[dict[str, float]], *, config: dict[str, Any], bootstrap: int) -> dict[str, Any]:
    # --- H-cm-1: ATR-decoupled calibration on E (pooled curve + day-level CI) ---
    c33, c67 = _terciles([r["gr"] for r in cands])
    order = sorted(cands, key=lambda r: r["gr"])
    third = len(order) // 3
    curve = {"low": _tranche(order[:third], "gr"),
             "mid": _tranche(order[third:2 * third], "gr"),
             "high": _tranche(order[2 * third:], "gr")}
    h1_ci = _ci(_day_high_minus_low(cands, "gr", "E", c33, c67), bootstrap)
    monotone_E = curve["low"]["mean_E"] < curve["mid"]["mean_E"] < curve["high"]["mean_E"]
    h_cm_1 = {"calibration_curve": curve, "diff_high_minus_low_E": h1_ci,
              "monotone_E": monotone_E, "supported": monotone_E and h1_ci["ci_low"] > 0}

    # --- H-cm-2: ATR-stratified calibration on CM (≥2 of 3 ATR bands) ---
    a33, a67 = _terciles([r["atr"] for r in cands])

    def band_rows(name: str) -> list[dict[str, float]]:
        if name == "low_atr":
            return [r for r in cands if r["atr"] <= a33]
        if name == "high_atr":
            return [r for r in cands if r["atr"] >= a67]
        return [r for r in cands if a33 < r["atr"] < a67]

    bands: dict[str, Any] = {}
    bands_passed = 0
    for name in ATR_BANDS:
        br = band_rows(name)
        bc33, bc67 = _terciles([r["gr"] for r in br])
        series = _day_high_minus_low(br, "gr", "CM", bc33, bc67)
        bo = sorted(br, key=lambda r: r["gr"])
        bthird = len(bo) // 3
        band_curve = {"low": _tranche(bo[:bthird], "gr"),
                      "high": _tranche(bo[2 * bthird:], "gr")} if bthird else {}
        if len(series) < MIN_BAND_DAYS:
            bands[name] = {"candidates": len(br), "paired_days": len(series),
                           "insufficient": True, "curve": band_curve}
            continue
        ci = _ci(series, bootstrap)
        passed = ci["ci_low"] > 0
        bands_passed += int(passed)
        bands[name] = {"candidates": len(br), "paired_days": len(series),
                       "insufficient": False, "diff_high_minus_low_CM": ci,
                       "passed": passed, "curve": band_curve}
    h_cm_2 = {"atr_terciles": {"c33": round(a33, 4), "c67": round(a67, 4)},
              "bands": bands, "bands_passed": bands_passed, "supported": bands_passed >= 2}

    # --- H-cm-3: decoupled-confidence lift (top-K by gr vs flat) ---
    sel_E, sel_CM, atr_topk, atr_flat = [], [], [], []
    for day_rows in _by_day(cands).values():
        flat_E = ev._mean([r["E"] for r in day_rows])
        flat_CM = ev._mean([r["CM"] for r in day_rows])
        topk = sorted(day_rows, key=lambda r: -r["gr"])[:TOP_K]
        sel_E.append(ev._mean([r["E"] for r in topk]) - flat_E)
        sel_CM.append(ev._mean([r["CM"] for r in topk]) - flat_CM)
        atr_topk.append(ev._mean([r["atr"] for r in topk]))
        atr_flat.append(ev._mean([r["atr"] for r in day_rows]))
    h3a = _ci(sel_E, bootstrap)
    h3b = _ci(sel_CM, bootstrap)
    h_cm_3 = {
        "topk_minus_flat_E": h3a, "topk_minus_flat_CM": h3b,
        "supported_E": h3a["ci_low"] > 0,
        "decoupling_check": {"mean_atr_topk": round(ev._mean(atr_topk), 4),
                             "mean_atr_flat": round(ev._mean(atr_flat), 4),
                             "note": "if topk≈flat ATR, the CM lift is not an ATR-selection artifact"},
    }

    dist = _distribution([r["gr"] for r in cands])

    return {"config": config, "confidence_distribution": dist,
            "h_cm_1": h_cm_1, "h_cm_2": h_cm_2, "h_cm_3": h_cm_3}


def _classify(headline: dict[str, Any]) -> dict[str, Any]:
    h1 = headline["h_cm_1"]["supported"]
    h2 = headline["h_cm_2"]["supported"]
    h3 = headline["h_cm_3"]["supported_E"]
    if (h1 or h2) and h3:
        verdict = ("DECOUPLED-CALIBRATED — Gap+RVOL strength predicts a de-tautologized outcome and "
                   "lifts the book; ship confidence_gr as the Candidate Report confidence (ranking gated)")
    elif h1 or h2:
        verdict = ("CALIBRATED, NOT YET A RANKING LIFT — decoupled confidence carries signal but top-K "
                   "selection doesn't capture it")
    else:
        verdict = ("CONFIRMED UNINFORMATIVE (double-negative) — even ATR-decoupled, confidence magnitude "
                   "does not predict a de-tautologized outcome; close the confidence-model research line")
    return {"verdict": verdict, "h_cm_1": h1, "h_cm_2": h2, "h_cm_3_E": h3,
            "note": ("v0.2 Validated / v0.3 Operating-Envelope / v0.4 Confidence-Uninformative verdicts "
                     "are unchanged; Capability Maturity stays L3; L4 gated on the premarket-data step.")}


def _curve_rows(curve: dict[str, Any], bands: tuple[str, ...] = ("low", "mid", "high")) -> list[str]:
    out = ["| Gap+RVOL confidence | n | conf range | realized E | realized CM |",
           "| --- | --- | --- | --- | --- |"]
    label = {"low": "Low", "mid": "Medium", "high": "High"}
    for k in bands:
        if k not in curve:
            continue
        t = curve[k]
        out.append(f"| {label[k]} | {t['n']} | [{t['conf_min']}, {t['conf_max']}] | "
                   f"{t['mean_E']} | {t['mean_CM']} |")
    return out


def _write_report(result: dict[str, Any], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "candidate_engine_v0_5_evidence.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    v = result["verdict"]
    h = result["headline"]
    L = [
        "# SCAN-001 v0.5 — The De-Tautologized (ATR-decoupled) Confidence evidence",
        "",
        f"*Generated {result['generated_utc']} · read-only · SCAN-001 §0a: candidate set is evidence, "
        "not a signal. Confidence under test = Gap+RVOL only (ATR excluded). Lift at the evidence layer "
        "only — no P&L.*",
        "",
        f"## Verdict: {v['verdict']}",
        "",
        f"*{v['note']}*",
        "",
        "### De-tautologized calibration curve — does Gap+RVOL strength predict expansion? (headline)",
        "",
        "Realized `E` by ATR-decoupled (Gap+RVOL) confidence band. The ATR signal is excluded from the "
        "confidence, so this is not the v0.1 mechanical channel.",
        "",
        *_curve_rows(h["h_cm_1"]["calibration_curve"]),
        "",
        f"Monotone Low<Med<High (E): **{h['h_cm_1']['monotone_E']}** · high−low E "
        f"{h['h_cm_1']['diff_high_minus_low_E']['point']} "
        f"CI [{h['h_cm_1']['diff_high_minus_low_E']['ci_low']}, "
        f"{h['h_cm_1']['diff_high_minus_low_E']['ci_high']}] "
        f"→ **H-cm-1 {'SUPPORTED' if h['h_cm_1']['supported'] else 'not supported'}**",
        "",
        "### Discovery Confidence distribution (headline)",
        "",
        "Where the bounded [0,1] Gap+RVOL confidence lands across candidates:",
        "",
        "| Bin | count | % |",
        "| --- | --- | --- |",
        *[f"| {b['bin']} | {b['count']} | {b['pct']} |" for b in h["confidence_distribution"]],
        "",
    ]
    for label, cut in (("HEADLINE (top-200, 2010–2026)", result["headline"]),
                       ("RECENCY cross-check (top-500, 2021–2026)", result["recency"])):
        c = cut["config"]
        h1, h2, h3 = cut["h_cm_1"], cut["h_cm_2"], cut["h_cm_3"]
        L += [
            f"## {label} — {c['start']} → {c['end']}, {c['scored_days']} days, {c['candidates']} candidates",
            "",
            "### H-cm-1 — ATR-decoupled calibration on E",
            *_curve_rows(h1["calibration_curve"]),
            f"\nmonotone={h1['monotone_E']}, high−low E {h1['diff_high_minus_low_E']['point']} "
            f"CI [{h1['diff_high_minus_low_E']['ci_low']}, {h1['diff_high_minus_low_E']['ci_high']}] → "
            f"**{'SUPPORTED' if h1['supported'] else 'not supported'}**",
            "",
            f"### H-cm-2 — ATR-stratified calibration on CM ({h2['bands_passed']}/3 bands, need ≥2)",
            "| ATR band | candidates | paired days | high−low CM (CI) | pass |",
            "| --- | --- | --- | --- | --- |",
        ]
        for name in ATR_BANDS:
            b = h2["bands"][name]
            if b["insufficient"]:
                L.append(f"| {name} | {b['candidates']} | {b['paired_days']} | insufficient (<60d) | — |")
            else:
                d = b["diff_high_minus_low_CM"]
                L.append(f"| {name} | {b['candidates']} | {b['paired_days']} | "
                         f"{d['point']} [{d['ci_low']}, {d['ci_high']}] | {'✓' if b['passed'] else '—'} |")
        L += [
            f"\n→ **H-cm-2 {'SUPPORTED' if h2['supported'] else 'not supported'}** "
            f"({h2['bands_passed']}/3 bands separated)",
            "",
            "### H-cm-3 — decoupled-confidence lift (top-K by Gap+RVOL vs flat)",
            f"- E lift: {h3['topk_minus_flat_E']['point']} "
            f"CI [{h3['topk_minus_flat_E']['ci_low']}, {h3['topk_minus_flat_E']['ci_high']}] → "
            f"**{'SUPPORTED' if h3['supported_E'] else 'not supported'}**",
            f"- CM lift: {h3['topk_minus_flat_CM']['point']} "
            f"CI [{h3['topk_minus_flat_CM']['ci_low']}, {h3['topk_minus_flat_CM']['ci_high']}]",
            f"- Decoupling check: mean ATR top-K {h3['decoupling_check']['mean_atr_topk']} vs flat "
            f"{h3['decoupling_check']['mean_atr_flat']} ({h3['decoupling_check']['note']})",
            "",
        ]
    L += [
        "## Honest scope",
        "",
        "- Confidence under test is **Gap+RVOL only** (`confidence_gr`); ATR still drives *selection*, never "
        "the tested confidence — the anti-tautology decoupling.",
        "- Every CM test is **within ATR terciles** so the mechanical high-ATR→high-CM channel can't pose as a "
        "confidence signal.",
        "- Lift is **evidence-layer** (E / CM diffs), never a P&L backtest — the premarket-data gate (PR #221) "
        "stays the hard prerequisite before any live use.",
        "- Survivorship-biased universe (today's liquid names) — read effects as relative.",
        "",
    ]
    (report_dir / "candidate_engine_v0_5_evidence.md").write_text("\n".join(L), encoding="utf-8")


def _trailing(end: date, years: int) -> date:
    return end.replace(year=end.year - years)


def main() -> None:
    p = argparse.ArgumentParser(description="SCAN-001 v0.5 ATR-decoupled confidence research harness")
    p.add_argument("--store", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--bootstrap", type=int, default=2000)
    p.add_argument("--report-dir",
                   default="docs/implementation/evidence/scan_001_candidate_engine_v0_5")
    args = p.parse_args()
    end = date.fromisoformat(args.end)

    with FactorDataStore(args.store, read_only=True) as store:
        headline = run_cut(store, start=_trailing(end, 16), end=end, n=200, bootstrap=args.bootstrap)
        recency = run_cut(store, start=_trailing(end, 5), end=end, n=500, bootstrap=args.bootstrap)

    result: dict[str, Any] = {
        "program": "SCAN-001", "plan": "v0.5",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "headline": headline, "recency": recency,
    }
    result["verdict"] = _classify(headline)
    _write_report(result, Path(args.report_dir))
    v = result["verdict"]
    print(f"[SCAN-001 v0.5] {v['verdict']}")
    print(f"  H-cm-1={v['h_cm_1']} | H-cm-2={v['h_cm_2']} | H-cm-3(E)={v['h_cm_3_E']}")


if __name__ == "__main__":
    main()
