"""ADR-0043 Phase-0 WP5 — statistical design freeze (offline).

Implements AMD-02 / owner D2 and Controlling Design §3.6:

* provisional planning floors 59 / 20 / 10 (not automatic sufficiency);
* one governed floor replacement at WP5 exit, then lock;
* one-sided Clopper–Pearson upper bounds on critical false-reachable rate;
* gate scoring: zero failures necessary but not sufficient; bound above threshold
  → INCONCLUSIVE (not PASS);
* per-symbol n≥20 is a diagnostic floor only.

Does not submit orders or import the order path.
"""

from __future__ import annotations

import inspect
import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# --- D2 provisional planning floors ----------------------------------------------------------

FLOOR_POOLED_BINDING_REACHABLE = 59
FLOOR_PER_SYMBOL_STRATUM = 20
FLOOR_SHADOW_SESSIONS = 10

# Frozen maximum allowable one-sided upper confidence bound on critical false-reachable rate.
DEFAULT_MAX_ONE_SIDED_UPPER_BOUND = 0.05
DEFAULT_CONFIDENCE_ALPHA = 0.05  # 95% one-sided

# Derivation note (design-review / D2): with zero failures, U = 1 - α^(1/n).
# For n=59, α=0.05 → U ≈ 0.0495 (near 5%). n=20 → U ≈ 0.139 (materially above 5%).
DERIVATION_POOLED_N59 = (
    "With zero failures, one-sided 95% Clopper–Pearson upper bound is 1 - 0.05^(1/n). "
    "n=59 yields U≈0.0495 (near 5%). This is a planning floor under independence/"
    "exchangeability; it is not automatic '95% coverage at 95% confidence'."
)


class SampleGateVerdict(StrEnum):
    PASS = "PASS"
    REJECT = "REJECT"
    INCONCLUSIVE = "INCONCLUSIVE"


class FloorReplaceRefuse(StrEnum):
    ALREADY_LOCKED = "ALREADY_LOCKED"
    REPLACEMENT_ALREADY_USED = "REPLACEMENT_ALREADY_USED"
    INVALID_FLOORS = "INVALID_FLOORS"


@dataclass(frozen=True)
class StatisticalAssumptions:
    """Controlling Design §3.6 — recorded independence / clustering assumptions."""

    independence_unit: str = "binding_reachable_execution_plan"
    multiple_plans_per_session_count_separately: bool = True
    clustering_adjustment: str = (
        "same_session_plans_positively_dependent; report n_eff <= n_raw"
    )
    same_symbol_repeats_allowed: bool = True
    pooled_weighting: str = "equal_weight_per_binding_reachable_plan"
    effective_sample_vs_raw: str = "gates_may_use_n_eff_for_confidence_bound"
    per_symbol_floor_is_diagnostic_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "independence_unit": self.independence_unit,
            "multiple_plans_per_session_count_separately": (
                self.multiple_plans_per_session_count_separately
            ),
            "clustering_adjustment": self.clustering_adjustment,
            "same_symbol_repeats_allowed": self.same_symbol_repeats_allowed,
            "pooled_weighting": self.pooled_weighting,
            "effective_sample_vs_raw": self.effective_sample_vs_raw,
            "per_symbol_floor_is_diagnostic_only": self.per_symbol_floor_is_diagnostic_only,
        }


@dataclass(frozen=True)
class SampleFloors:
    pooled_binding_reachable_plans: int = FLOOR_POOLED_BINDING_REACHABLE
    per_intended_symbol_stratum: int = FLOOR_PER_SYMBOL_STRATUM
    shadow_sessions: int = FLOOR_SHADOW_SESSIONS
    max_one_sided_upper_bound: float = DEFAULT_MAX_ONE_SIDED_UPPER_BOUND
    confidence_alpha: float = DEFAULT_CONFIDENCE_ALPHA

    def as_dict(self) -> dict[str, Any]:
        return {
            "pooled_binding_reachable_plans": self.pooled_binding_reachable_plans,
            "per_intended_symbol_stratum": self.per_intended_symbol_stratum,
            "shadow_sessions": self.shadow_sessions,
            "max_one_sided_upper_bound": self.max_one_sided_upper_bound,
            "confidence_alpha": self.confidence_alpha,
            "derivation_pooled_n59": DERIVATION_POOLED_N59,
        }


