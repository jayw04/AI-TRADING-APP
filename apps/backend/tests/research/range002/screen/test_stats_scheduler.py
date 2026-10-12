"""Bootstrap/max-statistic behaviour on synthetic dependent and skewed data, and the chronological
portfolio scheduler. Synthetic only; no verdict is attached to any real data."""

from __future__ import annotations

from datetime import date, time, timedelta
from pathlib import Path

import numpy as np
import pytest

from app.research.range002.governance.errors import InvalidCapabilityError
from app.research.range002.screen.errors import ParamsUnsetError, SpecBindingError
from app.research.range002.screen.scheduler import (
    REJECT_CONCURRENCY,
    REJECT_NAME,
    PortfolioLimits,
    limits_from_draft,
    schedule_portfolio,
)
from app.research.range002.screen.stats import (
    BootstrapConfig,
    DayMatrix,
    build_day_matrix,
    max_statistic_test,
    mean_interval,
)
from app.research.range002.screen.types import Trade
from app.research.range002.spec.loader import parse_draft
from tests.research.range002.screen.conftest import make_capability, synth_payload

DAYS = tuple(date(2019, 1, 1) + timedelta(days=i) for i in range(250))
CFG = BootstrapConfig(mean_block_days=10.0, reps=600, seed=20261012)


def matrix(daily: np.ndarray) -> DayMatrix:
    k = daily.shape[1]
    return DayMatrix(
        days=DAYS[: len(daily)],
        candidates=tuple(f"C{i}" for i in range(k)),
        net_r=daily,
        trades=np.ones(daily.shape, dtype=np.int64),
    )


def _ar1_skewed(rng: np.random.Generator, n: int, k: int, mean: float) -> np.ndarray:
    """Autocorrelated daily R with a heavy right skew; candidates share the same day shocks."""
    shock = rng.standard_exponential(n) - 1.0  # skewed, mean 0
    day = np.empty(n)
    day[0] = shock[0]
    for t in range(1, n):
        day[t] = 0.6 * day[t - 1] + shock[t]
    return day[:, None] * np.linspace(0.8, 1.2, k)[None, :] + mean


@pytest.fixture
def cap(tmp_path: Path) -> object:
    return make_capability(tmp_path, synth_payload())[0]


def test_same_seed_same_result_and_config_is_returned(cap: object) -> None:
    m = matrix(_ar1_skewed(np.random.default_rng(1), 250, 3, 0.0))
    a = max_statistic_test(cap, m, 0.10, CFG)
    b = max_statistic_test(cap, m, 0.10, CFG)
    assert a == b and a.config == CFG
    c = max_statistic_test(cap, m, 0.10, BootstrapConfig(10.0, 600, CFG.seed + 1))
    assert c.config != a.config


def test_null_size_under_dependence_and_skew_is_not_wildly_inflated(cap: object) -> None:
    rejections = 0
    sims = 60
    for s in range(sims):
        m = matrix(_ar1_skewed(np.random.default_rng(1000 + s), 250, 4, 0.0))
        if max_statistic_test(cap, m, 0.10, BootstrapConfig(10.0, 300, 7 + s)).rejects:
            rejections += 1
    assert rejections / sims <= 0.25  # nominal 0.10; coarse bound, recorded not tuned


def test_real_edge_is_detected_and_interval_excludes_zero(cap: object) -> None:
    m = matrix(_ar1_skewed(np.random.default_rng(5), 250, 3, 0.9))
    t = max_statistic_test(cap, m, 0.10, CFG)
    assert t.rejects and t.p_value is not None and t.p_value < 0.05
    ci = mean_interval(cap, m, "C1", 0.90, CFG)
    assert ci.lower is not None and ci.observed_mean is not None and ci.upper is not None
    assert ci.lower > 0 and ci.lower < ci.observed_mean < ci.upper


def test_interval_for_a_null_candidate_spans_zero(cap: object) -> None:
    m = matrix(_ar1_skewed(np.random.default_rng(11), 250, 2, 0.0))
    ci = mean_interval(cap, m, "C0", 0.90, CFG)
    assert ci.lower is not None and ci.upper is not None and ci.lower < 0 < ci.upper


