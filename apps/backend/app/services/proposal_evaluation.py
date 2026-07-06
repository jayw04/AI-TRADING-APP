"""Backtest eval pipeline for strategy proposals (P6 §2b-backtest).

Per Decisions doc Decision 8 + ADR-0014: eval uses backtests as primary ground
truth. Rule: variant.sharpe ≥ baseline.sharpe AND
variant.max_drawdown ≥ max(baseline.max_drawdown − 0.05, −0.20).

Design (verified against p6-cleanup-1-complete):
- Service-layer **direct `BacktestJob` insert** (sidesteps the HTTP endpoint's
  single-flight 409 + USER-attributed audit). Same `config_json` shape
  `_config_from_dict`/`submit_backtest` use; params flow to the strategy via
  `strategy_class(ctx, params={**default_params, **config.params})`.
- The existing `BacktestWorker` runs the jobs and sets `job.result_id` on
  completion. A 60s reconcile cron reads completion via `result_id` and writes
  the verdict to `strategy_proposals.evaluation_results_json`.
- Proposal state stays REVIEWING; eval lives in
  `evaluation_results_json.status` (pending|running|complete|skipped|failed).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import BacktestJobStatus
from app.db.models.backtest_job import BacktestJob
from app.db.models.backtest_result import BacktestResult
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import StrategyProposal

logger = structlog.get_logger(__name__)

DEFAULT_EVAL_WINDOW_DAYS = 90
DEFAULT_DRAWDOWN_FLOOR_DELTA = 0.05
DEFAULT_DRAWDOWN_FLOOR_ABS = -0.20

_DELTA_KEYS = (
    "sharpe_ratio",
    "max_drawdown",
    "total_return",
    "annualized_return",
    "win_rate",
    "profit_factor",
)


def _eval_window_for_user(envelope: dict[str, Any]) -> int:
    raw = envelope.get("eval_window_days")
    if isinstance(raw, int) and 7 <= raw <= 365:
        return raw
    return DEFAULT_EVAL_WINDOW_DAYS


def _label_pair(proposal_id: int) -> tuple[str, str]:
    return f"proposal_{proposal_id}_baseline", f"proposal_{proposal_id}_variant"


def _apply_changes(
    base_params: dict[str, Any], changes: list[dict[str, Any]]
) -> dict[str, Any]:
    """Merge the proposal's changes list (`[{param, from, to, reason}, ...]`)
    into base_params (the variant param set)."""
    out = dict(base_params)
    for change in changes:
        param = change.get("param")
        if param is not None:
            out[param] = change.get("to")
    return out


def _build_config_json(
    *, start: datetime, end: datetime, params: dict[str, Any], symbols: list[str]
) -> dict[str, Any]:
    """Mirror `submit_backtest`'s config_dict so `_config_from_dict` rehydrates
    it identically. initial_equity is a stringified Decimal; defaults verified
    against BacktestRequest + _config_from_dict."""
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "initial_equity": "100000",
        "slippage_bps": 5.0,
        "commission_per_share": 0.0,
        "timeframe": "1Min",
        "params": params,
        "_symbols": symbols,
    }


async def enqueue_eval_for_proposal(
    session: AsyncSession, *, proposal_id: int
) -> dict[str, Any]:
    """Enqueue baseline + variant BacktestJobs for a proposal. Called by the
    PATCH /proposals/{id} DRAFT→REVIEWING branch (same session/transaction).
    Returns the `evaluation_results_json` fragment the caller writes onto the
    proposal row: pending | skipped(non_python_strategy|no_symbols)."""
    proposal = await session.get(StrategyProposal, proposal_id)
    if proposal is None:
        raise ValueError(f"Proposal {proposal_id} not found")
    strategy = await session.get(Strategy, proposal.strategy_id)
    if strategy is None:
        raise ValueError(f"Strategy {proposal.strategy_id} not found")

    # Non-PYTHON strategies (AGENT/Pine) have no code_path → can't backtest.
    if not strategy.code_path:
        return {"status": "skipped", "skipped_reason": "non_python_strategy"}

    symbols = list(strategy.symbols_json or [])
    if not symbols:
        return {"status": "skipped", "skipped_reason": "no_symbols"}

    from app.services.trading_profile import TradingProfileService

    profile = await TradingProfileService(session).get(proposal.user_id)
    window_days = _eval_window_for_user(profile.agent_envelope or {})

    now = datetime.now(UTC)
    start = now - timedelta(days=window_days)
    baseline_label, variant_label = _label_pair(proposal_id)
    baseline_params = dict(strategy.params_json or {})
    changes = (proposal.proposal_payload_json or {}).get("changes") or []
    variant_params = _apply_changes(baseline_params, changes)

    baseline_job = BacktestJob(
        user_id=proposal.user_id,
        strategy_id=strategy.id,
        status=BacktestJobStatus.QUEUED,
        label=baseline_label,
        config_json=_build_config_json(
            start=start, end=now, params=baseline_params, symbols=symbols
        ),
        submitted_at=now,
    )
    variant_job = BacktestJob(
        user_id=proposal.user_id,
        strategy_id=strategy.id,
        status=BacktestJobStatus.QUEUED,
        label=variant_label,
        config_json=_build_config_json(
            start=start, end=now, params=variant_params, symbols=symbols
        ),
        submitted_at=now,
    )
    session.add(baseline_job)
    session.add(variant_job)
    await session.flush()  # populate job ids

    return {
        "status": "pending",
        "started_at": now.isoformat(),
        "window_days": window_days,
        "baseline_job_id": baseline_job.id,
        "variant_job_id": variant_job.id,
        "baseline_label": baseline_label,
        "variant_label": variant_label,
    }


# Verdict states. The first two are the Decision-8 comparison; the last two enforce the
# Evidence Engineering rule (review comments.md, E4): a verdict requires EVIDENCE — a
# zero-trade backtest must never read as "above baseline".
VERDICT_ABOVE = "above_baseline"
VERDICT_BELOW = "below_baseline"
VERDICT_INSUFFICIENT = "insufficient_evidence"   # neither side traded → no evidence
VERDICT_NEEDS_REVIEW = "needs_review"            # only the variant traded → human look


def compute_verdict(
    baseline_metrics: dict[str, Any], variant_metrics: dict[str, Any]
) -> str:
    """Decision 8 rule, gated by the evidence guard (E4).

    A proposal verdict requires evidence; absence of evidence is not evidence of success.
    So before comparing Sharpe/drawdown we check trade counts:
      - both 0 trades        → ``insufficient_evidence`` (never a pass)
      - variant 0, baseline>0 → ``below_baseline`` (the change stopped trading — strictly worse)
      - baseline 0, variant>0 → ``needs_review`` (new behavior emerged; a human should look)
      - both > 0             → the Sharpe/drawdown comparison (ties count as above_baseline)
    """
    baseline_trades = int(baseline_metrics.get("trade_count", 0) or 0)
    variant_trades = int(variant_metrics.get("trade_count", 0) or 0)
    if baseline_trades == 0 and variant_trades == 0:
        return VERDICT_INSUFFICIENT
    if variant_trades == 0:
        return VERDICT_BELOW
    if baseline_trades == 0:
        return VERDICT_NEEDS_REVIEW

    variant_sharpe = float(variant_metrics.get("sharpe_ratio", 0.0))
    baseline_sharpe = float(baseline_metrics.get("sharpe_ratio", 0.0))
    variant_dd = float(variant_metrics.get("max_drawdown", 0.0))
    baseline_dd = float(baseline_metrics.get("max_drawdown", 0.0))
    drawdown_floor = max(
        baseline_dd - DEFAULT_DRAWDOWN_FLOOR_DELTA, DEFAULT_DRAWDOWN_FLOOR_ABS
    )
    if variant_sharpe >= baseline_sharpe and variant_dd >= drawdown_floor:
        return VERDICT_ABOVE
    return VERDICT_BELOW


def _delta_metrics(
    baseline: dict[str, Any], variant: dict[str, Any]
) -> dict[str, float]:
    return {
        f"{k}_delta": float(variant.get(k, 0.0)) - float(baseline.get(k, 0.0))
        for k in _DELTA_KEYS
    }


async def reconcile_pending_evals(*, session_factory) -> dict[str, int]:
    """Reconcile cron (~60s): finds proposals with eval pending/running and
    advances them based on the BacktestJobs' state."""
    counts = {"completed": 0, "failed": 0, "still_pending": 0}
    async with session_factory() as session:
        in_flight = (
            await session.execute(
                select(StrategyProposal.id).where(
                    func.json_extract(
                        StrategyProposal.evaluation_results_json, "$.status"
                    ).in_(["pending", "running"])
                )
            )
        ).scalars().all()
        for proposal_id in in_flight:
            outcome = await _reconcile_one(session, proposal_id)
            if outcome == "complete":
                counts["completed"] += 1
            elif outcome == "failed":
                counts["failed"] += 1
            else:
                counts["still_pending"] += 1
        await session.commit()
    logger.info("proposal_evaluation_reconcile_pass", **counts)
    return counts


