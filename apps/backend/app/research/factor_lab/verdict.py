"""Factor Lab verdict evaluator (plan v0.2 §3.4) — pure, data-driven A/B/C/D.

The verdict tree is declared as data (``VerdictSpec``); this evaluator just returns the
first rule whose predicate fires against the runner's flat metrics dict, else the spec's
default. Pure and unit-tested — the same shape as the (now data-driven) TREND-001
``classify_outcome`` that the frozen plan, not drifting code, must drive.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.research.factor_lab.spec import VerdictSpec


def classify(metrics: Mapping[str, Any], spec: VerdictSpec) -> tuple[str, str]:
    """Return ``(outcome, action)`` — the first matching verdict rule, else the default.

    ``metrics`` is the flat dict the runner assembles from the books + hypotheses
    (e.g. ``h1_real``, ``consistent``, ``blend_helps``, ``dd_vs_mom``, ``dd_vs_eqw``,
    ``beats_regime``). Predicates that reference a missing key raise — surfacing a
    spec/runner mismatch loudly rather than silently mis-verdicting.
    """
    for rule in spec.rules:
        if rule.predicate(metrics):
            return rule.outcome, rule.action
    return spec.default_outcome, spec.default_action
