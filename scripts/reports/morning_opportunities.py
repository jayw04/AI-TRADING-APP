#!/usr/bin/env python3
"""GAPPER-001 — Morning Opportunities Candidate Report.

Renders the day's SCAN-001 premarket candidates (the *validated* Candidate Engine's Gap/RVOL/ATR +
Discovery Confidence output) as a lightweight, user-facing watchlist. Reads the already-persisted
premarket-gate evidence records (``premarket_scan_<date>.json``) — no store, no network, no order path.

This is the sprint's user-visible GAPPER-001 artifact WHILE the strategy accrues evidence: GAPPER-001
has NO verdict yet (its minimum-sample gate needs >=40 trading days of gappers; see the pre-registration),
so every row is labelled **Backtest Pending** under the ADR-0037 whitelist — this is a *watchlist*, not a
buy/sell signal. The "entry trigger" column names the pre-registered rule being studied; it is never an
instruction to the reader.

Usage:
  python morning_opportunities.py --evidence-dir /app/data/premarket_gate_evidence            # latest day
  python morning_opportunities.py --evidence-dir <dir> --date 2026-07-08                       # a given day
  python morning_opportunities.py --evidence-dir <dir> --accrual                               # accrual only
"""
from __future__ import annotations

import argparse
import glob
import json
import os

# ADR-0037 label whitelist — the ONLY vocabulary allowed on this report.
LABEL = "Backtest Pending"  # GAPPER-001 is pre-registered but not validated → Backtest Pending
ENTRY_TRIGGER = "30-min OR-high break (studied)"  # the pre-registered rule, described — not an instruction
SAMPLE_GATE_DATES = 40  # GAPPER-001 minimum-sample gate: >=40 distinct dates


def _fmt(v, kind="num"):
    if v is None:
        return "—"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    if kind == "pct":
        return f"{x:.1f}%"
    if kind == "money":
        return f"${x:,.2f}"
    if kind == "dvol":
        return f"${x/1e6:,.1f}M"
    if kind == "conf":
        return f"{x:.2f}"
    return f"{x:,.2f}"


def _records(directory: str) -> list[str]:
    return sorted(glob.glob(os.path.join(directory, "premarket_scan_*.json")))


def render(record: dict, *, accrued_dates: int) -> str:
    f = record.get("funnel", {})
    cands = record.get("candidates", []) or []
    lines: list[str] = []
    lines.append(f"# Morning Opportunities — Candidate Report ({record.get('asof', '?')})")
    lines.append("")
    lines.append(
        f"*Source gappers: {record.get('source_date') or '—'} · scanned {record.get('scanned_at') or '—'}"
        f"{' · STALE' if record.get('stale') else ''}*"
    )
    lines.append("")
    lines.append(
        f"**Funnel:** {f.get('gappers_in', 0)} gappers → {f.get('store_covered', 0)} store-covered → "
        f"{f.get('eligible_count', 0)} engine-eligible → **{f.get('candidate_count', 0)} candidates**"
    )
    lines.append("")
    if not cands:
        lines.append("_No candidates today (no fresh gappers, or none cleared the engine's gates)._")
    else:
        lines.append("| Ticker | Gap % | RVOL | ATR % | Discovery Conf. | Price | $ Vol (20d) | "
                     "Entry trigger | VWAP | Label |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---|---|---|")
        for c in cands:
            lines.append(
                f"| **{c.get('symbol', '?')}** "
                f"| {_fmt(c.get('gap_pct'), 'pct')} "
                f"| {_fmt(c.get('rvol'))}× "
                f"| {_fmt(c.get('atr_pct'), 'pct')} "
                f"| {_fmt(c.get('confidence'), 'conf')} "
                f"| {_fmt(c.get('price'), 'money')} "
                f"| {_fmt(c.get('dollar_vol'), 'dvol')} "
                f"| {ENTRY_TRIGGER} "
                f"| pending (intraday) "
                f"| {LABEL} |"
            )
    lines.append("")
    lines.append("---")
    lines.append(
        f"**Status:** GAPPER-001 is under evaluation — **{accrued_dates}/{SAMPLE_GATE_DATES}** trading "
        f"days of gappers accrued toward the minimum-sample gate; no verdict yet. "
    )
    lines.append(
        "_Advisory watchlist only. Candidates are **evidence, not a signal** (SCAN-001 §0a) and never "
        "reach the order path. Labels follow the ADR-0037 whitelist; the entry-trigger column names the "
        "pre-registered rule under study, not an instruction to trade. RVOL is a premarket-vs-daily "
        "proxy; the gappers universe differs from the validated liquid universe._"
    )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="GAPPER-001 Morning Opportunities Candidate Report")
    ap.add_argument("--evidence-dir", default="data/premarket_gate_evidence")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: latest available)")
    ap.add_argument("--accrual", action="store_true", help="print only the accrual count")
    args = ap.parse_args()

    files = _records(args.evidence_dir)
    accrued = len(files)
    if args.accrual:
        print(f"GAPPER-001 accrual: {accrued}/{SAMPLE_GATE_DATES} trading days of gappers evidence "
              f"({'GATE MET' if accrued >= SAMPLE_GATE_DATES else 'accruing'})")
        return
    if not files:
        print(f"No evidence records in {args.evidence_dir!r} yet.")
        return
    path = (os.path.join(args.evidence_dir, f"premarket_scan_{args.date}.json")
            if args.date else files[-1])
    if not os.path.exists(path):
        print(f"No record for {args.date} in {args.evidence_dir!r}.")
        return
    with open(path, encoding="utf-8") as fh:
        record = json.load(fh)
    print(render(record, accrued_dates=accrued))


if __name__ == "__main__":
    main()
