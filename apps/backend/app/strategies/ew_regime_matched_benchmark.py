"""PIT_UNIVERSE_EQUAL_WEIGHT_REGIME_MATCHED — the primary validation benchmark (PREREG v1.0 §6.1).

The benchmark must share EVERYTHING with the production momentum strategy except the selection /
construction rule: PIT universe & eligibility, session calendar, price & execution timing, the
graduated-regime gross path, investability filters, cash treatment, the transaction-cost model, and
the rebalance opportunity dates. The ONLY intended difference:

    strategy   : hold the momentum-ranked selected names (≤ max_names)
    benchmark  : hold an EQUAL allocation across the FULL eligible PIT universe

Design guarantee — *shared machinery by construction, not by assertion.* This module does NOT
reimplement eligibility, regime, sizing, pricing, or cost. It is a thin selection swap that calls the
LIVE strategy instance's own seams:

    benchmark candidate set   = strategy._eligible(scores).index          (all eligible names)
    benchmark target weights  = strategy.target_weights(targets)          (equal, cap, gross-scaled)
    regime gross              = strategy._regime_gross                    (identical path)
    price / investable equity = strategy._price / strategy._investable_equity

Because the momentum strategy selects a subset of exactly this eligible set, and both size through the
same `target_weights` seam, the benchmark differs from the strategy in the target-name set alone. Per
§6.1, the naturally different per-name concentration and turnover of a ~200-name equal-weight book vs
a 5-name book is *intentional selection exposure* — every non-selection setting stays matched.

⚠ This module computes construct/equivalence structure only. Forward performance must NOT be computed
or inspected until every benchmark SHA and the PREREG §0 bindings are countersigned (§5.4 no-peeking).
"""

from __future__ import annotations

from typing import Any

# The strategy seams this benchmark REUSES (never reimplements). The structural-identity test asserts
# the benchmark path invokes these and defines no parallel eligibility/regime/sizing/pricing of its own.
SHARED_STRATEGY_SEAMS: tuple[str, ...] = (
    "_eligible",          # PIT universe + investability filters
    "target_weights",     # equal-weight, cap, gross-scaled sizing (the production seam)
    "_regime",            # graduated-regime gross path
    "_investable_equity", # cash treatment + regime gross applied to equity
    "_price",             # pricing / execution convention
)

BENCHMARK_ID = "PIT_UNIVERSE_EQUAL_WEIGHT_REGIME_MATCHED"


def benchmark_targets(strategy: Any, scores: Any) -> list[str]:
    """The benchmark's held names for this session: the FULL eligible PIT universe, equal-weighted.

    Uses the strategy's OWN eligibility seam, so the universe and investability filters are identical
    to what the strategy screens — the benchmark simply keeps every eligible name instead of the
    momentum top-``max_names`` subset ``strategy._select_targets`` would keep.
    """
    return [str(t) for t in strategy._eligible(scores).index]


def benchmark_target_weights(strategy: Any, targets: list[str]) -> dict[str, float]:
    """Equal-weight, cap-respecting, gross-scaled weights via the strategy's OWN sizing seam.

    At full-universe breadth (k ≫ 1/max_position_pct) the per-name cap does not bind, so this is a
    plain equal weight across the eligible set, scaled by the identical regime gross, remainder cash —
    matching the strategy's cash treatment exactly (same `target_weights`).
    """
    return strategy.target_weights(targets)


def uses_only_shared_seams(strategy: Any) -> bool:
    """True iff every shared seam this benchmark depends on exists on the strategy instance — the
    machinery the benchmark reuses instead of reimplementing. The structural test also asserts this
    module declares no competing eligibility/regime/sizing implementation of its own."""
    return all(hasattr(strategy, s) for s in SHARED_STRATEGY_SEAMS)
