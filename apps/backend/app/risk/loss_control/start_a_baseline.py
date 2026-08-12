"""ADR-0043 canary Model A — Start A authoritative baseline capture.

Capture accepts a durable ``start_a_id``, loads and verifies the sealed authorization
row, and never trusts caller-supplied EFFECTIVE / hash / identity fields.
Opening window: America/New_York [09:30:00, 09:35:00). Missed window → REFUSED.
Shadow ``risk_session_baselines`` rows are never upgraded.

Transaction contract: ``session`` must be dedicated and clean (no unrelated
pending new/dirty/deleted objects). Capture commits only on success/reuse audit;
any refusal after writes begin rolls back before returning.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, time
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.logger import AuditAction, AuditActorType, AuditLogger
from app.db.models.risk_canary_session_baseline import (
    BASELINE_SOURCE_SESSION_OPEN_BROKER_EQUITY,
    CANARY_BASELINE_STATUS_ACTIVE,
    RiskCanarySessionBaseline,
)
from app.db.models.risk_canary_start_a_authorization import (
    START_A_STATUS_EFFECTIVE,
    RiskCanaryStartAAuthorization,
)

ET = ZoneInfo("America/New_York")
OPEN_WINDOW_START = time(9, 30, 0)
OPEN_WINDOW_END = time(9, 35, 0)  # exclusive
CAPTURE_MECHANISM_VERSION = "ADR0043-CANARY-MODEL-A-CAPTURE-1.0"
EXPECTED_BROKER_ACCOUNT_ID = "PA34USW0Q8UO"


class StartACaptureRefused(Exception):
    """Authoritative baseline was not persisted; reason is machine-readable."""

    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"{reason_code}: {detail}" if detail else reason_code)


@dataclass(frozen=True)
class VerifiedStartAAuthorization:
    """Read-only view of a durable, hash-verified Start A authorization row."""

    start_a_id: str
    freeze_id: str
    freeze_body_sha256: str
    broker_account_id: str
    workbench_account_id: int
    configuration_digest: str
    image_digest: str
    commit_sha: str
    authorized_session_date: str  # YYYY-MM-DD ET
    design_version: str
    applicable_daily_loss_limit: Decimal
    authorization_status: str
    authorization_body_sha256: str


# Backward-compatible name; callers must not fabricate EFFECTIVE — use seal + load.
StartAAuthorization = VerifiedStartAAuthorization


@dataclass(frozen=True)
class StartACaptureResult:
    baseline_id: int
    reused: bool
    raw_response_sha256: str
    projection_sha256: str
    baseline_equity: Decimal
    market_session_date: str


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def authorization_body_sha256(
    *,
    start_a_id: str,
    freeze_id: str,
    freeze_body_sha256: str,
    broker_account_id: str,
    workbench_account_id: int,
    configuration_digest: str,
    image_digest: str,
    commit_sha: str,
    authorized_session_date: str,
    design_version: str,
    applicable_daily_loss_limit: Decimal,
    authorization_status: str,
) -> str:
    # Numeric(20,4) round-trips as 500.0000; canonicalize so seal/verify agree.
    limit_s = format(
        Decimal(applicable_daily_loss_limit).quantize(Decimal("0.0001")),
        "f",
    )
    payload = {
        "applicable_daily_loss_limit": limit_s,
        "authorization_status": authorization_status,
        "authorized_session_date": authorized_session_date,
        "broker_account_id": broker_account_id,
        "commit_sha": commit_sha,
        "configuration_digest": configuration_digest,
        "design_version": design_version,
        "freeze_body_sha256": freeze_body_sha256,
        "freeze_id": freeze_id,
        "image_digest": image_digest,
        "start_a_id": start_a_id,
        "workbench_account_id": workbench_account_id,
    }
    return _sha256_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


async def seal_start_a_authorization(
    session: AsyncSession,
    *,
    start_a_id: str,
    freeze_id: str,
    freeze_body_sha256: str,
    broker_account_id: str,
    workbench_account_id: int,
    configuration_digest: str,
    image_digest: str,
    commit_sha: str,
    authorized_session_date: str,
    design_version: str,
    applicable_daily_loss_limit: Decimal,
    authorization_status: str = START_A_STATUS_EFFECTIVE,
    created_by: str = "SYSTEM",
    now: datetime | None = None,
) -> RiskCanaryStartAAuthorization:
    """Persist a durable Start A authorization with sealed body hash.

    Issuance path for tests and future Start A tooling — not caller-fabricated at capture.
    """
    if broker_account_id != EXPECTED_BROKER_ACCOUNT_ID:
        raise StartACaptureRefused(
            "BROKER_IDENTITY_MISMATCH",
            f"expected={EXPECTED_BROKER_ACCOUNT_ID} got={broker_account_id}",
        )
    if len(freeze_body_sha256) != 64:
        raise StartACaptureRefused("FREEZE_BODY_HASH_INVALID")
    if authorization_status != START_A_STATUS_EFFECTIVE:
        # Sealing non-EFFECTIVE is allowed for DRAFT records, but capture will refuse them.
        pass
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise StartACaptureRefused("TIMESTAMP_NAIVE", "now must be timezone-aware")
    body_hash = authorization_body_sha256(
        start_a_id=start_a_id,
        freeze_id=freeze_id,
        freeze_body_sha256=freeze_body_sha256,
        broker_account_id=broker_account_id,
        workbench_account_id=workbench_account_id,
        configuration_digest=configuration_digest,
        image_digest=image_digest,
        commit_sha=commit_sha,
        authorized_session_date=authorized_session_date,
        design_version=design_version,
        applicable_daily_loss_limit=applicable_daily_loss_limit,
        authorization_status=authorization_status,
    )
    row = RiskCanaryStartAAuthorization(
        start_a_id=start_a_id,
        freeze_id=freeze_id,
        freeze_body_sha256=freeze_body_sha256,
        broker_account_id=broker_account_id,
        workbench_account_id=workbench_account_id,
        configuration_digest=configuration_digest,
        image_digest=image_digest,
        commit_sha=commit_sha,
        authorized_session_date=authorized_session_date,
        design_version=design_version,
        applicable_daily_loss_limit=applicable_daily_loss_limit,
        authorization_status=authorization_status,
        authorization_body_sha256=body_hash,
        created_at=now,
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    return row


async def load_and_verify_start_a_authorization(
    session: AsyncSession,
    start_a_id: str,
) -> VerifiedStartAAuthorization:
    """Load durable Start A by ID and verify sealed body hash + EFFECTIVE status."""
    row = await session.scalar(
        select(RiskCanaryStartAAuthorization).where(
            RiskCanaryStartAAuthorization.start_a_id == start_a_id
        )
    )
    if row is None:
        raise StartACaptureRefused("START_A_NOT_FOUND", start_a_id)
    if row.authorization_status != START_A_STATUS_EFFECTIVE:
        raise StartACaptureRefused(
            "START_A_NOT_EFFECTIVE", f"status={row.authorization_status}"
        )
    expected = authorization_body_sha256(
        start_a_id=row.start_a_id,
        freeze_id=row.freeze_id,
        freeze_body_sha256=row.freeze_body_sha256,
        broker_account_id=row.broker_account_id,
        workbench_account_id=row.workbench_account_id,
        configuration_digest=row.configuration_digest,
        image_digest=row.image_digest,
        commit_sha=row.commit_sha,
        authorized_session_date=row.authorized_session_date,
        design_version=row.design_version,
        applicable_daily_loss_limit=Decimal(row.applicable_daily_loss_limit),
        authorization_status=row.authorization_status,
    )
    if expected != row.authorization_body_sha256:
        raise StartACaptureRefused("START_A_BODY_HASH_MISMATCH")
    if row.broker_account_id != EXPECTED_BROKER_ACCOUNT_ID:
        raise StartACaptureRefused(
            "BROKER_IDENTITY_MISMATCH",
            f"expected={EXPECTED_BROKER_ACCOUNT_ID} got={row.broker_account_id}",
        )
    if not row.freeze_id or len(row.freeze_body_sha256) != 64:
        raise StartACaptureRefused("START_A_BINDING_INCOMPLETE")
    return VerifiedStartAAuthorization(
        start_a_id=row.start_a_id,
        freeze_id=row.freeze_id,
        freeze_body_sha256=row.freeze_body_sha256,
        broker_account_id=row.broker_account_id,
        workbench_account_id=row.workbench_account_id,
        configuration_digest=row.configuration_digest,
        image_digest=row.image_digest,
        commit_sha=row.commit_sha,
        authorized_session_date=row.authorized_session_date,
        design_version=row.design_version,
        applicable_daily_loss_limit=Decimal(row.applicable_daily_loss_limit),
        authorization_status=row.authorization_status,
        authorization_body_sha256=row.authorization_body_sha256,
    )


def parse_broker_equity(raw: Any) -> tuple[str, Decimal]:
    """Return (raw_string, exact Decimal). Reject illegal forms."""
    if raw is None:
        raise StartACaptureRefused("EQUITY_NULL")
    if isinstance(raw, bool):
        raise StartACaptureRefused("EQUITY_INVALID_TYPE", "bool")
    raw_s = str(raw).strip()
    if not raw_s or raw_s.lower() in {"nan", "inf", "-inf", "+inf"}:
        raise StartACaptureRefused("EQUITY_INVALID", raw_s)
    if "e" in raw_s.lower():
        raise StartACaptureRefused("EQUITY_SCIENTIFIC_NOTATION", raw_s)
    if raw_s in {"-0", "-0.0", "-0.00", "-0.0000"}:
        raise StartACaptureRefused("EQUITY_NEGATIVE_ZERO", raw_s)
    try:
        exact = Decimal(raw_s)
    except (InvalidOperation, ValueError) as e:
        raise StartACaptureRefused("EQUITY_PARSE_FAILED", raw_s) from e
    if not exact.is_finite():
        raise StartACaptureRefused("EQUITY_NOT_FINITE", raw_s)
    return raw_s, exact


def canonical_4dp(exact: Decimal) -> str:
    """Serialization-only quantization; control P&L must use exact Decimal."""
    q = exact.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
    return format(q, "f")


def et_session_date(now: datetime) -> str:
    return now.astimezone(ET).date().isoformat()


def in_opening_window(local_receipt: datetime) -> bool:
    local_et = local_receipt.astimezone(ET)
    t = local_et.time().replace(tzinfo=None)
    return OPEN_WINDOW_START <= t < OPEN_WINDOW_END


def parse_broker_timestamp(raw: Any) -> datetime:
    """Parse Alpaca-style timestamps (datetime or ISO-8601 string)."""
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=UTC)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            raise StartACaptureRefused("BROKER_TIMESTAMP_EMPTY")
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError as e:
            raise StartACaptureRefused("BROKER_TIMESTAMP_PARSE_FAILED", raw) from e
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    raise StartACaptureRefused("BROKER_TIMESTAMP_INVALID_TYPE", type(raw).__name__)


def _assert_session_clean(session: AsyncSession) -> None:
    if session.new or session.dirty or session.deleted:
        raise StartACaptureRefused(
            "SESSION_NOT_CLEAN",
            "capture requires a dedicated session with no unrelated pending changes",
        )


def _canonical_projection(
    *,
    auth: VerifiedStartAAuthorization,
    session_date: str,
    equity_raw: str,
    equity_exact: Decimal,
    equity_4dp: str,
    local_receipt_at: datetime,
    broker_response_at: datetime | None,
    raw_sha: str,
) -> str:
    payload = {
        "account_id": auth.workbench_account_id,
        "applicable_daily_loss_limit": format(auth.applicable_daily_loss_limit, "f"),
        "baseline_equity_canonical_4dp": equity_4dp,
        "baseline_equity_exact": format(equity_exact, "f"),
        "baseline_equity_raw": equity_raw,
        "baseline_source": BASELINE_SOURCE_SESSION_OPEN_BROKER_EQUITY,
        "broker_account_id": auth.broker_account_id,
        "broker_response_at": broker_response_at.isoformat() if broker_response_at else None,
        "commit_sha": auth.commit_sha,
        "configuration_digest": auth.configuration_digest,
        "design_version": auth.design_version,
        "freeze_body_sha256": auth.freeze_body_sha256,
        "freeze_id": auth.freeze_id,
        "image_digest": auth.image_digest,
        "local_receipt_at": local_receipt_at.isoformat(),
        "market_session_date": session_date,
        "raw_response_sha256": raw_sha,
        "session_timezone": "America/New_York",
        "start_a_id": auth.start_a_id,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _audit_capture(
    session: AsyncSession,
    *,
    outcome: str,
    reason_code: str | None,
    auth: VerifiedStartAAuthorization | None,
    start_a_id: str,
    session_date: str | None,
    baseline_id: int | None,
    actor_id: str,
) -> None:
    AuditLogger.write(
        session,
        actor_type=AuditActorType.SYSTEM,
        actor_id=actor_id,
        action=AuditAction.CANARY_MODEL_A_BASELINE_CAPTURE,
        target_type="account",
        target_id=auth.workbench_account_id if auth is not None else 0,
        payload={
            "outcome": outcome,
            "reason_code": reason_code,
            "start_a_id": start_a_id,
            "freeze_id": auth.freeze_id if auth is not None else None,
            "session_date": session_date,
            "baseline_id": baseline_id,
            "broker_account_id": auth.broker_account_id if auth is not None else None,
            "configuration_digest": auth.configuration_digest if auth is not None else None,
            "design_version": auth.design_version if auth is not None else None,
        },
    )


async def capture_model_a_baseline(
    session: AsyncSession,
    *,
    start_a_id: str,
    broker_account_payload: dict[str, Any],
    now: datetime | None = None,
    dry_run: bool = False,
    actor_id: str = "start_a_capture",
) -> StartACaptureResult:
    """Persist authoritative Model A baseline or refuse.

    Loads Start A by ``start_a_id`` from durable storage. ``dry_run`` validates without
    persisting. Session must be clean/dedicated; commits on success.
    """
    auth: VerifiedStartAAuthorization | None = None
    session_date: str | None = None
    wrote = False
    try:
        _assert_session_clean(session)
        auth = await load_and_verify_start_a_authorization(session, start_a_id)
        # Identity map may mark the loaded row; expunge so SESSION_NOT_CLEAN stays meaningful
        # for subsequent unrelated dirty detection isn't needed mid-capture.

        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            raise StartACaptureRefused("TIMESTAMP_NAIVE", "now must be timezone-aware")

        local_receipt = now
        session_date = et_session_date(local_receipt)
        if session_date != auth.authorized_session_date:
            raise StartACaptureRefused(
                "SESSION_DATE_MISMATCH",
                f"authorized={auth.authorized_session_date} actual={session_date}",
            )
        if not in_opening_window(local_receipt):
            raise StartACaptureRefused(
                "OUTSIDE_OPENING_WINDOW",
                f"local_receipt_et={local_receipt.astimezone(ET).isoformat()}",
            )

        payload_account_id = broker_account_payload.get("id")
        if payload_account_id is None:
            raise StartACaptureRefused("BROKER_PAYLOAD_ACCOUNT_ID_MISSING")
        if str(payload_account_id) != auth.broker_account_id:
            raise StartACaptureRefused(
                "BROKER_PAYLOAD_ACCOUNT_ID_MISMATCH",
                f"payload={payload_account_id} auth={auth.broker_account_id}",
            )

        equity_raw, equity_exact = parse_broker_equity(broker_account_payload.get("equity"))
        equity_4dp = canonical_4dp(equity_exact)

        broker_response_at: datetime | None = None
        for key in ("timestamp", "created_at", "updated_at"):
            if key in broker_account_payload and broker_account_payload[key]:
                broker_response_at = parse_broker_timestamp(broker_account_payload[key])
                break
        if broker_response_at is not None:
            broker_et_date = broker_response_at.astimezone(ET).date().isoformat()
            if broker_et_date != auth.authorized_session_date:
                raise StartACaptureRefused(
                    "SESSION_DATE_MISMATCH",
                    f"broker_ts_date={broker_et_date} authorized={auth.authorized_session_date}",
                )
            if not in_opening_window(broker_response_at):
                raise StartACaptureRefused(
                    "TIMESTAMP_WINDOW_CONFLICT",
                    f"broker_ts_et={broker_response_at.astimezone(ET).isoformat()}",
                )

        raw_json = json.dumps(
            broker_account_payload, sort_keys=True, separators=(",", ":"), default=str
        )
        raw_sha = _sha256_text(raw_json)
        projection = _canonical_projection(
            auth=auth,
            session_date=session_date,
            equity_raw=equity_raw,
            equity_exact=equity_exact,
            equity_4dp=equity_4dp,
            local_receipt_at=local_receipt,
            broker_response_at=broker_response_at,
            raw_sha=raw_sha,
        )
        proj_sha = _sha256_text(projection)

        if dry_run:
            raise StartACaptureRefused(
                "DRY_RUN_OK",
                f"would_persist equity={equity_raw} raw_sha={raw_sha} proj_sha={proj_sha}",
            )

        existing = await session.scalar(
            select(RiskCanarySessionBaseline).where(
                RiskCanarySessionBaseline.account_id == auth.workbench_account_id,
                RiskCanarySessionBaseline.market_session_date == session_date,
                RiskCanarySessionBaseline.design_version == auth.design_version,
                RiskCanarySessionBaseline.freeze_id == auth.freeze_id,
            )
        )
        if existing is not None:
            if (
                existing.raw_response_sha256 == raw_sha
                and existing.broker_account_id == auth.broker_account_id
                and existing.configuration_digest == auth.configuration_digest
                and existing.image_digest == auth.image_digest
                and existing.start_a_id == auth.start_a_id
                and existing.freeze_body_sha256 == auth.freeze_body_sha256
                and existing.status == CANARY_BASELINE_STATUS_ACTIVE
            ):
                _audit_capture(
                    session,
                    outcome="REUSED",
                    reason_code=None,
                    auth=auth,
                    start_a_id=start_a_id,
                    session_date=session_date,
                    baseline_id=existing.id,
                    actor_id=actor_id,
                )
                await session.commit()
                return StartACaptureResult(
                    baseline_id=existing.id,
                    reused=True,
                    raw_response_sha256=existing.raw_response_sha256,
                    projection_sha256=existing.projection_sha256,
                    baseline_equity=existing.baseline_equity,
                    market_session_date=existing.market_session_date,
                )
            raise StartACaptureRefused(
                "BASELINE_IDENTITY_CONFLICT",
                f"existing_id={existing.id}",
            )

        persisted_at = datetime.now(UTC)
        row = RiskCanarySessionBaseline(
            account_id=auth.workbench_account_id,
            broker_account_id=auth.broker_account_id,
            market_session_date=session_date,
            session_timezone="America/New_York",
            baseline_equity=equity_exact,
            baseline_equity_raw=equity_raw,
            baseline_equity_canonical_4dp=equity_4dp,
            baseline_source=BASELINE_SOURCE_SESSION_OPEN_BROKER_EQUITY,
            broker_response_at=broker_response_at,
            local_receipt_at=local_receipt,
            persisted_at=persisted_at,
            raw_response_json=raw_json,
            raw_response_sha256=raw_sha,
            projection_json=projection,
            projection_sha256=proj_sha,
            raw_object_ref=None,
            design_version=auth.design_version,
            freeze_id=auth.freeze_id,
            start_a_id=auth.start_a_id,
            freeze_body_sha256=auth.freeze_body_sha256,
            configuration_digest=auth.configuration_digest,
            image_digest=auth.image_digest,
            commit_sha=auth.commit_sha,
            applicable_daily_loss_limit=auth.applicable_daily_loss_limit,
            capture_mechanism_version=CAPTURE_MECHANISM_VERSION,
            status=CANARY_BASELINE_STATUS_ACTIVE,
        )
        session.add(row)
        wrote = True
        await session.flush()
        if not row.raw_response_json or not row.raw_response_sha256 or not row.projection_sha256:
            raise StartACaptureRefused("PARTIAL_WRITE_GUARD")
        _audit_capture(
            session,
            outcome="CAPTURED",
            reason_code=None,
            auth=auth,
            start_a_id=start_a_id,
            session_date=session_date,
            baseline_id=row.id,
            actor_id=actor_id,
        )
        await session.commit()
        await session.refresh(row)
        return StartACaptureResult(
            baseline_id=row.id,
            reused=False,
            raw_response_sha256=row.raw_response_sha256,
            projection_sha256=row.projection_sha256,
            baseline_equity=row.baseline_equity,
            market_session_date=row.market_session_date,
        )
    except StartACaptureRefused as e:
        if wrote:
            await session.rollback()
        # Durable refusal audit (including dry-run) on a clean transaction.
        if e.reason_code != "SESSION_NOT_CLEAN":
            try:
                if wrote:
                    pass  # already rolled back
                elif session.new or session.dirty or session.deleted:
                    await session.rollback()
                _audit_capture(
                    session,
                    outcome="REFUSED",
                    reason_code=e.reason_code,
                    auth=auth,
                    start_a_id=start_a_id,
                    session_date=session_date,
                    baseline_id=None,
                    actor_id=actor_id,
                )
                await session.commit()
            except Exception:
                await session.rollback()
        raise
