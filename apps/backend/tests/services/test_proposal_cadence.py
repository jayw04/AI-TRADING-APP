"""P6 §2a — proposal cadence service.

parse/register/reconcile use a FakeScheduler; run_proposal_cadence uses the
conftest ``session_factory`` (seeded profile/strategies/credential) + an injected
MockTransport httpx client (no live stack, no real LLM).
"""
from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from app.audit.logger import AuditLog
from app.db.models.strategy import Strategy
from app.db.models.trading_profile import TradingProfile
from app.db.models.user import User
from app.security.credential_store import CredentialKind, CredentialStore
from app.services.proposal_cadence import (
    ProposalCadence,
    parse_cadence,
    reconcile_cadence_for_user,
    register_all_cadence_jobs,
    run_proposal_cadence,
)


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}

    def add_job(self, func, trigger=None, *, kwargs=None, id=None, **kw):
        self.jobs[id] = {"func": func, "trigger": trigger, "kwargs": kwargs}

    def remove_job(self, job_id):
        if job_id not in self.jobs:
            raise KeyError(job_id)
        del self.jobs[job_id]


# ---------------- parse_cadence ----------------


def test_parse_cadence_off_for_missing():
    assert parse_cadence(None) == ProposalCadence.OFF


def test_parse_cadence_off_for_invalid():
    assert parse_cadence("hourly") == ProposalCadence.OFF


def test_parse_cadence_enum_for_valid():
    assert parse_cadence("daily") == ProposalCadence.DAILY
    assert parse_cadence("weekday_market_open") == ProposalCadence.WEEKDAY_MARKET_OPEN


# ---------------- registration ----------------


async def _seed_profile(session_factory, user_id: int, cadence: str | None):
    async with session_factory() as s:
        now = datetime.now(UTC)
        s.add(User(id=user_id, email=f"u{user_id}@test"))
        s.add(
            TradingProfile(
                user_id=user_id,
                watchlist_json={}, bias_criteria_json={}, bias_thresholds_json={},
                session_preferences_json={}, risk_preferences_json={},
                agent_envelope_json=({"proposal_cadence": cadence} if cadence else {}),
                created_at=now, updated_at=now,
            )
        )
        await s.commit()


async def test_register_all_skips_off_and_adds_enabled(session_factory):
    await _seed_profile(session_factory, 1, "off")
    await _seed_profile(session_factory, 2, "daily")
    sched = FakeScheduler()
    await register_all_cadence_jobs(sched, session_factory)
    assert "proposal_cadence_user_2" in sched.jobs
    assert "proposal_cadence_user_1" not in sched.jobs


async def test_reconcile_adds_then_removes(session_factory):
    await _seed_profile(session_factory, 5, "weekly")
    sched = FakeScheduler()
    await reconcile_cadence_for_user(sched, session_factory, 5)
    assert "proposal_cadence_user_5" in sched.jobs
    # Flip to off → reconcile removes.
    async with session_factory() as s:
        prof = (
            await s.execute(select(TradingProfile).where(TradingProfile.user_id == 5))
        ).scalars().first()
        prof.agent_envelope_json = {"proposal_cadence": "off"}
        await s.commit()
    await reconcile_cadence_for_user(sched, session_factory, 5)
    assert "proposal_cadence_user_5" not in sched.jobs


async def test_reconcile_no_profile_is_noop(session_factory):
    sched = FakeScheduler()
    await reconcile_cadence_for_user(sched, session_factory, 999)  # no raise
    assert sched.jobs == {}


async def test_register_replace_existing_one_job_per_user(session_factory):
    await _seed_profile(session_factory, 7, "weekly")
    sched = FakeScheduler()
    await reconcile_cadence_for_user(sched, session_factory, 7)
    async with session_factory() as s:
        prof = (
            await s.execute(select(TradingProfile).where(TradingProfile.user_id == 7))
        ).scalars().first()
        prof.agent_envelope_json = {"proposal_cadence": "daily"}
        await s.commit()
    await reconcile_cadence_for_user(sched, session_factory, 7)
    assert list(sched.jobs.keys()) == ["proposal_cadence_user_7"]


