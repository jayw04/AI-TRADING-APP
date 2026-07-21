"""Operational-hold guard + CAS-backed HoldService (P7 §7-B, ADR 0044 inv 5-7).

The guard (``assert_no_active_hold``) is what every activation-capable path calls.
``HoldService`` places and clears holds with the revisioned CAS primitive — no
silent overwrite, stale clears fail, re-clear is a no-op. State lives in
``strategy_state['operational_hold']`` (option 1, minimum scope).

Transactional note (7-B): these methods return an explicit ``HoldMutationResult``
so the caller can coordinate the audit write. Piece 3 emits the audit event in the
same transaction as the CAS so state and audit commit together (or neither does).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit.logger import AuditAction, AuditActorType, AuditLogger
from app.db.models.audit_log import AuditLog
from app.db.models.strategy_state import StrategyState
from app.strategies.operational_hold import (
    HOLD_SCHEMA_VERSION,
    K_OPERATIONAL_HOLD,
    HoldConflict,
    HoldRecord,
    HoldStateInvalid,
    HoldStatus,
    HoldStoreUnavailable,
    StrategyOnHold,
    load_hold_record,
)

RETRO_SOURCE = "RETROSPECTIVE_FORMALIZATION"


class RetroFormalizationRefused(Exception):
    """The retrospective hold formalization was refused fail-closed: the live hold is
    absent/cleared, or its (rev, reason_code, effective_at) differs from the operator-
    asserted expectation. (Malformed/unreadable state raises HoldStateInvalid /
    HoldStoreUnavailable via ``read_hold`` and also blocks.) No audit is written."""


@dataclass(frozen=True)
class HoldMutationResult:
    record: HoldRecord
    changed: bool
    was_noop: bool = False


@dataclass(frozen=True)
class FormalizeResult:
    strategy_id: int
    action: str  # would_write | wrote | already_formalized
    audit_id: int | None
    hold_rev: int
    planned_payload: dict


async def read_hold(session: AsyncSession, strategy_id: int) -> HoldRecord | None:
    """Read + validate the hold for ``strategy_id`` within ``session``. Returns None
    if absent; raises HoldStateInvalid (malformed) or HoldStoreUnavailable (query
    failed) — both of which the caller must treat as fail-closed."""
    try:
        raw = (
            await session.execute(
                select(StrategyState.value).where(
                    StrategyState.strategy_id == strategy_id,
                    StrategyState.key == K_OPERATIONAL_HOLD,
                )
            )
        ).scalars().first()
    except SQLAlchemyError as exc:
        raise HoldStoreUnavailable(str(exc)) from exc
    return load_hold_record(raw)


async def assert_no_active_hold(session: AsyncSession, strategy_id: int) -> None:
    """Block activation if an ACTIVE hold exists. Fail-closed: an absent row is the
    ONLY allow case; malformed/unreadable/unavailable all raise. Cleared allows."""
    rec = await read_hold(session, strategy_id)  # may raise Invalid / Unavailable
    if rec is not None and rec.is_active:
        raise StrategyOnHold(strategy_id, rec.reason_code, rec.rev)


class HoldService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def read(self, strategy_id: int) -> HoldRecord | None:
        async with self._sf() as session:
            return await read_hold(session, strategy_id)

    async def place(
        self, strategy_id: int, *, reason_code: str, reason: str, effective_at: str,
        placed_at: str, placed_by: str,
        actor_type: AuditActorType = AuditActorType.SYSTEM, actor_id: str | None = None,
        evidence_refs: list | None = None, approval_ref: str | None = None,
        source: str | None = None,
    ) -> HoldMutationResult:
        """Place an ACTIVE hold. Idempotent for an identical (same reason_code) active
        hold; HoldConflict on a DIFFERENT-reason active hold (no silent replace) or a
        lost CAS. The ``STRATEGY_HOLD_PLACED`` audit event is written in the SAME
        transaction as the state CAS — both persist or neither does."""
        async with self._sf() as session, session.begin():
            cur = await read_hold(session, strategy_id)  # Invalid/Unavailable -> rollback, no audit
            if cur is not None and cur.is_active:
                if cur.reason_code == reason_code:
                    return HoldMutationResult(cur, changed=False, was_noop=True)  # no CAS/audit
                raise HoldConflict(
                    f"active hold with reason_code {cur.reason_code!r} != {reason_code!r}; "
                    "clear-and-place explicitly to change reason"
                )
            new = HoldRecord(
                status=HoldStatus.ACTIVE, reason_code=reason_code, reason=reason,
                effective_at=effective_at, placed_at=placed_at, placed_by=placed_by,
                rev=(cur.rev + 1) if cur is not None else 1,
                evidence_refs=evidence_refs or [], approval_ref=approval_ref, source=source,
            )
            await self._cas_in(session, strategy_id,
                               expected_rev=(cur.rev if cur is not None else None),
                               new_value=new.to_dict())
            AuditLogger.write(
                session, actor_type=actor_type, actor_id=actor_id,
                action=AuditAction.STRATEGY_HOLD_PLACED, target_type="strategy",
                target_id=strategy_id,
                payload={"strategy_id": strategy_id, "reason_code": reason_code,
                         "reason": reason, "rev": new.rev, "effective_at": effective_at,
                         "placed_by": placed_by, "source": source,
                         "evidence_refs": evidence_refs or [], "approval_ref": approval_ref},
            )
            return HoldMutationResult(new, changed=True)

    async def clear(
        self, strategy_id: int, *, expected_rev: int, cleared_at: str, cleared_by: str,
        actor_type: AuditActorType = AuditActorType.USER, actor_id: str | None = None,
    ) -> HoldMutationResult:
        """Clear an ACTIVE hold at ``expected_rev``. Re-clearing an already-CLEARED
        hold is a no-op (NO ``STRATEGY_HOLD_CLEARED``). Stale/absent/concurrent raise
        HoldConflict. The row is preserved (CLEARED), never deleted. The clear audit
        is written in the SAME transaction as the CAS."""
        async with self._sf() as session, session.begin():
            cur = await read_hold(session, strategy_id)
            if cur is None:
                raise HoldConflict("no hold to clear")
            if not cur.is_active:
                return HoldMutationResult(cur, changed=False, was_noop=True)  # no audit
            if cur.rev != expected_rev:
                raise HoldConflict(f"stale clear: expected rev {expected_rev}, found {cur.rev}")
            new = HoldRecord(
                status=HoldStatus.CLEARED, reason_code=cur.reason_code, reason=cur.reason,
                effective_at=cur.effective_at, placed_at=cur.placed_at, placed_by=cur.placed_by,
                rev=cur.rev + 1, evidence_refs=cur.evidence_refs, approval_ref=cur.approval_ref,
                source=cur.source, cleared_at=cleared_at, cleared_by=cleared_by,
            )
            await self._cas_in(session, strategy_id, expected_rev=cur.rev, new_value=new.to_dict())
            AuditLogger.write(
                session, actor_type=actor_type, actor_id=actor_id,
                action=AuditAction.STRATEGY_HOLD_CLEARED, target_type="strategy",
                target_id=strategy_id,
                payload={"strategy_id": strategy_id, "reason_code": cur.reason_code,
                         "rev": new.rev, "prior_rev": cur.rev, "cleared_by": cleared_by},
            )
            return HoldMutationResult(new, changed=True)

    @staticmethod
    async def _cas_in(session: AsyncSession, strategy_id: int, *, expected_rev: int | None,
                      new_value: dict[str, Any]) -> None:
        """CAS on the hold blob's ``_rev`` (or insert-if-absent) WITHIN the caller's
        transaction. Raises HoldConflict on a lost race (so the audit write in the
        same transaction is rolled back with the failed mutation)."""
        if expected_rev is None:
            session.add(StrategyState(strategy_id=strategy_id, key=K_OPERATIONAL_HOLD,
                                      value=new_value, updated_at=datetime.now(UTC)))
            try:
                await session.flush()
            except IntegrityError as exc:
                raise HoldConflict("concurrent place lost the CAS") from exc
            return
        res = await session.execute(
            update(StrategyState).where(
                StrategyState.strategy_id == strategy_id,
                StrategyState.key == K_OPERATIONAL_HOLD,
                func.json_extract(StrategyState.value, "$._rev") == expected_rev,
            ).values(value=new_value, updated_at=datetime.now(UTC))
        )
        if res.rowcount != 1:
            raise HoldConflict("concurrent CAS lost")


async def record_activation_blocked(
    session: AsyncSession, *, strategy_id: int, reason_code: str, hold_rev: int,
    source: str, run_id: str,
) -> bool:
    """Record a REJECTED activation attempt (not a mutation) — written independently
    after the guard blocks. Deduplicated by (strategy_id, hold_rev, source, run_id) so
    a boot loop produces one event. Returns True iff a new event was written; the
    caller commits."""
    existing = (
        await session.execute(
            select(AuditLog.id).where(
                AuditLog.action == AuditAction.STRATEGY_ACTIVATION_BLOCKED_BY_HOLD.value,
                func.json_extract(AuditLog.payload_json, "$.strategy_id") == strategy_id,
                func.json_extract(AuditLog.payload_json, "$.hold_rev") == hold_rev,
                func.json_extract(AuditLog.payload_json, "$.source") == source,
                func.json_extract(AuditLog.payload_json, "$.run_id") == run_id,
            ).limit(1)
        )
    ).first()
    if existing is not None:
        return False
    AuditLogger.write(
        session, actor_type=AuditActorType.SYSTEM, actor_id=None,
        action=AuditAction.STRATEGY_ACTIVATION_BLOCKED_BY_HOLD, target_type="strategy",
        target_id=strategy_id,
        payload={"strategy_id": strategy_id, "reason_code": reason_code,
                 "hold_rev": hold_rev, "source": source, "run_id": run_id},
    )
    return True


async def formalize_retrospective_hold_placed(
    session: AsyncSession, *, strategy_id: int, expected_rev: int,
    expected_reason_code: str, expected_effective_at: str,
    evidence_refs: list | None = None, approval_ref: str | None = None,
    actor_type: AuditActorType = AuditActorType.USER, actor_id: str | None = None,
    apply: bool = False,
) -> FormalizeResult:
    """Emit EXACTLY ONE retrospective ``STRATEGY_HOLD_PLACED`` audit event for an
    ALREADY-ACTIVE operational hold, WITHOUT mutating the hold blob.

    This is the sanctioned way to back-record a hold that became effective before the
    ``STRATEGY_HOLD_PLACED`` action existed (the acct-4 cold-start case). It is NOT a
    placement: it never writes, clears, or edits ``operational_hold`` (or any
    ``strategy_state``) — it only adds the audit event, tagged ``source=
    RETROSPECTIVE_FORMALIZATION``. This is why ``HoldService.place`` is wrong here: on
    an existing identical active hold, ``place`` is an idempotent no-op and writes no
    audit at all.

    Fail-closed refusals (raise, no audit): the live hold is absent/cleared, or its
    ``(rev, reason_code, effective_at)`` differs from the operator-asserted expectation
    (``RetroFormalizationRefused``); malformed/unreadable state raises
    ``HoldStateInvalid`` / ``HoldStoreUnavailable`` via ``read_hold`` and also blocks.

    Deduplicated by ``(strategy_id, hold_rev, source=RETROSPECTIVE_FORMALIZATION)``: a
    second run is an idempotent no-op that writes no second event. ``apply=False``
    (default) validates + plans without writing. The caller owns the transaction.
    """
    rec = await read_hold(session, strategy_id)  # Invalid/Unavailable -> refuse (block)
    if rec is None or not rec.is_active:
        raise RetroFormalizationRefused(
            f"strategy {strategy_id}: no ACTIVE hold to formalize")
    if rec.rev != expected_rev:
        raise RetroFormalizationRefused(
            f"hold rev {rec.rev} != expected {expected_rev}")
    if rec.reason_code != expected_reason_code:
        raise RetroFormalizationRefused(
            f"reason_code {rec.reason_code!r} != expected {expected_reason_code!r}")
    if rec.effective_at != expected_effective_at:
        raise RetroFormalizationRefused(
            f"effective_at {rec.effective_at!r} != expected {expected_effective_at!r}")

    payload = {
        "strategy_id": strategy_id, "reason_code": rec.reason_code, "reason": rec.reason,
        "rev": rec.rev, "effective_at": rec.effective_at, "placed_by": rec.placed_by,
        "source": RETRO_SOURCE, "retrospective": True,
        "evidence_refs": list(evidence_refs) if evidence_refs is not None
        else list(rec.evidence_refs),
        "approval_ref": approval_ref if approval_ref is not None else rec.approval_ref,
    }
    existing = (
        await session.execute(
            select(AuditLog.id).where(
                AuditLog.action == AuditAction.STRATEGY_HOLD_PLACED.value,
                func.json_extract(AuditLog.payload_json, "$.strategy_id") == strategy_id,
                func.json_extract(AuditLog.payload_json, "$.rev") == rec.rev,
                func.json_extract(AuditLog.payload_json, "$.source") == RETRO_SOURCE,
            ).limit(1)
        )
    ).scalars().first()
    if existing is not None:
        return FormalizeResult(strategy_id, "already_formalized", existing, rec.rev, payload)
    if not apply:
        return FormalizeResult(strategy_id, "would_write", None, rec.rev, payload)
    row = AuditLogger.write(
        session, actor_type=actor_type, actor_id=actor_id,
        action=AuditAction.STRATEGY_HOLD_PLACED, target_type="strategy",
        target_id=strategy_id, payload=payload,
    )
    await session.flush()  # populate row.id (hash chain computed on insert)
    return FormalizeResult(strategy_id, "wrote", row.id, rec.rev, payload)


__all__ = [
    "FormalizeResult",
    "RETRO_SOURCE",
    "RetroFormalizationRefused",
    "formalize_retrospective_hold_placed",
    "HoldMutationResult",
    "HoldService",
    "assert_no_active_hold",
    "read_hold",
    "record_activation_blocked",
    # re-exports so callers import from one place
    "HoldConflict",
    "HoldStateInvalid",
    "HoldStoreUnavailable",
    "StrategyOnHold",
    "HOLD_SCHEMA_VERSION",
]
