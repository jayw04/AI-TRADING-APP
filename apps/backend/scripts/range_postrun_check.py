"""Range auto-select Post-Run check (first live fire, Mon 2026-06-29).

Read-only. Confirms the daily Opportunity Assignment fired pre-open and assigned today's
Opportunity Set to the Range sleeve (strategy #1), and seeds the §11.8 Post-Run Report.

Looks for the morning's ``STRATEGY_UPDATED`` audit row (actor SYSTEM, payload
``source = daily_preopen_auto_select``) for the target strategy and reports the assigned
symbols + selection evidence (qualified/universe sizes, ranking version, exclusions). Writes
a timestamped markdown report and prints a one-line verdict.

Usage:
    python scripts/range_postrun_check.py [--db PATH] [--strategy-id N] [--out DIR]

Designed to be driven by a Windows scheduled task at ~09:15 ET; safe to re-run any time
(e.g. end of day) to refresh the report.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
_HERE = Path(__file__).resolve()
_DEFAULT_DB = _HERE.parents[3] / "data" / "workbench.sqlite"
_DEFAULT_OUT = _HERE.parents[3] / "Docs" / "implementation" / "evidence"
AUTOSELECT_SOURCE = "daily_preopen_auto_select"


def _latest_assignment(conn: sqlite3.Connection, strategy_id: int) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, ts, actor_type, payload_json FROM audit_log "
        "WHERE action = 'STRATEGY_UPDATED' AND target_id = ? "
        "ORDER BY id DESC LIMIT 50",
        (str(strategy_id),),
    ).fetchall()
    for r in rows:
        try:
            p = json.loads(r["payload_json"] or "{}")
        except json.JSONDecodeError:
            continue
        if p.get("source") == AUTOSELECT_SOURCE:
            return r
    return None


def _current_symbols(conn: sqlite3.Connection, strategy_id: int) -> list[str]:
    row = conn.execute(
        "SELECT symbols_json FROM strategies WHERE id = ?", (strategy_id,)
    ).fetchone()
    if not row or not row[0]:
        return []
    try:
        return list(json.loads(row[0]))
    except json.JSONDecodeError:
        return []


def build_report(db: Path, strategy_id: int) -> tuple[str, bool]:
    now_et = datetime.now(ET)
    today = now_et.date()
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = _latest_assignment(conn, strategy_id)
        symbols_now = _current_symbols(conn, strategy_id)
    finally:
        conn.close()

    lines = [
        f"# Range Post-Run Report — strategy #{strategy_id}",
        "",
        f"- **Generated:** {now_et.isoformat()} ({today} ET)",
        f"- **DB:** `{db}`",
        f"- **Current symbols_json:** `{symbols_now}`",
        "",
    ]

    fired_today = False
    if row is None:
        lines += [
            "## ⚠️ No auto-select assignment found",
            "",
            "No `STRATEGY_UPDATED` audit row with `source=daily_preopen_auto_select` exists for "
            "this strategy. The job may not have fired (stack down at 09:00 ET?), been skipped "
            "(LIVE / after-open / open position / pending order), or yielded no candidates.",
            "",
            "Next: `docker compose logs backend | grep range_autoselect` for "
            "`range_autoselect_applied` or a `skipped_*` / `no_candidates` reason.",
        ]
    else:
        payload = json.loads(row["payload_json"] or "{}")
        ts = row["ts"]
        fired_today = str(ts).startswith(str(today))  # ts is UTC; same calendar day in summer
        sel = payload.get("selection", {})
        chosen = payload.get("changed", {}).get("symbols", [])
        mark = "✅" if fired_today else "ℹ️ (not today — most recent prior fire)"
        lines += [
            f"## {mark} Assignment fired",
            "",
            f"- **Audit row:** id={row['id']}  ts={ts}  actor={row['actor_type']}",
            f"- **Opportunity Set (assigned):** `{chosen}`",
            f"- **Previous symbols:** `{payload.get('previous')}`",
            f"- **N requested:** {sel.get('n_requested')}  "
            f"min_score={sel.get('min_score')}  ranking={sel.get('ranking_version')}",
            f"- **Universe / qualified sizes:** {sel.get('universe_size')} / "
            f"{sel.get('qualified_size')}",
            "",
            "### Selected (rank · score · win · backtested)",
        ]
        for s in sel.get("selected", []):
            lines.append(
                f"- {s.get('rank')}. **{s.get('symbol')}** "
                f"score={s.get('score')} win={s.get('win_rate')} "
                f"sharpe={s.get('sharpe')} backtested={s.get('backtested')}"
            )
        excluded = sel.get("excluded", [])
        if excluded:
            lines += ["", "### Excluded (symbol → reason)"]
            lines += [f"- {e.get('symbol')} → {e.get('reason')}" for e in excluded]

    lines += [
        "",
        "---",
        "### Post-Run Report checklist (fill in across the session/week)",
        "- [x] Did the Assignment fire at 09:00 ET? (above)",
        "- [x] How many qualified? / the frozen Opportunity Set (above)",
        "- [ ] How many symbols triggered entries? (Orders → Today)",
        "- [ ] Selection Precision = entered / selected",
        "- [ ] Opportunity Conversion funnel: Qualified→Selected→Triggered→Filled→Exited",
        "- [ ] Any scheduler / risk-engine / execution anomalies?",
        "",
        "_See `Docs/review/RangeStrategy_Implementation_Review_v1.2.md` §11.8 / §16._",
    ]
    return "\n".join(lines) + "\n", fired_today


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=_DEFAULT_DB)
    ap.add_argument("--strategy-id", type=int, default=1)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if not args.db.exists():
        print(f"ERROR: DB not found: {args.db}", file=sys.stderr)
        return 2

    report, fired = build_report(args.db, args.strategy_id)
    now_et = datetime.now(ET)
    out_dir = args.out or (_DEFAULT_OUT / f"range_postrun_{now_et:%Y-%m-%d}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"postrun_{now_et:%H%M}_ET.md"
    out_file.write_text(report, encoding="utf-8")

    verdict = "FIRED" if fired else "NO ASSIGNMENT TODAY"
    print(f"[range_postrun_check] {verdict}  ->  {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
