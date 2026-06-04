"""P6b §3a-gate — schema additions (enum values, audit action, column).

The Alembic up→down→up round-trip is verified via the CLI (the §2a migration
precedent); these assert the app-level shape the suite can exercise against
create_all.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.audit import AuditAction
from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


def test_proposalstate_has_promotion_lifecycle_values():
    assert ProposalState.EVIDENCE_READY.value == "EVIDENCE_READY"
    assert ProposalState.PROMOTING.value == "PROMOTING"
    assert ProposalState.PROMOTED.value == "PROMOTED"
    # All fit the SQLEnum length=16 column.
    assert all(len(v.value) <= 16 for v in ProposalState)


def test_audit_action_has_strategy_promoted():
    assert AuditAction.STRATEGY_PROMOTED.value == "STRATEGY_PROMOTED"


async def test_strategy_last_promoted_at_nullable_defaults_none(session_factory):
    async with session_factory() as s:
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="s.py", params_json={},
            symbols_json=[], status=StrategyStatus.LIVE, created_at=NOW, updated_at=NOW,
        ))
        await s.commit()
    async with session_factory() as s:
        row = await s.get(Strategy, 1)
    assert row.last_promoted_at is None
