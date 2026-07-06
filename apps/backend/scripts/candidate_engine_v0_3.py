"""SCAN-001 v0.3 — Operating-Envelope (Discovery-Stability) research (frozen plan v0.3).

Read-only research. Reuses the v0.2 engine + panel plumbing and decomposes the ALREADY-
VALIDATED expansion edge by market regime (bull/bear/sideways) and volatility regime
(high/low), to define the Discovery Engine's **Operating Envelope** — where the capability
works (★★★★★), works marginally (★★), or should NOT be used (★).

Outputs (plan §4a / §9): a Capability Strength Map (★ per regime, frozen mapping) and a
Discovery Confidence Heatmap ([0,1] per regime). NOT a re-validation — v0.2's verdict
stands; v0.3 maps its boundaries. Read-only; no order path.

Regimes are labelled PIT from a broad-market proxy = the equal-weight cumulative index of
the day's liquid universe (SPY is absent from the SEP store). Each scan day is classified
from the proxy through the PRIOR close (strict pre-open PIT — a day's regime is known at
its 09:25 scan, never using its own close).

Frozen config (plan §3, owner-approved): PRIMARY = 2010-06 → 2026-06, top-200; RECENCY
cross-check = 2021-06 → 2026-06, top-500; market 3-state; ≥60-day minimum cell sample.

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
        apps/backend/scripts/candidate_engine_v0_3.py \
        --store apps/backend/data/factor_data_full.duckdb --end 2026-06-12 --bootstrap 2000 \
        --report-dir docs/implementation/evidence/scan_001_candidate_engine_v0_3
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

import candidate_engine_v0_2 as v2  # noqa: E402  (reuse the v0.2 panel plumbing)
import pandas as pd  # noqa: E402

from app.factor_data import candidate_engine as ce  # noqa: E402
from app.factor_data import evidence as ev  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402

MIN_CELL_DAYS = 60      # below this a regime is "insufficient sample", not a verdict
HISTORY_BUFFER = 60
MARKET_REGIMES = ("bull", "bear", "sideways")
VOL_REGIMES = ("high", "low")


def _market_return(by_symbol: dict, pos_index: dict, syms: list[str], d: date) -> float | None:
    """Equal-weight close-to-close return of the universe on day d (the proxy increment)."""
    rets: list[float] = []
    for s in syms:
        g = by_symbol.get(s)
        if g is None:
            continue
        i = pos_index[s].get(d)
        if i is None or i < 1:
            continue
        pc = float(g.iloc[i - 1]["close"])
        if pc > 0:
            rets.append(float(g.iloc[i]["close"]) / pc - 1.0)
    return sum(rets) / len(rets) if rets else None


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

    # Per scored day: (market_regime, vol_regime, E_edge, CM_edge), labelled PIT.
    rows: list[dict[str, Any]] = []
    proxy_levels: list[float] = [1.0]   # the equal-weight market index
    proxy_returns: list[float] = []
    vol_series: list[float] = []        # trailing realized-vol series for the median split

    cur_universe: list[str] = []
    cp_iter = iter(checkpoints)
    next_cp = next(cp_iter, None)

    for d in days:
        while next_cp is not None and next_cp <= d:
            cur_universe = universes[next_cp]
            next_cp = next(cp_iter, None)
        if not cur_universe:
            continue

        # Classify day d from the proxy through the PRIOR close (strict pre-open PIT).
        mkt = ce.market_regime(proxy_levels)
        vol_today = ce.realized_vol(proxy_returns, n=ce.VOL_WINDOW)
        vol = ce.vol_regime(vol_today, vol_series[-ce.VOL_MEDIAN_WINDOW:])

        # Score the day (full-engine candidates vs eligible baseline), reusing v0.2 features.
        panel = []
        for sym in cur_universe:
            g = by_symbol.get(sym)
            if g is None:
                continue
            i = pos_index[sym].get(d)
            if i is None:
                continue
            fr = v2._feature_row(g, i, sym)
            if fr is not None:
                panel.append(fr)
        eligible = [r for r in panel if ce.is_eligible(r)]
        if len(eligible) >= 20 and mkt is not None and vol is not None:
            cands = ce.select_candidates(panel, top_n=v2.TOP_N)
            outcomes = {r["symbol"]: r for r in eligible}
            cset = {c.symbol for c in cands if c.symbol in outcomes}
            if cset:
                e_edge = v2._mean([outcomes[s]["_E"] for s in cset]) - v2._mean(
                    [r["_E"] for r in eligible])
                cm_edge = v2._mean([outcomes[s]["_CM"] for s in cset]) - v2._mean(
                    [r["_CM"] for r in eligible])
                rows.append({"market": mkt, "vol": vol, "E": e_edge, "CM": cm_edge})

        # Advance the proxy with day d's realized market return (now part of history).
        mret = _market_return(by_symbol, pos_index, cur_universe, d)
        if mret is not None:
            proxy_returns.append(mret)
            proxy_levels.append(proxy_levels[-1] * (1.0 + mret))
            rv = ce.realized_vol(proxy_returns, n=ce.VOL_WINDOW)
            if rv is not None:
                vol_series.append(rv)

    if not rows:
        raise SystemExit("no scorable, classifiable days in cut")

    def bucket(label_key: str, label: str) -> dict[str, Any]:
        e = [r["E"] for r in rows if r[label_key] == label]
        cm = [r["CM"] for r in rows if r[label_key] == label]
        days_n = len(e)
        if days_n < MIN_CELL_DAYS:
            return {"days": days_n, "insufficient": True}
        ce_ = ev.block_bootstrap_ci(e, ev._mean, n_resamples=bootstrap)
        cm_ = ev.block_bootstrap_ci(cm, ev._mean, n_resamples=bootstrap)
        return {
            "days": days_n, "insufficient": False,
            "expansion_edge": {"point": round(ce_.point, 4), "ci_low": round(ce_.ci_low, 4),
                               "ci_high": round(ce_.ci_high, 4), "p_value": round(ce_.p_value, 4)},
            "capturable_edge": {"point": round(cm_.point, 4), "ci_low": round(cm_.ci_low, 4),
                                "ci_high": round(cm_.ci_high, 4), "p_value": round(cm_.p_value, 4)},
        }

    cells = {r: bucket("market", r) for r in MARKET_REGIMES}
    cells.update({r: bucket("vol", r) for r in VOL_REGIMES})
    _assign_envelope(cells)
    return {
        "config": {"universe_n": n, "start": start.isoformat(), "end": end.isoformat(),
                   "scored_days": len(rows), "min_cell_days": MIN_CELL_DAYS,
                   "bootstrap": bootstrap},
        "regime_day_counts": {
            "market": {r: sum(1 for x in rows if x["market"] == r) for r in MARKET_REGIMES},
            "vol": {r: sum(1 for x in rows if x["vol"] == r) for r in VOL_REGIMES},
        },
        "cells": cells,
    }


def _assign_envelope(cells: dict[str, dict[str, Any]]) -> None:
    """Add the frozen Strength-Map ★ rating + Discovery-Confidence [0,1] to each cell
    (plan §4a). Separated regimes are tercile-ranked by expansion-edge point estimate."""
    sep = [k for k, c in cells.items()
           if not c["insufficient"] and c["expansion_edge"]["ci_low"] > 0]
    pts = sorted(cells[k]["expansion_edge"]["point"] for k in sep)
    ref = max(pts) if pts else 1.0

    def tercile_stars(point: float) -> int:
        if len(pts) < 3:
            return 4  # too few separated regimes to tercile — middle band
        lo, hi = pts[len(pts) // 3], pts[2 * len(pts) // 3]
        return 5 if point >= hi else (3 if point < lo else 4)

    for c in cells.values():
        if c["insufficient"]:
            c["stars"], c["confidence"] = None, None
            continue
        ee = c["expansion_edge"]
        pt, sep_ok = ee["point"], ee["ci_low"] > 0
        if pt <= 0:
            stars, conf = 1, 0.0
        elif not sep_ok:
            stars, conf = 2, round(0.4 * max(0.0, 1.0 - ee["p_value"]), 3)
        else:
            stars = tercile_stars(pt)
            mag = min(1.0, max(0.0, pt / ref)) if ref > 0 else 0.0
            conf = round(0.5 * max(0.0, 1.0 - ee["p_value"]) + 0.5 * mag, 3)
        c["stars"], c["confidence"] = stars, conf


def _classify(headline: dict[str, Any], recency: dict[str, Any]) -> dict[str, Any]:
    """Operating-envelope classification per the frozen §4 decision matrix, on the headline
    cut (recency is the cross-check)."""
    cells = headline["cells"]
    judged = {k: c for k, c in cells.items() if not c["insufficient"]}
    negatives = [k for k, c in judged.items() if c["expansion_edge"]["point"] <= 0]
    not_sep = [k for k, c in judged.items() if c["expansion_edge"]["ci_low"] <= 0
               and c["expansion_edge"]["point"] > 0]
    if negatives:
        verdict = f"REGIME-FRAGILE — no-go in: {', '.join(negatives)}"
    elif not_sep:
        verdict = f"REGIME-CONDITIONAL — weak (CI spans 0) in: {', '.join(not_sep)}"
    else:
        verdict = "REGIME-ROBUST — positive, CI-separated in every judged regime"
    return {
        "verdict": verdict,
        "strength_map": {k: ("—" if c["stars"] is None else "★" * c["stars"])
                         for k, c in cells.items()},
        "confidence_heatmap": {k: c["confidence"] for k, c in cells.items()},
        "note": "v0.2 Validated verdict is unchanged; this annotates WHERE it applies.",
    }


def _row(name: str, c: dict[str, Any]) -> str:
    if c["insufficient"]:
        return f"| {name} | {c['days']} | insufficient (<60d) | — | — |"
    ee = c["expansion_edge"]
    stars = "—" if c["stars"] is None else "★" * c["stars"]
    return (f"| {name} | {c['days']} | {ee['point']} [{ee['ci_low']}, {ee['ci_high']}] "
            f"(p={ee['p_value']}) | {stars} | {c['confidence']} |")


def _write_report(result: dict[str, Any], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "candidate_engine_v0_3_evidence.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    env = result["operating_envelope"]
    L = [
        "# SCAN-001 v0.3 — Operating Envelope (Discovery-Stability) evidence",
        "",
        f"*Generated {result['generated_utc']} · read-only · SCAN-001 §0a: candidate set is evidence, not a signal.*",
        "",
        f"## Operating-Envelope verdict: {env['verdict']}",
        "",
        f"*{env['note']}*",
        "",
        "### Capability Strength Map (★ = expansion edge magnitude + significance)",
        "",
        "| Regime | Stars | Discovery Confidence |",
        "| --- | --- | --- |",
    ]
    order = list(MARKET_REGIMES) + list(VOL_REGIMES)
    for k in order:
        L.append(f"| {k} | {env['strength_map'][k]} | {env['confidence_heatmap'][k]} |")
    for label, cut in (("HEADLINE (top-200, 2010–2026)", result["headline"]),
                       ("RECENCY cross-check (top-500, 2021–2026)", result["recency"])):
        cfg = cut["config"]
        L += [
            "",
            f"## {label} — {cfg['start']} → {cfg['end']}, {cfg['scored_days']} scored days",
            "",
            "Regime day counts: market "
            + ", ".join(f"{r}={cut['regime_day_counts']['market'][r]}" for r in MARKET_REGIMES)
            + " · vol "
            + ", ".join(f"{r}={cut['regime_day_counts']['vol'][r]}" for r in VOL_REGIMES),
            "",
            "| Regime | Days | Expansion edge (CI, p) | Stars | Confidence |",
            "| --- | --- | --- | --- | --- |",
        ]
        for k in order:
            L.append(_row(k, cut["cells"][k]))
    L += [
        "",
        "## Honest scope",
        "",
        "- Market proxy is the equal-weight liquid-universe index (SPY absent from SEP); an index-based re-run is a follow-on.",
        "- Each day is classified PIT from the proxy through the prior close (no look-ahead).",
        "- Confirmatory tests = the 5 marginal regimes; seasonality/grid would be descriptive-only (not run here).",
        "- v0.2's Validated verdict is unchanged — this study defines the envelope, it cannot un-validate the full-sample result.",
        "",
    ]
    (report_dir / "candidate_engine_v0_3_evidence.md").write_text("\n".join(L), encoding="utf-8")


def _trailing(end: date, years: int) -> date:
    return end.replace(year=end.year - years)


def main() -> None:
    p = argparse.ArgumentParser(description="SCAN-001 v0.3 Operating-Envelope research harness")
    p.add_argument("--store", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--bootstrap", type=int, default=2000)
    p.add_argument("--report-dir", default="docs/implementation/evidence/scan_001_candidate_engine_v0_3")
    args = p.parse_args()
    end = date.fromisoformat(args.end)

    with FactorDataStore(args.store, read_only=True) as store:
        headline = run_cut(store, start=_trailing(end, 16), end=end, n=200, bootstrap=args.bootstrap)
        recency = run_cut(store, start=_trailing(end, 5), end=end, n=500, bootstrap=args.bootstrap)

    result: dict[str, Any] = {
        "program": "SCAN-001", "plan": "v0.3",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "headline": headline, "recency": recency,
    }
    result["operating_envelope"] = _classify(headline, recency)
    _write_report(result, Path(args.report_dir))
    env = result["operating_envelope"]
    print(f"[SCAN-001 v0.3] {env['verdict']}")
    print("  Strength map: " + " · ".join(
        f"{k}={env['strength_map'][k]}" for k in list(MARKET_REGIMES) + list(VOL_REGIMES)))


if __name__ == "__main__":
    main()
