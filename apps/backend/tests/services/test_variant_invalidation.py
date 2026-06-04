"""P6b §2b-variant D8 — invalidation hooks terminate the in-flight variant.

The service primitive (``terminate_for_parent``) is exercised directly with a
fake engine; the apply_proposal wiring is exercised end-to-end through the API
(engine=None path → the variant is flipped to IDLE in-process)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.enums import StrategyStatus
from app.db.models.audit_log import AuditLog
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.db.session import get_sessionmaker
from app.services.paper_variant import PaperVariantService

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
BASE = "/api/v1"


class _FakeEngine:
    def __init__(self) -> None:
        self.unregistered: list[tuple[int, str]] = []

    async def register(self, sid: int) -> None:  # pragma: no cover - unused here
        pass

    async def unregister(self, sid: int, *, reason: str = "user_stop") -> None:
        self.unregistered.append((sid, reason))


async def _seed_live_with_variant(session_factory) -> int:
    """Seed a LIVE parent + ACCEPTED proposal, spawn a variant, return variant id."""
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="s.py", params_json={"rsi": 30},
            symbols_json=["AAPL"], status=StrategyStatus.LIVE, created_at=NOW, updated_at=NOW,
        ))
        s.add(StrategyProposal(
            id=1, strategy_id=1, user_id=1, state=ProposalState.ACCEPTED,
            proposal_payload_json={"changes": [{"param": "rsi", "to": 40}]},
            evidence_bundle_json={}, evaluation_results_json={},
            generated_at=NOW, transitioned_at=NOW, created_at=NOW, updated_at=NOW,
        ))
        await s.commit()
    async with session_factory() as s:
        v = await PaperVariantService(s, _FakeEngine()).spawn(proposal_id=1, user_id=1)
        return v.id


# ---- service primitive ----


async def test_terminate_for_parent_invalidates_in_flight_variant(session_factory):
    vid = await _seed_live_with_variant(session_factory)
    eng = _FakeEngine()
    async with session_factory() as s:
        await PaperVariantService(s, eng).terminate_for_parent(
            parent_strategy_id=1, reason="parent_deactivated", user_id=1
        )
    assert (vid, "paper_variant_parent_deactivated") in eng.unregistered
    async with session_factory() as s:
        # proposal moved EVALUATING → REJECTED; a termination audit was written.
        p = await s.get(StrategyProposal, 1)
        assert p.state == ProposalState.REJECTED
        terms = (await s.execute(
            select(AuditLog).where(AuditLog.action == "PAPER_VARIANT_TERMINATED")
        )).scalars().all()
        assert len(terms) == 1


async def test_terminate_for_parent_noop_without_variant(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="s.py", params_json={},
            symbols_json=[], status=StrategyStatus.LIVE, created_at=NOW, updated_at=NOW,
        ))
        await s.commit()
    eng = _FakeEngine()
    async with session_factory() as s:
        await PaperVariantService(s, eng).terminate_for_parent(
            parent_strategy_id=1, reason="x", user_id=1
        )  # no raise
    assert eng.unregistered == []


# ---- apply_proposal D8 wiring (through the API) ----


@pytest.fixture
async def _seed_idle_parent_with_lingering_variant(client):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="s.py", params_json={"rsi": 30},
            symbols_json=["AAPL"], status=StrategyStatus.IDLE, created_at=NOW, updated_at=NOW,
        ))
        s.add(Strategy(
            id=2, user_id=1, name="S1 (variant)", code_path="s.py", params_json={"rsi": 40},
            symbols_json=["AAPL"], status=StrategyStatus.PAPER_VARIANT, parent_strategy_id=1,
            created_at=NOW, updated_at=NOW,
        ))
        s.add(StrategyProposal(
            id=1, strategy_id=1, user_id=1, state=ProposalState.ACCEPTED,
            proposal_payload_json={"changes": [{"param": "rsi", "to": 50}]},
            evidence_bundle_json={}, evaluation_results_json={},
            generated_at=NOW, transitioned_at=NOW, created_at=NOW, updated_at=NOW,
        ))
        await s.commit()
    return client


async def test_apply_proposal_terminates_lingering_variant(
    client, _seed_idle_parent_with_lingering_variant
):
    r = await client.post(f"{BASE}/proposals/1/apply")
    assert r.status_code == 200
    assert r.json()["state"] == "APPLIED"
    async with get_sessionmaker()() as s:
        variant = await s.get(Strategy, 2)
        assert variant.status == StrategyStatus.IDLE  # terminated before apply
        parent = await s.get(Strategy, 1)
        assert parent.params_json["rsi"] == 50  # apply still happened


async def test_apply_proposal_noop_when_no_variant(client):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="s.py", params_json={"rsi": 30},
            symbols_json=["AAPL"], status=StrategyStatus.IDLE, created_at=NOW, updated_at=NOW,
        ))
        s.add(StrategyProposal(
            id=1, strategy_id=1, user_id=1, state=ProposalState.ACCEPTED,
            proposal_payload_json={"changes": [{"param": "rsi", "to": 55}]},
            evidence_bundle_json={}, evaluation_results_json={},
            generated_at=NOW, transitioned_at=NOW, created_at=NOW, updated_at=NOW,
        ))
        await s.commit()
    r = await client.post(f"{BASE}/proposals/1/apply")
    assert r.status_code == 200
    assert r.json()["state"] == "APPLIED"