@dataclass
class StatisticalDesignFreeze:
    """WP5 freeze object: floors + assumptions + one-shot replacement lock."""

    floors: SampleFloors = field(default_factory=SampleFloors)
    assumptions: StatisticalAssumptions = field(default_factory=StatisticalAssumptions)
    locked: bool = False
    replacement_used: bool = False
    replacement_note: str | None = None

    def lock(self) -> None:
        self.locked = True

    def replace_floors_once(
        self, new_floors: SampleFloors, *, note: str
    ) -> FloorReplaceRefuse | None:
        """Governed one-time replacement at WP5 exit, before model evaluation / unseal."""
        if self.locked:
            return FloorReplaceRefuse.ALREADY_LOCKED
        if self.replacement_used:
            return FloorReplaceRefuse.REPLACEMENT_ALREADY_USED
        if (
            new_floors.pooled_binding_reachable_plans < 1
            or new_floors.per_intended_symbol_stratum < 1
            or new_floors.shadow_sessions < 1
            or not (0 < new_floors.max_one_sided_upper_bound <= 1)
            or not (0 < new_floors.confidence_alpha < 1)
        ):
            return FloorReplaceRefuse.INVALID_FLOORS
        self.floors = new_floors
        self.replacement_used = True
        self.replacement_note = note
        self.locked = True
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "floors": self.floors.as_dict(),
            "assumptions": self.assumptions.as_dict(),
            "locked": self.locked,
            "replacement_used": self.replacement_used,
            "replacement_note": self.replacement_note,
        }


def _binom_pmf(n: int, k: int, p: float) -> float:
    if k < 0 or k > n:
        return 0.0
    # Stable-ish recursive product for moderate n (Phase-0 sample sizes << 10k).
    log_c = math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
    if p <= 0.0:
        return 1.0 if k == 0 else 0.0
    if p >= 1.0:
        return 1.0 if k == n else 0.0
    return math.exp(log_c + k * math.log(p) + (n - k) * math.log(1.0 - p))


