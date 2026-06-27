"""Range auto-select calibration report: Range-Score band -> realized outcomes (read-only).

The input the empirical `auto_select_min_score` threshold will read after >=40 trading days
(ADR 0028 / RangeStrategy_Implementation_Review v1.2 SS11.3/SS16). Joins each daily
Opportunity-Set selection (audit log `STRATEGY_UPDATED`, `source=daily_preopen_auto_select`,
carrying per-symbol `score`) to the realized outcomes that selection produced (orders/fills/
signals), then aggregates **per Range-Score band**:

    selections | trigger rate (OR-touch proxy) | fills | exits | win rate | avg P&L | P&L Sharpe

Plus the two v1.2 metrics: **Selection Precision** (selected -> entered) and the **Opportunity
Conversion funnel** (Qualified -> Selected -> Triggered -> Filled -> Exited).

Read-only, stdlib-only, ASCII stdout (cp1252-safe). No order path. Safe to run any time and
**before any data has accrued** (the first auto-select fire is Mon 2026-06-29) -- it then reports
"no selections yet" and the structure that will fill in. Run it weekly (the rolling report).

    apps/backend/.venv/Scripts/python.exe apps/backend/scripts/range_calibration_report.py \
        --db data/workbench.sqlite --strategy-id 1
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AUTOSELECT_SOURCE = "daily_preopen_auto_select"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DB = _REPO_ROOT / "data" / "workbench.sqlite"
_DEFAULT_OUT = _REPO_ROOT / "Docs" / "implementation" / "evidence" / "range_calibration"
DEFAULT_BANDS = [0.0, 0.02, 0.04, 0.06, 0.08, 0.10]  # last band is [0.10, inf)
_QTY_FLAT_EPS = 1e-6  # net qty within this of 0 => the symbol-day round-tripped (exited flat)


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def _band_index(score: float, edges: list[float]) -> int:
    """Index of the half-open band [edges[i], edges[i+1]) the score falls in; the final band
    is [edges[-1], inf)."""
    for i in range(len(edges) - 1):
        if edges[i] <= score < edges[i + 1]:
            return i
    return len(edges) - 1  # >= last edge


def _band_label(i: int, edges: list[float]) -> str:
    if i == len(edges) - 1:
        return f">={edges[-1]:.2f}"
    return f"{edges[i]:.2f}-{edges[i + 1]:.2f}"


def gather(con: sqlite3.Connection, strategy_id: int) -> dict[str, Any]:
    """Pull selections (audit) + realized outcomes (orders/fills/signals), keyed by (day, ticker)."""
    con.row_factory = sqlite3.Row

    # --- selections: one record per (day, symbol) from each pre-open assignment ---
    selections: list[dict[str, Any]] = []
    per_day_meta: dict[str, dict[str, Any]] = {}
    rows = con.execute(
        "SELECT id, ts, payload_json FROM audit_log "
        "WHERE action='STRATEGY_UPDATED' AND target_id=? ORDER BY id",
        (str(strategy_id),),
    ).fetchall()
    for r in rows:
        try:
            payload = json.loads(r["payload_json"] or "{}")
        except json.JSONDecodeError:
            continue
        if payload.get("source") != AUTOSELECT_SOURCE:
            continue
        sel = payload.get("selection") or {}
        day = str(r["ts"])[:10]  # UTC date == ET trading day for RTH range trades
        per_day_meta[day] = {
            "universe_size": sel.get("universe_size"),
            "qualified_size": sel.get("qualified_size"),
            "n_requested": sel.get("n_requested"),
            "min_score": sel.get("min_score"),
            "opportunity_set_id": sel.get("opportunity_set_id"),
            "symbols": payload.get("changed", {}).get("symbols", []),
        }
        for s in sel.get("selected", []):
            if s.get("score") is None:
                continue
            selections.append({
                "day": day, "symbol": str(s["symbol"]).upper(),
                "score": float(s["score"]), "rank": s.get("rank"),
                "win_rate": s.get("win_rate"), "backtested": s.get("backtested"),
            })

    # --- realized P&L + net qty per (ticker, day) from fills (round-trip = exited flat) ---
    pnl: dict[tuple[str, str], dict[str, float]] = {}
    for r in con.execute(
        "SELECT s.ticker AS ticker, date(f.filled_at) AS d, "
        "  SUM(CASE WHEN o.side='SELL' THEN f.qty*f.price ELSE -f.qty*f.price END) "
        "    - COALESCE(SUM(f.commission),0) AS pnl, "
        "  SUM(CASE WHEN o.side='BUY' THEN f.qty ELSE -f.qty END) AS net_qty, "
        "  COUNT(DISTINCT o.id) AS n_orders "
        "FROM fills f JOIN orders o ON o.id=f.order_id JOIN symbols s ON s.id=o.symbol_id "
        "WHERE o.source_type='STRATEGY' AND o.source_id=? "
        "GROUP BY s.ticker, date(f.filled_at)",
        (str(strategy_id),),
    ).fetchall():
        pnl[(r["d"], str(r["ticker"]).upper())] = {
            "pnl": float(r["pnl"] or 0.0), "net_qty": float(r["net_qty"] or 0.0),
            "n_orders": int(r["n_orders"] or 0),
        }

    # --- triggers (ENTRY signals) per (ticker, day): the entry zone / OR was reached ---
    triggered: set[tuple[str, str]] = set()
    for r in con.execute(
        "SELECT s.ticker AS ticker, date(sig.received_at) AS d "
        "FROM signals sig JOIN symbols s ON s.id=sig.symbol_id "
        "WHERE sig.strategy_id=? AND sig.type='ENTRY' "
        "GROUP BY s.ticker, date(sig.received_at)",
        (strategy_id,),
    ).fetchall():
        triggered.add((r["d"], str(r["ticker"]).upper()))

    return {"selections": selections, "per_day_meta": per_day_meta,
            "pnl": pnl, "triggered": triggered}


def aggregate(data: dict[str, Any], edges: list[float]) -> dict[str, Any]:
    sels = data["selections"]
    pnl, triggered = data["pnl"], data["triggered"]

    bands: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "triggered": 0, "filled": 0, "exited": 0, "wins": 0, "pnls": []}
    )
    funnel = {"selected": 0, "triggered": 0, "filled": 0, "exited": 0}

    for s in sels:
        key = (s["day"], s["symbol"])
        bi = _band_index(s["score"], edges)
        b = bands[bi]
        b["n"] += 1
        funnel["selected"] += 1
        if key in triggered:
            b["triggered"] += 1
            funnel["triggered"] += 1
        cell = pnl.get(key)
        if cell:
            b["filled"] += 1
            funnel["filled"] += 1
            if abs(cell["net_qty"]) <= _QTY_FLAT_EPS:  # round-tripped flat => realized P&L
                b["exited"] += 1
                funnel["exited"] += 1
                b["pnls"].append(cell["pnl"])
                if cell["pnl"] > 0:
                    b["wins"] += 1

    band_rows = []
    for bi in sorted(bands):
        b = bands[bi]
        pnls = b["pnls"]
        band_rows.append({
            "band": _band_label(bi, edges),
            "n_selected": b["n"],
            "trigger_rate": (b["triggered"] / b["n"]) if b["n"] else None,
            "n_filled": b["filled"],
            "n_exited": b["exited"],
            "win_rate": (b["wins"] / b["exited"]) if b["exited"] else None,
            "avg_pnl": (statistics.fmean(pnls)) if pnls else None,
            "pnl_sharpe": (statistics.fmean(pnls) / statistics.pstdev(pnls))
                          if len(pnls) >= 2 and statistics.pstdev(pnls) > 0 else None,
        })

    # qualified total across days (per-day qualified-universe sizes)
    qualified_total = sum(
        (m.get("qualified_size") or 0) for m in data["per_day_meta"].values()
    )
    days = sorted(data["per_day_meta"])
    return {
        "bands": band_rows,
        "funnel": {"qualified": qualified_total, **funnel},
        "selection_precision": (funnel["triggered"] / funnel["selected"]) if funnel["selected"] else None,
        "n_days": len(days), "first_day": days[0] if days else None,
        "last_day": days[-1] if days else None,
        "n_selections": len(sels),
    }


def _pct(x: float | None) -> str:
    return f"{x:.0%}" if x is not None else "n/a"


def render(agg: dict[str, Any], strategy_id: int, db: str, edges: list[float]) -> str:
    f = agg["funnel"]
    lines = [
        f"# Range Calibration Report -- strategy #{strategy_id} (score band -> outcomes)",
        "",
        f"_Generated {datetime.now(UTC).isoformat()} - git {_git_sha()} - read-only_",
        f"- **DB:** `{db}`",
        f"- **Window:** {agg['first_day'] or '-'} .. {agg['last_day'] or '-'} "
        f"({agg['n_days']} day(s), {agg['n_selections']} symbol-day selection(s))",
        f"- **Score bands (edges):** {edges} (final band is open-ended)",
        "",
    ]

    if agg["n_selections"] == 0:
        lines += [
            "## No selections have accrued yet",
            "",
            "No `daily_preopen_auto_select` assignment exists in the audit log for this strategy "
            "yet (the first live fire is **Mon 2026-06-29 09:00 ET**). This report populates as the "
            "daily auto-select runs; the per-band table and the conversion funnel below will fill in.",
            "",
            "Re-run it weekly (the rolling report, v1.2 SS11.3); the empirical `auto_select_min_score` "
            "threshold reads it after >=40 trading days (ADR 0028 SS15).",
            "",
        ]

    lines += [
        "## Score band -> realized outcomes",
        "",
        "| Score band | Selected | Trigger rate | Fills | Exits | Win rate | Avg P&L | P&L Sharpe |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for b in agg["bands"]:
        avg = f"${b['avg_pnl']:,.2f}" if b["avg_pnl"] is not None else "n/a"
        sharpe = f"{b['pnl_sharpe']:.2f}" if b["pnl_sharpe"] is not None else "n/a"
        lines.append(
            f"| {b['band']} | {b['n_selected']} | {_pct(b['trigger_rate'])} | {b['n_filled']} | "
            f"{b['n_exited']} | {_pct(b['win_rate'])} | {avg} | {sharpe} |"
        )
    if not agg["bands"]:
        lines.append("| _(none yet)_ | | | | | | | |")

    lines += [
        "",
        "- **Trigger rate** = selections that produced an ENTRY signal / selections "
        "(the opening-range / entry-zone touch proxy, owner's 'OR-touch rate').",
        "- **Win rate / Avg P&L / P&L Sharpe** are over *exited* (round-tripped flat) symbol-days; "
        "P&L is realized intraday net cash. P&L Sharpe = mean/stdev of per-symbol-day P&L (>=2 exits).",
        "",
        "## Selection Precision",
        "",
        f"- **{_pct(agg['selection_precision'])}** of selected symbol-days produced an entry "
        f"({f['triggered']} triggered / {f['selected']} selected). Lets the Ranking Engine improve "
        "without touching the strategy (v1.2 SS16).",
        "",
        "## Opportunity Conversion funnel",
        "",
        "| Qualified | -> Selected | -> Triggered | -> Filled | -> Exited |",
        "|---|---|---|---|---|",
        f"| {f['qualified']} | {f['selected']} | {f['triggered']} | {f['filled']} | {f['exited']} |",
        "",
        "_Qualified = sum of the daily qualified-universe sizes; the rest are symbol-day counts across "
        "the window. Each drop-off points at a different lever (qualification too tight / ranking picking "
        "non-triggering names / entries too strict / exits failing)._",
        "",
        "---",
        "_Read-only/advisory; no order path. See `Docs/review/RangeStrategy_Implementation_Review_v1.2.md` "
        "SS11.3/SS16 and ADR 0028. The empirical `auto_select_min_score` is derived from this after "
        ">=40 trading days -- it is a research result, not an assumption._",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Range auto-select calibration report (read-only)")
    ap.add_argument("--db", default=str(_DEFAULT_DB))
    ap.add_argument("--strategy-id", type=int, default=1)
    ap.add_argument("--bands", default=None,
                    help="Comma-separated band edges, e.g. '0,0.02,0.04,0.06,0.08,0.10'.")
    ap.add_argument("--out", type=Path, default=None,
                    help=f"Output dir (default {_DEFAULT_OUT}). A dated .md is written there.")
    ap.add_argument("--no-file", action="store_true", help="Print only; do not write a file.")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}")
        return 2
    edges = ([float(x) for x in args.bands.split(",")] if args.bands else list(DEFAULT_BANDS))

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        data = gather(con, args.strategy_id)
    finally:
        con.close()
    agg = aggregate(data, edges)
    report = render(agg, args.strategy_id, str(db_path), edges)

    if not args.no_file:
        out_dir = args.out or _DEFAULT_OUT
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "range_calibration.md"  # canonical (stable name); wrapper archives dated copies
        out_file.write_text(report, encoding="utf-8")
        print(f"[range-calibration] wrote {out_file}")

    p = agg["selection_precision"]
    print(f"[range-calibration] days={agg['n_days']} selections={agg['n_selections']} "
          f"selection_precision={(f'{p:.0%}' if p is not None else 'n/a')} "
          f"funnel={agg['funnel']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
