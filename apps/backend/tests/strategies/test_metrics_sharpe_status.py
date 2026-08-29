"""Sharpe zero-variance diagnostic — reporting correctness only.

``sharpe_ratio`` returns 0.0 for four *different* reasons, only one of which is a
measurement. On a report that 0.00 reads as "computed, and the risk-adjusted
return is exactly zero" — a strategy-separation failure — when the statistic was
usually never computable at all.

``sharpe_ratio_status`` separates the cases. The decision contract does not move:
the equivalence test below is the guard that ranking, promotion gates and
persisted ``metrics_json`` see byte-identical values.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.strategies.metrics import SharpeStatus, sharpe_ratio, sharpe_ratio_status


def _curve(values: list[float], *, same_day: bool = False) -> list[tuple[datetime, float]]:
    base = datetime(2026, 1, 5, 16, 0, tzinfo=UTC)
    step = timedelta(hours=1) if same_day else timedelta(days=1)
    return [(base + step * i, v) for i, v in enumerate(values)]


class TestZeroVarianceIsNotAZero:
    def test_constant_equity_is_insufficient_variance_not_zero_sharpe(self) -> None:
        """A perfectly flat book has NO variance — the ratio is undefined, not 0."""
        value, status = sharpe_ratio_status(_curve([100.0, 100.0, 100.0, 100.0]))
        assert status is SharpeStatus.INSUFFICIENT_VARIANCE
        assert value is None

    def test_constant_nonzero_return_is_degenerate_not_a_real_sharpe(self) -> None:
        """Compounding at a fixed 10%/day. Mathematically the returns are constant,
        so the ratio is undefined — but they differ by ONE ULP, so ``stdev == 0``
        (an exact comparison) never fires and the frozen formula returns ~4.7e16.

        This is the sharper half of the defect: not a misleading 0.00, but a
        number large enough to clear any ratio gate.
        """
        curve = _curve([100.0, 110.0, 121.0, 133.1])
        value, status = sharpe_ratio_status(curve)
        assert status is SharpeStatus.DEGENERATE_VARIANCE
        # The value is still carried, because the frozen contract still returns it.
        assert value is not None
        assert value > 1e15
        assert sharpe_ratio(curve) == value

    def test_exactly_constant_equity_has_bitwise_zero_variance(self) -> None:
        """The flat-book case DOES hit stdev == 0 exactly (all returns are 0.0)."""
        value, status = sharpe_ratio_status(_curve([100.0, 100.0, 100.0]))
        assert status is SharpeStatus.INSUFFICIENT_VARIANCE
        assert value is None


class TestOtherNonComputableCases:
    def test_single_point(self) -> None:
        assert sharpe_ratio_status(_curve([100.0]))[1] is SharpeStatus.INSUFFICIENT_POINTS

    def test_empty(self) -> None:
        assert sharpe_ratio_status([])[1] is SharpeStatus.INSUFFICIENT_POINTS

    def test_intraday_only_is_insufficient_trading_days(self) -> None:
        """Many points, one date — annualizing this would be 60x sqrt(252) nonsense."""
        curve = _curve([100.0, 101.0, 102.0, 103.0], same_day=True)
        assert sharpe_ratio_status(curve)[1] is SharpeStatus.INSUFFICIENT_TRADING_DAYS

    def test_nonpositive_prior_equity_yields_no_usable_returns(self) -> None:
        curve = _curve([0.0, 0.0, 0.0])
        assert sharpe_ratio_status(curve)[1] is SharpeStatus.NO_USABLE_RETURNS


class TestComputableCase:
    def test_varying_returns_are_ok_and_carry_a_value(self) -> None:
        value, status = sharpe_ratio_status(_curve([100.0, 105.0, 103.0, 110.0]))
        assert status is SharpeStatus.OK
        assert value is not None
        assert value != 0.0

    def test_ok_value_is_the_annualized_ratio(self) -> None:
        curve = _curve([100.0, 105.0, 103.0, 110.0])
        value, _ = sharpe_ratio_status(curve)
        assert value == pytest.approx(sharpe_ratio(curve))


class TestDecisionContractIsFrozen:
    """The guard: no ranking, promotion gate or metrics_json value may move."""

    @pytest.mark.parametrize(
        "curve",
        [
            [],
            _curve([100.0]),
            _curve([100.0, 100.0, 100.0]),
            _curve([100.0, 110.0, 121.0]),
            _curve([0.0, 0.0, 0.0]),
            _curve([100.0, 105.0, 103.0, 110.0]),
            _curve([100.0, 95.0, 99.0, 90.0]),
            _curve([100.0, 101.0, 102.0], same_day=True),
        ],
    )
    def test_sharpe_ratio_matches_the_pre_change_formula(self, curve: list) -> None:
        """Re-implements the ORIGINAL body verbatim and asserts equality.

        If this fails, the refactor changed a number some gate depends on.
        """
        import math

        def original(equity_curve: list) -> float:
            if len(equity_curve) < 2:
                return 0.0
            by_day: dict[str, float] = {}
            for ts, eq in equity_curve:
                by_day[ts.date().isoformat()] = float(eq)
            if len(by_day) < 2:
                return 0.0
            sorted_eq = [by_day[k] for k in sorted(by_day.keys())]
            returns: list[float] = []
            for i in range(1, len(sorted_eq)):
                prev = sorted_eq[i - 1]
                if prev <= 0:
                    continue
                returns.append((sorted_eq[i] - prev) / prev)
            if not returns:
                return 0.0
            mean = sum(returns) / len(returns)
            variance = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
            stdev = math.sqrt(variance)
            if stdev == 0:
                return 0.0
            return (mean / stdev) * math.sqrt(252.0)

        assert sharpe_ratio(curve) == original(curve)

    def test_every_non_ok_status_still_reports_zero(self) -> None:
        for curve in ([], _curve([100.0]), _curve([100.0, 100.0]), _curve([0.0, 0.0, 0.0])):
            _, status = sharpe_ratio_status(curve)
            if status is not SharpeStatus.OK:
                assert sharpe_ratio(curve) == 0.0

    def test_decimal_equity_is_accepted(self) -> None:
        base = datetime(2026, 1, 5, 16, 0, tzinfo=UTC)
        curve = [
            (base + timedelta(days=i), Decimal(v)) for i, v in enumerate(["100", "105", "103"])
        ]
        assert sharpe_ratio_status(curve)[1] is SharpeStatus.OK
