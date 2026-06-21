"""P13.5 — Production Confidence Score from the live paper book (read-only).

Reads the same operational/safety/verifiability signals as ``live_evidence.py`` / ``monthly_evidence.py``
and composes them into a single 0–100 score (``app.ops.confidence``) that rises with clean operation
over time. The complement to the evidence *report*: a number an allocator/buyer can track week over week.

> Read-only. ASCII-only stdout (cp1252-safe). No order path; queries the SQLite DB read-only.

    apps/backend/.venv/Scripts/python.exe apps/backend/scripts/confidence_score.py \
        --db data/workbench.sqlite --report-dir docs/implementation/evidence/p12_5_live/confidence
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

from app.ops.confidence import ConfidenceSignals, compute_confidence  # noqa: E402


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def _audit_counts(con: sqlite3.Connection) -> dict[str, int]:
    return {a: n for a, n in con.execute("SELECT action, COUNT(*) FROM audit_log GROUP BY action")}


def _scalar(con: sqlite3.Connection, sql: str) -> Any:
    try:
        row = con.execute(sql).fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def _track_record_days(con: sqlite3.Connection) -> int:
    """Days since the book started — earliest of the first equity snapshot and the first strategy
    order — through today. 0 if nothing has happened yet."""
    firsts = [
        _scalar(con, "SELECT MIN(date(ts)) FROM equity_snapshots"),
        _scalar(con, "SELECT MIN(date(created_at)) FROM orders WHERE source_type='STRATEGY'"),
    ]
    days = [d for d in firsts if d]
    if not days:
        return 0
    start = min(date.fromisoformat(d) for d in days)
    return max(0, (datetime.now(UTC).date() - start).days)


def build(db: str) -> dict[str, Any]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        a = _audit_counts(con)
        recon_runs = _scalar(con, "SELECT COUNT(*) FROM reconciliation_runs") or 0
        recon_disc = _scalar(con, "SELECT COALESCE(SUM(n_discrepancies),0) FROM reconciliation_runs") or 0
        replay_mis = _scalar(con, "SELECT COALESCE(SUM(n_mismatched),0) FROM replay_runs") or 0
        track_days = _track_record_days(con)
    finally:
        con.close()

    signals = ConfidenceSignals(
        track_record_days=track_days,
        replay_mismatches=int(replay_mis) + a.get("REPLAY_MISMATCH", 0),
        reconciliation_discrepancies=int(recon_disc) + a.get("RECONCILIATION_DISCREPANCY", 0),
        reconciliation_runs=int(recon_runs),
        breaker_trips=a.get("CIRCUIT_BREAKER_TRIPPED", 0),
        breaker_resets=a.get("CIRCUIT_BREAKER_RESET", 0),
        orders_risk_passed=a.get("ORDER_RISK_PASSED", 0),
        orders_rejected_by_risk=a.get("ORDER_REJECTED_BY_RISK", 0),
        orders_rejected_by_broker=a.get("ORDER_REJECTED_BY_BROKER", 0),
        fills_ingested=a.get("ORDER_FILL_INGESTED", 0),
    )
    result = compute_confidence(signals)
    return {
        "generated_at": datetime.now(UTC).isoformat(), "git_sha": _git_sha(), "db": db,
        "signals": vars(signals), **result,
    }


def _render(r: dict[str, Any]) -> str:
    c = r["components"]
    lines = [
        f"# Production Confidence Score — {r['score']:.0f}/100 ({r['band']})",
        "",
        f"_Generated {r['generated_at']} · git {r['git_sha']} · live paper book (read-only)_",
        "",
        "> A single 0–100 measure of how trustworthy the live book is — rises with clean operation "
        "over time, falls when the discipline visibly fails (P13.5).",
        "",
        f"## Score: **{r['score']:.0f} / 100** — {r['band']}",
        "",
        "| Component | Weight | Score |",
        "|---|---|---|",
        f"| Verifiability (replay + reconcile clean) | {r['weights']['verifiability']:.0%} | {c['verifiability']:.0f} |",
        f"| Safety (gates fire, breaker recovers) | {r['weights']['safety']:.0%} | {c['safety']:.0f} |",
        f"| Maturity (clean track record) | {r['weights']['maturity']:.0%} | {c['maturity']:.0f} |",
        f"| Operational (running, no broker rejects) | {r['weights']['operational']:.0%} | {c['operational']:.0f} |",
        "",
        "## Why",
        "",
        *[f"- {ln}" for ln in r["rationale"]],
        "",
        "_The score is conservative by design: a new book scores low (no track record), an "
        "incident-free mature book scores high. Run weekly; it climbs as the clean record lengthens._",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="P13.5 Production Confidence Score")
    ap.add_argument("--db", default="data/workbench.sqlite")
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    r = build(args.db)
    print(f"[confidence] {r['score']:.0f}/100 ({r['band']})")
    print(f"  verifiability {r['components']['verifiability']:.0f} | safety {r['components']['safety']:.0f} "
          f"| maturity {r['components']['maturity']:.0f} | operational {r['components']['operational']:.0f}")
    for ln in r["rationale"]:
        print(f"  - {ln}")

    if args.report_dir:
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "confidence_score.json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
        (d / "confidence_score.md").write_text(_render(r), encoding="utf-8")
        print(f"  wrote {d / 'confidence_score.json'} + confidence_score.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
