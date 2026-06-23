"""SCAN-001 v0.2 — de-tautologized Candidate Engine research (frozen plan v0.2).

Read-only research. Reuses the pure engine (`app.factor_data.candidate_engine`) but replaces
the v0.1 question ("do candidates realize higher range?" — which was partly DEFINITIONAL
because we select on ATR, a range measure) with three frozen hypotheses that remove the
tautology and decide whether the engine found something *tradeable*:

    H1′ Expansion  — do candidates expand BEYOND their own ATR? (range / ATR; >1 and
                     CI-separated from the baseline)
    H2  Directionality — is the range tradeable, not chop? 2-of-3 of {trend-efficiency,
                     capturable-move, net-move}, each CI-separated (owner: moderate bar)
    H3  Attribution — do Gap and RVOL add over an ATR-only screen, or simplify the engine?

Frozen run config (plan §4a, owner): HEADLINE = top-500 universe, trailing 3y; ROBUSTNESS =
top-200, 5y. Verdict is Supported only if it holds on BOTH cuts (divergence is the finding).

Never routes an order — the candidate set is evidence, not a signal (SCAN-001 §0a). Daily-bar
gap/RVOL approximations carry over from v0.1; a real premarket feed stays a hard gate BEFORE
any promotion (explicitly out of v0.2 scope).

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
        apps/backend/scripts/candidate_engine_v0_2.py \
        --store apps/backend/data/factor_data_full.duckdb --end 2026-06-12 \
        --bootstrap 2000 --report-dir docs/implementation/evidence/scan_001_candidate_engine_v0_2
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pandas as pd  # noqa: E402

from app.factor_data import candidate_engine as ce  # noqa: E402
from app.factor_data import evidence as ev  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402
from app.factor_data.universe import universe_asof  # noqa: E402

ATR_N = 14
RVOL_LOOKBACK = 20
HISTORY_BUFFER = 60
MIN_UNIVERSE = 20
TOP_N = 15

# H3 attribution sets — each a restriction of the engine's opportunity signals.
SIGNAL_SETS: dict[str, tuple[str, ...]] = {
    "ATR_only": ("ATR",),
    "ATR_Gap": ("Gap", "ATR"),
    "ATR_RVOL": ("RVOL", "ATR"),
    "full": ("Gap", "RVOL", "ATR"),
}


def _trading_days(store: FactorDataStore, start: date, end: date) -> list[date]:
    rows = store.con.execute(
        "SELECT DISTINCT date FROM sep WHERE date BETWEEN ? AND ? ORDER BY date",
        [start, end],
    ).fetchall()
    return [r[0] for r in rows]


def _monthly_universes(
    store: FactorDataStore, days: list[date], *, n: int, lookback_days: int
) -> dict[date, list[str]]:
    checkpoints: dict[date, list[str]] = {}
    seen: set[tuple[int, int]] = set()
    for d in days:
        key = (d.year, d.month)
        if key in seen:
            continue
        seen.add(key)
        with contextlib.suppress(Exception):
            checkpoints[d] = universe_asof(store, d, n=n, lookback_days=lookback_days)
    return checkpoints


def _load_bars(store: FactorDataStore, symbols: list[str], start: date, end: date) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    placeholders = ",".join("?" for _ in symbols)
    df = store.con.execute(
        f"""
        SELECT ticker, date, open, high, low, close, volume
        FROM sep
        WHERE ticker IN ({placeholders}) AND date BETWEEN ? AND ?
        ORDER BY ticker, date
        """,
        [*symbols, start, end],
    ).fetchdf()
    return df


def _feature_row(g: pd.DataFrame, i: int, symbol: str) -> dict[str, Any] | None:
    """Pre-open features (gap/rvol/atr/price/$vol) + the day's OHLC for outcome scoring."""
    if i < ATR_N + 1 or i < RVOL_LOOKBACK + 1:
        return None
    today = g.iloc[i]
    prev = g.iloc[i - 1]
    prev_close = float(prev["close"])
    if prev_close <= 0:
        return None
    o, h, low_, c = (float(today[k]) for k in ("open", "high", "low", "close"))
    if o <= 0:
        return None
    window = g.iloc[i - RVOL_LOOKBACK : i]
    avg_vol = float(window["volume"].mean())
    highs = [float(x) for x in g.iloc[i - ATR_N - 1 : i]["high"]]
    lows = [float(x) for x in g.iloc[i - ATR_N - 1 : i]["low"]]
    closes = [float(x) for x in g.iloc[i - ATR_N - 1 : i]["close"]]
    atr = ce.atr_pct(highs, lows, closes, n=ATR_N)
    rng = ce.intraday_range_pct(h, low_, o)
    return {
        "symbol": symbol,
        "gap_pct": ce.gap_pct(o, prev_close),
        "rvol": ce.rvol(float(today["volume"]), avg_vol),
        "atr_pct": atr,
        "price": prev_close,
        "dollar_vol": prev_close * float(prev["volume"]),
        # outcomes (post-open) — scored after selection, never fed to the filters
        "_E": ce.expansion_ratio(rng, atr),
        "_TE": ce.trend_efficiency(o, h, low_, c),
        "_CM": ce.capturable_move(o, h, low_),
        "_NM": ce.net_move(o, c),
    }


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def run_cut(
    store: FactorDataStore, *, start: date, end: date, n: int, bootstrap: int
) -> dict[str, Any]:
    """One (universe, window) cut → H1′/H2/H3 evidence."""
    days = _trading_days(store, start, end)
    universes = _monthly_universes(store, days, n=n, lookback_days=90)
    checkpoints = sorted(universes)
    union = sorted({s for syms in universes.values() for s in syms})
    bars = _load_bars(store, union, start - pd.Timedelta(days=HISTORY_BUFFER).to_pytimedelta(), end)
    if bars.empty:
        raise SystemExit("no bars for cut")
    bars = bars.assign(date=pd.to_datetime(bars["date"]).dt.date)
    by_symbol = {sym: g.reset_index(drop=True) for sym, g in bars.groupby("ticker")}
    pos_index = {sym: {d: i for i, d in enumerate(g["date"])} for sym, g in by_symbol.items()}

    # daily edge series, per metric, for the full-engine candidate set vs the baseline
    edges: dict[str, list[float]] = {"E": [], "TE": [], "CM": [], "NM": []}
    cand_means: dict[str, list[float]] = {"E": [], "TE": [], "CM": [], "NM": []}
    base_means: dict[str, list[float]] = {"E": [], "TE": [], "CM": [], "NM": []}
    # H3: per-day candidate-set means of E and CM for each signal set
    h3_E: dict[str, list[float]] = {k: [] for k in SIGNAL_SETS}
    h3_CM: dict[str, list[float]] = {k: [] for k in SIGNAL_SETS}

    cur_universe: list[str] = []
    cp_iter = iter(checkpoints)
    next_cp = next(cp_iter, None)
    scored_days = 0

    for d in days:
        while next_cp is not None and next_cp <= d:
            cur_universe = universes[next_cp]
            next_cp = next(cp_iter, None)
        if len(cur_universe) < MIN_UNIVERSE:
            continue
        panel: list[dict[str, Any]] = []
        for sym in cur_universe:
            g = by_symbol.get(sym)
            if g is None:
                continue
            i = pos_index[sym].get(d)
            if i is None:
                continue
            row = _feature_row(g, i, sym)
            if row is not None:
                panel.append(row)
        eligible = [r for r in panel if ce.is_eligible(r)]
        if len(eligible) < MIN_UNIVERSE:
            continue
        outcomes = {r["symbol"]: r for r in eligible}

        full = ce.select_candidates(panel, top_n=TOP_N, active_signals=SIGNAL_SETS["full"])
        cand_syms = {c.symbol for c in full if c.symbol in outcomes}
        if not cand_syms:
            continue
        scored_days += 1
        for key in edges:
            mk = f"_{key}"
            cm = _mean([outcomes[s][mk] for s in cand_syms])
            bm = _mean([r[mk] for r in eligible])
            cand_means[key].append(cm)
            base_means[key].append(bm)
            edges[key].append(cm - bm)
        # H3 sets
        for set_name, sig in SIGNAL_SETS.items():
            sel = ce.select_candidates(panel, top_n=TOP_N, active_signals=sig)
            ssyms = {c.symbol for c in sel if c.symbol in outcomes}
            h3_E[set_name].append(_mean([outcomes[s]["_E"] for s in ssyms]) if ssyms else 0.0)
            h3_CM[set_name].append(_mean([outcomes[s]["_CM"] for s in ssyms]) if ssyms else 0.0)

    if scored_days == 0:
        raise SystemExit("no scorable days in cut")

    def ci(series: list[float]) -> dict[str, float]:
        r = ev.block_bootstrap_ci(series, ev._mean, n_resamples=bootstrap)
        return {"point": round(r.point, 4), "ci_low": round(r.ci_low, 4),
                "ci_high": round(r.ci_high, 4), "p_value": round(r.p_value, 4)}

    edge_ci = {k: ci(v) for k, v in edges.items()}

    # H1′ — expansion beyond ATR
    cand_E = round(_mean(cand_means["E"]), 4)
    h1p_supported = cand_E > 1.0 and edge_ci["E"]["ci_low"] > 0

    # H2 — 2-of-3 tradeability (TE non-regression; CM/NM strictly positive)
    te_clears = edge_ci["TE"]["ci_low"] >= 0.0
    cm_clears = edge_ci["CM"]["ci_low"] > 0.0
    nm_clears = edge_ci["NM"]["ci_low"] > 0.0
    h2_count = sum([te_clears, cm_clears, nm_clears])
    h2_supported = h2_count >= 2

    # H3 — does each extra signal beat the ATR-only screen (daily diff, CI-separated)?
    def additive(set_name: str) -> dict[str, Any]:
        dE = [a - b for a, b in zip(h3_E[set_name], h3_E["ATR_only"], strict=True)]
        dCM = [a - b for a, b in zip(h3_CM[set_name], h3_CM["ATR_only"], strict=True)]
        cE, cCM = ci(dE), ci(dCM)
        return {
            "vs_atr_only_E": cE, "vs_atr_only_CM": cCM,
            "additive": cE["ci_low"] > 0 or cCM["ci_low"] > 0,
        }

    h3 = {name: additive(name) for name in ("ATR_Gap", "ATR_RVOL", "full")}

    return {
        "config": {"universe_n": n, "start": start.isoformat(), "end": end.isoformat(),
                   "days": scored_days, "top_n": TOP_N, "bootstrap": bootstrap},
        "h1_prime": {
            "candidate_expansion_ratio": cand_E,
            "baseline_expansion_ratio": round(_mean(base_means["E"]), 4),
            "edge": edge_ci["E"], "supported": h1p_supported,
        },
        "h2": {
            "trend_efficiency": {"edge": edge_ci["TE"], "clears": te_clears,
                                 "candidate": round(_mean(cand_means["TE"]), 4),
                                 "baseline": round(_mean(base_means["TE"]), 4)},
            "capturable_move": {"edge": edge_ci["CM"], "clears": cm_clears,
                                "candidate": round(_mean(cand_means["CM"]), 4),
                                "baseline": round(_mean(base_means["CM"]), 4)},
            "net_move": {"edge": edge_ci["NM"], "clears": nm_clears,
                         "candidate": round(_mean(cand_means["NM"]), 4),
                         "baseline": round(_mean(base_means["NM"]), 4)},
            "clears_count": h2_count, "supported": h2_supported,
        },
        "h3_attribution": h3,
    }


