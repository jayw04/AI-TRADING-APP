"""Factor Lab declarative spec (plan v0.2 §3.1, OQ1 = Python dataclasses).

A ``ProgramSpec`` captures everything that varies between research programs so a new
program is *a config (+ maybe one score function)*, not a new script. The verdict tree
(``VerdictSpec``) is data — an ordered list of predicate→outcome rules — so the A/B/C/D
decision is declared, not coded (the discipline that caught the TREND-001 verdict bug).

These are frozen, pure dataclasses (no I/O); the runner (later session) consumes them.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

# A verdict predicate reads the flat metrics dict the runner assembles (h1_real,
# h1_ci_high, consistent, blend_helps, dd_vs_mom, dd_vs_eqw, beats_regime, ...) and
# returns whether this rule fires. Keeping it a callable (not a parsed string) is the
# Python-declarative choice (OQ1): type-checked, testable, no eval.
VerdictPredicate = Callable[[Mapping[str, Any]], bool]


@dataclass(frozen=True)
class VerdictRule:
    """One branch of the verdict tree: if ``predicate(metrics)`` then this outcome."""
    predicate: VerdictPredicate
    outcome: str   # e.g. "A - Validated", "B - Diversifier / Defensive"
    action: str    # what it means for the product / next step


@dataclass(frozen=True)
class VerdictSpec:
    """An ordered verdict tree: the first rule whose predicate fires wins; else default."""
    rules: tuple[VerdictRule, ...]
    default_outcome: str
    default_action: str


@dataclass(frozen=True)
class ProgramSpec:
    """A declarative research program (the Factor Lab "configuration")."""

    # identity
    id: str
    name: str
    philosophy: str

    # factor (stage 1) — a registry key + its params (resolved to a score_fn by the runner)
    factor: str
    factor_params: Mapping[str, Any]

    # universe & window
    n: int
    start: date
    end: date

    # verdict tree (stage 6) — declared as data
    verdict: VerdictSpec

    # construction (stage 2) — defaults match the platform's standard quantile book
    construction: str = "quantile"        # "quantile" | "sector_baskets" | "participation"
    top_quantile: float = 0.20
    weighting: str = "equal_weight"       # | "inverse_vol" | "risk_parity_diagonal"
    vol_target_annual: float | None = None
    max_sector_pct: float | None = None
    turnover_cost_bps: float = 10.0
    initial_equity: float = 100_000.0

    # benchmark / control (stage 3 — H2/H3)
    baseline: str = "equal_weight"        # | "regime_filter"

    # evaluation
    windows: int = 5
    bootstrap: int = 2000
    seed: int = 17

    # optional: a research/promotion GateProfile name to also run (ADR 0019)
    gate_profile: str | None = None

    # free-form notes (e.g. the pre-registered hypotheses text), not used by the runner
    notes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.construction not in ("quantile", "sector_baskets", "participation"):
            raise ValueError(f"unknown construction: {self.construction!r}")
        if self.baseline not in ("equal_weight", "regime_filter"):
            raise ValueError(f"unknown baseline: {self.baseline!r}")
        if not (0.0 < self.top_quantile <= 1.0):
            raise ValueError("top_quantile must be in (0, 1]")
