"""P12.5 — Monthly evidence report (institutional cadence, read-only).

Aggregates one calendar month of the live paper book into an institutional report — the monthly
complement to the weekly ``live_evidence.py`` snapshot. Sections: performance, risk, operations,
incidents, recovery, replay, reconciliation, changes, lessons learned.

> Read-only. ASCII-only stdout (cp1252-safe). No order path; queries the SQLite DB read-only.

    apps/backend/.venv/Scripts/python.exe apps/backend/scripts/monthly_evidence.py \
        --db data/workbench.sqlite --strategy-id 2 --month 2026-06 \
        --report-dir docs/implementation/evidence/p12_5_live/monthly

Performance comes from the ``equity_snapshots`` time series filtered to the month (accrues daily);
the operational/safety/verifiability trail comes from ``audit_log`` + ``reconciliation_runs`` +
``replay_runs``. A risk-engine *rejection* is a success signal (the gate worked), NOT an incident.
"""

from __future__ import annotations

import argparse
import calendar
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

from app.factor_data import evidence as ev  # noqa: E402  (reuse the §1 curve metrics)

# audit actions that represent a real operational problem (a risk *rejection* is NOT here — that is
# the gate doing its job, reported under Risk).
INCIDENT_ACTIONS = {
    "CIRCUIT_BREAKER_TRIPPED": ("breaker", "high"),
    "ORDER_REJECTED_BY_BROKER": ("broker_reject", "medium"),
    "REPLAY_MISMATCH": ("replay_mismatch", "critical"),
    "RECONCILIATION_DISCREPANCY": ("reconciliation", "high"),
}
# Meaningful configuration / lifecycle changes worth listing individually. STRATEGY_REGISTERED /
# _UNREGISTERED are deliberately excluded — they fire on every backend boot (resume-on-boot churn),
# so they are summarized as a count under Operations instead of flooding the Changes table.
CHANGE_ACTIONS = (
    "STRATEGY_UPDATED",
    "STRATEGY_DEACTIVATED",
    "STRATEGY_PROPOSAL_TRANSITIONED",
)


def _fmt_target(e: dict[str, Any]) -> str:
    return f"{e.get('target_type') or ''}:{e.get('target_id') or ''}".strip(":")


def _month_bounds(month: str) -> tuple[str, str]:
    """('YYYY-MM') -> ('YYYY-MM-01', 'YYYY-MM-<last>') ISO date strings (inclusive)."""
    year, mon = (int(p) for p in month.split("-"))
    last = calendar.monthrange(year, mon)[1]
    return f"{year:04d}-{mon:02d}-01", f"{year:04d}-{mon:02d}-{last:02d}"