def test_zero_trade_days_stay_in_the_sequence(cap: object) -> None:
    daily = np.zeros((250, 1))
    counts = np.zeros((250, 1), dtype=np.int64)
    daily[::5, 0] = 1.0
    counts[::5, 0] = 1
    ci = mean_interval(cap, DayMatrix(DAYS, ("C0",), daily, counts), "C0", 0.90, CFG)
    assert ci.observed_mean == pytest.approx(1.0)  # total R / total trades


def test_candidate_with_no_trades_is_undefined_not_zero(cap: object) -> None:
    m = DayMatrix(DAYS, ("C0", "C1"), np.zeros((250, 2)), np.zeros((250, 2), dtype=np.int64))
    t = max_statistic_test(cap, m, 0.10, CFG)
    assert t.observed_max is None and t.p_value is None and not t.rejects


def test_entry_points_need_a_capability_and_valid_config(cap: object) -> None:
    m = matrix(np.zeros((10, 1)))
    with pytest.raises(InvalidCapabilityError):
        max_statistic_test(None, m, 0.10, CFG)
    with pytest.raises(InvalidCapabilityError):
        mean_interval(object(), m, "C0", 0.9, CFG)
    with pytest.raises(ParamsUnsetError):
        max_statistic_test(cap, m, 0.10, BootstrapConfig(0.5, 100, 1))
    with pytest.raises(ParamsUnsetError):
        max_statistic_test(cap, m, 1.5, CFG)


def _trade(
    sym: str,
    day: date,
    entry: time,
    exit_: time,
    net: float,
    qty: int = 100,
    px: float = 10.0,
    permaticker: str | None = None,
) -> Trade:
    return Trade(
        candidate_id="X",
        symbol=sym,
        permaticker=permaticker if permaticker is not None else f"PERM-{sym}",
        day=day,
        or_high=px,
        or_low=px - 0.1,
        trigger=px + 0.01,
        entry_time=entry,
        entry_price=px,
        r_pre=0.11,
        r_fill=0.11,
        qty=qty,
        exit_time=exit_,
        exit_price=px,
        exit_reason="EOD",
        gross_r=net,
        net_r_base=net,
        net_r_stress=net,
        scaled_out=False,
        exit_unexecutable=False,
        exit_after_unavailable=False,
        gapped_entry=False,
        path_ambiguous=False,
    )


def test_build_day_matrix_counts_per_day(cap: object) -> None:
    d0 = DAYS[0]
    t1 = _trade("AAA", d0, time(10, 5), time(11, 0), 0.5)
    t2 = _trade("BBB", d0, time(10, 6), time(11, 0), -1.0)
    m = build_day_matrix(cap, {"X": [t1, t2], "Y": []}, [d0, DAYS[1]])
    assert m.trades.tolist() == [[2, 0], [0, 0]]
    assert m.net_r[0, 0] == pytest.approx(-0.5)


LIM = PortfolioLimits(
    equity=100_000.0, max_concurrent=2, gross_cap=0.5, per_name_cap=0.1, daily_loss_limit_r=3.0
)
DAY = date(2019, 3, 4)


def test_concurrency_cap_in_time_order_not_by_outcome(cap: object) -> None:
    early_loser = _trade("AAA", DAY, time(10, 0), time(15, 0), -1.0)
    second = _trade("BBB", DAY, time(10, 1), time(15, 0), -1.0)
    late_winner = _trade("CCC", DAY, time(10, 2), time(15, 0), 5.0)
    run = schedule_portfolio(
        cap, [late_winner, second, early_loser], LIM, tie_break="PERMATICKER_ASC"
    )
    assert [t.symbol for t in run.accepted] == ["AAA", "BBB"]  # no hindsight pick of the winner
    assert run.rejected == {"MAX_CONCURRENT": 1} and run.signal_trades == 3


