"""Guard: backtest P&L, fees and notional use ACTUAL contract prices; the difference-adjusted series only drives signals.
Run: python3 test_pnl_uses_actual_prices.py

The adjusted level is not a price (under the SPEC open-interest rule its daily proxy goes below zero; Track B3).
Two checks: (1) every line of backtest() that touches P&L, fees or fill prices is free of the *_cont columns;
(2) shifting the adjusted series by a constant (even to negative levels) shifts its MA equally, so signals are
unchanged and the resulting trades (entry price, P&L, fees) must be identical."""

import inspect
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import breadth_ic as B  # noqa: E402
import test_breadth_ic as T  # noqa: E402


def test_pnl_lines_do_not_read_adjusted_columns() -> None:
    src = inspect.getsource(B.backtest).splitlines()
    pnl_lines = [
        ln
        for ln in src
        if any(
            k in ln
            for k in (
                "pnl_pts",
                "_fee(",
                "fill_open",
                "exit_px",
                "new_px",
                "entry_px",
                "notional",
                "px =",
            )
        )
    ]
    assert pnl_lines, "could not find P&L lines"
    bad = [ln.strip() for ln in pnl_lines if "_cont" in ln]
    assert not bad, f"P&L code reads the adjusted series: {bad}"
    cont_uses = [ln.strip() for ln in src if "_cont" in ln]
    assert all(
        ("ma" in ln or "above" in ln or "recs" in ln or "close_cont" in ln) for ln in cont_uses
    ), cont_uses
    print(
        "ok no P&L/fee/fill line reads close_cont/open_cont; adjusted columns appear only in the signal and record-list lines"
    )


def test_shifted_adjusted_series_gives_identical_trades() -> None:
    days = pd.bdate_range("2014-01-02", "2018-12-31")
    stocks, f = T.make_stocks(days, 120)
    ic30, oi = T.make_ic(days, f)
    cfg = B.Config()
    br = B.stock_breadth(stocks, cfg)
    setups = B.daily_setups(br, cfg)
    ser = B.build_main_series(ic30, B.main_contract_by_day(oi))
    win = B.setup_windows(setups, pd.DatetimeIndex(ser["date"].unique()), cfg)
    base = B.backtest(ser, win, cfg)
    assert len(base) > 5
    shifted = ser.copy()
    shifted["close_cont"] = shifted["close_cont"] - 1.0e5  # adjusted levels now far below zero
    shifted["open_cont"] = shifted["open_cont"] - 1.0e5
    assert (shifted["close_cont"] < 0).all()
    other = B.backtest(shifted, win, cfg)
    cols = [
        "side",
        "entry_time",
        "exit_time",
        "contract",
        "entry_px",
        "pnl_pts",
        "fees",
        "pnl_cny",
        "notional",
    ]
    pd.testing.assert_frame_equal(
        base[cols].reset_index(drop=True), other[cols].reset_index(drop=True)
    )
    print(
        f"ok {len(base)} trades identical with the adjusted series shifted to negative levels (P&L, fees, entry prices unchanged)"
    )


if __name__ == "__main__":
    test_pnl_lines_do_not_read_adjusted_columns()
    test_shifted_adjusted_series_gives_identical_trades()
    print("ALL TESTS PASSED")
