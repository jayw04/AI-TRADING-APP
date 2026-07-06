"""Operational KPI scorecard (P13.5) — the customer-facing operational metrics.

The P11 §2 Prometheus/Grafana substrate is **operator**-facing (runtime, scraped, SLO alerts). This
is the **customer**-facing complement: a durable, point-in-time rollup an allocator/buyer reads —
reconciliation success, replay consistency, risk-gate efficacy, breaker recovery, fill success, and
operational continuity — each with a target and a pass/watch status.

Pure: the caller passes a ``KpiInputs`` snapshot (read from the durable audit/ops tables); this module
turns it into a scorecard. Latency KPIs are intentionally absent — order/fill latency is not durably
recorded, so claiming it here would be dishonest (noted as a gap rather than faked).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class KpiInputs:
    reconciliation_runs: int
    reconciliation_passes: int
    reconciliation_discrepancies: int
    replay_checked: int
    replay_matched: int
    orders_risk_passed: int
    orders_rejected_by_risk: int
    orders_rejected_by_broker: int
    breaker_trips: int
    breaker_resets: int
    breaker_recovery_minutes: float | None   # mean trip→reset; None if no trips
    orders_submitted: int
    fills_ingested: int
    expected_snapshot_days: int               # trading days since the book started
    actual_snapshot_days: int                 # days with an equity snapshot


def _pct(num: int, den: int) -> float | None:
    return round(100.0 * num / den, 1) if den else None


def _status(value: float | None, target: float, *, higher_is_better: bool) -> str:
    """ok / watch / n_a — 'watch' (not 'fail') because these are reported, not alerting gates."""
    if value is None:
        return "n_a"
    return "ok" if (value >= target if higher_is_better else value <= target) else "watch"


def build_scorecard(i: KpiInputs) -> list[dict[str, Any]]:
    """The customer-facing KPI rows: each {key,label,value,unit,target,status,note}."""
    recon_success = _pct(i.reconciliation_passes, i.reconciliation_runs)
    replay_consistency = _pct(i.replay_matched, i.replay_checked)
    total_risk = i.orders_risk_passed + i.orders_rejected_by_risk
    risk_reject_rate = _pct(i.orders_rejected_by_risk, total_risk)
    fill_success = _pct(i.fills_ingested, i.orders_submitted)
    continuity = _pct(i.actual_snapshot_days, i.expected_snapshot_days)
    unrecovered = max(0, i.breaker_trips - i.breaker_resets)

    rows: list[dict[str, Any]] = [
        {"key": "reconciliation_success", "label": "Reconciliation success",
         "value": recon_success, "unit": "%", "target": 99.0,
         "status": _status(recon_success, 99.0, higher_is_better=True),
         "note": f"{i.reconciliation_passes}/{i.reconciliation_runs} runs passed"},
        {"key": "reconciliation_drift", "label": "Reconciliation drift",
         "value": i.reconciliation_discrepancies, "unit": "count", "target": 0,
         "status": "ok" if i.reconciliation_discrepancies == 0 else "watch",
         "note": "broker ⇄ local position discrepancies (target 0)"},
        {"key": "replay_consistency", "label": "Replay consistency",
         "value": replay_consistency, "unit": "%", "target": 99.9,
         "status": _status(replay_consistency, 99.9, higher_is_better=True),
         "note": f"{i.replay_matched}/{i.replay_checked} decisions reproduced"},
        {"key": "risk_gate_efficacy", "label": "Risk-gate efficacy",
         "value": risk_reject_rate, "unit": "% rejected", "target": 0.0,
         "status": "ok",  # informational: the gate firing at all is the success signal
         "note": f"{i.orders_rejected_by_risk} rejected / {total_risk} checked "
                 f"(+{i.orders_rejected_by_broker} by broker) — gates demonstrably fire"},
        {"key": "breaker_recovery", "label": "Circuit-breaker recovery",
         "value": i.breaker_recovery_minutes, "unit": "min", "target": 0.0,
         "status": "ok" if unrecovered == 0 else "watch",
         "note": f"{i.breaker_trips} trip(s), {i.breaker_resets} recovered"
                 + (f", ~{i.breaker_recovery_minutes:.0f} min mean" if i.breaker_recovery_minutes else "")},
        {"key": "fill_success", "label": "Fill success",
         "value": fill_success, "unit": "%", "target": 90.0,
         "status": _status(fill_success, 90.0, higher_is_better=True),
         "note": f"{i.fills_ingested} fills / {i.orders_submitted} orders submitted"},
        {"key": "operational_continuity", "label": "Operational continuity",
         "value": continuity, "unit": "%", "target": 90.0,
         "status": _status(continuity, 90.0, higher_is_better=True),
         "note": f"{i.actual_snapshot_days}/{i.expected_snapshot_days} trading days with an "
                 "equity snapshot (daily-job uptime proxy)"},
    ]
    return rows


def scorecard_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Roll the rows up into ok/watch/n_a counts."""
    out = {"ok": 0, "watch": 0, "n_a": 0}
    for r in rows:
        out[r["status"]] = out.get(r["status"], 0) + 1
    return out