def test_exit_releases_capacity_only_strictly_after_the_exit_minute(cap: object) -> None:
    a = _trade("AAA", DAY, time(10, 0), time(10, 30), 1.0)
    b = _trade("BBB", DAY, time(10, 0), time(10, 30), 1.0)
    same_minute = _trade("CCC", DAY, time(10, 30), time(11, 0), 1.0)
    later = _trade("DDD", DAY, time(10, 31), time(11, 0), 1.0)
    run = schedule_portfolio(cap, [a, b, same_minute, later], LIM, tie_break="PERMATICKER_ASC")
    assert [t.symbol for t in run.accepted] == ["AAA", "BBB", "DDD"]
    assert run.rejected == {"MAX_CONCURRENT": 1}


def test_ties_break_by_symbol_and_input_order_is_irrelevant(cap: object) -> None:
    ts = [_trade(s, DAY, time(10, 0), time(15, 0), 0.0) for s in ("ZZZ", "AAA", "MMM")]
    one = schedule_portfolio(cap, ts, LIM, tie_break="PERMATICKER_ASC")
    two = schedule_portfolio(cap, list(reversed(ts)), LIM, tie_break="PERMATICKER_ASC")
    assert [t.symbol for t in one.accepted] == ["AAA", "MMM"]
    assert [t.symbol for t in two.accepted] == ["AAA", "MMM"]


def test_gross_name_qty_and_daily_loss_limits(cap: object) -> None:
    lim = PortfolioLimits(100_000.0, 10, 0.15, 0.10, 2.0)
    big = _trade("AAA", DAY, time(10, 0), time(15, 0), 0.0, qty=1500)  # 15,000 > 10% name cap
    ok1 = _trade("BBB", DAY, time(10, 0), time(15, 0), 0.0, qty=900)  # 9,000
    ok2 = _trade("CCC", DAY, time(10, 1), time(15, 0), 0.0, qty=900)  # gross 18,000 > 15,000
    zero = _trade("DDD", DAY, time(10, 2), time(15, 0), 0.0, qty=0)
    run = schedule_portfolio(cap, [big, ok1, ok2, zero], lim, tie_break="PERMATICKER_ASC")
    assert [t.symbol for t in run.accepted] == ["BBB"]
    assert run.rejected == {"PER_NAME_CAP": 1, "GROSS_CAP": 1, "QTY_ZERO": 1}
    l1 = _trade("AAA", DAY, time(10, 0), time(10, 10), -1.5)
    l2 = _trade("BBB", DAY, time(10, 1), time(10, 20), -1.0)
    after = _trade("CCC", DAY, time(11, 0), time(15, 0), 2.0)
    r2 = schedule_portfolio(cap, [l1, l2, after], lim, tie_break="PERMATICKER_ASC")
    assert [t.symbol for t in r2.accepted] == ["AAA", "BBB"]
    assert r2.rejected == {"DAILY_LOSS_LIMIT": 1}


def test_same_name_cannot_be_open_twice_and_days_are_independent(cap: object) -> None:
    a = _trade("AAA", DAY, time(10, 0), time(15, 0), 0.0)
    b = _trade("AAA", DAY, time(10, 5), time(15, 0), 0.0)
    nxt = _trade("AAA", DAY + timedelta(days=1), time(10, 0), time(15, 0), 0.0)
    run = schedule_portfolio(cap, [a, b, nxt], LIM, tie_break="PERMATICKER_ASC")
    assert len(run.accepted) == 2 and run.rejected == {"NAME_ALREADY_OPEN": 1}


def test_limits_from_draft_binds_to_the_capability_spec(tmp_path: Path) -> None:
    payload = synth_payload()
    cap, _ = make_capability(tmp_path, payload)
    lim = limits_from_draft(cap, parse_draft(payload), 100_000.0)
    assert lim.max_concurrent == 2 and lim.equity == 100_000.0
    other = synth_payload(**{"risk__max_concurrent": 5})
    with pytest.raises(SpecBindingError):
        limits_from_draft(cap, parse_draft(other), 100_000.0)


