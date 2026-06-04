"""Proposal cadence — opt-in scheduled invocation of the propose endpoint (P6 §2a).

Per Decisions doc Decision 5: APScheduler-driven, max_instances=1 per user.
Opt-in via ``agent_envelope_json.proposal_cadence``; default ``off`` (no
scheduled firings). The cron is a *programmatic caller* of the existing
``POST /api/v1/strategies/{id}/propose`` endpoint (with ``trigger="cadence"``),
using the user's own ``AGENT_API_KEY`` as the bearer token — it does not bypass
auth, audit, or risk gates. Every fire writes an ``AGENT_CADENCE_FIRED`` audit
row per strategy describing the outcome.

Registration lives in ``lifespan.py`` (inside the alpaca-enabled block, where the
scheduler exists) and on trading-profile updates (``reconcile_cadence_for_user``).
The registration helpers take the APScheduler instance directly
(``WorkbenchScheduler.scheduler``).
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any

import httpx
import structlog
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.models.strategy import Strategy
from app.db.models.trading_profile import TradingProfile

logger = structlog.get_logger(__name__)

_CADENCE_TZ = "America/New_York"  # matches the morning-brief convention


class ProposalCadence(StrEnum):
    OFF = "off"
    WEEKDAY_MARKET_OPEN = "weekday_market_open"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY_FIRST = "monthly_first"


# APScheduler CronTrigger kwargs per cadence (timezone applied at trigger build).
CADENCE_CRON: dict[ProposalCadence, dict[str, Any]] = {
    ProposalCadence.WEEKDAY_MARKET_OPEN: {"day_of_week": "mon-fri", "hour": 9, "minute": 30},
    ProposalCadence.DAILY: {"hour": 9, "minute": 30},
    ProposalCadence.WEEKLY: {"day_of_week": "mon", "hour": 9, "minute": 30},
    ProposalCadence.MONTHLY_FIRST: {"day": 1, "hour": 9, "minute": 30},
}


def parse_cadence(value: Any) -> ProposalCadence:
    """Parse an envelope's proposal_cadence value. Returns OFF for missing or
    invalid values (defensive — never break registration on a malformed
    envelope)."""
    if not isinstance(value, str):
        return ProposalCadence.OFF
    try:
        return ProposalCadence(value)
    except ValueError:
        logger.warning("invalid_proposal_cadence_value", value=value)
        return ProposalCadence.OFF


def _job_id(user_id: int) -> str:
    return f"proposal_cadence_user_{user_id}"


# --------------------------- cron callback ---------------------------------


async def _resolve_user_agent_key(session, user_id: int) -> str | None:
    """Return the user's active AGENT_API_KEY plaintext, or None if absent/revoked."""
    from app.db.models.user_credential import UserCredential
    from app.security.credential_store import CredentialKind, CredentialStore

    rows = (
        await session.execute(
            select(UserCredential).where(
                UserCredential.user_id == user_id,
                UserCredential.kind == CredentialKind.AGENT_API_KEY.value,
                UserCredential.revoked_at.is_(None),
            )
        )
    ).scalars().all()
    if not rows:
        return None
    store = CredentialStore(session)
    for r in rows:
        value = await store.get(r.user_id, CredentialKind.AGENT_API_KEY)
        if value:
            return value
    return None


async def _attempt_propose_for_strategy(
    *,
    client: httpx.AsyncClient,
    strategy_id: int,
) -> tuple[str, int | None, str, str | None]:
    """Budget pre-check then propose. Returns (outcome, proposal_id,
    estimated_cost_cents_str, details). Outcomes: proposal_generated |
    budget_skipped | propose_failed."""
    estimated_cost_cents = 10  # conservative pre-check ceiling (Sonnet ~3-8c)
    try:
        r = await client.get(
            "/api/v1/agent/cost-envelope",
            params={"estimated_cost_cents": estimated_cost_cents},
        )
        r.raise_for_status()
        envelope_check = r.json()
    except Exception as exc:
        return ("propose_failed", None, str(estimated_cost_cents),
                f"cost-envelope query failed: {exc}"[:500])

    if envelope_check.get("decision") == "REJECTED":
        return ("budget_skipped", None, str(estimated_cost_cents),
                f"current_spend_cents={envelope_check.get('current_spend_cents')}; "
                f"envelope_cents={envelope_check.get('envelope_cents')}")

    try:
        r = await client.post(
            f"/api/v1/strategies/{strategy_id}/propose",
            json={"trigger": "cadence"},
        )
        r.raise_for_status()
        proposal = r.json()
        return ("proposal_generated", proposal.get("id"), str(estimated_cost_cents), None)
    except httpx.HTTPStatusError as exc:
        return ("propose_failed", None, str(estimated_cost_cents),
                f"HTTP {exc.response.status_code}: {exc.response.text[:200]}")
    except Exception as exc:
        return ("propose_failed", None, str(estimated_cost_cents),
                f"propose failed: {exc}"[:500])


