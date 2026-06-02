"""P6 §1a — strategy_proposals schema (Decision 3).

Exercises the model/table created in §1a: column defaults, the ProposalState
enum round-trip, the JSON columns, and the composite-unique-per-minute index
(the empirical check of correction #8 — the functional index must reference the
``generated_at`` column, not a string literal). FK enforcement is off in the
test engine (project-wide), so these tests don't depend on a real strategies row.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models.strategy_proposal import ProposalState, StrategyProposal


def _proposal(**overrides) -> StrategyProposal:
    now = datetime(2026, 6, 2, 9, 0, 0, tzinfo=UTC)
    base = dict(
        strategy_id=1,
        user_id=1,
        generated_at=now,
        transitioned_at=now,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return StrategyProposal(**base)


async def test_create_proposal_with_defaults(session_factory) -> None:
    async with session_factory() as s:
        s.add(_proposal())
        await s.commit()
        row = (await s.execute(select(StrategyProposal))).scalars().one()
        assert row.state == ProposalState.DRAFT
        assert row.proposal_payload_json == {}
        assert row.evidence_bundle_json == {}
        assert row.evaluation_results_json == {}


async def test_proposal_state_enum_round_trips(session_factory) -> None:
    async with session_factory() as s:
        s.add(_proposal(state=ProposalState.ACCEPTED))
        await s.commit()
        row = (await s.execute(select(StrategyProposal))).scalars().one()
        assert row.state is ProposalState.ACCEPTED
        assert row.state == "ACCEPTED"  # StrEnum value == name


async def test_json_columns_round_trip(session_factory) -> None:
    payload = {"param_delta": {"rsi_min": 55}, "confidence": "MEDIUM"}
    evidence = {"backtest_ref": 42}
    async with session_factory() as s:
        s.add(_proposal(proposal_payload_json=payload, evidence_bundle_json=evidence))
        await s.commit()
        row = (await s.execute(select(StrategyProposal))).scalars().one()
        assert row.proposal_payload_json == payload
        assert row.evidence_bundle_json == evidence


async def test_composite_unique_minute_blocks_duplicates(session_factory) -> None:
    # Same strategy_id + same generated_at minute (00s vs 30s) → blocked.
    async with session_factory() as s:
        s.add(_proposal(generated_at=datetime(2026, 6, 2, 9, 0, 0, tzinfo=UTC)))
        s.add(_proposal(generated_at=datetime(2026, 6, 2, 9, 0, 30, tzinfo=UTC)))
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_same_strategy_different_minute_allowed(session_factory) -> None:
    async with session_factory() as s:
        s.add(_proposal(generated_at=datetime(2026, 6, 2, 9, 0, 0, tzinfo=UTC)))
        s.add(_proposal(generated_at=datetime(2026, 6, 2, 9, 1, 0, tzinfo=UTC)))
        await s.commit()
        rows = (await s.execute(select(StrategyProposal))).scalars().all()
        assert len(rows) == 2


async def test_different_strategy_same_minute_allowed(session_factory) -> None:
    async with session_factory() as s:
        s.add(_proposal(strategy_id=1, generated_at=datetime(2026, 6, 2, 9, 0, 0, tzinfo=UTC)))
        s.add(_proposal(strategy_id=2, generated_at=datetime(2026, 6, 2, 9, 0, 0, tzinfo=UTC)))
        await s.commit()
        rows = (await s.execute(select(StrategyProposal))).scalars().all()
        assert len(rows) == 2
