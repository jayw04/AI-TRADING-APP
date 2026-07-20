"""ADR 0043 PR4 — the loss-control GATE: the thin orchestration between the persisted state machine
and the risk engine.

Keeps ``RiskEngine.evaluate`` free of persistence queries and mode branching. Given the account and
the order's already-established verified-reduction status, it loads the persisted loss-control state
(NEVER bootstrapping it), computes the per-order outcome via the pure state machine, classifies the
divergence from the legacy decision, and returns a structured result the engine acts on by mode:

* OFF     — the engine never calls this.
* SHADOW  — the result is non-authoritative; the engine emits comparison evidence and keeps the
            legacy decision. A gate error becomes ERROR evidence, not an order failure.
* ENFORCE — the result is authoritative at the gate; the engine combines it by the precedence ladder
            and NEVER lets it weaken a stricter legacy result. A gate error fails closed.

It reads only; it neither persists transitions (the engine fires those via the service) nor mutates
any decision itself. ``CancelledError`` (a ``BaseException``) is never swallowed.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import LossControlMode
from app.risk.loss_control import constants as C
from app.risk.loss_control import state_machine as sm
from app.risk.loss_control.service import LossControlService
from app.risk.reason_codes import ReasonCode

logger = structlog.get_logger(__name__)

# --- divergence classification (ADR outcome vs legacy, by EFFECTIVE permit/deny for this order) ---
DIVERGENCE_MATCH = "MATCH"
DIVERGENCE_ADR_STRICTER = "ADR_STRICTER"  # ADR denies, legacy permits
DIVERGENCE_ADR_LOOSER = "ADR_LOOSER"  # ADR permits, legacy denies
DIVERGENCE_INCOMPARABLE = "INCOMPARABLE"  # legacy decision not supplied
DIVERGENCE_ERROR = "ERROR"  # the gate itself errored (fail closed)


@dataclass(frozen=True)
class LossControlDecision:
    """The gate's structured result — evidence in SHADOW, authoritative input in ENFORCE."""

    mode: str
    authoritative: bool  # True only in ENFORCE
    state: str | None
    state_version: int | None
    state_known: bool
    outcome: str  # OUTCOME_* from the precedence ladder
    permits_order: bool  # the EFFECTIVE ADR decision for THIS order
    verified_reduction: bool | None
    legacy_outcome: str | None
    legacy_permits: bool | None
    divergence: str
    reason_code: str | None  # a ReasonCode when ADR would refuse (used only in ENFORCE)
    error: str | None = None

    def provenance(self) -> dict[str, str | None]:
        """Flat, string-valued provenance for the durable enforce evidence / audit payload."""

        def s(v: object) -> str | None:
            return str(v) if v is not None else None

        return {
            "loss_control_mode": self.mode,
            "loss_control_state": self.state,
            "loss_control_state_version": s(self.state_version),
            "loss_control_outcome": self.outcome,
            "verified_reduction": s(self.verified_reduction),
            "reason_code": self.reason_code,
            "divergence": self.divergence,
        }


def fail_closed_decision(
    mode: LossControlMode, legacy_outcome: str | None, legacy_permits: bool | None, error: str | None = None
) -> LossControlDecision:
    """A fail-closed (deny) decision — used when the gate can't be evaluated. Authoritative only in
    ENFORCE, where the engine denies the order; in SHADOW the engine ignores it (legacy stands)."""
    return LossControlDecision(
        mode=mode.value,
        authoritative=mode == LossControlMode.ENFORCE,
        state=None,
        state_version=None,
        state_known=False,
        outcome=C.OUTCOME_INTEGRITY_STOP,
        permits_order=False,
        verified_reduction=None,
        legacy_outcome=legacy_outcome,
        legacy_permits=legacy_permits,
        divergence=DIVERGENCE_ERROR,
        reason_code=ReasonCode.LOSS_CONTROL_STOP.value,
        error=error,
    )


