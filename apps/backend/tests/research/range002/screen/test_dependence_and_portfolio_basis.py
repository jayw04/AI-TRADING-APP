"""Two properties that must hold by construction, tested directly (SYNTHETIC):

* the bootstrap resamples whole TRADING DAYS, so cross-symbol and cross-candidate dependence
  inside a day is preserved (never resampled symbol-by-symbol or candidate-by-candidate);
* a portfolio-basis result can only come from the scheduler, so its rejection ledger always
  travels with it and an unconstrained signal list cannot be reported as portfolio performance.
"""

from __future__ import annotations

from datetime import time
from pathlib import Path

import numpy as np
import pytest

from app.research.range002.screen.report import summarize, summarize_portfolio
from app.research.range002.screen.scheduler import REJECT_CONCURRENCY, schedule_portfolio
from app.research.range002.screen.stats import (
    BootstrapConfig,
    DayMatrix,
    _resample_means,
    build_day_matrix,
    mean_interval,
)
from tests.research.range002.screen.conftest import make_capability, synth_payload
from tests.research.range002.screen.test_stats_scheduler import DAY, DAYS, LIM, _trade

CFG = BootstrapConfig(mean_block_days=5.0, reps=400, seed=99)


@pytest.fixture
def cap(tmp_path: Path) -> object:
    return make_capability(tmp_path, synth_payload())[0]


def test_offsetting_symbols_on_the_same_day_stay_offset_in_every_replicate(cap: object) -> None:
    """If symbols were resampled independently, +1/-1 pairs would stop cancelling and the
    interval would have width. Day-cluster resampling keeps every day's net at exactly zero."""
    trades = []
    for i, d in enumerate(DAYS[:60]):
        shock = 0.2 + 0.05 * (i % 7)
        trades += [
            _trade("AAA", d, time(10, 0), time(11, 0), shock),
            _trade("BBB", d, time(10, 1), time(11, 0), -shock),
        ]
    m = build_day_matrix(cap, {"X": trades}, DAYS[:60])
    assert np.allclose(m.net_r, 0.0) and (m.trades == 2).all()
    iv = mean_interval(cap, m, "X", 0.9, CFG)
    assert iv.lower == pytest.approx(0.0) and iv.upper == pytest.approx(0.0)


def test_candidates_move_together_across_replicates() -> None:
    """Candidate Y is exactly 2x candidate X on every day; with shared day indices their
    replicate means are perfectly correlated (independent resampling would not be)."""
    rng = np.random.default_rng(5)
    x = rng.standard_normal(120)
    m = DayMatrix(
        days=DAYS[:120],
        candidates=("X", "Y"),
        net_r=np.column_stack([x, 2 * x]),
        trades=np.ones((120, 2), dtype=np.int64),
    )
    means, _ = _resample_means(m, CFG)
    assert np.corrcoef(means[:, 0], means[:, 1])[0, 1] == pytest.approx(1.0)
    assert np.allclose(means[:, 1], 2 * means[:, 0])


def test_portfolio_summary_carries_the_rejection_ledger(cap: object) -> None:
    trades = [
        _trade("AAA", DAY, time(10, 0), time(15, 0), 1.0),
        _trade("BBB", DAY, time(10, 1), time(15, 0), -0.5),
        _trade("CCC", DAY, time(10, 2), time(15, 0), 2.0),  # third concurrent: refused (cap = 2)
    ]
    signal = summarize(cap, trades)
    assert signal["basis"] == "signal" and signal["trades"] == 3

    run = schedule_portfolio(cap, trades, LIM, tie_break="PERMATICKER_ASC")
    port = summarize_portfolio(cap, run)
    assert port["basis"] == "portfolio"
    assert port["signal_trades"] == 3 and port["accepted_trades"] == 2
    assert port["rejected_by_reason"] == {REJECT_CONCURRENCY: 1}
    assert port["base"]["total_net_r"] == pytest.approx(0.5)  # the refused +2.0 is not in it
    with pytest.raises(TypeError):
        summarize_portfolio(cap, trades)  # type: ignore[arg-type]
