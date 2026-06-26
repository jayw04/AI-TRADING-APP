"""P13.5 — Operational KPI scorecard from the live paper book (read-only).

Reads the durable audit/ops tables and renders the customer-facing operational KPIs
(``app.ops.kpis``): reconciliation success + drift, replay consistency, risk-gate efficacy,
circuit-breaker recovery, fill success, operational continuity. The complement to the P11
operator-facing Prometheus/Grafana dashboard (runtime) — this is the allocator-readable rollup.

> Read-only. ASCII-only stdout (cp1252-safe). No order path; queries the SQLite DB read-only.

    apps/backend/.venv/Scripts/python.exe apps/backend/scripts/ops_kpis.py \
        --db data/workbench.sqlite --report-dir docs/implementation/evidence/p12_5_live/kpis
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.ops.kpis import KpiInputs, build_scorecard, scorecard_summary  # noqa: E402


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def _scalar(con: sqlite3.Connection, sql: str, params: tuple = ()) -> Any:
    try:
        row = con.execute(sql, params).fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def _breaker_recovery_minutes(con: sqlite3.Connection) -> tuple[float | None, int, int]:
    """Mean trip→reset minutes (pairing each trip with the next reset), + trip/reset counts."""
    def ts_list(action: str) -> list[datetime]:
        try:
            rows = con.execute(
                "SELECT ts FROM audit_log WHERE action=? ORDER BY ts", (action,)).fetchall()
        except sqlite3.OperationalError:
            return []
        out = []
        for (t,) in rows:
            try:
                out.append(datetime.fromisoformat(t.replace(" ", "T")))
            except (ValueError, AttributeError):
                continue
        return out
    trips, resets = ts_list("CIRCUIT_BREAKER_TRIPPED"), ts_list("CIRCUIT_BREAKER_RESET")
    deltas: list[float] = []
    ri = 0
    for trip in trips:
        while ri < len(resets) and resets[ri] < trip:
            ri += 1
        if ri < len(resets):
            deltas.append((resets[ri] - trip).total_seconds() / 60.0)
            ri += 1
    mean = round(sum(deltas) / len(deltas), 1) if deltas else None
    return mean, len(trips), len(resets)


def build(db: str) -> dict[str, Any]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        a = {act: n for act, n in con.execute("SELECT action, COUNT(*) FROM audit_log GROUP BY action")}
        recon_runs = _scalar(con, "SELECT COUNT(*) FROM reconciliation_runs") or 0
        recon_pass = _scalar(con, "SELECT COUNT(*) FROM reconciliation_runs WHERE result='pass'") or 0
        recon_disc = _scalar(con, "SELECT COALESCE(SUM(n_discrepancies),0) FROM reconciliation_runs") or 0
        replay_checked = _scalar(con, "SELECT COALESCE(SUM(n_checked),0) FROM replay_runs") or 0
        replay_matched = _scalar(con, "SELECT COALESCE(SUM(n_matched),0) FROM replay_runs") or 0
        recovery_min, trips, resets = _breaker_recovery_minutes(con)
        actual_days = _scalar(con, "SELECT COUNT(DISTINCT date(ts)) FROM equity_snapshots") or 0
        first_day = _scalar(con, "SELECT MIN(date(ts)) FROM equity_snapshots")
    finally:
        con.close()

    expected_days = 0
    if first_day:
        # rough trading-day count since the book started (≈ 5/7 of calendar days)
        span = (datetime.now(UTC).date() - date.fromisoformat(first_day)).days + 1
        expected_days = max(actual_days, round(span * 5 / 7))

    inputs = KpiInputs(
        reconciliation_runs=int(recon_runs), reconciliation_passes=int(recon_pass),
        reconciliation_discrepancies=int(recon_disc) + a.get("RECONCILIATION_DISCREPANCY", 0),
        replay_checked=int(replay_checked), replay_matched=int(replay_matched),
        orders_risk_passed=a.get("ORDER_RISK_PASSED", 0),
        orders_rejected_by_risk=a.get("ORDER_REJECTED_BY_RISK", 0),
        orders_rejected_by_broker=a.get("ORDER_REJECTED_BY_BROKER", 0),
        breaker_trips=trips or a.get("CIRCUIT_BREAKER_TRIPPED", 0),
        breaker_resets=resets or a.get("CIRCUIT_BREAKER_RESET", 0),
        breaker_recovery_minutes=recovery_min,
        orders_submitted=a.get("ORDER_SUBMITTED", 0), fills_ingested=a.get("ORDER_FILL_INGESTED", 0),
        expected_snapshot_days=int(expected_days), actual_snapshot_days=int(actual_days),
    )
    rows = build_scorecard(inputs)
    return {
        "generated_at": datetime.now(UTC).isoformat(), "git_sha": _git_sha(), "db": db,
        "kpis": rows, "summary": scorecard_summary(rows),
        "latency_note": "Execution/broker latency is not durably recorded — omitted rather than "
                        "estimated (an instrumentation follow-on).",
    }


def _render(r: dict[str, Any]) -> str:
    s = r["summary"]
    lines = [
        "# Operational KPI Scorecard",
        "",
        f"_Generated {r['generated_at']} · git {r['git_sha']} · live paper book (read-only)_",
        "",
        "> The customer-facing operational metrics — the durable complement to the P11 operator "
        "Prometheus/Grafana dashboard. Status **ok** / **watch** (reported, not alerting).",
        "",
        f"**{s['ok']} ok · {s.get('watch', 0)} watch · {s.get('n_a', 0)} n/a**",
        "",
        "| KPI | Value | Target | Status | Detail |",
        "|---|---|---|---|---|",
    ]
    for k in r["kpis"]:
        val = "n/a" if k["value"] is None else (
            f"{k['value']:.1f}{k['unit']}" if k["unit"] == "%" else f"{k['value']} {k['unit']}")
        tgt = f"{k['target']}{'%' if k['unit'] == '%' else ''}"
        mark = {"ok": "ok", "watch": "WATCH", "n_a": "n/a"}[k["status"]]
        lines.append(f"| {k['label']} | {val} | {tgt} | {mark} | {k['note']} |")
    lines += ["", f"_{r['latency_note']}_", "",
              "_Run weekly; the KPIs strengthen as the clean operating record lengthens._"]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="P13.5 operational KPI scorecard")
    ap.add_argument("--db", default="data/workbench.sqlite")
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    r = build(args.db)
    s = r["summary"]
    print(f"[ops-kpis] {s['ok']} ok | {s.get('watch', 0)} watch | {s.get('n_a', 0)} n/a")
    for k in r["kpis"]:
        val = "n/a" if k["value"] is None else f"{k['value']}{k['unit'] if k['unit'] == '%' else ''}"
        print(f"  [{k['status']:>5}] {k['label']}: {val}")

    if args.report_dir:
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "ops_kpis.json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
        (d / "ops_kpis.md").write_text(_render(r), encoding="utf-8")
        print(f"  wrote {d / 'ops_kpis.json'} + ops_kpis.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
