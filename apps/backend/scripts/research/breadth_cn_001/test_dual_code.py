"""Tests for dual_code.py (synthetic).  Run: python3 test_dual_code.py"""

import sys
import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import dual_code as D  # noqa: E402

DAYS = pd.bdate_range("2014-01-02", "2019-12-31")


def series(code: str, days, seed: int, shift: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    px = np.round(10 + np.cumsum(rng.standard_normal(len(DAYS))) * 0.1 + 50, 2)
    s = pd.Series(px, index=DAYS).loc[days]
    return pd.DataFrame(
        {
            "date": s.index.strftime("%Y-%m-%d"),
            "code": code,
            "close": [f"{x + shift:.4f}" for x in s.to_numpy()],
        }
    )


def build() -> tuple[duckdb.DuckDBPyConnection, pd.DataFrame]:
    old_days = DAYS[DAYS <= "2018-12-26"]
    new_days = DAYS  # successor carries the full history (as 001872/302132 do)
    p = pd.concat([
        series("sz.000022", old_days, seed=1),             # predecessor
        series("sz.001872", new_days, seed=1),             # successor: identical closes on common dates
        series("sz.000100", DAYS, seed=2),                 # unrelated
        series("sz.000200", DAYS, seed=3),                 # unrelated
        series("sh.600500", old_days, seed=4),             # near-miss pair: 0.5% of closes differ
        series("sh.600501", old_days, seed=4),
    ], ignore_index=True)  # fmt: skip
    idx = p.index[(p["code"] == "sh.600501")][::200]  # ~0.5% differ -> share ~0.995 < 0.999
    p.loc[idx, "close"] = "1.0000"
    one = p.index[(p["code"] == "sz.001872") & (p["date"] == "2017-10-24")]
    p.loc[one, "close"] = p.loc[one, "close"].map(
        lambda x: f"{float(x) + 0.02:.4f}"
    )  # one differing day, as in the real pair
    con = duckdb.connect()
    con.register("bars_df", p)
    con.execute("create table bars as select * from bars_df")
    return con, p


def test_detect_flags_only_the_true_pair() -> None:
    con, _ = build()
    r = D.detect(con)
    assert len(r) == 1, r
    row = r.iloc[0]
    assert {row["code_a"], row["code_b"]} == {"sz.000022", "sz.001872"}
    assert row["identical_share"] >= D.IDENTICAL_SHARE_MIN and row["common_dates"] == len(
        DAYS[DAYS <= "2018-12-26"]
    )
    assert (
        row["approved"] == 0 and row["proposed_drop_code"] == ""
    )  # no master given -> no proposal, nothing approved
    print(
        "ok detector flags the dual-code pair (one differing day tolerated), rejects near-miss 0.995 pair and unrelated codes"
    )


def test_master_proposes_predecessor_and_apply_needs_approval() -> None:
    con, p = build()
    with tempfile.TemporaryDirectory() as tmp:
        m = Path(tmp) / "m.csv"
        pd.DataFrame(
            {"code": ["SZSE.000022", "SZSE.001872"], "delist_date": ["2018-12-26", None]}
        ).to_csv(m, index=False)
        r = D.detect(con, "bars", str(m))
    assert r.iloc[0]["proposed_drop_code"] == "sz.000022"
    unchanged = D.apply_approved(p, r)  # approved == 0 -> nothing happens
    assert len(unchanged) == len(p)
    r.loc[:, "approved"] = 1
    out = D.apply_approved(p, r)
    both = set(p.loc[p["code"] == "sz.000022", "date"]) & set(
        p.loc[p["code"] == "sz.001872", "date"]
    )
    assert (
        (out["code"] == "sz.000022").sum()
        == len(set(p.loc[p["code"] == "sz.000022", "date"]) - both)
        == 0
    )
    assert (out["code"] == "sz.001872").sum() == (
        p["code"] == "sz.001872"
    ).sum()  # successor untouched
    assert len(out) == len(p) - len(both)
    print(
        "ok no auto-apply; once approved, only the predecessor rows on dates where both codes have rows are dropped"
    )


def test_apply_keeps_predecessor_rows_outside_the_overlap() -> None:
    con, p = build()
    p2 = p[
        ~((p["code"] == "sz.001872") & (p["date"] < "2015-01-01"))
    ]  # successor starts later than predecessor
    con2 = duckdb.connect()
    con2.register("b", p2)
    con2.execute("create table bars as select * from b")
    r = D.detect(con2)
    r.loc[:, ["approved", "proposed_drop_code"]] = [1, "sz.000022"]
    out = D.apply_approved(p2, r)
    early = out[(out["code"] == "sz.000022") & (out["date"] < "2015-01-01")]
    assert (
        len(early) == len(p2[(p2["code"] == "sz.000022") & (p2["date"] < "2015-01-01")]) > 0
    )  # no successor row there -> kept
    assert not ((out["code"] == "sz.000022") & (out["date"] >= "2015-01-01")).any()
    print("ok predecessor rows with no successor row on the same date are kept")


if __name__ == "__main__":
    test_detect_flags_only_the_true_pair()
    test_master_proposes_predecessor_and_apply_needs_approval()
    test_apply_keeps_predecessor_rows_outside_the_overlap()
    print("ALL TESTS PASSED")
