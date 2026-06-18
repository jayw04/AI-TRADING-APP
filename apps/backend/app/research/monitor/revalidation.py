"""Continuous revalidation — the edge-decay loop-closer (P10 Phase 2 §4).

A scheduled job re-runs the watched metrics (rolling Sharpe / IC / turnover /
drawdown) for every PAPER/CANARY/LIVE strategy and, on a threshold breach, writes
a **Research Alert** recommending owner review (e.g. RETIRE). It is strictly
**read-only / alert-only**: it NEVER transitions a strategy or stops trading — the
owner acts on the alert (per docs/runbook/promotion-workflow.md).

``revalidate`` takes an injected ``rerun`` (fresh metrics for a strategy) so it is
unit-testable without slow backtests; the scheduled wrapper wires the real rerun
(the orchestrator) — that wiring lands when strategy run-configs are persisted.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import structlog

from app.research.registry import AlertRecord, ResearchStore, StrategyRecord

logger = structlog.get_logger(__name__)

# Deployment states that are "in production" and therefore revalidated.
ACTIVE_DEPLOYMENT_STATES = ("PAPER", "CANARY", "LIVE")


@dataclass(frozen=True)
class RevalidationWatch:
    """A metric to watch. ``op='min'`` alerts when value < threshold (Sharpe/IC);
    ``op='max'`` alerts when value > threshold (drawdown magnitude/turnover)."""
    metric: str
    op: str
    threshold: float


# Conservative defaults: a live momentum book whose rolling Sharpe falls below ~0.5
# or whose drawdown blows past the crash-study range is worth a human look.
DEFAULT_WATCHES: tuple[RevalidationWatch, ...] = (
    RevalidationWatch("rolling_sharpe", "min", 0.5),
    RevalidationWatch("oos_ic", "min", 0.0),
    RevalidationWatch("max_drawdown_abs", "max", 0.35),
)

# rerun(strategy) -> fresh metrics dict. Injected so revalidate() is testable.
Rerun = Callable[[StrategyRecord], dict]


def _breached(value: float | None, watch: RevalidationWatch) -> bool:
    if value is None:
        return False  # a missing metric is not a breach (don't cry wolf on absent data)
    return value < watch.threshold if watch.op == "min" else value > watch.threshold


def revalidate(
    store: ResearchStore,
    rerun: Rerun,
    *,
    watches: tuple[RevalidationWatch, ...] = DEFAULT_WATCHES,
) -> list[AlertRecord]:
    """Re-run watched metrics for every active (PAPER/CANARY/LIVE) strategy; record
    + return a Research Alert for each breach. Read-only: never transitions state."""
    alerts: list[AlertRecord] = []
    strategies = [
        s for s in store.list_strategies() if s.deployment_state in ACTIVE_DEPLOYMENT_STATES
    ]
    for strat in strategies:
        metrics = rerun(strat)
        for w in watches:
            value = metrics.get(w.metric)
            if not _breached(value, w):
                continue
            rec = AlertRecord(
                strategy_id=strat.strategy_id, kind="edge_decay", metric=w.metric,
                value=value, threshold=w.threshold,
                message=(f"{strat.name}: {w.metric}={value} breached "
                         f"{'<' if w.op == 'min' else '>'} {w.threshold} "
                         f"(deployment={strat.deployment_state})"),
                recommended_action="RETIRE_REVIEW",
            )
            store.record_alert(rec)
            alerts.append(rec)
            logger.warning("research_revalidation_alert", strategy_id=strat.strategy_id,
                           metric=w.metric, value=value, threshold=w.threshold)
    logger.info("research_revalidation_complete", strategies=len(strategies), alerts=len(alerts))
    return alerts
