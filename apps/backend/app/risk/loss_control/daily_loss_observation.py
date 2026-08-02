"""ADR-0043 canary — shared daily-loss observation + central surface policy mapper.

Binding is resolved from durable EFFECTIVE Start A authorizations independently of
baseline rows. Missing baseline under an effective binding is UNAVAILABLE (fail closed),
never a silent return to legacy last_equity / cumulative control paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.risk_canary_session_baseline import (
    BASELINE_SOURCE_SESSION_OPEN_BROKER_EQUITY,
    CANARY_BASELINE_STATUS_ACTIVE,
    RiskCanarySessionBaseline,
)
from app.db.models.risk_canary_start_a_authorization import (
    START_A_STATUS_EFFECTIVE,
    RiskCanaryStartAAuthorization,
)
from app.risk.loss_control.start_a_baseline import (
    EXPECTED_BROKER_ACCOUNT_ID,
    authorization_body_sha256,
)


class ObservationStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    CONFLICT = "CONFLICT"
    INVALID = "INVALID"


class SurfaceAction(StrEnum):
    EVALUATE = "EVALUATE"
    REFUSE = "REFUSE"
    REJECT = "REJECT"
    PERMIT_REDUCTION = "PERMIT_REDUCTION"
    FAIL_OR_INCOMPLETE = "FAIL_OR_INCOMPLETE"
    FAIL = "FAIL"
    PERMIT_REDUCTION_ADR0042_ONLY = "PERMIT_REDUCTION_ADR0042_ONLY"


@dataclass(frozen=True)
class EffectiveCanaryBinding:
    """Durable canary freeze binding — independent of baseline row presence."""

    start_a_id: str
    freeze_id: str
    freeze_body_sha256: str
    broker_account_id: str
    workbench_account_id: int
    configuration_digest: str
    image_digest: str
    commit_sha: str
    authorized_session_date: str
    design_version: str
    applicable_daily_loss_limit: Decimal
    authorization_body_sha256: str
    authorization_status: str


@dataclass(frozen=True)
class DailyLossObservation:
    status: ObservationStatus
    basis_source: str | None
    baseline_id: int | None
    raw_response_hash: str | None
    projection_hash: str | None
    session_date: str | None
    baseline_equity: Decimal | None  # exact
    baseline_equity_canonical_4dp: str | None
    current_equity: Decimal | None
    daily_pnl: Decimal | None  # exact current - exact baseline when AVAILABLE
    reason_code: str | None
    freeze_id: str | None
    design_version: str | None
    start_a_id: str | None
    configuration_digest: str | None
    canary_model_a: bool
    binding: EffectiveCanaryBinding | None


def map_surface_action(status: ObservationStatus, *, surface: str) -> SurfaceAction:
    """Single policy mapper — every consumer must use this."""
    table: dict[tuple[ObservationStatus, str], SurfaceAction] = {
        (ObservationStatus.AVAILABLE, "phase0"): SurfaceAction.EVALUATE,
        (ObservationStatus.AVAILABLE, "new_risk"): SurfaceAction.EVALUATE,
        (ObservationStatus.AVAILABLE, "verified_reduction"): SurfaceAction.PERMIT_REDUCTION,
        (ObservationStatus.AVAILABLE, "recovery"): SurfaceAction.EVALUATE,
        (ObservationStatus.UNAVAILABLE, "phase0"): SurfaceAction.REFUSE,
        (ObservationStatus.UNAVAILABLE, "new_risk"): SurfaceAction.REJECT,
        (ObservationStatus.UNAVAILABLE, "verified_reduction"): SurfaceAction.PERMIT_REDUCTION,
        (ObservationStatus.UNAVAILABLE, "recovery"): SurfaceAction.FAIL_OR_INCOMPLETE,
        (ObservationStatus.STALE, "phase0"): SurfaceAction.REFUSE,
        (ObservationStatus.STALE, "new_risk"): SurfaceAction.REJECT,
        (ObservationStatus.STALE, "verified_reduction"): SurfaceAction.PERMIT_REDUCTION,
        (ObservationStatus.STALE, "recovery"): SurfaceAction.FAIL_OR_INCOMPLETE,
        (ObservationStatus.CONFLICT, "phase0"): SurfaceAction.REFUSE,
        (ObservationStatus.CONFLICT, "new_risk"): SurfaceAction.REJECT,
        (ObservationStatus.CONFLICT, "verified_reduction"): SurfaceAction.PERMIT_REDUCTION_ADR0042_ONLY,
        (ObservationStatus.CONFLICT, "recovery"): SurfaceAction.FAIL,
        (ObservationStatus.INVALID, "phase0"): SurfaceAction.REFUSE,
        (ObservationStatus.INVALID, "new_risk"): SurfaceAction.REJECT,
        (ObservationStatus.INVALID, "verified_reduction"): SurfaceAction.PERMIT_REDUCTION_ADR0042_ONLY,
        (ObservationStatus.INVALID, "recovery"): SurfaceAction.FAIL,
    }
    try:
        return table[(status, surface)]
    except KeyError as e:
        raise ValueError(f"unknown surface/status: {surface}/{status}") from e


def _obs(
    *,
    status: ObservationStatus,
    reason_code: str | None,
    binding: EffectiveCanaryBinding | None,
    current_equity: Decimal | None,
    session_date: str | None,
    row: RiskCanarySessionBaseline | None = None,
    daily_pnl: Decimal | None = None,
) -> DailyLossObservation:
    return DailyLossObservation(
        status=status,
        basis_source=row.baseline_source if row is not None else (
            BASELINE_SOURCE_SESSION_OPEN_BROKER_EQUITY if binding is not None else None
        ),
        baseline_id=row.id if row is not None else None,
        raw_response_hash=row.raw_response_sha256 if row is not None else None,
        projection_hash=row.projection_sha256 if row is not None else None,
        session_date=session_date or (binding.authorized_session_date if binding else None),
        baseline_equity=Decimal(row.baseline_equity) if row is not None else None,
        baseline_equity_canonical_4dp=(
            row.baseline_equity_canonical_4dp if row is not None else None
        ),
        current_equity=current_equity,
        daily_pnl=daily_pnl,
        reason_code=reason_code,
        freeze_id=binding.freeze_id if binding else (row.freeze_id if row else None),
        design_version=(
            binding.design_version if binding else (row.design_version if row else None)
        ),
        start_a_id=binding.start_a_id if binding else (row.start_a_id if row else None),
        configuration_digest=(
            binding.configuration_digest
            if binding
            else (row.configuration_digest if row else None)
        ),
        canary_model_a=True,
        binding=binding,
    )


def binding_from_auth_row(row: RiskCanaryStartAAuthorization) -> EffectiveCanaryBinding:
    return EffectiveCanaryBinding(
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
        authorization_body_sha256=row.authorization_body_sha256,
        authorization_status=row.authorization_status,
    )


async def resolve_effective_canary_binding(
    session: AsyncSession,
    account_id: int,
    session_date: str,
) -> EffectiveCanaryBinding | ObservationStatus | None:
    """Resolve durable EFFECTIVE Start A binding for account + ET session date.

    Returns:
      EffectiveCanaryBinding — single verified EFFECTIVE authorization;
      ObservationStatus.CONFLICT — multiple EFFECTIVE or body-hash mismatch;
      None — no canary binding (legacy paths allowed).
    """
    rows = (
        await session.scalars(
            select(RiskCanaryStartAAuthorization).where(
                RiskCanaryStartAAuthorization.workbench_account_id == account_id,
                RiskCanaryStartAAuthorization.authorized_session_date == session_date,
                RiskCanaryStartAAuthorization.authorization_status == START_A_STATUS_EFFECTIVE,
            )
        )
    ).all()
    if not rows:
        return None
    if len(rows) > 1:
        return ObservationStatus.CONFLICT

    row = rows[0]
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
        return ObservationStatus.CONFLICT
    if row.broker_account_id != EXPECTED_BROKER_ACCOUNT_ID:
        return ObservationStatus.CONFLICT
    return binding_from_auth_row(row)


async def load_bound_model_a_baseline(
    session: AsyncSession,
    binding: EffectiveCanaryBinding,
) -> RiskCanarySessionBaseline | list[RiskCanarySessionBaseline] | None:
    """Load baseline bound to the exact current freeze / Start A / config identity."""
    rows = (
        await session.scalars(
            select(RiskCanarySessionBaseline).where(
                RiskCanarySessionBaseline.account_id == binding.workbench_account_id,
                RiskCanarySessionBaseline.market_session_date == binding.authorized_session_date,
                RiskCanarySessionBaseline.design_version == binding.design_version,
                RiskCanarySessionBaseline.freeze_id == binding.freeze_id,
                RiskCanarySessionBaseline.start_a_id == binding.start_a_id,
                RiskCanarySessionBaseline.configuration_digest == binding.configuration_digest,
                RiskCanarySessionBaseline.status == CANARY_BASELINE_STATUS_ACTIVE,
                RiskCanarySessionBaseline.baseline_source
                == BASELINE_SOURCE_SESSION_OPEN_BROKER_EQUITY,
            )
        )
    ).all()
    if not rows:
        return None
    if len(rows) > 1:
        return list(rows)
    return rows[0]


async def observe_model_a_daily_loss(
    session: AsyncSession,
    account_id: int,
    *,
    current_equity: Decimal | None,
    session_date: str | None,
) -> DailyLossObservation | None:
    """Model A observation when a durable canary binding exists; else None (legacy OK).

    Effective binding + missing/invalid baseline → structured fail-closed status.
    Never falls back to last_equity or cumulative under an effective binding.
    """
    if session_date is None:
        # Without a session date we cannot resolve binding identity; treat as no binding.
        return None

    resolved = await resolve_effective_canary_binding(session, account_id, session_date)
    if resolved is None:
        return None
    if resolved is ObservationStatus.CONFLICT:
        return _obs(
            status=ObservationStatus.CONFLICT,
            reason_code="CANARY_BINDING_CONFLICT",
            binding=None,
            current_equity=current_equity,
            session_date=session_date,
        )

    binding = resolved
    row = await load_bound_model_a_baseline(session, binding)
    if row is None:
        return _obs(
            status=ObservationStatus.UNAVAILABLE,
            reason_code="MODEL_A_BASELINE_MISSING",
            binding=binding,
            current_equity=current_equity,
            session_date=session_date,
        )
    if isinstance(row, list):
        return _obs(
            status=ObservationStatus.CONFLICT,
            reason_code="MULTIPLE_BOUND_MODEL_A_BASELINES",
            binding=binding,
            current_equity=current_equity,
            session_date=session_date,
        )

    if (
        row.freeze_body_sha256 != binding.freeze_body_sha256
        or row.image_digest != binding.image_digest
        or row.commit_sha != binding.commit_sha
        or row.broker_account_id != binding.broker_account_id
    ):
        return _obs(
            status=ObservationStatus.CONFLICT,
            reason_code="BASELINE_BINDING_MISMATCH",
            binding=binding,
            current_equity=current_equity,
            session_date=session_date,
            row=row,
        )

    if row.broker_account_id != EXPECTED_BROKER_ACCOUNT_ID:
        return _obs(
            status=ObservationStatus.CONFLICT,
            reason_code="BROKER_IDENTITY_MISMATCH",
            binding=binding,
            current_equity=current_equity,
            session_date=session_date,
            row=row,
        )

    if not row.raw_response_json or not row.raw_response_sha256 or not row.projection_sha256:
        return _obs(
            status=ObservationStatus.INVALID,
            reason_code="BASELINE_EVIDENCE_INCOMPLETE",
            binding=binding,
            current_equity=current_equity,
            session_date=session_date,
            row=row,
        )

    if current_equity is None:
        return _obs(
            status=ObservationStatus.UNAVAILABLE,
            reason_code="CURRENT_EQUITY_MISSING",
            binding=binding,
            current_equity=None,
            session_date=session_date,
            row=row,
        )

    daily_pnl = current_equity - Decimal(row.baseline_equity)
    return _obs(
        status=ObservationStatus.AVAILABLE,
        reason_code=None,
        binding=binding,
        current_equity=current_equity,
        session_date=session_date,
        row=row,
        daily_pnl=daily_pnl,
    )


async def load_active_model_a_baseline(
    session: AsyncSession,
    account_id: int,
    session_date: str,
) -> RiskCanarySessionBaseline | list[RiskCanarySessionBaseline] | None:
    """Bound lookup via effective Start A authorization (not unbound account/date)."""
    resolved = await resolve_effective_canary_binding(session, account_id, session_date)
    if resolved is None or resolved is ObservationStatus.CONFLICT:
        return None
    return await load_bound_model_a_baseline(session, resolved)
