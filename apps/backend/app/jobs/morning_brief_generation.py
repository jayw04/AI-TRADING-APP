"""Scheduled morning-brief generation (P5.5 §2). Mon-fri 09:00 US/Eastern.

For each TOTP-verified user, generate and save today's brief. Idempotent: a
user who already has a *scheduled* brief for today is skipped (a manual brief
does not block the scheduled run — the scheduled pass is the source of record).
Per-user failures are logged and do not stop the pass.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.user import User
from app.services.morning_brief import MorningBriefService

logger = structlog.get_logger(__name__)


async def run_morning_brief_generation(
    *,
    session_factory: async_sessionmaker[Any],
    bar_cache: Any = None,
    indicator_computer: Any = None,
) -> dict[str, int]:
    generated = skipped = failed = 0

    async with session_factory() as session:
        user_ids = (
            await session.execute(
                select(User.id).where(User.totp_verified_at.isnot(None))
            )
        ).scalars().all()

    for user_id in user_ids:
        try:
            async with session_factory() as session:
                svc = MorningBriefService(
                    session=session,
                    bar_cache=bar_cache,
                    indicator_computer=indicator_computer,
                )
                from app.utils.time import today_eastern

                existing = await svc.get(user_id, today_eastern())
                if existing is not None and existing.trigger == "scheduled":
                    skipped += 1
                    continue
                brief = await svc.generate(user_id, trigger="scheduled")
                await svc.save(brief)
                generated += 1

                # P6b §1a-drift: detect strategy drift on the morning-brief
                # cadence (Q3) and audit each finding. Own try so a drift
                # failure never fails the brief.
                try:
                    from app.services.drift_detection import (
                        run_drift_detection_for_user,
                    )

                    await run_drift_detection_for_user(session, user_id)
                except Exception:
                    logger.exception("drift_detection_pass_failed", user_id=user_id)

                # P6b §3a-gate: evaluate the 4-criterion promotion gate for the
                # user's in-flight variants (ADR 0007), refresh evidence bundles,
                # and transition EVALUATING → EVIDENCE_READY on first pass. Own
                # try (sibling to drift) so a gate failure never fails the brief.
                # bar_cache is needed for the variant equity-curve reconstruction.
                try:
                    from app.services.promotion_gate import (
                        run_promotion_gate_for_user,
                    )

                    await run_promotion_gate_for_user(
                        session, user_id, bar_cache=bar_cache
                    )
                except Exception:
                    logger.exception("promotion_gate_pass_failed", user_id=user_id)
        except Exception:
            logger.exception("morning_brief_generation_failed", user_id=user_id)
            failed += 1

    logger.info(
        "morning_brief_generation_pass",
        generated=generated,
        skipped=skipped,
        failed=failed,
    )
    return {"generated": generated, "skipped": skipped, "failed": failed}