def _rows(con: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def _equity_curve(con: sqlite3.Connection, start: str, end: str) -> list[tuple[date, float]]:
    """Daily equity curve within [start, end] (last snapshot per calendar day). Empty if the table
    is absent (pre-first-snapshot)."""
    try:
        rows = con.execute(
            "SELECT date(ts) AS d, equity FROM equity_snapshots "
            "WHERE date(ts) BETWEEN ? AND ? ORDER BY ts",
            (start, end),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    by_day: dict[str, float] = {}
    for d, eq in rows:
        by_day[d] = float(eq)
    return [(date.fromisoformat(d), v) for d, v in sorted(by_day.items())]


def _audit_counts(con: sqlite3.Connection, start: str, end: str) -> dict[str, int]:
    return {r["action"]: r["n"] for r in _rows(
        con,
        "SELECT action, COUNT(*) AS n FROM audit_log "
        "WHERE date(ts) BETWEEN ? AND ? GROUP BY action",
        (start, end),
    )}


def _audit_events(con: sqlite3.Connection, start: str, end: str,
                  actions: tuple[str, ...]) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in actions)
    return _rows(
        con,
        f"SELECT ts, action, actor_type, target_type, target_id FROM audit_log "
        f"WHERE date(ts) BETWEEN ? AND ? AND action IN ({placeholders}) ORDER BY ts",
        (start, end, *actions),
    )


def _runs(con: sqlite3.Connection, table: str, start: str, end: str) -> list[dict[str, Any]]:
    try:
        return _rows(
            con, f"SELECT * FROM {table} WHERE date(ran_at) BETWEEN ? AND ? ORDER BY ran_at",
            (start, end))
    except sqlite3.OperationalError:
        return []


def build(db: str, strategy_id: int, month: str) -> dict[str, Any]:
    start, end = _month_bounds(month)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        audit = _audit_counts(con, start, end)
        curve = _equity_curve(con, start, end)
        incidents_raw = _audit_events(con, start, end, tuple(INCIDENT_ACTIONS))
        changes_raw = _audit_events(con, start, end, CHANGE_ACTIONS)
        recon = _runs(con, "reconciliation_runs", start, end)
        replay = _runs(con, "replay_runs", start, end)
        strat = _rows(con, "SELECT name, version, status, params_json FROM strategies WHERE id=?",
                      (strategy_id,))
        params = json.loads(strat[0]["params_json"]) if strat and strat[0].get("params_json") else {}
    finally:
        con.close()

    # performance from the in-month equity curve
    if len(curve) >= 2:
        rets = ev.daily_returns(curve)
        performance: dict[str, Any] = {
            "status": "live curve", "n_days": len(curve),
            "start": str(curve[0][0]), "end": str(curve[-1][0]),
            "start_equity": curve[0][1], "end_equity": curve[-1][1],
            "total_return": round(ev.total_return(curve), 4),
            "ann_volatility": round(ev.ann_volatility(rets), 4),
            "sharpe": round(ev.sharpe(rets), 2),
            "sortino": round(ev.sortino(rets), 2),
            "max_drawdown": round(ev.max_drawdown(curve), 4),
            "drawdown_profile": ev.drawdown_profile(curve),
        }
    else:
        performance = {"status": "accruing (need >=2 daily snapshots in the month)",
                       "n_days": len(curve)}

    risk = {
        "orders_risk_passed": audit.get("ORDER_RISK_PASSED", 0),
        "orders_rejected_by_risk": audit.get("ORDER_REJECTED_BY_RISK", 0),
        "orders_rejected_by_broker": audit.get("ORDER_REJECTED_BY_BROKER", 0),
        "breaker_trips": audit.get("CIRCUIT_BREAKER_TRIPPED", 0),
        "breaker_resets": audit.get("CIRCUIT_BREAKER_RESET", 0),
    }
    operations = {
        "orders_submitted": audit.get("ORDER_SUBMITTED", 0),
        "fills_ingested": audit.get("ORDER_FILL_INGESTED", 0),
        "orders_canceled": audit.get("ORDER_CANCELED", 0),
        "scanner_runs": audit.get("SCANNER_RUN", 0),
        "reconciliation_runs": len(recon),
        "replay_runs": len(replay),
        # boot-time resume-on-boot churn — a proxy for backend restarts, not config changes
        "strategy_reregistrations": audit.get("STRATEGY_REGISTERED", 0),
        "audit_actions_total": sum(audit.values()),
    }
    incidents = [
        {"ts": e["ts"], "kind": INCIDENT_ACTIONS[e["action"]][0],
         "severity": INCIDENT_ACTIONS[e["action"]][1], "action": e["action"],
         "target": _fmt_target(e)}
        for e in incidents_raw
    ]
    changes = [{"ts": e["ts"], "action": e["action"], "target": _fmt_target(e)} for e in changes_raw]
    # also count run-level discrepancies/mismatches that may not have an audit row
    recon_discrepancies = sum(int(r.get("n_discrepancies") or 0) for r in recon)
    recon_failed = sum(1 for r in recon if r.get("result") in ("fail", "warning"))
    replay_mismatched = sum(int(r.get("n_mismatched") or 0) for r in replay)
    replay_checked = sum(int(r.get("n_checked") or 0) for r in replay)
    replay_matched = sum(int(r.get("n_matched") or 0) for r in replay)

    verifiability = {
        "replay_runs": len(replay), "replay_checked": replay_checked,
        "replay_matched": replay_matched, "replay_mismatched": replay_mismatched,
        "replay_consistency": round(replay_matched / replay_checked, 4) if replay_checked else None,
        "reconciliation_runs": len(recon), "reconciliation_discrepancies": recon_discrepancies,
        "reconciliation_failed_runs": recon_failed,
        "clean": replay_mismatched == 0 and recon_discrepancies == 0 and recon_failed == 0,
    }
    recovery = {
        "breaker_trips": risk["breaker_trips"], "breaker_resets": risk["breaker_resets"],
        "recovered": risk["breaker_resets"] >= risk["breaker_trips"] and risk["breaker_trips"] > 0,
    }

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(), "db": db, "month": month, "window": {"start": start, "end": end},
        "strategy": {
            "id": strategy_id, "name": strat[0]["name"] if strat else None,
            "version": strat[0]["version"] if strat else None,
            "status": strat[0]["status"] if strat else None,
            "config": "v1.1 (momentum + vol-scaling)" if params.get("use_daily_overlay")
                      else "v1.0 (momentum only)",
            "vol_target_annual": params.get("vol_target_annual"),
        },
        "performance": performance, "risk": risk, "operations": operations,
        "incidents": incidents, "recovery": recovery, "verifiability": verifiability,
        "changes": changes,
    }
    report["lessons_learned"] = _lessons(report)
    return report


