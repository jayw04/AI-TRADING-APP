"""TradingProfileService — get/update the user's soft-preferences profile.

Read by: morning brief (§2), agent (P6+). Written by: the user via
Settings → Trading Profile. Updates are audit-logged with an old/new diff
(mirrors the P5 §5 risk_limits pattern).

As-built notes vs the P5.5 §1 v0.2 plan (verified against p5-complete):
  - ``AuditAction``/``AuditActorType``/``AuditLogger`` import from ``app.audit``
    (the package re-export), NOT ``app.db.enums``. The doc's §1.4 import was wrong.
  - ``AuditLogger.write`` is sync and does NOT commit — the caller owns the txn.
  - ``update`` uses a SINGLE commit: the row mutation and the audit-row insert
    flush together. The §8 hash chain requires one audit row per commit, which
    this satisfies. (§5's live risk.py happens to two-commit; both are valid.)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.models.trading_profile import TradingProfile

logger = structlog.get_logger(__name__)


# The five mutable JSON columns. ``update`` validates field names against this
# tuple (top-level only — per-section structure is not enforced in §1).
PROFILE_FIELDS = (
    "watchlist_json",
    "bias_criteria_json",
    "bias_thresholds_json",
    "session_preferences_json",
    "risk_preferences_json",
    # P6 §1a (Decision 4): the agent behavioral envelope.
    "agent_envelope_json",
)


@dataclass
class TradingProfileData:
    user_id: int
    watchlist: dict[str, Any]
    bias_criteria: dict[str, Any]
    bias_thresholds: dict[str, Any]
    session_preferences: dict[str, Any]
    risk_preferences: dict[str, Any]
    # P6 §1a (Decision 4): read by the agent budget endpoint + the agent itself.
    agent_envelope: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TradingProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int) -> TradingProfileData:
        """Return the profile, auto-creating an empty one if absent (handles
        users created after the migration ran).

        Race handling: if two first-time gets for the same user both see no
        row and both insert, the loser hits IntegrityError on the unique
        ``user_id`` constraint — catch it, roll back, and re-select the winner.
        """
        row = await self._select(user_id)
        if row is not None:
            return self._to_data(row)

        row = self._new_row(user_id)
        self._session.add(row)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            row = await self._select(user_id)
            if row is None:  # pragma: no cover - the other inserter committed
                raise
        return self._to_data(row)

    async def update(
        self,
        user_id: int,
        *,
        changes: dict[str, Any],
        actor_user_id: int,
    ) -> TradingProfileData:
        """Update one or more profile sections. Validates field names (top-level
        only). Audit-logs the old/new diff of fields that actually changed.
        Single commit — row mutation and audit row land together.
        """
        # Validate field names BEFORE touching the DB.
        for key in changes:
            if key not in PROFILE_FIELDS:
                raise ValueError(f"Unknown profile field: {key}")

        row = await self._select(user_id)
        if row is None:
            # Defensive — get() normally creates it lazily. Flush so row.id is
            # available for the audit target_id below.
            row = self._new_row(user_id)
            self._session.add(row)
            await self._session.flush()

        audit_diff: dict[str, dict[str, Any]] = {"old": {}, "new": {}}
        for field, new_value in changes.items():
            old_value = getattr(row, field)
            if old_value != new_value:
                audit_diff["old"][field] = old_value
                audit_diff["new"][field] = new_value
                setattr(row, field, new_value)

        # No-op update: nothing changed → no row touch, no audit row.
        if not audit_diff["old"]:
            return self._to_data(row)

        row.updated_at = datetime.now(UTC)

        # Queue the audit row (sync; does NOT commit on its own).
        AuditLogger.write(
            self._session,
            actor_type=AuditActorType.USER,
            actor_id=str(actor_user_id),
            action=AuditAction.TRADING_PROFILE_UPDATED,
            target_type="trading_profile",
            target_id=row.id,
            payload={"changes": audit_diff},
            user_id=user_id,
        )

        # SINGLE commit — both the row UPDATE and the audit INSERT flush together.
        await self._session.commit()
        await self._session.refresh(row)
        return self._to_data(row)

    # ------------------------ internals ------------------------

    async def _select(self, user_id: int) -> TradingProfile | None:
        return (
            await self._session.execute(
                select(TradingProfile).where(TradingProfile.user_id == user_id)
            )
        ).scalars().first()

    @staticmethod
    def _new_row(user_id: int) -> TradingProfile:
        now = datetime.now(UTC)
        return TradingProfile(
            user_id=user_id,
            watchlist_json={},
            bias_criteria_json={},
            bias_thresholds_json={},
            session_preferences_json={},
            risk_preferences_json={},
            agent_envelope_json={},
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _to_data(row: TradingProfile) -> TradingProfileData:
        return TradingProfileData(
            user_id=row.user_id,
            watchlist=row.watchlist_json,
            bias_criteria=row.bias_criteria_json,
            bias_thresholds=row.bias_thresholds_json,
            session_preferences=row.session_preferences_json,
            risk_preferences=row.risk_preferences_json,
            agent_envelope=row.agent_envelope_json,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