def test_capital_rules_proceeds_are_not_compounded_and_freed_notional_is_reusable_next_minute(
    cap: object,
) -> None:
    """Stated, not implied by the priority rule (scheduler docstring):
    * the same-minute entry cannot use an exit's notional or realised R;
    * from the next minute the freed notional IS reusable;
    * realised profit never enlarges the caps (equity is fixed)."""
    one_slot = PortfolioLimits(
        equity=100_000.0, max_concurrent=1, gross_cap=0.5, per_name_cap=0.5, daily_loss_limit_r=9.0
    )
    a = _trade("AAA", DAY, time(10, 0), time(10, 30), 5.0)  # exits at 10:30 with +5R
    same_minute = _trade("BBB", DAY, time(10, 30), time(15, 0), 1.0)
    next_minute = _trade("CCC", DAY, time(10, 31), time(15, 0), 1.0)
    run = schedule_portfolio(
        cap, [a, same_minute, next_minute], one_slot, tie_break="PERMATICKER_ASC"
    )
    assert [t.symbol for t in run.accepted] == ["AAA", "CCC"]
    assert run.rejected == {REJECT_CONCURRENCY: 1}  # BBB: AAA still counted in its exit minute

    # +5R of realised profit does not lift the per-name cap measured on the FIXED equity:
    # 12_000 shares at 10.0 = 120_000 notional > 0.5 * 100_000 even after the win
    big = _trade("DDD", DAY, time(10, 40), time(15, 0), 1.0, qty=12_000, px=10.0)
    run2 = schedule_portfolio(cap, [a, big], one_slot, tie_break="PERMATICKER_ASC")
    assert [t.symbol for t in run2.accepted] == ["AAA"] and run2.rejected == {REJECT_NAME: 1}


# --- one-sided lower confidence bound (before any statistical selection) -------------------


def test_one_sided_lower_bound_is_the_alpha_quantile_and_matches_the_two_sided_lower_end(
    cap: object,
) -> None:
    from app.research.range002.screen.stats import one_sided_lower_bound

    m = matrix(_ar1_skewed(np.random.default_rng(11), 250, 2, 0.0))
    lb = one_sided_lower_bound(cap, m, "C0", 0.05, CFG)
    two = mean_interval(cap, m, "C0", 0.90, CFG)  # (1 - 0.90) / 2 == 0.05 on each side
    assert lb.lower == pytest.approx(two.lower)
    assert lb.alpha == 0.05 and lb.config == CFG
    # a smaller alpha is a more conservative (lower) bound
    assert one_sided_lower_bound(cap, m, "C0", 0.01, CFG).lower < lb.lower


def test_lower_bound_excludes_zero_for_a_planted_edge_and_not_for_a_null(cap: object) -> None:
    from app.research.range002.screen.stats import one_sided_lower_bound

    edge = matrix(_ar1_skewed(np.random.default_rng(3), 250, 1, 0.6))
    assert one_sided_lower_bound(cap, edge, "C0", 0.05, CFG).lower > 0
    raw = _ar1_skewed(np.random.default_rng(4), 250, 1, 0.0)
    null = matrix(raw - raw.mean(axis=0))  # sample mean exactly 0: no edge is observable
    assert one_sided_lower_bound(cap, null, "C0", 0.05, CFG).lower < 0


def test_lower_bound_is_deterministic_undefined_without_trades_and_needs_a_capability(
    cap: object,
) -> None:
    from app.research.range002.screen.stats import one_sided_lower_bound

    m = matrix(_ar1_skewed(np.random.default_rng(5), 100, 1, 0.1))
    assert one_sided_lower_bound(cap, m, "C0", 0.05, CFG) == one_sided_lower_bound(
        cap, m, "C0", 0.05, CFG
    )
    empty = DayMatrix(
        days=DAYS[:5],
        candidates=("Z",),
        net_r=np.zeros((5, 1)),
        trades=np.zeros((5, 1), dtype=np.int64),
    )
    assert one_sided_lower_bound(cap, empty, "Z", 0.05, CFG).lower is None  # undefined, not zero
    with pytest.raises(InvalidCapabilityError):
        one_sided_lower_bound(None, m, "C0", 0.05, CFG)
    for bad in (0.0, 1.0, -0.1):
        with pytest.raises(ParamsUnsetError):
            one_sided_lower_bound(cap, m, "C0", bad, CFG)
