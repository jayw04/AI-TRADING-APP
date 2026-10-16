"""Focused tests for the symbol-set coverage check in build_indicator.coverage_by_date.
Run from this folder: python3 test_coverage_sets.py   (imports the real breadth_ic; the earlier stub is no longer needed)."""
import tempfile
from pathlib import Path

import build_indicator as b
import pandas as pd

CAL = pd.bdate_range("2024-01-01", "2024-01-12")        # 10 sessions
MASTER = pd.DataFrame({
    "code": ["600001.SH", "600002.SH", "600003.SH", "600004.SH"],
    "list_date": ["2020-01-01"] * 4,
    "delist_date": ["2038-01-01", "2038-01-01", "2024-01-10", "2038-01-01"],
    "board": ["SH_MAIN"] * 4})


def run(rows, master=None, start=None, end=None, extra_cal=None):
    d = Path(tempfile.mkdtemp())
    cal = CAL if extra_cal is None else extra_cal
    pd.DataFrame({"date": cal.strftime("%Y-%m-%d")}).to_csv(d / "cal.csv", index=False)
    (MASTER if master is None else master).to_csv(d / "m.csv", index=False)
    panel = pd.DataFrame(rows, columns=["date", "code"])
    cov = b.coverage_by_date(panel, str(d / "m.csv"), str(d / "cal.csv"), d, start or CAL[0], end or CAL[-1])
    rd = lambda n: pd.read_csv(d / n, parse_dates=["date"], dtype={"key": str})   # noqa: E731
    return cov, rd("coverage_missing_symbols.csv"), rd("coverage_unexpected_symbols.csv"), d


def full(code, dates):
    return [(x, code) for x in dates]


def test_offsetting_gap_is_visible():
    """one symbol missing + one unknown symbol present => counts equal, sets differ"""
    rows = full("600001.SH", CAL) + full("600003.SH", CAL[CAL < "2024-01-10"]) + full("600004.SH", CAL) \
        + full("600999.SH", CAL)                       # 600002 absent, 600999 not in master
    cov, miss, unexp, _ = run(rows)
    assert set(miss.key) == {"600002"} and set(miss.kind) == {"whole_symbol"}, miss
    assert set(unexp.key) == {"600999"} and set(unexp.reason) == {"not_in_master"}, unexp
    day = cov[cov.date == "2024-01-02"].iloc[0]
    assert day.expected - day.missing == day.retrieved_expected
    assert day.missing == 1 and day.unexpected == 1       # count subtraction alone would show 0 net gap


def test_delisting_date_is_not_a_session():
    rows = full("600001.SH", CAL) + full("600002.SH", CAL) + full("600004.SH", CAL) + full("600003.SH", CAL)
    _, miss, unexp, _ = run(rows)
    assert miss.empty, miss
    u = unexp[unexp.key == "600003"]
    assert set(u.reason) == {"on_or_after_delisting"} and u.date.min() == pd.Timestamp("2024-01-10"), u
    assert len(u) == 3                                    # 01-10, 01-11, 01-12


def test_missing_kinds_and_not_in_calendar():
    holes = CAL.delete([3])                                # interior hole
    rows = full("600001.SH", holes) + full("600002.SH", CAL[2:]) + full("600004.SH", CAL[:-2]) \
        + full("600003.SH", CAL[CAL < "2024-01-10"]) + [(pd.Timestamp("2024-01-06"), "600001.SH")]   # a Saturday
    _, miss, unexp, _ = run(rows)
    kinds = miss.groupby("key").kind.agg(lambda s: sorted(set(s))).to_dict()
    assert kinds == {"600001": ["interior"], "600002": ["leading"], "600004": ["trailing"]}, kinds
    assert unexp.loc[unexp.key == "600001", "reason"].tolist() == ["not_in_calendar"], unexp


def test_requested_period_not_observed_period():
    """a download that silently starts late / ends early is a gap against the explicit request"""
    rows = [r for c in ("600001.SH", "600002.SH", "600004.SH") for r in full(c, CAL[4:8])] + full("600003.SH", CAL[4:8])
    _, miss, _, d = run(rows)                              # request is the full 10 sessions
    assert set(miss.kind) == {"leading", "trailing"} and len(miss) == 3 * 6 + 4, miss.groupby("kind").size()   # 600003 expects only up to 01-09
    _, miss2, _, d2 = run(rows, start=CAL[4], end=CAL[7])  # request matches what was pulled: no gap
    assert miss2.empty, miss2
    import json
    per = json.loads((d / "coverage_period.json").read_text())
    assert per["requested_sessions"] == 10 and per["requested_sessions_with_no_rows"] == 6, per


