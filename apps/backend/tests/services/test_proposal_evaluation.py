"""P6 §2b-backtest — proposal_evaluation service.

compute_verdict is pure. enqueue + reconcile use the conftest session_factory
with seeded Strategy/Proposal/BacktestJob/BacktestResult rows (no live worker).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.enums import BacktestJobStatus
from app.db.models.backtest_job import BacktestJob
from app.db.models.backtest_result import BacktestResult
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.trading_profile import TradingProfile
from app.db.models.user import User
from app.services.proposal_evaluation import (
    compute_verdict,
    enqueue_eval_for_proposal,
    reconcile_pending_evals,
)


def _now() -> datetime:
    return datetime(2026, 6, 3, 12, 0, 0, tzinfo=UTC)


async def _seed(
    session_factory, *, code_path="strat.py", symbols=("AAPL",),
    changes=None, envelope=None, params=None,
) -> int:
    """Seed a user + python strategy + DRAFT proposal. Returns proposal_id."""
    async with session_factory() as s:
        now = _now()
        s.add(User(id=1, email="jay@test"))
        if envelope is not None:
            s.add(
                TradingProfile(
                    user_id=1, watchlist_json={}, bias_criteria_json={},
                    bias_thresholds_json={}, session_preferences_json={},
                    risk_preferences_json={}, agent_envelope_json=envelope,
                    created_at=now, updated_at=now,
                )
            )
        s.add(
            Strategy(
                id=1, user_id=1, name="S1", code_path=code_path,
                params_json=(params if params is not None else {"rsi_min": 50}),
                symbols_json=list(symbols), created_at=now, updated_at=now,
            )
        )
        prop = StrategyProposal(
            strategy_id=1, user_id=1, state=ProposalState.DRAFT,
            proposal_payload_json={"changes": changes or []},
            evidence_bundle_json={}, evaluation_results_json={},
            generated_at=now, transitioned_at=now, created_at=now, updated_at=now,
        )
        s.add(prop)
        await s.commit()
        return prop.id


# ---------------- compute_verdict ----------------


def test_verdict_above_when_sharpe_up_and_dd_ok():
    base = {"sharpe_ratio": 1.0, "max_drawdown": -0.10}
    var = {"sharpe_ratio": 1.2, "max_drawdown": -0.11}
    assert compute_verdict(base, var) == "above_baseline"


def test_verdict_below_when_sharpe_down():
    base = {"sharpe_ratio": 1.0, "max_drawdown": -0.10}
    var = {"sharpe_ratio": 0.9, "max_drawdown": -0.10}
    assert compute_verdict(base, var) == "below_baseline"


def test_verdict_below_when_drawdown_breaches_relative_floor():
    # baseline_dd -0.10 → floor = max(-0.15, -0.20) = -0.15; variant -0.18 < floor.
    base = {"sharpe_ratio": 1.0, "max_drawdown": -0.10}
    var = {"sharpe_ratio": 1.5, "max_drawdown": -0.18}
    assert compute_verdict(base, var) == "below_baseline"


def test_verdict_below_when_drawdown_breaches_absolute_floor():
    # baseline_dd -0.50 → floor = max(-0.55, -0.20) = -0.20; variant -0.25 < -0.20.
    base = {"sharpe_ratio": 1.0, "max_drawdown": -0.50}
    var = {"sharpe_ratio": 1.5, "max_drawdown": -0.25}
    assert compute_verdict(base, var) == "below_baseline"


def test_verdict_ties_count_as_above():
    m = {"sharpe_ratio": 1.0, "max_drawdown": -0.10}
    assert compute_verdict(dict(m), dict(m)) == "above_baseline"


# ---------------- enqueue ----------------


async def test_enqueue_skips_non_python(session_factory):
    pid = await _seed(session_factory, code_path=None)
    async with session_factory() as s:
        frag = await enqueue_eval_for_proposal(s, proposal_id=pid)
        await s.commit()
    assert frag == {"status": "skipped", "skipped_reason": "non_python_strategy"}
    async with session_factory() as s:
        jobs = (await s.execute(select(BacktestJob))).scalars().all()
    assert jobs == []


async def test_enqueue_skips_no_symbols(session_factory):
    pid = await _seed(session_factory, symbols=())
    async with session_factory() as s:
        frag = await enqueue_eval_for_proposal(s, proposal_id=pid)
        await s.commit()
    assert frag["status"] == "skipped"
    assert frag["skipped_reason"] == "no_symbols"


async def test_enqueue_inserts_baseline_and_variant(session_factory):
    pid = await _seed(
        session_factory,
        changes=[{"param": "rsi_min", "from": 50, "to": 55, "reason": "r"}],
    )
    async with session_factory() as s:
        frag = await enqueue_eval_for_proposal(s, proposal_id=pid)
        await s.commit()
    assert frag["status"] == "pending"
    assert frag["window_days"] == 90
    async with session_factory() as s:
        jobs = {j.label: j for j in (await s.execute(select(BacktestJob))).scalars().all()}
    assert set(jobs) == {f"proposal_{pid}_baseline", f"proposal_{pid}_variant"}
    # Variant params reflect the merged change; baseline keeps the original.
    assert jobs[f"proposal_{pid}_baseline"].config_json["params"]["rsi_min"] == 50
    assert jobs[f"proposal_{pid}_variant"].config_json["params"]["rsi_min"] == 55
    # config_json shape matches the worker's _config_from_dict expectations.
    cfg = jobs[f"proposal_{pid}_variant"].config_json
    assert cfg["timeframe"] == "1Min"
    assert cfg["initial_equity"] == "100000"
    assert cfg["_symbols"] == ["AAPL"]


async def test_enqueue_uses_envelope_window(session_factory):
    pid = await _seed(session_factory, envelope={"eval_window_days": 180})
    async with session_factory() as s:
        frag = await enqueue_eval_for_proposal(s, proposal_id=pid)
        await s.commit()
    assert frag["window_days"] == 180


async def test_enqueue_invalid_window_falls_back_to_default(session_factory):
    pid = await _seed(session_factory, envelope={"eval_window_days": 9999})
    async with session_factory() as s:
        frag = await enqueue_eval_for_proposal(s, proposal_id=pid)
        await s.commit()
    assert frag["window_days"] == 90


# ---------------- reconcile ----------------


async def _seed_eval_in_flight(
    session_factory, *, baseline_status, variant_status,
    with_results=False, baseline_metrics=None, variant_metrics=None,
) -> int:
    """Seed a REVIEWING proposal with a pending eval + two backtest jobs."""
    pid = await _seed(session_factory)
    async with session_factory() as s:
        now = _now()

        def _mk_job(label, status):
            return BacktestJob(
                user_id=1, strategy_id=1, status=status, label=label,
                config_json={}, submitted_at=now,
            )

        bjob = _mk_job(f"proposal_{pid}_baseline", baseline_status)
        vjob = _mk_job(f"proposal_{pid}_variant", variant_status)
        s.add(bjob)
        s.add(vjob)
        await s.flush()

        if with_results:
            def _mk_result(label, metrics):
                return BacktestResult(
                    strategy_id=1, label=label, params_json={},
                    metrics_json=metrics, equity_curve_json=[], trades_json=[],
                    range_start=now - timedelta(days=90), range_end=now,
                    created_at=now,
                )

            br = _mk_result(f"proposal_{pid}_baseline", baseline_metrics or {})
            vr = _mk_result(f"proposal_{pid}_variant", variant_metrics or {})
            s.add(br)
            s.add(vr)
            await s.flush()
            bjob.result_id = br.id
            vjob.result_id = vr.id

        prop = await s.get(StrategyProposal, pid)
        prop.state = ProposalState.REVIEWING
        prop.evaluation_results_json = {
            "status": "pending",
            "baseline_job_id": bjob.id,
            "variant_job_id": vjob.id,
            "baseline_label": bjob.label,
            "variant_label": vjob.label,
            "window_days": 90,
        }
        await s.commit()
    return pid


async def _eval_status(session_factory, pid: int) -> dict:
    async with session_factory() as s:
        prop = await s.get(StrategyProposal, pid)
        return dict(prop.evaluation_results_json or {})


async def test_reconcile_both_complete_writes_verdict(session_factory):
    pid = await _seed_eval_in_flight(
        session_factory,
        baseline_status=BacktestJobStatus.COMPLETED,
        variant_status=BacktestJobStatus.COMPLETED,
        with_results=True,
        baseline_metrics={"sharpe_ratio": 1.0, "max_drawdown": -0.10},
        variant_metrics={"sharpe_ratio": 1.3, "max_drawdown": -0.10},
    )
    counts = await reconcile_pending_evals(session_factory=session_factory)
    assert counts["completed"] == 1
    state = await _eval_status(session_factory, pid)
    assert state["status"] == "complete"
    assert state["verdict"] == "above_baseline"
    assert round(state["delta_metrics"]["sharpe_ratio_delta"], 4) == 0.3


async def test_reconcile_one_running_marks_running(session_factory):
    pid = await _seed_eval_in_flight(
        session_factory,
        baseline_status=BacktestJobStatus.COMPLETED,
        variant_status=BacktestJobStatus.RUNNING,
    )
    counts = await reconcile_pending_evals(session_factory=session_factory)
    assert counts["still_pending"] == 1
    state = await _eval_status(session_factory, pid)
    assert state["status"] == "running"


async def test_reconcile_neither_started_stays_pending(session_factory):
    pid = await _seed_eval_in_flight(
        session_factory,
        baseline_status=BacktestJobStatus.QUEUED,
        variant_status=BacktestJobStatus.QUEUED,
    )
    counts = await reconcile_pending_evals(session_factory=session_factory)
    assert counts["still_pending"] == 1
    state = await _eval_status(session_factory, pid)
    assert state["status"] == "pending"


async def test_reconcile_baseline_failed_marks_failed(session_factory):
    pid = await _seed_eval_in_flight(
        session_factory,
        baseline_status=BacktestJobStatus.FAILED,
        variant_status=BacktestJobStatus.COMPLETED,
    )
    counts = await reconcile_pending_evals(session_factory=session_factory)
    assert counts["failed"] == 1
    state = await _eval_status(session_factory, pid)
    assert state["status"] == "failed"
    assert "baseline_failed" in state["failure_reason"]
