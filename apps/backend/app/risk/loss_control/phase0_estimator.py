"""ADR-0043 Phase-0 WP6 — estimator ladder E0/E1/E2 (offline).

Implements AMD-03:

* objective: conservative executable-loss bound with demonstrated OOS coverage;
* E0: empirical lower-tail quantile of non-negative loss (default q=0.10);
* below stratum minimum n → INDETERMINATE;
* E1: E0 + monotone quantity/notional adjustment (+ optional envelopes);
* E2: only after governed graduation, frozen n met, OOS coverage ≥ E0 on same splits;
* active level recorded on every estimate; graduation never automatic.

Does not submit orders or import the order path.
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.risk.loss_control.phase0_contracts import (
    VERDICT_INDETERMINATE,
    normalize_round_trip_loss_amount,
)
from app.risk.loss_control.phase0_statistical_design import (
    FLOOR_PER_SYMBOL_STRATUM,
    FLOOR_POOLED_BINDING_REACHABLE,
)

# Governed risk parameter (design-review AMD-03 correction): lower-tail quantile of
# realized non-negative loss so the bound rarely exceeds amounts actually realized.
E0_DEFAULT_LOWER_TAIL_QUANTILE = Decimal("0.10")

ESTIMATOR_OBJECTIVE = (
    "Estimate a conservative executable-loss bound with demonstrated out-of-sample "
    "coverage. Model complexity must be justified by sample size and calibration "
    "performance."
)


class EstimatorLevel(StrEnum):
    E0 = "E0"
    E1 = "E1"
    E2 = "E2"


class EstimateStatus(StrEnum):
    OK = "OK"
    INDETERMINATE = "INDETERMINATE"
    REFUSED = "REFUSED"


class GraduationRefuseReason(StrEnum):
    NOT_GOVERNED = "NOT_GOVERNED"
    N_BELOW_THRESHOLD = "N_BELOW_THRESHOLD"
    OOS_WORSE_THAN_E0 = "OOS_WORSE_THAN_E0"
    INVALID_TARGET_LEVEL = "INVALID_TARGET_LEVEL"
    ALREADY_AT_OR_ABOVE = "ALREADY_AT_OR_ABOVE"


@dataclass(frozen=True)
class StratumObservations:
    """Non-negative realized round-trip loss amounts for one intended-symbol stratum."""

    symbol: str
    losses: tuple[Decimal, ...]

    def __post_init__(self) -> None:
        for x in self.losses:
            normalize_round_trip_loss_amount(x)


@dataclass(frozen=True)
class LossEstimate:
    status: EstimateStatus
    level: EstimatorLevel
    symbol: str
    conservative_min_supported_loss: Decimal | None
    quantile: Decimal | None
    n: int
    verdict_hint: str | None
    detail: str
    extras: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": str(self.status),
            "active_estimator_level": str(self.level),
            "symbol": self.symbol,
            "conservative_min_supported_loss": (
                str(self.conservative_min_supported_loss)
                if self.conservative_min_supported_loss is not None
                else None
            ),
            "lower_tail_quantile": str(self.quantile) if self.quantile is not None else None,
            "n": self.n,
            "verdict_hint": self.verdict_hint,
            "detail": self.detail,
            "extras": dict(self.extras),
            "objective": ESTIMATOR_OBJECTIVE,
        }


@dataclass(frozen=True)
class GovernedGraduation:
    """Explicit owner/governance decision to raise the active estimator level."""

    to_level: EstimatorLevel
    decision_id: str
    note: str
    pooled_n: int
    oos_coverage_e0: float
    oos_coverage_candidate: float


@dataclass
class EstimatorRegistry:
    """Active level + graduation history. Level changes only via ``graduate``."""

    active_level: EstimatorLevel = EstimatorLevel.E0
    lower_tail_quantile: Decimal = E0_DEFAULT_LOWER_TAIL_QUANTILE
    stratum_min_n: int = FLOOR_PER_SYMBOL_STRATUM
    pooled_n_threshold_for_e2: int = FLOOR_POOLED_BINDING_REACHABLE
    history: list[dict[str, Any]] = field(default_factory=list)

    def graduate(self, decision: GovernedGraduation) -> GraduationRefuseReason | None:
        """Governed graduation — never automatic."""
        if decision.to_level not in {EstimatorLevel.E1, EstimatorLevel.E2}:
            return GraduationRefuseReason.INVALID_TARGET_LEVEL
        order = {EstimatorLevel.E0: 0, EstimatorLevel.E1: 1, EstimatorLevel.E2: 2}
        if order[decision.to_level] <= order[self.active_level]:
            return GraduationRefuseReason.ALREADY_AT_OR_ABOVE
        if not decision.decision_id.strip() or not decision.note.strip():
            return GraduationRefuseReason.NOT_GOVERNED
        if decision.to_level == EstimatorLevel.E2:
            if decision.pooled_n < self.pooled_n_threshold_for_e2:
                return GraduationRefuseReason.N_BELOW_THRESHOLD
            if decision.oos_coverage_candidate < decision.oos_coverage_e0:
                return GraduationRefuseReason.OOS_WORSE_THAN_E0
        self.active_level = decision.to_level
        self.history.append(
            {
                "to_level": str(decision.to_level),
                "decision_id": decision.decision_id,
                "note": decision.note,
                "pooled_n": decision.pooled_n,
                "oos_coverage_e0": decision.oos_coverage_e0,
                "oos_coverage_candidate": decision.oos_coverage_candidate,
            }
        )
        return None


def empirical_lower_tail_quantile(
    losses: Sequence[Decimal],
    q: Decimal,
) -> Decimal:
    """Lower-tail empirical quantile of non-negative losses (inclusive rank, linear)."""
    if not losses:
        raise ValueError("empty loss sample")
    if q <= 0 or q > 1:
        raise ValueError("quantile must be in (0, 1]")
    xs = sorted(normalize_round_trip_loss_amount(x) for x in losses)
    n = len(xs)
    # Hyndman-Fan type-7 style position: 1 + (n-1)*q
    pos = 1 + (n - 1) * float(q)
    lo = int(pos) - 1
    hi = min(lo + 1, n - 1)
    lo = max(0, min(lo, n - 1))
    frac = pos - int(pos)
    if lo == hi or frac == 0:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * Decimal(str(frac))


def estimate_e0(
    stratum: StratumObservations,
    *,
    quantile: Decimal = E0_DEFAULT_LOWER_TAIL_QUANTILE,
    stratum_min_n: int = FLOOR_PER_SYMBOL_STRATUM,
) -> LossEstimate:
    n = len(stratum.losses)
    if n < stratum_min_n:
        return LossEstimate(
            status=EstimateStatus.INDETERMINATE,
            level=EstimatorLevel.E0,
            symbol=stratum.symbol,
            conservative_min_supported_loss=None,
            quantile=quantile,
            n=n,
            verdict_hint=VERDICT_INDETERMINATE,
            detail=(
                f"stratum n={n} below minimum {stratum_min_n}; "
                "E0 cannot emit a binding loss bound"
            ),
        )
    bound = empirical_lower_tail_quantile(stratum.losses, quantile)
    return LossEstimate(
        status=EstimateStatus.OK,
        level=EstimatorLevel.E0,
        symbol=stratum.symbol,
        conservative_min_supported_loss=bound,
        quantile=quantile,
        n=n,
        verdict_hint=None,
        detail=f"E0 empirical lower-tail quantile q={quantile} on n={n}",
    )


def _monotone_size_factor(
    *,
    reference_notional: Decimal,
    reference_qty: Decimal,
    notional: Decimal,
    qty: Decimal,
) -> Decimal:
    """Non-decreasing scale vs reference size (max of notional and qty ratios)."""
    if reference_notional <= 0 or reference_qty <= 0:
        raise ValueError("reference size must be positive")
    if notional < 0 or qty < 0:
        raise ValueError("size must be non-negative")
    r_n = notional / reference_notional
    r_q = qty / reference_qty
    factor = r_n if r_n >= r_q else r_q
    if factor < 1:
        # Reduction is allowed (safety); do not invent a higher bound from a smaller size.
        return factor
    return factor


def estimate_e1(
    stratum: StratumObservations,
    *,
    reference_notional: Decimal,
    reference_qty: Decimal,
    notional: Decimal,
    qty: Decimal,
    quantile: Decimal = E0_DEFAULT_LOWER_TAIL_QUANTILE,
    stratum_min_n: int = FLOOR_PER_SYMBOL_STRATUM,
    envelope_floor: Decimal | None = None,
    broker_executable_bound: Decimal | None = None,
) -> LossEstimate:
    base = estimate_e0(stratum, quantile=quantile, stratum_min_n=stratum_min_n)
    if base.status != EstimateStatus.OK or base.conservative_min_supported_loss is None:
        return LossEstimate(
            status=base.status,
            level=EstimatorLevel.E1,
            symbol=stratum.symbol,
            conservative_min_supported_loss=None,
            quantile=quantile,
            n=base.n,
            verdict_hint=base.verdict_hint,
            detail=f"E1 blocked by E0: {base.detail}",
        )
    factor = _monotone_size_factor(
        reference_notional=reference_notional,
        reference_qty=reference_qty,
        notional=notional,
        qty=qty,
    )
    scaled = normalize_round_trip_loss_amount(
        (base.conservative_min_supported_loss * factor).quantize(Decimal("0.01"))
    )
    candidates = [scaled]
    if envelope_floor is not None:
        candidates.append(normalize_round_trip_loss_amount(envelope_floor))
    if broker_executable_bound is not None:
        candidates.append(normalize_round_trip_loss_amount(broker_executable_bound))
    # Conservative minimum supported loss among permitted E1 inputs: take the min of
    # positive candidates that are size-consistent — actually for conservative *minimum*
    # achievable loss we want the lower bound; envelopes that are higher are less
    # conservative for reachability. Reachability uses conservative_achievable_loss as
    # lower bound on loss — so we take the minimum of E0-scaled and any broker bound
    # that is itself a lower bound. Rule-based envelope_floor is a floor (raise bound).
    bound = scaled
    if broker_executable_bound is not None:
        beb = normalize_round_trip_loss_amount(broker_executable_bound)
        bound = min(bound, beb)
    if envelope_floor is not None:
        env = normalize_round_trip_loss_amount(envelope_floor)
        bound = max(bound, env)  # envelope raises the conservative floor if required
    return LossEstimate(
        status=EstimateStatus.OK,
        level=EstimatorLevel.E1,
        symbol=stratum.symbol,
        conservative_min_supported_loss=bound,
        quantile=quantile,
        n=base.n,
        verdict_hint=None,
        detail=f"E1 monotone scale factor={factor} from E0",
        extras={
            "size_factor": str(factor),
            "e0_bound": str(base.conservative_min_supported_loss),
            "candidates": [str(c) for c in candidates],
        },
    )


def estimate_e2_bootstrap_lower(
    stratum: StratumObservations,
    *,
    registry: EstimatorRegistry,
    quantile: Decimal = E0_DEFAULT_LOWER_TAIL_QUANTILE,
    stratum_min_n: int = FLOOR_PER_SYMBOL_STRATUM,
    bootstrap_draws: int = 200,
    seed: int = 43,
) -> LossEstimate:
    """E2 bootstrap lower-tail bound — refused unless registry is at E2."""
    if registry.active_level != EstimatorLevel.E2:
        return LossEstimate(
            status=EstimateStatus.REFUSED,
            level=EstimatorLevel.E2,
            symbol=stratum.symbol,
            conservative_min_supported_loss=None,
            quantile=quantile,
            n=len(stratum.losses),
            verdict_hint=VERDICT_INDETERMINATE,
            detail=(
                f"E2 refused: active level is {registry.active_level}; "
                "graduation is a governed decision, never automatic"
            ),
        )
    base = estimate_e0(stratum, quantile=quantile, stratum_min_n=stratum_min_n)
    if base.status != EstimateStatus.OK:
        return LossEstimate(
            status=base.status,
            level=EstimatorLevel.E2,
            symbol=stratum.symbol,
            conservative_min_supported_loss=None,
            quantile=quantile,
            n=base.n,
            verdict_hint=base.verdict_hint,
            detail=f"E2 blocked by E0: {base.detail}",
        )
    # Deterministic bootstrap of the same lower-tail quantile; report the lower 10% of
    # bootstrap quantiles as a conservative lower bound (no numpy dependency).
    xs = list(stratum.losses)
    n = len(xs)
    rng = _Lcg(seed)
    boots: list[Decimal] = []
    for _ in range(bootstrap_draws):
        sample = tuple(xs[rng.randrange(n)] for _ in range(n))
        boots.append(empirical_lower_tail_quantile(sample, quantile))
    boots.sort()
    idx = max(0, int(0.10 * (len(boots) - 1)))
    bound = boots[idx]
    return LossEstimate(
        status=EstimateStatus.OK,
        level=EstimatorLevel.E2,
        symbol=stratum.symbol,
        conservative_min_supported_loss=bound,
        quantile=quantile,
        n=n,
        verdict_hint=None,
        detail=f"E2 bootstrap lower-tail of q={quantile} quantiles (draws={bootstrap_draws})",
        extras={"bootstrap_q10_of_quantile": str(bound), "e0_bound": str(base.conservative_min_supported_loss)},
    )


def estimate(
    stratum: StratumObservations,
    registry: EstimatorRegistry,
    **kwargs: Any,
) -> LossEstimate:
    """Dispatch at the registry's active level."""
    if registry.active_level == EstimatorLevel.E0:
        return estimate_e0(
            stratum,
            quantile=registry.lower_tail_quantile,
            stratum_min_n=registry.stratum_min_n,
        )
    if registry.active_level == EstimatorLevel.E1:
        return estimate_e1(
            stratum,
            quantile=registry.lower_tail_quantile,
            stratum_min_n=registry.stratum_min_n,
            **kwargs,
        )
    return estimate_e2_bootstrap_lower(
        stratum,
        registry=registry,
        quantile=registry.lower_tail_quantile,
        stratum_min_n=registry.stratum_min_n,
    )