def _lessons(r: dict[str, Any]) -> list[str]:
    """Derive the lessons-learned bullets from the month's record."""
    out: list[str] = []
    risk, v = r["risk"], r["verifiability"]
    if not r["incidents"] and v["clean"]:
        out.append("Clean month: no breaker trips, no broker rejects, replay + reconciliation clean. "
                   "The discipline held.")
    else:
        for inc in r["incidents"]:
            out.append(f"Incident ({inc['severity']}, {inc['kind']}) at {inc['ts']} "
                       f"[{inc['action']} {inc['target']}] - see the incident log.")
        if r["recovery"]["recovered"]:
            out.append("The circuit breaker tripped and recovered under the documented runbook "
                       "(deactivate != stop; reset confirmed) - the safety net worked.")
    if risk["orders_rejected_by_risk"]:
        out.append(f"The risk engine rejected {risk['orders_rejected_by_risk']} order(s) this month - "
                   "the gates demonstrably fire, they do not just exist.")
    out.append("Equity curve + trade log + operational trail continue to accumulate into the live "
               "track record (P12.5).")
    return out


def _perf_lines(p: dict[str, Any]) -> list[str]:
    if p.get("status") != "live curve":
        return [f"_Accruing - {p.get('n_days', 0)} daily snapshot(s) in the month; the curve needs "
                ">=2 days. Run with `--month` set to a completed month for a full picture._", ""]
    dd = p.get("drawdown_profile", {})
    return [
        f"- **{p['n_days']} trading days** ({p['start']} -> {p['end']}); equity "
        f"${p['start_equity']:,.0f} -> ${p['end_equity']:,.0f}.",
        f"- Return **{p['total_return']:+.2%}** · ann. vol {p['ann_volatility']:.1%} · "
        f"Sharpe {p['sharpe']:.2f} · Sortino {p['sortino']:.2f} · max drawdown "
        f"**{p['max_drawdown']:.1%}** (avg {dd.get('avg_drawdown', 0):.1%}, "
        f"time underwater {dd.get('time_underwater', 0):.0%}).",
        "_Live realized metrics over one month = indicative, not a track record yet; accrues._", "",
    ]


