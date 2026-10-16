"""Tests for two definitional rules.  Run: python3 test_build_invariance.py
1. Stale MA: after a suspension longer than ma_max_span, a stock is ineligible until it has 5 fresh bars.
2. Pull-start invariance: rows before --start feed only the MA warm-up, so pulling from 2013-01 or 2013-07
   gives the identical indicator for --start 2014-01-01."""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import breadth_ic as B


def test_stale_ma():
    days = pd.bdate_range("2024-01-01", periods=60)
    rows = []
    for code in ("A", "B"):
        keep = np.ones(60, bool)
        if code == "A":
            keep[10:40] = False                                  # 30-session suspension
        rows.append(pd.DataFrame({"date": days[keep], "code": code, "close_adj": 10.0 + np.arange(keep.sum()),
                                  "is_excluded": False}))
    df = B._above_ma(pd.concat(rows), 5, 10)
    a = df[df.code == "A"].set_index("date")
    resume = days[40:45]
    assert not a.loc[resume[:4], "eligible"].any(), "stale MA counted after resumption"
    assert a.loc[resume[4], "eligible"], "5th fresh bar should be eligible"
    b = df[df.code == "B"].set_index("date")
    assert b.loc[days[4]:, "eligible"].all()
    print("ok stale MA: resumed stock ineligible for 4 bars, eligible on the 5th")


def test_pull_start_invariance():
    import test_breadth_ic as T
    days = pd.bdate_range("2013-01-02", "2017-06-30")
    s, _ = T.make_stocks(days, 120)
    s = s.assign(close=s["close_adj"], adj_factor=1.0, is_st=0, is_suspended=0,
                 is_new_listing_nc=0, is_delisting_period=0).drop(columns=["close_adj", "is_excluded"])
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        for tag, start in (("jan", "2013-01-01"), ("jul", "2013-07-01")):
            csv = Path(tmp) / f"{tag}.csv"
            s[s["date"] >= start].to_csv(csv, index=False)
            r = subprocess.run([sys.executable, str(Path(__file__).parent / "build_indicator.py"), "--csv", str(csv),
                                "--start", "2014-01-01", "--out", str(Path(tmp) / tag)], capture_output=True, text=True)
            assert r.returncode == 0, r.stderr[-600:]
            out[tag] = {f: pd.read_csv(Path(tmp) / tag / f"breadth_{f}.csv", index_col=0) for f in ("daily", "weekly", "monthly")}
    for f in ("daily", "weekly", "monthly"):
        a, b = out["jan"][f], out["jul"][f]
        assert a.index.equals(b.index) and np.allclose(a.fillna(-9).values, b.fillna(-9).values), f"{f} depends on pull start"
    print("ok pull-start invariance: 2013-01 vs 2013-07 pulls give identical daily/weekly/monthly output")


if __name__ == "__main__":
    test_stale_ma()
    test_pull_start_invariance()
    print("ALL TESTS PASSED")
