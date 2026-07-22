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
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
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
REASON_UPDATE_SOURCE = "GOVERNING_ADJUDICATION_UPDATE"


class HoldReasonUpdateRefused(Exception):
    """Re-labelling an ACTIVE hold's reason_code was refused fail-closed: the hold is
    absent, is not ACTIVE, is at a different revision than the operator asserted, or
    carries a different CURRENT reason_code than asserted. No state and no audit are
    written. (Malformed/unreadable state raises HoldStateInvalid / HoldStoreUnavailable
    and also blocks.)"""


class RetroFormalizationRefused(Exception):
    """The retrospective hold formalization was refused fail-closed: the live hold is
    absent/cleared, or its (rev, reason_code, effective_at) differs from the operator-
    asserted expectation. (Malformed/unreadable state raises HoldStateInvalid /
    HoldStoreUnavailable via ``read_hold`` and also blocks.) No audit is written."""


class LegacyHoldAdoptionRefused(Exception):
    """Adoption of a LEGACY (pre-schema-v1) operational-hold marker into a schema-v1
    ACTIVE hold was refused fail-closed: the marker is absent, is already schema-v1, or
    its legacy fields (reason_code / paused_at / status) differ from the operator-
    asserted expectation. No state is written and no audit is written."""


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


@dataclass(frozen=True)
class ReasonUpdateResult:
    strategy_id: int
    action: str  # would_update | updated | already_updated
    audit_id: int | None
    planned_blob: dict
    previous_rev: int
    new_rev: int