# ---------------- run_proposal_cadence ----------------


async def _seed_full(session_factory, *, user_id=1, cadence="daily", n_strategies=2, with_key=True):
    async with session_factory() as s:
        now = datetime.now(UTC)
        s.add(User(id=user_id, email=f"u{user_id}@test"))
        s.add(
            TradingProfile(
                user_id=user_id,
                watchlist_json={}, bias_criteria_json={}, bias_thresholds_json={},
                session_preferences_json={}, risk_preferences_json={},
                agent_envelope_json={"proposal_cadence": cadence},
                created_at=now, updated_at=now,
            )
        )
        for i in range(n_strategies):
            s.add(
                Strategy(
                    id=user_id * 100 + i, user_id=user_id, name=f"S{i}",
                    params_json={}, symbols_json=[], created_at=now, updated_at=now,
                )
            )
        await s.commit()
        if with_key:
            await CredentialStore(s).set(user_id, CredentialKind.AGENT_API_KEY, "agt-key")


def _client(decision: str = "ALLOWED", propose_status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/agent/cost-envelope":
            return httpx.Response(
                200,
                json={
                    "current_spend_cents": 0 if decision == "ALLOWED" else 300,
                    "envelope_cents": 200,
                    "headroom_cents": 200,
                    "decision": decision,
                },
            )
        if request.url.path.endswith("/propose"):
            if propose_status != 200:
                return httpx.Response(propose_status, json={"detail": "boom"})
            return httpx.Response(200, json={"id": 4321, "state": "REVIEWING"})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://backend")


async def _audit_rows(session_factory, action: str):
    async with session_factory() as s:
        return (
            await s.execute(select(AuditLog).where(AuditLog.action == action))
        ).scalars().all()


async def test_run_writes_audit_per_strategy_on_success(session_factory):
    await _seed_full(session_factory, n_strategies=2)
    async with _client("ALLOWED") as c:
        counts = await run_proposal_cadence(user_id=1, session_factory=session_factory, client=c)
    assert counts["generated"] == 2
    rows = await _audit_rows(session_factory, "AGENT_CADENCE_FIRED")
    assert len(rows) == 2
    assert all(r.actor_type == "agent" for r in rows)


async def test_run_budget_skipped(session_factory):
    await _seed_full(session_factory, n_strategies=1)
    async with _client("REJECTED") as c:
        counts = await run_proposal_cadence(user_id=1, session_factory=session_factory, client=c)
    assert counts["budget_skipped"] == 1
    assert counts["generated"] == 0


async def test_run_continues_on_propose_failure(session_factory):
    await _seed_full(session_factory, n_strategies=2)
    async with _client("ALLOWED", propose_status=502) as c:
        counts = await run_proposal_cadence(user_id=1, session_factory=session_factory, client=c)
    assert counts["failed"] == 2  # both fail, batch still completes
    rows = await _audit_rows(session_factory, "AGENT_CADENCE_FIRED")
    assert len(rows) == 2


async def test_run_no_api_key_writes_audit(session_factory):
    await _seed_full(session_factory, n_strategies=2, with_key=False)
    counts = await run_proposal_cadence(user_id=1, session_factory=session_factory)
    assert counts["no_api_key"] == 1
    rows = await _audit_rows(session_factory, "AGENT_CADENCE_FIRED")
    assert len(rows) == 1
    import json

    assert json.loads(rows[0].payload_json)["outcome"] == "no_api_key"


async def test_run_off_cadence_is_noop(session_factory):
    await _seed_full(session_factory, cadence="off", n_strategies=2)
    async with _client("ALLOWED") as c:
        counts = await run_proposal_cadence(user_id=1, session_factory=session_factory, client=c)
    assert counts == {"generated": 0, "budget_skipped": 0, "failed": 0, "no_api_key": 0}
    assert await _audit_rows(session_factory, "AGENT_CADENCE_FIRED") == []
