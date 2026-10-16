"""BREADTH-CN-001 Track B3: main-contract table (diagnostic only; no prices, no returns).

Applies breadth_ic.main_contract_by_day (the contract with the most open interest at the PREVIOUS close, never an
expired one) to the B2 open-interest panel, and compares it with 掘金's continuous mapping, which only starts on
2021-07-09.  Neither mapping is overridden: this reports where they agree and where they differ.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import breadth_ic as B
import pandas as pd
from gm.api import get_continuous_contracts, set_token


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--b2-dir", required=True)
    a = ap.parse_args()
    d = Path(a.b2_dir)
    oi = pd.read_csv(d / "ic_daily_oi.csv", parse_dates=["date", "expiry"])
    panel = oi.rename(columns={"oi_history": "oi"})[["date", "contract", "oi", "expiry"]].dropna(
        subset=["oi"]
    )
    ours = B.main_contract_by_day(panel)
    t = pd.DataFrame({"date": ours.index, "main_ours": ours.to_numpy()})

    set_token(Path(a.token_file).read_text().strip())
    gm = pd.DataFrame(
        get_continuous_contracts(csymbol="CFFEX.IC", start_date="2016-07-01", end_date="2026-10-15")
    )
    gm["date"] = pd.to_datetime(gm["trade_date"]).dt.tz_localize(None).dt.normalize()
    t = t.merge(
        gm.rename(columns={"symbol": "main_gm_continuous"})[["date", "main_gm_continuous"]],
        on="date",
        how="left",
    )
    both = t.dropna(subset=["main_gm_continuous"]).copy()
    both["agree"] = both["main_ours"] == both["main_gm_continuous"]
    t["agree"] = t["main_ours"] == t["main_gm_continuous"]
    t.loc[t["main_gm_continuous"].isna(), "agree"] = pd.NA
    t.to_csv(d / "ic_main_contract_table.csv", index=False)
    diff = both[~both["agree"]]
    # does gm's mapping look like "max OI at the SAME day's close" instead of the previous close?
    same = (
        oi.sort_values(["date", "oi_history"], ascending=[True, False])
        .groupby("date")
        .head(1)
        .set_index("date")["contract"]
    )
    both = both.assign(same_day_max_oi=both["date"].map(same))
    summary = {
        "ours_first": str(t["date"].min().date()),
        "ours_last": str(t["date"].max().date()),
        "ours_days": int(len(t)),
        "ours_roll_count": int((t["main_ours"] != t["main_ours"].shift()).sum() - 1),
        "gm_overlap_first": str(both["date"].min().date()),
        "gm_overlap_days": int(len(both)),
        "agree_days": int(both["agree"].sum()),
        "differ_days": int(len(diff)),
        "agreement_share": round(float(both["agree"].mean()), 4),
        "differ_days_where_gm_equals_same_day_max_oi": int(
            (
                diff.merge(both[["date", "same_day_max_oi"]], on="date").eval(
                    "main_gm_continuous == same_day_max_oi"
                )
            ).sum()
        ),
        "differ_sample": diff.head(15)
        .assign(date=lambda x: x["date"].dt.strftime("%Y-%m-%d"))
        .to_dict("records"),
    }
    (d / "trackB_b3_summary.json").write_text(
        json.dumps(summary, indent=1, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