@dataclass(frozen=True)
class AdoptResult:
    strategy_id: int
    action: str  # would_adopt | adopted | already_adopted | already_adopted_and_cleared
    audit_id: int | None
    planned_blob: dict  # the schema-v1 blob that (would be) written
    legacy_marker: dict  # the preserved legacy marker (read-only echo)


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

    async def update_reason(
        self, strategy_id: int, *, expected_rev: int, expected_reason_code: str,
        new_reason_code: str, new_reason: str, updated_at: str, updated_by: str,
        actor_type: AuditActorType = AuditActorType.USER, actor_id: str | None = None,
        evidence_refs: list | None = None, source: str = REASON_UPDATE_SOURCE,
        apply: bool = True,
    ) -> ReasonUpdateResult:
        """Re-label an ACTIVE hold whose governing reason has changed, WITHOUT ever
        leaving the strategy unheld.

        Why this exists. ``place()`` refuses a different-reason active hold and directs
        the caller to "clear-and-place explicitly" — correct as a no-silent-replacement
        rule, but wrong for a *re-labelling*: clearing would momentarily unblock
        activation, emit a spurious CLEARED event, and detach the hold's lineage. This
        method keeps the hold continuously ACTIVE and records the relabel as its own
        governed mutation.

        Fail-closed preconditions (ALL required): the hold exists, status is ACTIVE, its
        ``_rev`` equals ``expected_rev``, and its CURRENT ``reason_code`` equals
        ``expected_reason_code``. ``effective_at``/``placed_at``/``placed_by`` and EVERY
        extra key on the stored blob (``legacy_marker``, evidence snapshots — keys the
        ``HoldRecord`` dataclass does not model and ``to_dict()`` would drop) are carried
        forward verbatim. ``_rev`` increments. The activation cooldown is not read,
        started, or reset.

        Idempotent: a hold already ACTIVE at ``new_reason_code`` is a no-op with no audit.
        With ``apply=False`` nothing is written and the planned blob is returned for
        dry-run review.
        """
        async with self._sf() as session, session.begin():
            raw = (
                await session.execute(
                    select(StrategyState.value).where(
                        StrategyState.strategy_id == strategy_id,
                        StrategyState.key == K_OPERATIONAL_HOLD,
                    )
                )
            ).scalars().first()
            cur = load_hold_record(raw)  # Invalid/Unavailable -> rollback, no audit
            if cur is None:
                raise HoldReasonUpdateRefused(f"strategy {strategy_id}: no hold to relabel")
            if cur.reason_code == new_reason_code and cur.is_active:
                return ReasonUpdateResult(strategy_id, "already_updated", None,
                                          cast("dict[str, Any]", raw), cur.rev, cur.rev)
            if not cur.is_active:
                raise HoldReasonUpdateRefused(
                    f"hold is {cur.status}, not ACTIVE — a cleared hold is not relabelled, "
                    f"it is re-placed under the new reason")
            if cur.rev != expected_rev:
                raise HoldReasonUpdateRefused(
                    f"stale relabel: expected rev {expected_rev}, found {cur.rev}")
            if cur.reason_code != expected_reason_code:
                raise HoldReasonUpdateRefused(
                    f"current reason_code {cur.reason_code!r} != expected "
                    f"{expected_reason_code!r}; adjudicate — do not relabel")

            new = HoldRecord(
                status=HoldStatus.ACTIVE, reason_code=new_reason_code, reason=new_reason,
                effective_at=cur.effective_at,      # UNCHANGED — the hold began when it began
                placed_at=cur.placed_at, placed_by=cur.placed_by, rev=cur.rev + 1,
                evidence_refs=list(evidence_refs) if evidence_refs is not None
                else list(cur.evidence_refs),
                approval_ref=cur.approval_ref, source=source,
            )
            blob = new.to_dict()
            # Carry forward every key the dataclass does not model, so a relabel can never
            # silently drop preserved provenance (legacy_marker, evidence_snapshot_sha256, …).
            assert isinstance(raw, dict)
            for k, v in raw.items():
                if k not in blob:
                    blob[k] = v
            blob["previous_reason_code"] = cur.reason_code
            if not apply:
                return ReasonUpdateResult(strategy_id, "would_update", None, blob,
                                          cur.rev, new.rev)

            # Byte-exact CAS: the UPDATE fires only if the stored value is STILL the exact
            # blob validated above. Any concurrent writer changes `value`, the WHERE misses,
            # rowcount is 0 → refuse with NO state and NO audit written.
            res = cast(
                "CursorResult[Any]",
                await session.execute(
                    update(StrategyState).where(
                        StrategyState.strategy_id == strategy_id,
                        StrategyState.key == K_OPERATIONAL_HOLD,
                        StrategyState.value == raw,
                    ).values(value=blob, updated_at=datetime.now(UTC))
                ),
            )
            if res.rowcount != 1:
                raise HoldReasonUpdateRefused(
                    "the hold changed between validation and write (concurrent mutation); "
                    "CAS failed — no state and no audit written")
            row = AuditLogger.write(
                session, actor_type=actor_type, actor_id=actor_id,
                action=AuditAction.STRATEGY_HOLD_REASON_UPDATED, target_type="strategy",
                target_id=strategy_id,
                payload={"strategy_id": strategy_id,
                         "old_reason_code": cur.reason_code, "new_reason_code": new_reason_code,
                         "reason": new_reason, "hold_remained_active": True,
                         "previous_rev": cur.rev, "new_rev": new.rev,
                         "effective_at": cur.effective_at, "effective_at_unchanged": True,
                         "updated_at": updated_at, "updated_by": updated_by, "source": source,
                         "evidence_refs": list(new.evidence_refs)},
            )
            await session.flush()  # populate row.id
            return ReasonUpdateResult(strategy_id, "updated", row.id, blob, cur.rev, new.rev)

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
        # `Session.execute` is statically typed as `Result`, but a DML statement yields a
        # `CursorResult` at runtime — and `rowcount` (the CAS witness) is the point here.
        res = cast(
            "CursorResult[Any]",
            await session.execute(
                update(StrategyState).where(
                    StrategyState.strategy_id == strategy_id,
                    StrategyState.key == K_OPERATIONAL_HOLD,
                    func.json_extract(StrategyState.value, "$._rev") == expected_rev,
                ).values(value=new_value, updated_at=datetime.now(UTC))
            ),
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


async def _read_raw_hold(session: AsyncSession, strategy_id: int) -> dict | None:
    """Read the RAW ``operational_hold`` value WITHOUT schema validation. Adoption must
    read a pre-schema-v1 marker that ``read_hold``/``load_hold_record`` would reject."""
    try:
        return (
            await session.execute(
                select(StrategyState.value).where(
                    StrategyState.strategy_id == strategy_id,
                    StrategyState.key == K_OPERATIONAL_HOLD,
                )
            )
        ).scalars().first()
    except SQLAlchemyError as exc:
        raise HoldStoreUnavailable(str(exc)) from exc


async def adopt_legacy_operational_hold(
    session: AsyncSession, *, strategy_id: int, expected_reason_code: str,
    expected_paused_at: str, expected_legacy_status: str = "PAUSED",
    placed_by: str, evidence_refs: list | None = None, approval_ref: str | None = None,
    actor_type: AuditActorType = AuditActorType.USER, actor_id: str | None = None,
    apply: bool = False,
) -> AdoptResult:
    """Adopt a LEGACY (pre-schema-v1) operational-hold marker into a canonical schema-v1
    ACTIVE hold, PRESERVING the full legacy marker, and emit exactly one retrospective
    ``STRATEGY_HOLD_PLACED``. This is the one governed migration for a hold that became
    effective before the hold schema existed (the acct-4 case): the marker is not
    parseable by ``read_hold`` (schema_version absent), so neither ``HoldService.place``
    (idempotent no-op / read_hold raises) nor ``formalize_retrospective_hold_placed``
    (read_hold raises) can operate on it, and it can never be ``clear``-ed until adopted.

    The resulting schema-v1 blob is ACTIVE (rev 1, ``effective_at`` = the legacy
    ``paused_at``, ``source=RETROSPECTIVE_FORMALIZATION``) and carries the entire original
    marker verbatim under a ``legacy_marker`` key — nothing is lost. The hold stays
    ACTIVE, so activation remains blocked; clearing is a separate, later step.

    Fail-closed refusals (raise ``LegacyHoldAdoptionRefused``, no writes): the marker is
    absent; is already schema-v1 but does NOT match this exact governed adoption (a
    conflict to adjudicate, never a silent success); its legacy ``(status, reason_code,
    paused_at)`` differ from the operator assertion; or the marker changed between
    validation and the value-CAS write. Idempotent only when the current schema-v1 record
    is PROVABLY this adoption: ``already_adopted`` (still ACTIVE) or
    ``already_adopted_and_cleared`` (adopted then legitimately cleared) — both no-ops with
    no second write/audit. The caller owns the transaction.
    """
    raw = await _read_raw_hold(session, strategy_id)
    if raw is None:
        raise LegacyHoldAdoptionRefused(f"strategy {strategy_id}: no operational_hold to adopt")
    if not isinstance(raw, dict):
        raise LegacyHoldAdoptionRefused(f"operational_hold is not an object: {type(raw).__name__}")

    if raw.get("schema_version") == HOLD_SCHEMA_VERSION:
        # Already schema-v1. The no-op must PROVE it is THIS governed adoption, not merely
        # any schema-v1 record that happens to carry a ``legacy_marker`` key (which could be
        # a manually-constructed / differently-parameterised / later-revised object). Require
        # the full adoption provenance to match the operator's assertion; anything else is a
        # conflict requiring adjudication, never a silent success.
        lm = raw.get("legacy_marker")
        is_this_adoption = (
            isinstance(lm, dict)
            and raw.get("source") == RETRO_SOURCE
            and raw.get("reason_code") == expected_reason_code
            and raw.get("effective_at") == expected_paused_at
            and lm.get("status") == expected_legacy_status
            and lm.get("reason_code") == expected_reason_code
            and lm.get("paused_at") == expected_paused_at
        )
        if not is_this_adoption:
            raise LegacyHoldAdoptionRefused(
                f"strategy {strategy_id}: operational_hold is already schema-v1 but does NOT "
                "match this governed adoption (source / reason_code / effective_at / "
                "legacy_marker mismatch); adjudicate — do not adopt"
            )
        assert isinstance(lm, dict)  # guaranteed by is_this_adoption; narrows for the type checker
        status = raw.get("status")
        if status == HoldStatus.ACTIVE.value:
            return AdoptResult(strategy_id, "already_adopted", None, raw, lm)
        if status == HoldStatus.CLEARED.value:
            # Adopted earlier and legitimately cleared since; NOT an active adoption.
            return AdoptResult(strategy_id, "already_adopted_and_cleared", None, raw, lm)
        raise LegacyHoldAdoptionRefused(
            f"strategy {strategy_id}: adopted hold has unexpected status {status!r}; adjudicate")

    # Validate the legacy marker matches the operator's assertion (fail-closed).
    if raw.get("status") != expected_legacy_status:
        raise LegacyHoldAdoptionRefused(
            f"legacy status {raw.get('status')!r} != expected {expected_legacy_status!r}")
    if raw.get("reason_code") != expected_reason_code:
        raise LegacyHoldAdoptionRefused(
            f"legacy reason_code {raw.get('reason_code')!r} != expected {expected_reason_code!r}")
    if raw.get("paused_at") != expected_paused_at:
        raise LegacyHoldAdoptionRefused(
            f"legacy paused_at {raw.get('paused_at')!r} != expected {expected_paused_at!r}")

    new = HoldRecord(
        status=HoldStatus.ACTIVE, reason_code=expected_reason_code, reason=raw.get("reason", ""),
        effective_at=expected_paused_at, placed_at=datetime.now(UTC).isoformat(),
        placed_by=placed_by, rev=1, evidence_refs=list(evidence_refs or []),
        approval_ref=approval_ref, source=RETRO_SOURCE,
    )
    blob = new.to_dict()
    blob["legacy_marker"] = raw  # preserve the entire original marker verbatim
    if not apply:
        return AdoptResult(strategy_id, "would_adopt", None, blob, raw)

    # GENUINE compare-and-set: the UPDATE fires only if the row's value is STILL byte-for-byte
    # the exact legacy marker we read and validated (``StrategyState.value == raw``) — not merely
    # the same (strategy_id, key) row. Any concurrent writer that replaced or modified the marker
    # (including a concurrent adoption, which sets a schema-v1 value) changes ``value``, so the
    # WHERE misses → rowcount 0 → refuse: NO overwrite, NO audit. This is what makes "the marker
    # changed since read" a mechanism, not just a message.
    res = cast(
        "CursorResult[Any]",
        await session.execute(
            update(StrategyState).where(
                StrategyState.strategy_id == strategy_id,
                StrategyState.key == K_OPERATIONAL_HOLD,
                StrategyState.value == raw,
            ).values(value=blob, updated_at=datetime.now(UTC))
        ),
    )
    if res.rowcount != 1:
        raise LegacyHoldAdoptionRefused(
            "the legacy marker changed between validation and write (concurrent modification or "
            "adoption); CAS failed — no state and no audit written"
        )
    row = AuditLogger.write(
        session, actor_type=actor_type, actor_id=actor_id,
        action=AuditAction.STRATEGY_HOLD_PLACED, target_type="strategy", target_id=strategy_id,
        payload={"strategy_id": strategy_id, "reason_code": expected_reason_code,
                 "reason": new.reason, "rev": 1, "effective_at": expected_paused_at,
                 "placed_by": placed_by, "source": RETRO_SOURCE, "retrospective": True,
                 "adopted_from_legacy": True, "evidence_refs": list(evidence_refs or []),
                 "approval_ref": approval_ref},
    )
    await session.flush()  # populate row.id
    return AdoptResult(strategy_id, "adopted", row.id, blob, raw)


__all__ = [
    "AdoptResult",
    "FormalizeResult",
    "LegacyHoldAdoptionRefused",
    "RETRO_SOURCE",
    "RetroFormalizationRefused",
    "adopt_legacy_operational_hold",
    "formalize_retrospective_hold_placed",
    "HoldMutationResult",
    "HoldReasonUpdateRefused",
    "HoldService",
    "REASON_UPDATE_SOURCE",
    "ReasonUpdateResult",
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
