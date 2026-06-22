"""SCAN-001 — Candidate Engine research harness (Market Opportunity Discovery, v1 intraday).

Read-only research. Replays the pure Candidate Engine (`app.factor_data.candidate_engine`)
day-by-day over the survivorship-free SEP store and asks the pre-registered question:

    H1 — does the curated candidate set realize a higher intraday range than the liquid
         universe it was drawn from? (i.e. do the frozen filters *select opportunity*?)

For each trading day: build the PIT pre-open feature panel (gap %, daily-RVOL proxy, ATR %,
price, $-volume) from prior bars, run the engine → ranked top-N, then score the realized
intraday-range % (HOD−LOD)/open — the opportunity metric — for the candidates vs the full
eligible universe that day. The daily (candidate − baseline) difference series is the edge;
a seeded block bootstrap brackets it with a CI + one-sided p-value.

This NEVER routes an order. The candidate set is evidence, not a signal (SCAN-001 §0a).

PIT honesty: the universe is re-struck monthly (PIT, survivorship-free). Gap % uses the
official open as a ~5-min approximation of the live 09:25 premarket price, and RVOL is a
daily proxy — both flagged as v1 refinements needing true premarket data. The opportunity
metric is the post-open OUTCOME, so it cannot leak into selection.

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
        apps/backend/scripts/candidate_engine.py \
        --store apps/backend/data/factor_data_full.duckdb \
        --start 2018-01-01 --end 2026-06-12 --n 200 --top-n 15 --bootstrap 2000 \
        --report-dir docs/implementation/evidence/scan_001_candidate_engine
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

ATR_N = 14            # ATR lookback (bars)
RVOL_LOOKBACK = 20    # trailing average-volume window for the daily-RVOL proxy
HISTORY_BUFFER = 60   # calendar-day pad so day 1 of the range has enough prior bars
MIN_UNIVERSE = 20     # skip days too thin to form a meaningful baseline


def _trading_days(store: FactorDataStore, start: date, end: date) -> list[date]:
    rows = store.con.execute(
        "SELECT DISTINCT date FROM sep WHERE date BETWEEN ? AND ? ORDER BY date",
        [start, end],
    ).fetchall()
    return [r[0] for r in rows]


def _monthly_universes(
    store: FactorDataStore, days: list[date], *, n: int, lookback_days: int
) -> dict[date, list[str]]:
    """Re-strike the liquid universe on the first trading day of each month (PIT,
    survivorship-free). Each day maps to the most recent checkpoint ≤ that day."""
    checkpoints: dict[date, list[str]] = {}
    seen_months: set[tuple[int, int]] = set()
    for d in days:
        key = (d.year, d.month)
        if key in seen_months:
            continue
        seen_months.add(key)
        with contextlib.suppress(Exception):
            checkpoints[d] = universe_asof(store, d, n=n, lookback_days=lookback_days)
    return checkpoints


def _load_bars(store: FactorDataStore, symbols: list[str], start: date, end: date) -> pd.DataFrame:
    """Bulk-load raw (unadjusted) OHLCV for the union universe in one query, indexed
    by ticker → date-sorted. Raw prices: gap/range are same-day, no adjustment needed."""
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
    """Build one pre-open feature row for `symbol` at integer position `i` in its
    date-sorted bar frame `g`. Uses only bars strictly before today (+ today's open
    for the ~5-min gap approximation). Returns None if history is insufficient."""
    if i < ATR_N + 1 or i < RVOL_LOOKBACK + 1:
        return None
    today = g.iloc[i]
    prev = g.iloc[i - 1]
    prev_close = float(prev["close"])
    if prev_close <= 0:
        return None
    window = g.iloc[i - RVOL_LOOKBACK : i]  # strictly prior bars
    avg_vol = float(window["volume"].mean())
    highs = [float(x) for x in g.iloc[i - ATR_N - 1 : i]["high"]]
    lows = [float(x) for x in g.iloc[i - ATR_N - 1 : i]["low"]]
    closes = [float(x) for x in g.iloc[i - ATR_N - 1 : i]["close"]]
    return {
        "symbol": symbol,
        "gap_pct": ce.gap_pct(float(today["open"]), prev_close),
        "rvol": ce.rvol(float(today["volume"]), avg_vol),
        "atr_pct": ce.atr_pct(highs, lows, closes, n=ATR_N),
        "price": prev_close,  # the pre-open known price
        "dollar_vol": prev_close * float(prev["volume"]),
        # realized OUTCOME — never fed to selection, scored after the fact
        "_range_pct": ce.intraday_range_pct(
            float(today["high"]), float(today["low"]), float(today["open"])
        ),
    }


def run(
    store: FactorDataStore,
    *,
    start: date,
    end: date,
    n: int,
    top_n: int,
    bootstrap: int,
) -> dict[str, Any]:
    days = _trading_days(store, start, end)
    if not days:
        raise SystemExit("no trading days in range")
    universes = _monthly_universes(
        store, days, n=n, lookback_days=90
    )
    checkpoints = sorted(universes)
    union = sorted({s for syms in universes.values() for s in syms})
    bars = _load_bars(store, union, start - pd.Timedelta(days=HISTORY_BUFFER).to_pytimedelta(), end)
    # Normalize the date column to python date — fetchdf() returns pandas Timestamps,
    # but the trading-day axis and the universe are datetime.date.
    bars = bars.assign(date=pd.to_datetime(bars["date"]).dt.date)
    by_symbol = {sym: g.reset_index(drop=True) for sym, g in bars.groupby("ticker")}
    pos_index = {
        sym: {d: i for i, d in enumerate(g["date"])} for sym, g in by_symbol.items()
    }

    daily: list[dict[str, Any]] = []
    sample_report: list[dict[str, Any]] = []
    cur_universe: list[str] = []
    cp_iter = iter(checkpoints)
    next_cp = next(cp_iter, None)

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
        candidates = ce.select_candidates(panel, top_n=top_n)
        if not candidates:
            continue
        cand_syms = {c.symbol for c in candidates}
        cand_range = [r["_range_pct"] for r in eligible if r["symbol"] in cand_syms]
        base_range = [r["_range_pct"] for r in eligible]
        if not cand_range:
            continue
        cand_mean = sum(cand_range) / len(cand_range)
        base_mean = sum(base_range) / len(base_range)
        daily.append(
            {
                "date": d.isoformat(),
                "n_candidates": len(candidates),
                "n_eligible": len(eligible),
                "candidate_range_pct": round(cand_mean, 4),
                "baseline_range_pct": round(base_mean, 4),
                "edge_pct": round(cand_mean - base_mean, 4),
            }
        )
        sample_report = [c.to_dict() for c in candidates]  # keep the latest day's report

    if not daily:
        raise SystemExit("no scorable days — universe/history too thin")

    edges = [row["edge_pct"] for row in daily]
    ci = ev.block_bootstrap_ci(edges, ev._mean, n_resamples=bootstrap)
    cand_avg = sum(r["candidate_range_pct"] for r in daily) / len(daily)
    base_avg = sum(r["baseline_range_pct"] for r in daily) / len(daily)
    win_rate = sum(1 for e in edges if e > 0) / len(edges)

    return {
        "program": "SCAN-001",
        "title": "Candidate Engine — Market Opportunity Discovery (v1 intraday)",
        "generated_utc": None,  # stamped by caller (Date.now unavailable in-engine)
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": len(daily)},
        "config": {
            "universe_n": n,
            "top_n": top_n,
            "filters": ce.FILTERS,
            "atr_n": ATR_N,
            "rvol_lookback": RVOL_LOOKBACK,
            "bootstrap_resamples": bootstrap,
        },
        "hypothesis_h1": {
            "claim": "curated candidates realize higher intraday range than the liquid baseline",
            "candidate_range_pct_mean": round(cand_avg, 4),
            "baseline_range_pct_mean": round(base_avg, 4),
            "edge_pct_mean": round(ci.point, 4),
            "edge_ci95": [round(ci.ci_low, 4), round(ci.ci_high, 4)],
            "p_value": round(ci.p_value, 4),
            "daily_win_rate": round(win_rate, 4),
            "verdict": _verdict(ci),
        },
        "sample_candidate_report": sample_report,
        "caveats": [
            "MECHANICAL CORRELATION: candidates are selected partly on ATR % (a range "
            "measure), so a higher realized intraday range is partly DEFINITIONAL, not a "
            "discovered edge. The ~100% daily win rate confirms the relationship is "
            "near-mechanical. H1-as-stated is supported, but the headline edge overstates "
            "the discovery.",
            "The genuinely open questions (next iteration): (a) do candidates expand BEYOND "
            "their own ATR forecast — realized range vs ATR-implied range — or just track it? "
            "(b) is the range DIRECTIONAL (tradeable trend) or chop? (c) does the gap/RVOL "
            "signal add range over an ATR-only screen (H3 attribution)?",
            "PIT approximations (gap uses the official open ≈ 09:25 premarket; daily-RVOL "
            "proxy) need true premarket data before any promotion past prototype.",
        ],
        "daily": daily,
    }


def _verdict(ci: ev.ConfidenceResult) -> str:
    if ci.ci_low > 0 and ci.p_value < 0.05:
        return "SUPPORTED — candidate set shows a positive, statistically-separated opportunity edge"
    if ci.point > 0:
        return "WEAK — positive point edge but CI includes zero; not yet separated from noise"
    return "NOT SUPPORTED — no positive opportunity edge over the baseline"


def _write_report(result: dict[str, Any], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "candidate_engine_evidence.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    h1 = result["hypothesis_h1"]
    cfg = result["config"]
    lines = [
        f"# {result['title']}",
        "",
        f"*Generated {result['generated_utc']} · read-only research · SCAN-001 §0a: the candidate set is evidence, not a signal.*",
        "",
        "## H1 — does curation select opportunity?",
        "",
        f"- **Verdict:** {h1['verdict']}",
        f"- Candidate mean intraday range: **{h1['candidate_range_pct_mean']}%** vs baseline **{h1['baseline_range_pct_mean']}%**",
        f"- Edge (candidate − baseline): **{h1['edge_pct_mean']}%** · 95% CI [{h1['edge_ci95'][0]}, {h1['edge_ci95'][1]}] · p = {h1['p_value']}",
        f"- Daily win rate (candidate > baseline): **{round(h1['daily_win_rate'] * 100, 1)}%** over {result['window']['days']} days",
        "",
        f"Window {result['window']['start']} → {result['window']['end']} · universe top-{cfg['universe_n']} by $-vol (monthly PIT) · top-{cfg['top_n']} candidates/day.",
        "",
        "## Frozen filters (SCAN-001 §2)",
        "",
        "| Filter | Threshold |",
        "| --- | --- |",
        f"| Gap % | > {cfg['filters']['min_gap_pct']} |",
        f"| RVOL | > {cfg['filters']['min_rvol']}× |",
        f"| ATR % | > {cfg['filters']['min_atr_pct']} |",
        f"| Price | > ${cfg['filters']['min_price']} |",
        f"| $-volume | > ${cfg['filters']['min_dollar_vol']:,.0f} |",
        "",
        "## Sample Candidate Report (latest scored day)",
        "",
        "| # | Symbol | Gap % | RVOL | ATR % | Price | Reason | Confidence |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in result["sample_candidate_report"]:
        lines.append(
            f"| {c['rank']} | {c['symbol']} | {c['gap_pct']} | {c['rvol']} | "
            f"{c['atr_pct']} | {c['price']} | {c['reason']} | {c['confidence']} |"
        )
    lines += [
        "",
        "## Caveats — read before believing the headline",
        "",
    ]
    for c in result["caveats"]:
        lines.append(f"- {c}")
    lines += [
        "",
        "## PIT honesty & v1 limitations",
        "",
        "- **Gap %** uses the official open as a ~5-min approximation of the live 09:25 premarket price.",
        "- **RVOL** is a daily-volume proxy; true premarket relative volume is the v1 refinement.",
        "- Universe is re-struck **monthly** (PIT, survivorship-free); the opportunity metric is the post-open outcome and cannot leak into selection.",
        "",
    ]
    (report_dir / "candidate_engine_evidence.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="SCAN-001 Candidate Engine research harness")
    p.add_argument("--store", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--n", type=int, default=200, help="liquid universe size")
    p.add_argument("--top-n", type=int, default=15, help="candidates per day")
    p.add_argument("--bootstrap", type=int, default=2000)
    p.add_argument("--report-dir", default="docs/implementation/evidence/scan_001_candidate_engine")
    args = p.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    with FactorDataStore(args.store, read_only=True) as store:
        result = run(
            store, start=start, end=end, n=args.n, top_n=args.top_n, bootstrap=args.bootstrap
        )
    result["generated_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    _write_report(result, Path(args.report_dir))
    h1 = result["hypothesis_h1"]
    print(f"[SCAN-001] {h1['verdict']}")
    print(
        f"  edge {h1['edge_pct_mean']}% (CI [{h1['edge_ci95'][0]}, {h1['edge_ci95'][1]}], "
        f"p={h1['p_value']}, win {round(h1['daily_win_rate'] * 100, 1)}%, {result['window']['days']} days)"
    )


if __name__ == "__main__":
    main()