def _effective_permits(outcome: str, verified_reduction: bool | None) -> bool:
    """Does ``outcome`` permit THIS order? ALLOW_REDUCTION_ONLY permits only a verified reduction."""
    if outcome == C.OUTCOME_ALLOW:
        return True
    if outcome == C.OUTCOME_ALLOW_REDUCTION_ONLY:
        return bool(verified_reduction)
    return False  # REFUSE / INTEGRITY_STOP


def _divergence(adr_permits: bool, legacy_permits: bool | None) -> str:
    if legacy_permits is None:
        return DIVERGENCE_INCOMPARABLE
    if adr_permits == legacy_permits:
        return DIVERGENCE_MATCH
    return DIVERGENCE_ADR_STRICTER if (legacy_permits and not adr_permits) else DIVERGENCE_ADR_LOOSER


class LossControlGate:
    def __init__(self, session: AsyncSession, mode: LossControlMode) -> None:
        self._session = session
        self._mode = mode

    async def evaluate(
        self,
        *,
        account_id: int,
        verified_reduction: bool | None,
        legacy_outcome: str | None,
        legacy_permits: bool | None,
    ) -> LossControlDecision:
        """Compute the loss-control decision for one order. Read-only; never bootstraps state.

        Missing / unknown state fails closed to INTEGRITY_STOP (via the state machine's §D2 rule).
        Any error (not ``CancelledError``) yields a fail-closed ERROR decision — the engine denies it
        in ENFORCE and ignores it in SHADOW.
        """
        authoritative = self._mode == LossControlMode.ENFORCE
        try:
            row = await LossControlService(self._session).load_state_row(account_id)
            state_known = row is not None
            state = row.state if row is not None else None
            version = row.state_version if row is not None else None
            outcome = sm.order_outcome_for_state(
                state or "", verified_reduction=bool(verified_reduction), state_known=state_known
            )
            permits = _effective_permits(outcome, verified_reduction)
            return LossControlDecision(
                mode=self._mode.value,
                authoritative=authoritative,
                state=state,
                state_version=version,
                state_known=state_known,
                outcome=outcome,
                permits_order=permits,
                verified_reduction=None if verified_reduction is None else bool(verified_reduction),
                legacy_outcome=legacy_outcome,
                legacy_permits=legacy_permits,
                divergence=_divergence(permits, legacy_permits),
                reason_code=None if permits else ReasonCode.LOSS_CONTROL_STOP.value,
            )
        except Exception as exc:  # noqa: BLE001 — BaseException (CancelledError) still propagates
            return LossControlDecision(
                mode=self._mode.value,
                authoritative=authoritative,
                state=None,
                state_version=None,
                state_known=False,
                outcome=C.OUTCOME_INTEGRITY_STOP,
                permits_order=False,  # fail closed
                verified_reduction=None,
                legacy_outcome=legacy_outcome,
                legacy_permits=legacy_permits,
                divergence=DIVERGENCE_ERROR,
                reason_code=ReasonCode.LOSS_CONTROL_STOP.value,
                error=str(exc),
            )

    def emit_comparison(self, decision: LossControlDecision, *, account_id: int, request_id: str | None) -> None:
        """One structured event PER EVALUATED ORDER (matches included, not only divergences) — the
        denominator canary evidence needs."""
        logger.info(
            "risk_loss_control_shadow_comparison",
            account_id=account_id,
            request_id=request_id,
            mode=decision.mode,
            loss_control_state=decision.state,  # doubles as the lock reason
            loss_control_state_version=decision.state_version,
            state_known=decision.state_known,
            adr_outcome=decision.outcome,
            adr_permits=decision.permits_order,
            legacy_outcome=decision.legacy_outcome,
            legacy_permits=decision.legacy_permits,
            divergence=decision.divergence,
            verified_reduction=decision.verified_reduction,
            adr_stricter=decision.divergence == DIVERGENCE_ADR_STRICTER,
            adr_looser=decision.divergence == DIVERGENCE_ADR_LOOSER,
            no_authority=not decision.authoritative,
            error=decision.error,
        )