def _overall_verdict(headline: dict[str, Any], robustness: dict[str, Any]) -> dict[str, Any]:
    h1 = headline["h1_prime"]["supported"] and robustness["h1_prime"]["supported"]
    h2 = headline["h2"]["supported"] and robustness["h2"]["supported"]
    if h1 and h2:
        verdict = "SUPPORTED — engine finds genuine, tradeable expansion (holds on both cuts)"
    elif h1 and not h2:
        verdict = "PARTIAL — expands beyond ATR but not cleanly tradeable (H2 fails a cut)"
    elif not headline["h1_prime"]["supported"] and not robustness["h1_prime"]["supported"]:
        verdict = "NOT SUPPORTED — expansion ≈ ATR on both cuts; the v0.1 edge was tautological"
    else:
        verdict = "DIVERGENT — H1′ holds on one cut only; opportunity is regime/universe-concentrated"
    gap_add = headline["h3_attribution"]["ATR_Gap"]["additive"]
    rvol_add = headline["h3_attribution"]["ATR_RVOL"]["additive"]
    keep = ["ATR"] + (["Gap"] if gap_add else []) + (["RVOL"] if rvol_add else [])
    return {
        "verdict": verdict,
        "h1_prime_both_cuts": h1, "h2_both_cuts": h2,
        "attribution_recommendation": (
            f"Keep signals: {' + '.join(keep)}."
            + ("" if (gap_add and rvol_add) else " Non-additive signals are decoration — simplify.")
        ),
    }


