"""P6 §2b-review — proposal_review_sampling service.

Uses the conftest ``session_factory`` fixture with seeded User/StrategyProposal
rows (no scheduler, no live cron). The two NON-NEGOTIABLE invariants
(de-dup-against-already-sampled, merge-not-overwrite) each have a dedicated test.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.models.audit_log import AuditLog
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.services.proposal_review_sampling import (
    _pick_sample,
    _seed_rng_for_testing,
    register_proposal_review_sampling_job,
    run_review_sampling,
)

# Distinct minute per proposal — §1a's composite-unique-per-minute index blocks
# same-(strategy, minute) duplicates.
_seq = 0


async def _seed_users(session_factory, *user_ids: int) -> None:
    async with session_factory() as s:
        for uid in user_ids:
            s.add(User(id=uid, email=f"u{uid}@test"))
        await s.commit()


async def _mk(
    session_factory,
    *,
    state: ProposalState = ProposalState.ACCEPTED,
    days_ago: float = 1,
    eval_state: dict | None = None,
    user_id: int = 1,
    strategy_id: int = 1,
) -> int:
    global _seq
    _seq += 1
    async with session_factory() as s:
        ts = (
            datetime.now(UTC)
            - timedelta(days=days_ago)
            - timedelta(minutes=_seq)
        )
        prop = StrategyProposal(
            strategy_id=strategy_id,
            user_id=user_id,
            state=state,
            proposal_payload_json={},
            evidence_bundle_json={},
            evaluation_results_json=eval_state or {},
            generated_at=ts,
            transitioned_at=ts,
            created_at=ts,
            updated_at=ts,
        )
        s.add(prop)
        await s.commit()
        return prop.id


async def _eval(session_factory, pid: int) -> dict:
    async with session_factory() as s:
        prop = await s.get(StrategyProposal, pid)
        return dict(prop.evaluation_results_json or {})


async def _audit_count(session_factory) -> int:
    async with session_factory() as s:
        return len((await s.execute(select(AuditLog))).scalars().all())


# ---------------- _pick_sample (pure) ----------------


def test_pick_sample_zero():
    assert _pick_sample([]) == []


def test_pick_sample_under_threshold_takes_all():
    items = list(range(5))
    assert sorted(_pick_sample(items)) == items  # type: ignore[arg-type]


def test_pick_sample_floor_ten_percent():
    _seed_rng_for_testing(42)
    assert len(_pick_sample(list(range(25)))) == 2  # 25 // 10  # type: ignore[arg-type]
    _seed_rng_for_testing(42)
    assert len(_pick_sample(list(range(10)))) == 1  # not < 10 → 10 // 10  # type: ignore[arg-type]


def test_pick_sample_is_deterministic_with_seed():
    _seed_rng_for_testing(7)
    first = _pick_sample(list(range(50)))  # type: ignore[arg-type]
    _seed_rng_for_testing(7)
    second = _pick_sample(list(range(50)))  # type: ignore[arg-type]
    assert first == second


# ---------------- run_review_sampling: invariants ----------------


async def test_sampling_excludes_already_sampled_proposals_from_prior_weeks(
    session_factory,
):
    await _seed_users(session_factory, 1)
    # Already sampled 2 days ago (in the 7-day window) → must be excluded.
    already = await _mk(
        session_factory,
        days_ago=2,
        eval_state={
            "status": "complete",
            "human_review": {"sampled_at": "2026-05-30T00:00:00+00:00", "rating": None},
        },
    )
    fresh = await _mk(session_factory, days_ago=1, eval_state={"status": "complete"})

    result = await run_review_sampling(session_factory=session_factory)

    assert result["total_sampled"] == 1
    # the fresh one got sampled; the already-sampled one is untouched.
    assert (await _eval(session_factory, fresh))["human_review"]["sampled_at"]
    assert (
        await _eval(session_factory, already)
    )["human_review"]["sampled_at"] == "2026-05-30T00:00:00+00:00"


async def test_sampling_preserves_existing_eval_subtree(session_factory):
    await _seed_users(session_factory, 1)
    pid = await _mk(
        session_factory,
        eval_state={
            "status": "complete",
            "baseline_metrics": {"sharpe_ratio": 1.0},
            "variant_metrics": {"sharpe_ratio": 1.2},
            "verdict": "above_baseline",
        },
    )
    await run_review_sampling(session_factory=session_factory)

    ev = await _eval(session_factory, pid)
    # merge, not overwrite: backtest sub-tree intact AND human_review added.
    assert ev["status"] == "complete"
    assert ev["verdict"] == "above_baseline"
    assert ev["baseline_metrics"] == {"sharpe_ratio": 1.0}
    assert ev["human_review"]["sampled_at"]
    assert ev["human_review"]["rating"] is None


# ---------------- state + window scope ----------------


async def test_sampling_only_includes_terminal_states(session_factory):
    await _seed_users(session_factory, 1)
    await _mk(session_factory, state=ProposalState.DRAFT)
    await _mk(session_factory, state=ProposalState.REVIEWING)
    acc = await _mk(session_factory, state=ProposalState.ACCEPTED)
    rej = await _mk(session_factory, state=ProposalState.REJECTED)
    app = await _mk(session_factory, state=ProposalState.APPLIED)

    result = await run_review_sampling(session_factory=session_factory)

    assert result["total_sampled"] == 3
    for pid in (acc, rej, app):
        assert (await _eval(session_factory, pid)).get("human_review")


async def test_sampling_is_eval_status_agnostic(session_factory):
    await _seed_users(session_factory, 1)
    for status in ("complete", "skipped", "failed"):
        await _mk(session_factory, eval_state={"status": status})

    result = await run_review_sampling(session_factory=session_factory)
    assert result["total_sampled"] == 3


async def test_sampling_window_7_days(session_factory):
    await _seed_users(session_factory, 1)
    inside = await _mk(session_factory, days_ago=6)
    await _mk(session_factory, days_ago=8)  # outside the window

    result = await run_review_sampling(session_factory=session_factory)
    assert result["total_sampled"] == 1
    assert (await _eval(session_factory, inside)).get("human_review")


# ---------------- sample size ----------------


async def test_sampling_zero_candidates_no_op(session_factory):
    await _seed_users(session_factory, 1)
    before = await _audit_count(session_factory)
    result = await run_review_sampling(session_factory=session_factory)
    assert result["total_sampled"] == 0
    assert result["users_with_no_candidates"] == 1
    assert await _audit_count(session_factory) == before


async def test_sampling_under_10_takes_all(session_factory):
    await _seed_users(session_factory, 1)
    for _ in range(5):
        await _mk(session_factory)
    result = await run_review_sampling(session_factory=session_factory)
    assert result["total_sampled"] == 5


async def test_sampling_10_or_more_takes_floor_10_percent(session_factory):
    _seed_rng_for_testing(42)
    await _seed_users(session_factory, 1)
    for _ in range(25):
        await _mk(session_factory)
    result = await run_review_sampling(session_factory=session_factory)
    assert result["total_sampled"] == 2  # 25 // 10


# ---------------- multi-user ----------------


async def test_sampling_iterates_all_users(session_factory):
    await _seed_users(session_factory, 1, 2, 3)
    for uid in (1, 2, 3):
        await _mk(session_factory, user_id=uid, strategy_id=uid)
    result = await run_review_sampling(session_factory=session_factory)
    assert result["users_processed"] == 3
    assert result["total_sampled"] == 3


async def test_sampling_per_user_isolated(session_factory):
    _seed_rng_for_testing(1)
    await _seed_users(session_factory, 1, 2)
    # user 1 has 20 candidates (→ 2 sampled), user 2 has 3 (→ all 3).
    for _ in range(20):
        await _mk(session_factory, user_id=1, strategy_id=1)
    for _ in range(3):
        await _mk(session_factory, user_id=2, strategy_id=2)
    result = await run_review_sampling(session_factory=session_factory)
    assert result["total_sampled"] == 2 + 3


# ---------------- silent (no audit) ----------------


async def test_sampling_writes_no_audit_rows(session_factory):
    await _seed_users(session_factory, 1)
    for _ in range(4):
        await _mk(session_factory)
    before = await _audit_count(session_factory)
    await run_review_sampling(session_factory=session_factory)
    assert await _audit_count(session_factory) == before


# ---------------- cron registration ----------------


class _FakeScheduler:
    def __init__(self) -> None:
        self.jobs: list[dict] = []

    def add_job(self, func, trigger=None, **kwargs):  # noqa: ANN001
        self.jobs.append({"func": func, "trigger": trigger, **kwargs})


def test_register_review_sampling_job_uses_scheduler():
    sched = _FakeScheduler()
    register_proposal_review_sampling_job(sched, session_factory=None)
    assert len(sched.jobs) == 1
    job = sched.jobs[0]
    assert job["id"] == "proposal_review_sampling"
    assert job["max_instances"] == 1
    assert job["func"] is run_review_sampling


def test_register_uses_replace_existing():
    sched = _FakeScheduler()
    register_proposal_review_sampling_job(sched, session_factory=None)
    assert sched.jobs[0]["replace_existing"] is True