def test_unconfirmed_boundary_cannot_shrink_expectation():
    """600190-style last_trade_date derived from the same download is only a candidate; a truncated download must still show as missing"""
    m = MASTER.copy()
    m["last_trade_date"] = [None, None, "2024-01-05", None]; m["last_trade_basis"] = [None, None, "vendor_tradestatus", None]
    m["last_trade_confirmed"] = [None, None, 0, None]
    rows = full("600001.SH", CAL) + full("600002.SH", CAL) + full("600004.SH", CAL) + full("600003.SH", CAL[CAL <= "2024-01-05"])
    _, miss, _, d = run(rows, master=m)
    k = miss[miss.key == "600003"]
    assert len(k) == 2 and set(k.kind) == {"trailing"}, miss                   # 01-08 and 01-09: listed interval ends before the 01-10 delisting date
    bnd = pd.read_csv(d / "coverage_boundaries.csv", dtype={"key": str})
    assert bnd.loc[bnd.key == "600003", "last_ignored_because"].iloc[0] == "not_confirmed", bnd
    m["last_trade_basis"] = ["panel_derived" if x else None for x in [False, False, True, False]]; m["last_trade_confirmed"] = [None, None, 1, None]
    _, miss2, _, d2 = run(rows, master=m)                                      # even flagged confirmed, a panel-derived basis is refused
    bnd2 = pd.read_csv(d2 / "coverage_boundaries.csv", dtype={"key": str})
    assert bnd2.loc[bnd2.key == "600003", "last_ignored_because"].iloc[0] == "derived_from_the_panel_itself", bnd2


def test_confirmed_trading_interval_overrides_listed_interval():
    """600190-style: confirmed last real trade before the delisting date; carry-forward rows after it are neither missing nor expected"""
    m = MASTER.copy()
    m["last_trade_date"] = [None, None, "2024-01-08", None]; m["last_trade_basis"] = [None, None, "exchange_notice", None]
    m["last_trade_confirmed"] = [None, None, 1, None]; m["delist_date"] = ["2038-01-01", "2038-01-01", "2024-01-11", "2038-01-01"]
    rows = [(x, c) for c in ("600001.SH", "600002.SH", "600004.SH") for x in CAL] + [(x, "600003.SH") for x in CAL[CAL <= "2024-01-08"]]
    _, miss, _, _ = run(rows, master=m)
    assert miss.empty, miss
    rows += [(pd.Timestamp("2024-01-09"), "600003.SH"), (pd.Timestamp("2024-01-10"), "600003.SH")]     # suspended carry-forward rows
    _, miss, unexp, _ = run(rows, master=m)
    u = unexp[unexp.key == "600003"]
    assert miss.empty and u.reason.tolist() == ["after_last_trade_before_delisting"] * 2, u
    # and a confirmed boundary does not hide a hole inside the trading interval
    _, miss3, _, _ = run([r for r in rows if r != (pd.Timestamp("2024-01-05"), "600003.SH")], master=m)
    assert miss3.key.tolist() == ["600003"] and miss3.kind.tolist() == ["interior"], miss3


def test_summary_includes_unexpected_only_groups():
    """a weekend row, and an unexpected-only board, must appear in coverage_by_date.csv"""
    rows = [r for c in ("600001.SH", "600002.SH", "600004.SH", "600003.SH") for r in full(c, CAL[CAL < "2024-01-10"])] \
        + [(pd.Timestamp("2024-01-06"), "600001.SH"), (pd.Timestamp("2024-01-03"), "688999.SH")]   # Saturday; STAR code not in master
    cov, _, unexp, _ = run(rows)
    sat = cov[(cov.date == "2024-01-06") & (cov.board == "SH_MAIN")]
    assert len(sat) == 1 and sat.iloc[0].expected == 0 and sat.iloc[0].unexpected == 1, cov
    star = cov[cov.board == "STAR"]
    assert len(star) == 1 and star.iloc[0].expected == 0 and star.iloc[0].unexpected == 1, cov
    assert cov.unexpected.sum() == len(unexp)


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
    print("ALL TESTS PASSED")