def _render(r: dict[str, Any]) -> str:
    s, p, risk, ops = r["strategy"], r["performance"], r["risk"], r["operations"]
    v, rec = r["verifiability"], r["recovery"]
    lines = [
        f"# Monthly Evidence Report — {r['month']} — {s['name']} {s['config']}",
        "",
        f"_Generated {r['generated_at']} · git {r['git_sha']} · window {r['window']['start']} -> "
        f"{r['window']['end']} · live paper book (read-only)_",
        "",
        "> **Monthly production-validation report (P12.5).** The institutional complement to the "
        "weekly snapshot: one month of performance + the operational / safety / verifiability record + "
        "an incident log + lessons learned. Short-window live P&L is *indicative*, not alpha (ADR 0014).",
        "",
        "## 1. Performance (live equity curve)", "",
        *_perf_lines(p),
        "## 2. Risk", "",
        f"- Risk gates: **{risk['orders_risk_passed']} passed / {risk['orders_rejected_by_risk']} "
        f"rejected** by the risk engine (+{risk['orders_rejected_by_broker']} by broker).",
        f"- Circuit breaker: **{risk['breaker_trips']} trip(s) / {risk['breaker_resets']} reset(s)**.",
        "",
        "## 3. Operations", "",
        f"- Orders submitted **{ops['orders_submitted']}** · fills **{ops['fills_ingested']}** · "
        f"canceled **{ops['orders_canceled']}** · scanner runs **{ops['scanner_runs']}**.",
        f"- Reconciliation runs **{ops['reconciliation_runs']}** · replay runs **{ops['replay_runs']}** "
        f"· audit actions logged **{ops['audit_actions_total']}**.",
        f"- Strategy re-registrations (resume-on-boot, ~= backend restarts): "
        f"**{ops['strategy_reregistrations']}**.",
        "",
        "## 4. Incidents", "",
    ]
    if r["incidents"]:
        lines += ["| When | Severity | Kind | Action | Target |", "|---|---|---|---|---|"]
        lines += [f"| {i['ts']} | {i['severity']} | {i['kind']} | {i['action']} | {i['target']} |"
                  for i in r["incidents"]]
    else:
        lines.append("_No incidents this month (no breaker trips, broker rejects, replay mismatches, "
                     "or reconciliation discrepancies)._")
    lines += [
        "",
        "## 5. Recovery", "",
        (f"- Breaker tripped **{rec['breaker_trips']}** and reset **{rec['breaker_resets']}** "
         "- recovered under the documented runbook." if rec["recovered"]
         else "- No recovery events this month (no breaker trips to recover from)."),
        "",
        "## 6. Replay (decision verifiability)", "",
        f"- **{v['replay_runs']}** runs, **{v['replay_checked']}** decisions checked, "
        f"**{v['replay_mismatched']}** mismatched"
        + (f" (consistency {v['replay_consistency']:.1%})." if v["replay_consistency"] is not None
           else "."),
        "",
        "## 7. Reconciliation (position verifiability)", "",
        f"- **{v['reconciliation_runs']}** runs, **{v['reconciliation_discrepancies']}** discrepancies, "
        f"**{v['reconciliation_failed_runs']}** non-pass runs.",
        f"- Verifiability this month: **{'CLEAN' if v['clean'] else 'SEE INCIDENTS'}**.",
        "",
        "## 8. Changes (configuration / lifecycle)", "",
        "_Meaningful changes only — strategy updates, deactivations, proposal transitions. "
        "Boot-time re-registrations are summarized under Operations._", "",
    ]
    if r["changes"]:
        lines += ["| When | Action | Target |", "|---|---|---|"]
        lines += [f"| {c['ts']} | {c['action']} | {c['target']} |" for c in r["changes"]]
    else:
        lines.append("_No configuration / lifecycle changes this month._")
    lines += ["", "## 9. Lessons learned", ""]
    lines += [f"- {ln}" for ln in r["lessons_learned"]]
    lines += ["", "_Run monthly; the monthly reports accumulate into the institutional track record._"]
    return "\n".join(lines) + "\n"


def _default_month() -> str:
    now = datetime.now(UTC)
    return f"{now.year:04d}-{now.month:02d}"


def main() -> int:
    ap = argparse.ArgumentParser(description="P12.5 monthly evidence report")
    ap.add_argument("--db", default="data/workbench.sqlite")
    ap.add_argument("--strategy-id", type=int, default=2)
    ap.add_argument("--month", default=None, help="YYYY-MM (default: current month)")
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()
    month = args.month or _default_month()

    r = build(args.db, args.strategy_id, month)
    s, p, v = r["strategy"], r["performance"], r["verifiability"]
    perf = (f"return {p['total_return']:+.2%}, maxDD {p['max_drawdown']:.1%}"
            if p.get("status") == "live curve" else p["status"])
    print(f"[monthly-evidence] {month} {s['name']} {s['config']}  ({perf})")
    print(f"  risk {r['risk']['orders_risk_passed']} passed / {r['risk']['orders_rejected_by_risk']} "
          f"rejected; incidents {len(r['incidents'])}; verifiability "
          f"{'clean' if v['clean'] else 'see-incidents'}")

    if args.report_dir:
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "monthly_evidence.json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
        (d / "monthly_evidence.md").write_text(_render(r), encoding="utf-8")
        print(f"  wrote {d / 'monthly_evidence.json'} + monthly_evidence.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
