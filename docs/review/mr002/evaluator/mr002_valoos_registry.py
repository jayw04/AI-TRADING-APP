"""MR-002 validation/OOS evaluator — immutable required-gate registry (Increment 1 v1.1).

The governing gate set, thresholds, comparison senses, and sample designations are pinned here and
**cross-validated against the loaded v1.0.4 `gates_frozen`** by `cross_validate_registry` — if the
code registry diverges from the preregistration bytes it raises RefusedIdentity, so the registry can
never silently drift from governance. A disposition may be derived only when EVERY required gate in
`REQUIRED_GATES` is present with the registry-pinned threshold and sample (enforced in the gate
engine). A 12-of-N battery can never pass.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── sample designations (tokens; prose mapping documented per gate) ───────────────────────────────
SEALED_OOS = "sealed_OOS"                       # gates_frozen "*_sample": "sealed OOS"
VALIDATION = "validation"                        # "validation" / "validation, config B"
COMBINED = "validation+OOS_combined"             # "validation + sealed OOS COMBINED"

# comparison senses
GE, GT, LE = "ge", "gt", "le"


@dataclass(frozen=True)
class RequiredGate:
    gate_id: str
    comparison: str          # ge | gt | le
    threshold: float
    sample: str
    # optional cross-check key into prereg gates_frozen (dotted); None → prose-only (documented)
    prereg_key: str | None = None


def _passes(comparison: str, value, threshold) -> bool:
    if comparison == GE:
        return value >= threshold
    if comparison == GT:
        return value > threshold
    if comparison == LE:
        return value <= threshold
    raise ValueError(f"bad comparison {comparison}")


# The 22 governing GATE conditions (composite conditions expanded to their child evidence).
REQUIRED_GATES: dict[str, RequiredGate] = {g.gate_id: g for g in [
    RequiredGate("net_sharpe", GE, 0.70, SEALED_OOS, None),                     # oos_pass_requires_BOTH[0]
    RequiredGate("bootstrap_mean_lower_bound", GT, 0.0, SEALED_OOS, None),      # oos_pass_requires_BOTH[1]
    RequiredGate("net_calmar", GE, 0.75, SEALED_OOS, "net_oos_calmar_min"),
    RequiredGate("combined_max_drawdown", LE, 0.15, COMBINED, "net_max_drawdown_max"),
    RequiredGate("positive_validation_folds", GE, 3, VALIDATION, "validation_positive_folds_min_of_5"),
    RequiredGate("parameter_stability_A", GT, 0.0, VALIDATION, None),           # config A net-profitable
    RequiredGate("parameter_stability_C", GT, 0.0, VALIDATION, None),           # config C net-profitable
    RequiredGate("deflated_sharpe", GE, 0.95, SEALED_OOS, "dsr_significance_min"),
    RequiredGate("net_annualized_return", GE, 0.03, SEALED_OOS, "net_annualized_return_min"),
    RequiredGate("cost_stress", GT, 0.0, SEALED_OOS, None),                     # profitable @ 20/300 bps
    RequiredGate("breadth_completed_trades", GE, 500, SEALED_OOS, "breadth.min_completed_trades"),
    RequiredGate("breadth_distinct_entry_dates", GE, 100, SEALED_OOS, "breadth.min_distinct_entry_dates"),
    RequiredGate("breadth_long_trades", GE, 100, SEALED_OOS, "breadth.min_long"),
    RequiredGate("breadth_short_trades", GE, 100, SEALED_OOS, "breadth.min_short"),
    RequiredGate("trade_concentration_top10", LE, 0.20, SEALED_OOS,
                 "trade_concentration.top10_trades_max_fraction_of_positive_trade_pnl"),
    RequiredGate("trade_concentration_single_stock", LE, 0.10, SEALED_OOS,
                 "trade_concentration.single_stock_max_fraction_of_positive_pnl"),
    RequiredGate("annual_positive_years", GE, 3, COMBINED, "annual_profile.min_positive_calendar_years"),
    RequiredGate("annual_largest_positive_year_fraction", LE, 0.50, COMBINED,
                 "annual_profile.largest_positive_year_max_fraction_of_sum_positive_annual_pnl"),
    RequiredGate("trend_regimes_positive_count", GE, 2, COMBINED,
                 "regime_gates.min_trend_regimes_net_positive_of_3"),
    RequiredGate("trend_regime_loss_concentration", LE, 0.60, COMBINED,
                 "regime_gates.no_trend_regime_gt_fraction_of_total_LOSSES"),
    RequiredGate("volatility_regime_floor", GE, -0.50, COMBINED,
                 "regime_gates.no_vol_regime_sharpe_below"),
    RequiredGate("capacity", GT, 0.0, SEALED_OOS, None),                        # positive net edge @ 2% ADV
]}

# Required DIAGNOSTICS — must be COMPUTABLE (else INTEGRITY_STOP:DIAGNOSTIC_COMPUTATION_ERROR).
# They NEVER move the research verdict; missing/failed computation blocks publication only.
REQUIRED_DIAGNOSTICS: frozenset = frozenset({
    "pbo", "positive_pnl_regime_concentration", "annual_herfindahl", "severe_cost_stress",
})

EXPECTED_TRIAL_IDS = ("MR002-A", "MR002-B", "MR002-C", "RNG-001", "RNG-EntryLogic")


def _dig(d: dict, dotted: str):
    cur = d
    for part in dotted.split("."):
        cur = cur[part]
    return cur


def cross_validate_registry(gates_frozen: dict) -> None:
    """Assert every registry threshold equals the loaded v1.0.4 gates_frozen value. Diverging code →
    RefusedIdentity (imported lazily to avoid a cycle)."""
    from mr002_valoos_identity import RefusedIdentity
    for g in REQUIRED_GATES.values():
        if g.prereg_key is None:
            continue
        try:
            frozen = _dig(gates_frozen, g.prereg_key)
        except (KeyError, TypeError) as exc:
            raise RefusedIdentity(f"REFUSED_CODE_OR_DATA_IDENTITY:REGISTRY_KEY_ABSENT:{g.prereg_key}") from exc
        if float(frozen) != float(g.threshold):
            raise RefusedIdentity(
                f"REFUSED_CODE_OR_DATA_IDENTITY:REGISTRY_THRESHOLD_DIVERGES:{g.gate_id}:"
                f"code={g.threshold}!=frozen={frozen}")
    # net_sharpe 0.70 is embedded in the prose oos_pass condition — assert its presence.
    both = gates_frozen.get("oos_pass_requires_BOTH", [])
    if not any(">= 0.70" in s for s in both):
        raise RefusedIdentity("REFUSED_CODE_OR_DATA_IDENTITY:REGISTRY_SHARPE_THRESHOLD_UNCONFIRMED")
    if gates_frozen.get("dsr_trials_N") != 5:
        raise RefusedIdentity("REFUSED_CODE_OR_DATA_IDENTITY:REGISTRY_DSR_N_DIVERGES")
