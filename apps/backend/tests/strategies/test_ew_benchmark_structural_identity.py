"""PIT_UNIVERSE_EQUAL_WEIGHT_REGIME_MATCHED — structural identity vs the production strategy.

PREREG v1.0 §6.1: the primary benchmark must share the PIT universe & eligibility, calendar, price &
execution timing, graduated-regime gross path, investability filters, cash treatment, cost model, and
rebalance opportunity dates — differing ONLY in the selection/construction rule. These tests prove the
shared machinery *structurally* (the benchmark calls the strategy's own seams and reimplements none of
them) and confirm the sole difference is the target-name set.
"""

from __future__ import annotations

import ast
import inspect
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from app.strategies import ew_regime_matched_benchmark as bench
from strategies_user.templates.momentum_daily import MomentumDaily

D = Decimal


def _scores(order):
    tickers = [t for t, _ in order]
    z = [s for _, s in order]
    mom = [0.10 + 0.01 * i for i in range(len(tickers))][::-1]
    df = pd.DataFrame({"momentum": mom, "winsorized": z, "zscore": z,
                       "rank": list(range(1, len(tickers) + 1)), "score": z}, index=tickers)
    df.index.name = "ticker"
    return df


def _strat(symbols, **over):
    ctx = MagicMock()
    ctx.strategy_id = 1
    ctx.symbols = symbols
    ctx.get_account_equity = AsyncMock(return_value=100_000)
    params = {**MomentumDaily.default_params, "use_market_regime_filter": False,
              "exit_confirm_closes": 1, **over}
    s = MomentumDaily(ctx=ctx, params=params)
    return s


# ---- structural: the benchmark reimplements no machinery ------------------------

def test_benchmark_declares_no_eligibility_regime_sizing_or_pricing_of_its_own():
    """The whole point: the benchmark is a SELECTION SWAP, not a parallel pipeline. Its source must
    define no function that re-derives eligibility, regime, sizing, pricing, or cost — those come from
    the strategy's own seams. A regression that inlined any of them would break the match silently."""
    src = inspect.getsource(bench)
    tree = ast.parse(src)
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    forbidden = {"_eligible", "_regime", "target_weights", "_investable_equity", "_price",
                 "_select_targets", "weigh", "gross_series"}
    assert not (defined & forbidden), f"benchmark reimplements shared machinery: {defined & forbidden}"
    # and it must reference the strategy seams it reuses
    assert "_eligible" in src and "target_weights" in src


def test_benchmark_reuses_the_strategy_shared_seams():
    s = _strat(["AAA", "BBB", "CCC"])
    assert bench.uses_only_shared_seams(s) is True
    for seam in bench.SHARED_STRATEGY_SEAMS:
        assert hasattr(s, seam), seam


# ---- identity: same eligibility/universe, weights via the same seam -------------

def test_benchmark_holds_the_full_eligible_universe_the_strategy_screens():
    """Same eligibility seam → identical candidate pool; the benchmark keeps ALL of it, the strategy
    keeps the momentum top-max_names subset."""
    s = _strat(["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"], max_names=5, entry_rank=5)
    scores = _scores([("AAA", 3.0), ("BBB", 2.5), ("CCC", 2.0), ("DDD", 1.5),
                      ("EEE", 1.0), ("FFF", 0.5), ("GGG", 0.2)])
    eligible = [str(t) for t in s._eligible(scores).index]
    bench_targets = bench.benchmark_targets(s, scores)
    strat_targets = s._select_targets(scores, held={})

    assert bench_targets == eligible                      # benchmark = the full eligible universe
    assert set(strat_targets) < set(bench_targets)        # strategy is a strict subset
    assert len(strat_targets) <= 5 and len(bench_targets) == 7


def test_only_the_target_set_differs_weights_come_from_the_same_seam():
    s = _strat(["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"], max_names=5)
    s._regime_gross = 0.98
    scores = _scores([("AAA", 3.0), ("BBB", 2.5), ("CCC", 2.0), ("DDD", 1.5),
                      ("EEE", 1.0), ("FFF", 0.5)])
    bt = bench.benchmark_targets(s, scores)

    # weights via the strategy's OWN target_weights — same function, same gross scaling and cash rule
    bw = bench.benchmark_target_weights(s, bt)
    assert bw == s.target_weights(bt)
    assert sum(bw.values()) == pytest.approx(0.98)        # gross-scaled, remainder cash (matched)
    # 6 eligible names, equal weight, cap 0.20 does not bind: each ≈ (1/6)*0.98
    assert all(v == pytest.approx(0.98 / 6) for v in bw.values())


def test_at_full_breadth_the_per_name_cap_does_not_bind():
    s = _strat([f"S{i}" for i in range(60)], max_names=5)
    s._regime_gross = 1.0
    scores = _scores([(f"S{i}", 2.0 - 0.01 * i) for i in range(60)])
    bt = bench.benchmark_targets(s, scores)
    bw = bench.benchmark_target_weights(s, bt)
    assert len(bt) == 60
    assert max(bw.values()) < float(s.params["max_position_pct"])   # 1/60 << 0.20
    assert sum(bw.values()) == pytest.approx(1.0)


def test_benchmark_regime_gross_is_the_strategys_regime_gross():
    """The regime overlay is shared: the benchmark scales by strategy._regime_gross, not its own.
    Use ≥5 eligible names so the 20% cap does not bind and the invested fraction is the full gross."""
    names = [f"S{i}" for i in range(8)]
    s = _strat(names)
    scores = _scores([(n, 2.0 - 0.1 * i) for i, n in enumerate(names)])
    for gross in (0.15, 0.60, 0.98, 1.0):
        s._regime_gross = gross
        bw = bench.benchmark_target_weights(s, bench.benchmark_targets(s, scores))
        assert sum(bw.values()) == pytest.approx(gross)


def test_a_below_five_name_benchmark_inherits_the_cap_and_cash_residual():
    """With fewer than 5 eligible names the 20% cap binds — the benchmark carries the SAME
    cap-plus-cash-residual seam as production (matched machinery), not a special case."""
    s = _strat(["AAA", "BBB", "CCC"])
    s._regime_gross = 1.0
    scores = _scores([("AAA", 3.0), ("BBB", 2.0), ("CCC", 1.0)])
    bw = bench.benchmark_target_weights(s, bench.benchmark_targets(s, scores))
    assert all(v == pytest.approx(0.20) for v in bw.values())   # capped
    assert sum(bw.values()) == pytest.approx(0.60)              # 40% cash residual


def test_empty_eligible_universe_yields_no_benchmark_position():
    s = _strat(["AAA"], min_score=99.0)   # floor excludes everything
    scores = _scores([("AAA", 1.0)])
    assert bench.benchmark_targets(s, scores) == []
    assert bench.benchmark_target_weights(s, []) == {}