def binomial_cdf_le(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    return sum(_binom_pmf(n, i, p) for i in range(0, k + 1))


def clopper_pearson_one_sided_upper(
    failures: int,
    n: int,
    *,
    alpha: float = DEFAULT_CONFIDENCE_ALPHA,
) -> float:
    """Exact one-sided Clopper–Pearson upper bound on a binomial failure rate.

    Solves F(failures; n, U) = α for U (or closed form when failures == 0).
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if failures < 0 or failures > n:
        raise ValueError("failures must be in [0, n]")
    if not (0 < alpha < 1):
        raise ValueError("alpha must be in (0, 1)")
    if failures == n:
        return 1.0
    if failures == 0:
        return 1.0 - alpha ** (1.0 / n)

    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if binomial_cdf_le(failures, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def stratum_diagnostic_bound_note(n_stratum: int, *, alpha: float = DEFAULT_CONFIDENCE_ALPHA) -> str:
    """Per-symbol n≥20 is diagnostic only — zero failures does not prove a 5% bound."""
    if n_stratum <= 0:
        return "stratum empty; no diagnostic bound"
    u = clopper_pearson_one_sided_upper(0, n_stratum, alpha=alpha)
    return (
        f"zero failures in n={n_stratum}: one-sided {1 - alpha:.0%} CP upper bound ≈ {u:.4f}; "
        "diagnostic floor only — does not by itself demonstrate a 5% upper failure bound"
    )


@dataclass(frozen=True)
class SampleGateResult:
    verdict: SampleGateVerdict
    pooled_n_raw: int
    pooled_n_eff: int
    critical_failures: int
    one_sided_upper_bound: float | None
    max_allowed_upper_bound: float
    floors_met: bool
    stratum_coverage: dict[str, int]
    shadow_sessions: int
    assumptions: dict[str, Any]
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": str(self.verdict),
            "pooled_n_raw": self.pooled_n_raw,
            "pooled_n_eff": self.pooled_n_eff,
            "critical_failures": self.critical_failures,
            "one_sided_upper_bound": self.one_sided_upper_bound,
            "max_allowed_upper_bound": self.max_allowed_upper_bound,
            "floors_met": self.floors_met,
            "stratum_coverage": dict(self.stratum_coverage),
            "shadow_sessions": self.shadow_sessions,
            "assumptions": dict(self.assumptions),
            "detail": self.detail,
        }


def assess_sample_gate(
    *,
    freeze: StatisticalDesignFreeze,
    pooled_n_raw: int,
    pooled_n_eff: int | None = None,
    critical_failures: int,
    stratum_coverage: dict[str, int],
    shadow_sessions: int,
) -> SampleGateResult:
    """Score an O5-style sample / confidence gate under the frozen statistical design.

    PASS requires: floors met, zero critical failures, and CP upper bound ≤ threshold.
    Any critical failure → REJECT. Bound above threshold or floors unmet → INCONCLUSIVE.
    """
    floors = freeze.floors
    n_eff = pooled_n_raw if pooled_n_eff is None else pooled_n_eff
    if n_eff > pooled_n_raw:
        n_eff = pooled_n_raw
    if n_eff < 0 or pooled_n_raw < 0:
        raise ValueError("sample counts must be non-negative")
    if critical_failures < 0:
        raise ValueError("critical_failures must be non-negative")

    min_stratum = min(stratum_coverage.values()) if stratum_coverage else 0
    floors_met = (
        pooled_n_raw >= floors.pooled_binding_reachable_plans
        and min_stratum >= floors.per_intended_symbol_stratum
        and shadow_sessions >= floors.shadow_sessions
        and n_eff >= 1
    )

    bound: float | None = None
    if n_eff >= 1 and critical_failures <= n_eff:
        bound = clopper_pearson_one_sided_upper(
            critical_failures, n_eff, alpha=floors.confidence_alpha
        )

    assumptions = freeze.assumptions.as_dict()

    def _result(verdict: SampleGateVerdict, detail: str) -> SampleGateResult:
        return SampleGateResult(
            verdict=verdict,
            pooled_n_raw=pooled_n_raw,
            pooled_n_eff=n_eff,
            critical_failures=critical_failures,
            one_sided_upper_bound=bound,
            max_allowed_upper_bound=floors.max_one_sided_upper_bound,
            floors_met=floors_met,
            stratum_coverage=dict(stratum_coverage),
            shadow_sessions=shadow_sessions,
            assumptions=assumptions,
            detail=detail,
        )

    if critical_failures > 0:
        return _result(
            SampleGateVerdict.REJECT,
            f"{critical_failures} critical false-reachable failure(s)",
        )

    # Zero failures necessary but not sufficient.
    if not floors_met:
        return _result(
            SampleGateVerdict.INCONCLUSIVE,
            (
                "planning floors not met "
                f"(need pooled≥{floors.pooled_binding_reachable_plans}, "
                f"stratum≥{floors.per_intended_symbol_stratum}, "
                f"shadow≥{floors.shadow_sessions}; "
                f"got pooled={pooled_n_raw}, min_stratum={min_stratum}, "
                f"shadow={shadow_sessions})"
            ),
        )

    assert bound is not None
    if bound > floors.max_one_sided_upper_bound:
        return _result(
            SampleGateVerdict.INCONCLUSIVE,
            (
                f"achieved one-sided CP upper bound {bound:.6f} exceeds frozen threshold "
                f"{floors.max_one_sided_upper_bound} (zero failures necessary but not sufficient)"
            ),
        )

    return _result(
        SampleGateVerdict.PASS,
        (
            f"floors met; zero critical failures; CP upper bound {bound:.6f} "
            f"≤ {floors.max_one_sided_upper_bound}"
        ),
    )


def default_freeze() -> StatisticalDesignFreeze:
    return StatisticalDesignFreeze()


def assert_no_order_path_imports() -> None:
    import app.risk.loss_control.phase0_statistical_design as mod

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
            raise AssertionError(f"phase0_statistical_design must not reference {needle}")


__all__ = [
    "DEFAULT_CONFIDENCE_ALPHA",
    "DEFAULT_MAX_ONE_SIDED_UPPER_BOUND",
    "DERIVATION_POOLED_N59",
    "FLOOR_PER_SYMBOL_STRATUM",
    "FLOOR_POOLED_BINDING_REACHABLE",
    "FLOOR_SHADOW_SESSIONS",
    "FloorReplaceRefuse",
    "SampleFloors",
    "SampleGateResult",
    "SampleGateVerdict",
    "StatisticalAssumptions",
    "StatisticalDesignFreeze",
    "assess_sample_gate",
    "assert_no_order_path_imports",
    "binomial_cdf_le",
    "clopper_pearson_one_sided_upper",
    "default_freeze",
    "stratum_diagnostic_bound_note",
]
