"""Dual-code detector (BREADTH-CN-001): one company listed under an old and a new code carries the same bars twice.

Observed 2026-10-16: 000022/001872, 000043/001914 and 300114/302132 each have bars under BOTH codes on the same
dates with identical closes; counting both would double-count the company in breadth.

CRITERIA (frozen 2026-10-16; changing either needs a new dated entry in the research log)
  * date match      : both codes have a row on the date (only such dates are ever candidates for removal);
  * identical close : the raw (unadjusted) close strings are exactly equal on that date;
  * a code pair is flagged when it has >= COMMON_DATES_MIN common dates and
    identical dates / common dates >= IDENTICAL_SHARE_MIN.
COMMON_DATES_MIN only guards against chance equality on a handful of dates; it is not a tuning knob.

NOTHING IS APPLIED AUTOMATICALLY.  detect() writes a review list.  A person sets `approved` = 1 on the rows to apply,
and apply_approved() then drops the proposed predecessor's rows ONLY on the dates where both codes have rows.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd

COMMON_DATES_MIN = 60
IDENTICAL_SHARE_MIN = 0.999


def detect(
    con: duckdb.DuckDBPyConnection, table: str = "bars", master_csv: str | None = None
) -> pd.DataFrame:
    """Review list of flagged code pairs.  `table` needs columns date, code, close (vendor strings)."""
    pairs = con.execute(f"""
        select a.code as code_a, b.code as code_b, count(*) as identical_dates
        from {table} a join {table} b on a.date = b.date and a.close = b.close and a.code < b.code
        group by 1, 2 having count(*) >= {COMMON_DATES_MIN}
    """).df()
    if pairs.empty:
        return pairs.assign(common_dates=[], identical_share=[])
    con.register("cand", pairs[["code_a", "code_b"]])
    common = con.execute(f"""
        select c.code_a, c.code_b, count(*) as common_dates, min(a.date) as first_common, max(a.date) as last_common
        from cand c join {table} a on a.code = c.code_a join {table} b on b.code = c.code_b and b.date = a.date
        group by 1, 2
    """).df()
    rows = (
        con.execute(f"select code, count(*) as n from {table} group by 1")
        .df()
        .set_index("code")["n"]
    )
    out = pairs.merge(common, on=["code_a", "code_b"])
    out["identical_share"] = out["identical_dates"] / out["common_dates"]
    out = out[
        (out["common_dates"] >= COMMON_DATES_MIN) & (out["identical_share"] >= IDENTICAL_SHARE_MIN)
    ].copy()
    out["rows_a"], out["rows_b"] = out["code_a"].map(rows), out["code_b"].map(rows)
    out["proposed_drop_code"], out["basis"] = "", "no master dates: needs review"
    if master_csv:
        m = pd.read_csv(master_csv, parse_dates=["delist_date"])
        m["k"] = m["code"].astype(str).str.extract(r"(\d{6})")[0]
        dl = m.drop_duplicates("k").set_index("k")["delist_date"]
        for i, r in out.iterrows():
            da, db = dl.get(r["code_a"][-6:]), dl.get(r["code_b"][-6:])
            if pd.notna(da) and pd.isna(db):
                out.loc[i, ["proposed_drop_code", "basis"]] = [
                    r["code_a"],
                    "master: code_a delisted, code_b still listed",
                ]
            elif pd.isna(da) and pd.notna(db):
                out.loc[i, ["proposed_drop_code", "basis"]] = [
                    r["code_b"],
                    "master: code_b delisted, code_a still listed",
                ]
            elif pd.notna(da) and pd.notna(db) and da != db:
                out.loc[i, ["proposed_drop_code", "basis"]] = [
                    r["code_a"] if da < db else r["code_b"],
                    "master: earlier delist_date",
                ]
    out["approved"] = 0
    return out.sort_values(["first_common", "code_a"]).reset_index(drop=True)


def apply_approved(panel: pd.DataFrame, review: pd.DataFrame) -> pd.DataFrame:
    """Drop, for each APPROVED pair, the proposed predecessor's rows on dates where both codes have a row."""
    ok = review[(review["approved"] == 1) & (review["proposed_drop_code"] != "")]
    drop = pd.Series(False, index=panel.index)
    for r in ok.itertuples():
        other = r.code_b if r.proposed_drop_code == r.code_a else r.code_a
        both = set(panel.loc[panel["code"] == other, "date"]) & set(
            panel.loc[panel["code"] == r.proposed_drop_code, "date"]
        )
        drop |= (panel["code"] == r.proposed_drop_code) & panel["date"].isin(both)
    return panel[~drop]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True)
    ap.add_argument("--master-csv")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    con = duckdb.connect(a.store, read_only=True)
    review = detect(con, "bars", a.master_csv)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    review.to_csv(a.out, index=False)
    print(f"{len(review)} flagged pair(s) written to {a.out}; none applied")


if __name__ == "__main__":
    main()