class _Lcg:
    """Tiny deterministic RNG so tests need no numpy."""

    def __init__(self, seed: int) -> None:
        self._s = seed % 2147483647
        if self._s <= 0:
            self._s = 1

    def randrange(self, n: int) -> int:
        self._s = (self._s * 48271) % 2147483647
        return self._s % n


def assert_no_order_path_imports() -> None:
    import app.risk.loss_control.phase0_estimator as mod

    src = inspect.getsource(mod)
    needles = [
        "from app." + "services.order_router",
        "import app." + "services.order_router",
        "from app." + "brokers",
        "import app." + "brokers",
        "from app." + "orders",
        "submit_" + "order(",
    ]
    for needle in needles:
        if needle in src:
            raise AssertionError(f"phase0_estimator must not reference {needle}")


__all__ = [
    "E0_DEFAULT_LOWER_TAIL_QUANTILE",
    "ESTIMATOR_OBJECTIVE",
    "EstimateStatus",
    "EstimatorLevel",
    "EstimatorRegistry",
    "GovernedGraduation",
    "GraduationRefuseReason",
    "LossEstimate",
    "StratumObservations",
    "assert_no_order_path_imports",
    "empirical_lower_tail_quantile",
    "estimate",
    "estimate_e0",
    "estimate_e1",
    "estimate_e2_bootstrap_lower",
]