def _fail(eval_state: dict[str, Any], reason: str) -> str:
    eval_state["status"] = "failed"
    eval_state["failure_reason"] = reason
    eval_state["completed_at"] = datetime.now(UTC).isoformat()
    return "failed"


async def _reconcile_one(session: AsyncSession, proposal_id: int) -> str:
    proposal = await session.get(StrategyProposal, proposal_id)
    if proposal is None:
        return "pending"
    eval_state = dict(proposal.evaluation_results_json or {})

    baseline_job_id = eval_state.get("baseline_job_id")
    variant_job_id = eval_state.get("variant_job_id")
    if baseline_job_id is None or variant_job_id is None:
        outcome = _fail(eval_state, "missing_job_ids")
        proposal.evaluation_results_json = eval_state
        return outcome

    baseline_job = await session.get(BacktestJob, baseline_job_id)
    variant_job = await session.get(BacktestJob, variant_job_id)
    if baseline_job is None or variant_job is None:
        outcome = _fail(eval_state, "job_row_missing")
        proposal.evaluation_results_json = eval_state
        return outcome

    for who, job in (("baseline", baseline_job), ("variant", variant_job)):
        if job.status in (BacktestJobStatus.FAILED, BacktestJobStatus.CANCELLED):
            outcome = _fail(
                eval_state, f"{who}_{job.status.value}: {job.error_text or 'unknown'}"
            )
            proposal.evaluation_results_json = eval_state
            return outcome

    if (
        baseline_job.status != BacktestJobStatus.COMPLETED
        or variant_job.status != BacktestJobStatus.COMPLETED
    ):
        # One or both still queued/running.
        if BacktestJobStatus.RUNNING in (baseline_job.status, variant_job.status):
            eval_state["status"] = "running"
            proposal.evaluation_results_json = eval_state
        return "pending"

    # Both COMPLETED → results are linked via result_id.
    baseline_result = (
        await session.get(BacktestResult, baseline_job.result_id)
        if baseline_job.result_id is not None
        else None
    )
    variant_result = (
        await session.get(BacktestResult, variant_job.result_id)
        if variant_job.result_id is not None
        else None
    )
    if baseline_result is None or variant_result is None:
        outcome = _fail(eval_state, "results_missing_despite_completion")
        proposal.evaluation_results_json = eval_state
        return outcome

    baseline_metrics = dict(baseline_result.metrics_json or {})
    variant_metrics = dict(variant_result.metrics_json or {})
    eval_state["status"] = "complete"
    eval_state["completed_at"] = datetime.now(UTC).isoformat()
    eval_state["baseline_metrics"] = baseline_metrics
    eval_state["variant_metrics"] = variant_metrics
    eval_state["delta_metrics"] = _delta_metrics(baseline_metrics, variant_metrics)
    eval_state["verdict"] = compute_verdict(baseline_metrics, variant_metrics)
    proposal.evaluation_results_json = eval_state
    proposal.updated_at = datetime.now(UTC)
    return "complete"


def register_proposal_evaluation_reconcile_job(scheduler, session_factory) -> None:
    """Register the reconcile cron on the APScheduler instance
    (WorkbenchScheduler.scheduler). Every minute, US/Eastern. Lives inside the
    alpaca-enabled boot block."""
    from apscheduler.triggers.cron import CronTrigger

    scheduler.add_job(
        reconcile_pending_evals,
        CronTrigger(minute="*", timezone="America/New_York"),
        kwargs={"session_factory": session_factory},
        id="proposal_evaluation_reconcile",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    logger.info("proposal_evaluation_reconcile_job_registered")
