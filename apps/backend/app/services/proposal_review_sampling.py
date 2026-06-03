"""Human-review sampling for proposals (P6 §2b-review).

Per Decisions doc Decision 8 + ADR-0014: backtests are the primary eval ground
truth (shipped in §2b-backtest); a 10% human-review sample is the qualitative
supplement (this module).

Design (verified against p6-session2b-backtest-complete):
- Singleton weekly cron (Mon 09:00 ET) iterates all users.
- For each user: candidates = past-7-days proposals where
  ``state in {ACCEPTED, REJECTED, APPLIED}`` AND
  ``evaluation_results_json.human_review IS NULL``.
- If 0 candidates -> no-op for that user.
- If < 10 candidates -> sample all.
- Else -> sample floor(len / 10).
- Write ``human_review = {sampled_at, reviewed_at: null, rating: null,
  reason: null}`` by MERGE (not overwrite) into ``evaluation_results_json``.

Sampling is silent (no audit). The review submission
(POST /proposals/{id}/review) writes ``PROPOSAL_REVIEW_RECORDED`` — that's the
meaningful event.

Two NON-NEGOTIABLE invariants (per the §2b-review confirmation turn):
1. De-dup against already-sampled — exclude ``human_review.sampled_at IS NOT
   NULL`` so overlapping 7-day windows never re-surface the same proposal.
2. Merge-not-overwrite — preserve the §2b-backtest eval sub-tree
   (``status``/``baseline_metrics``/``variant_metrics``/``verdict``...).

The register signature mirrors ``register_proposal_evaluation_reconcile_job``
(§2b-backtest): the caller passes the raw APScheduler
(``WorkbenchScheduler.scheduler``) and we call ``scheduler.add_job(...)``.
"""
from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User

logger = structlog.get_logger(__name__)

# Global constants (per §2b-review out-of-scope: per-user overrides are P6+
# polish, tunable as code constants only).
SAMPLE_PERCENT = 10
SAMPLE_THRESHOLD = 10
WINDOW_DAYS = 7

_TERMINAL_STATES = (
    ProposalState.ACCEPTED,
    ProposalState.REJECTED,
    ProposalState.APPLIED,
)

# Module-level RNG; reseeded by tests for deterministic sampling. Production
# runs use the un-seeded default (a different draw each Monday).
_rng = random.Random()


def _seed_rng_for_testing(seed: int) -> None:
    """Test-only: reseed the module RNG so sampling is deterministic."""
    global _rng
    _rng = random.Random(seed)


async def _candidates_for_user(
    session: AsyncSession, user_id: int, cutoff: datetime
) -> list[StrategyProposal]:
    """Proposals eligible for sampling for one user.

    Filter: user_id == N AND state in terminal AND generated_at >= cutoff AND
    ``evaluation_results_json.human_review IS NULL`` (the de-dup invariant).

    The last predicate uses SQLAlchemy Core ``func.json_extract`` — the
    established §1a / §2b-backtest pattern for ``evaluation_results_json``
    queries; ``json_extract`` returns SQL NULL when the key is absent.
    """
    q = (
        select(StrategyProposal)
        .where(StrategyProposal.user_id == user_id)
        .where(StrategyProposal.state.in_(_TERMINAL_STATES))
        .where(StrategyProposal.generated_at >= cutoff)
        .where(
            func.json_extract(
                StrategyProposal.evaluation_results_json, "$.human_review"
            ).is_(None)
        )
    )
    return list((await session.execute(q)).scalars().all())


def _pick_sample(
    candidates: list[StrategyProposal],
) -> list[StrategyProposal]:
    """Apply the 10%-of-7-days rule: floor 10%, threshold, min-1."""
    n = len(candidates)
    if n == 0:
        return []
    if n < SAMPLE_THRESHOLD:
        return list(candidates)
    k = max(1, n // SAMPLE_PERCENT)  # floor; n=10 -> 1, n=25 -> 2
    return _rng.sample(candidates, k=k)


def _merge_sampled_at(
    existing_eval: dict[str, Any] | None, now: datetime
) -> dict[str, Any]:
    """Build the merged ``evaluation_results_json`` dict with the
    ``human_review`` sub-key initialized — preserving any existing sub-keys
    (status / baseline_metrics / variant_metrics / verdict / ...).

    NON-NEGOTIABLE: reassign-not-mutate. SQLAlchemy JSON dirty detection is
    reassignment-based; an in-place ``existing["human_review"] = ...`` on the
    column may silently fail to persist, so the caller assigns this return.
    """
    merged = dict(existing_eval or {})
    merged["human_review"] = {
        "sampled_at": now.isoformat(),
        "reviewed_at": None,
        "rating": None,
        "reason": None,
    }
    return merged


async def run_review_sampling(*, session_factory) -> dict[str, int]:
    """Singleton weekly sweep. Iterates all users; for each, finds candidates
    and samples 10% (floor; all if < 10; none if 0)."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=WINDOW_DAYS)
    users_processed = 0
    users_with_no_candidates = 0
    total_sampled = 0

    async with session_factory() as session:
        users = list((await session.execute(select(User))).scalars().all())
        users_processed = len(users)

        for user in users:
            candidates = await _candidates_for_user(session, user.id, cutoff)
            if not candidates:
                users_with_no_candidates += 1
                continue
            for proposal in _pick_sample(candidates):
                proposal.evaluation_results_json = _merge_sampled_at(
                    proposal.evaluation_results_json, now
                )
                proposal.updated_at = now
                total_sampled += 1

        await session.commit()

    logger.info(
        "proposal_review_sampling_sweep_complete",
        users_processed=users_processed,
        users_with_no_candidates=users_with_no_candidates,
        total_sampled=total_sampled,
    )
    return {
        "users_processed": users_processed,
        "users_with_no_candidates": users_with_no_candidates,
        "total_sampled": total_sampled,
    }


def register_proposal_review_sampling_job(scheduler, session_factory) -> None:
    """Register the singleton Mon 09:00 ET sampling cron on the APScheduler
    instance (``WorkbenchScheduler.scheduler``). Lives inside the alpaca-enabled
    boot block, alongside §2a cadence + §2b-backtest reconcile. Mirrors
    ``register_proposal_evaluation_reconcile_job``."""
    from apscheduler.triggers.cron import CronTrigger

    scheduler.add_job(
        run_review_sampling,
        CronTrigger(
            day_of_week="mon", hour=9, minute=0, timezone="America/New_York"
        ),
        kwargs={"session_factory": session_factory},
        id="proposal_review_sampling",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    logger.info("proposal_review_sampling_job_registered")