async def run_proposal_cadence(
    *,
    user_id: int,
    session_factory,
    backend_api_base: str = "http://127.0.0.1:8000",
    client: httpx.AsyncClient | None = None,
) -> dict[str, int]:
    """Cron callback for one user's cadence fire. Iterates the user's strategies;
    for each, budget-pre-checks then proposes (trigger='cadence'); writes one
    AGENT_CADENCE_FIRED audit row per strategy. Per-strategy errors don't stop
    the batch (mirrors §2's morning-brief resilience). ``client`` is injectable
    for tests."""
    counts = {"generated": 0, "budget_skipped": 0, "failed": 0, "no_api_key": 0}

    async with session_factory() as session:
        profile = (
            await session.execute(
                select(TradingProfile).where(TradingProfile.user_id == user_id)
            )
        ).scalars().first()
        if profile is None:
            logger.warning("cadence_fire_user_has_no_profile", user_id=user_id)
            return counts

        envelope = profile.agent_envelope_json or {}
        current_cadence = parse_cadence(envelope.get("proposal_cadence"))
        if current_cadence == ProposalCadence.OFF:
            logger.info("cadence_fire_skipped_now_off", user_id=user_id)
            return counts

        agent_key = await _resolve_user_agent_key(session, user_id)
        if not agent_key and client is None:
            AuditLogger.write(
                session,
                actor_type=AuditActorType.AGENT,
                actor_id="cron_scheduler",
                action=AuditAction.AGENT_CADENCE_FIRED,
                target_type="user",
                target_id=user_id,
                payload={
                    "strategy_id": None,
                    "cadence": current_cadence.value,
                    "outcome": "no_api_key",
                    "details": "User has no AGENT_API_KEY; cadence cannot invoke propose.",
                    "proposal_id": None,
                },
                user_id=user_id,
            )
            await session.commit()
            counts["no_api_key"] = 1
            return counts

        strategy_ids = [
            s.id
            for s in (
                await session.execute(
                    # P6b §2a: exclude paper-variant clones — the cadence proposes
                    # against the user's own strategies, not validation variants.
                    select(Strategy)
                    .where(Strategy.user_id == user_id)
                    .where(Strategy.parent_strategy_id.is_(None))
                )
            ).scalars().all()
        ]

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            base_url=backend_api_base,
            headers={"Authorization": f"Bearer {agent_key}"},
            timeout=120.0,
        )
    try:
        for strategy_id in strategy_ids:
            outcome, proposal_id, est_cost, detail = await _attempt_propose_for_strategy(
                client=client, strategy_id=strategy_id
            )
            async with session_factory() as audit_session:
                AuditLogger.write(
                    audit_session,
                    actor_type=AuditActorType.AGENT,
                    actor_id="cron_scheduler",
                    action=AuditAction.AGENT_CADENCE_FIRED,
                    target_type="strategy",
                    target_id=strategy_id,
                    payload={
                        "strategy_id": strategy_id,
                        "cadence": current_cadence.value,
                        "outcome": outcome,
                        "estimated_cost_cents": est_cost,
                        "details": detail,
                        "proposal_id": proposal_id,
                    },
                    user_id=user_id,
                )
                await audit_session.commit()

            if outcome == "proposal_generated":
                counts["generated"] += 1
            elif outcome == "budget_skipped":
                counts["budget_skipped"] += 1
            else:
                counts["failed"] += 1
    finally:
        if owns_client:
            await client.aclose()

    logger.info("proposal_cadence_fire_complete", user_id=user_id,
                cadence=current_cadence.value, **counts)
    return counts


# --------------------------- registration ----------------------------------


def _register_cadence_job(scheduler, session_factory, user_id: int, cadence: ProposalCadence) -> None:
    """Add (or replace) the cron job for one user. ``scheduler`` is the
    APScheduler instance (WorkbenchScheduler.scheduler)."""
    trigger = CronTrigger(timezone=_CADENCE_TZ, **CADENCE_CRON[cadence])
    scheduler.add_job(
        run_proposal_cadence,
        trigger,
        kwargs={"user_id": user_id, "session_factory": session_factory},
        id=_job_id(user_id),
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    logger.info("proposal_cadence_job_registered", user_id=user_id, cadence=cadence.value)


def _unregister_cadence_job(scheduler, user_id: int) -> None:
    """Remove a user's cron job. Idempotent."""
    try:
        scheduler.remove_job(_job_id(user_id))
        logger.info("proposal_cadence_job_unregistered", user_id=user_id)
    except Exception:
        pass  # not registered — harmless


async def register_all_cadence_jobs(scheduler, session_factory) -> None:
    """Lifespan-startup pass: register a cron job for every user whose
    proposal_cadence != off."""
    async with session_factory() as session:
        profiles = (await session.execute(select(TradingProfile))).scalars().all()
    for profile in profiles:
        envelope = profile.agent_envelope_json or {}
        cadence = parse_cadence(envelope.get("proposal_cadence"))
        if cadence != ProposalCadence.OFF:
            _register_cadence_job(scheduler, session_factory, profile.user_id, cadence)


async def reconcile_cadence_for_user(scheduler, session_factory, user_id: int) -> None:
    """Add/update/remove a user's cron job to match their current cadence.
    Called after a trading-profile update."""
    async with session_factory() as session:
        profile = (
            await session.execute(
                select(TradingProfile).where(TradingProfile.user_id == user_id)
            )
        ).scalars().first()
    if profile is None:
        _unregister_cadence_job(scheduler, user_id)
        return
    envelope = profile.agent_envelope_json or {}
    cadence = parse_cadence(envelope.get("proposal_cadence"))
    if cadence == ProposalCadence.OFF:
        _unregister_cadence_job(scheduler, user_id)
    else:
        _register_cadence_job(scheduler, session_factory, user_id, cadence)