def _write_report(result: dict[str, Any], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "candidate_engine_v0_2_evidence.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    ov = result["overall"]
    L = [
        "# SCAN-001 v0.2 — Candidate Engine: de-tautologized evidence",
        "",
        f"*Generated {result['generated_utc']} · read-only research · SCAN-001 §0a: candidate set is evidence, not a signal.*",
        "",
        f"## Overall verdict: {ov['verdict']}",
        "",
        f"- H1′ (expansion beyond ATR) holds on both cuts: **{ov['h1_prime_both_cuts']}**",
        f"- H2 (2-of-3 tradeability) holds on both cuts: **{ov['h2_both_cuts']}**",
        f"- Attribution: {ov['attribution_recommendation']}",
        "",
    ]
    for label, cut in (("HEADLINE (top-500, 3y)", result["headline"]),
                       ("ROBUSTNESS (top-200, 5y)", result["robustness"])):
        c = cut["config"]
        h1, h2 = cut["h1_prime"], cut["h2"]
        L += [
            f"## {label} — {c['start']} → {c['end']}, {c['days']} days, top-{c['universe_n']}",
            "",
            "### H1′ — expansion beyond ATR",
            f"- Candidate {h1['candidate_expansion_ratio']}× vs baseline {h1['baseline_expansion_ratio']}× ATR · "
            f"edge {h1['edge']['point']} CI [{h1['edge']['ci_low']}, {h1['edge']['ci_high']}] p={h1['edge']['p_value']} → "
            f"**{'SUPPORTED' if h1['supported'] else 'not supported'}** (need >1.0× and CI>0)",
            "",
            "### H2 — tradeability (2-of-3)",
            "| Metric | Candidate | Baseline | Edge CI | Clears |",
            "| --- | --- | --- | --- | --- |",
        ]
        for mk, name in (("trend_efficiency", "Trend efficiency"),
                         ("capturable_move", "Capturable move %"),
                         ("net_move", "Net move %")):
            m = h2[mk]
            L.append(f"| {name} | {m['candidate']} | {m['baseline']} | "
                     f"[{m['edge']['ci_low']}, {m['edge']['ci_high']}] | {'✓' if m['clears'] else '—'} |")
        L += [
            f"\n→ {h2['clears_count']}/3 clear → **{'SUPPORTED' if h2['supported'] else 'not supported'}**",
            "",
            "### H3 — signal attribution (vs ATR-only screen)",
            "| Signal set | ΔE CI | ΔCM CI | Additive |",
            "| --- | --- | --- | --- |",
        ]
        for sn in ("ATR_Gap", "ATR_RVOL", "full"):
            a = cut["h3_attribution"][sn]
            L.append(f"| {sn} | [{a['vs_atr_only_E']['ci_low']}, {a['vs_atr_only_E']['ci_high']}] | "
                     f"[{a['vs_atr_only_CM']['ci_low']}, {a['vs_atr_only_CM']['ci_high']}] | "
                     f"{'✓' if a['additive'] else '—'} |")
        L.append("")
    L += [
        "## Honest scope",
        "",
        "- Daily-bar gap/RVOL approximations carry over from v0.1 (gap≈open, daily-RVOL proxy).",
        "- A real premarket feed (PR #221 gappers) stays a **hard gate before any promotion** — out of v0.2 scope.",
        "- Verdict requires holding on BOTH cuts; divergence is reported as the finding, not smoothed over.",
        "",
    ]
    (report_dir / "candidate_engine_v0_2_evidence.md").write_text("\n".join(L), encoding="utf-8")


def _trailing(end: date, years: int) -> date:
    return end.replace(year=end.year - years)


def main() -> None:
    p = argparse.ArgumentParser(description="SCAN-001 v0.2 de-tautologized research harness")
    p.add_argument("--store", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--bootstrap", type=int, default=2000)
    p.add_argument("--report-dir", default="docs/implementation/evidence/scan_001_candidate_engine_v0_2")
    args = p.parse_args()
    end = date.fromisoformat(args.end)

    with FactorDataStore(args.store, read_only=True) as store:
        headline = run_cut(store, start=_trailing(end, 3), end=end, n=500, bootstrap=args.bootstrap)
        robustness = run_cut(store, start=_trailing(end, 5), end=end, n=200, bootstrap=args.bootstrap)

    result: dict[str, Any] = {
        "program": "SCAN-001", "plan": "v0.2",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "headline": headline, "robustness": robustness,
    }
    result["overall"] = _overall_verdict(headline, robustness)
    _write_report(result, Path(args.report_dir))
    print(f"[SCAN-001 v0.2] {result['overall']['verdict']}")
    print(f"  H1' both cuts={result['overall']['h1_prime_both_cuts']} | "
          f"H2 both cuts={result['overall']['h2_both_cuts']}")
    print(f"  {result['overall']['attribution_recommendation']}")


if __name__ == "__main__":
    main()
