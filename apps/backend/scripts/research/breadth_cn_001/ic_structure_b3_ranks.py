"""BREADTH-CN-001 Track B3 supplement: which contract does each main-contract rule pick, and how do they disagree?

Reads the B1 contract master and the B3 table.  For every date, ranks the live contracts by expiry (1 = nearest)
and reports, per rule (SPEC previous-day highest open interest vs 掘金 continuous mapping), how often a non-front
contract is chosen, per year, plus the lengths of runs of consecutive disagreeing days.  No prices are used.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b-dir", required=True)
    d = Path(ap.parse_args().b_dir)
    m = pd.read_csv(
        d / "ic_contract_master.csv", parse_dates=["listed_date", "last_trading_day_vendor"]
    ).set_index("contract")
    t = pd.read_csv(d / "ic_main_contract_table.csv", parse_dates=["date"])

    def rank(day: pd.Timestamp, contract: str) -> float:
        live = m[(m["listed_date"] <= day) & (m["last_trading_day_vendor"] > day)].sort_values(
            "last_trading_day_vendor"
        )
        idx = list(live.index)
        return float(idx.index(contract) + 1) if contract in idx else np.nan

    g = t.dropna(subset=["main_gm_continuous"]).reset_index(drop=True)
    g["rank_oi_rule"] = [rank(x, c) for x, c in zip(g["date"], g["main_ours"], strict=True)]
    g["rank_volume_rule_gm"] = [
        rank(x, c) for x, c in zip(g["date"], g["main_gm_continuous"], strict=True)
    ]
    dis = g["main_ours"] != g["main_gm_continuous"]
    run_id = (dis != dis.shift()).cumsum()
    runs = dis.groupby(run_id).agg(["first", "size"])
    runs = runs[runs["first"]]["size"]
    yearly = g.groupby(g["date"].dt.year).apply(
        lambda x: pd.Series(
            {
                "oi_rule_non_front": round(float((x["rank_oi_rule"] > 1).mean()), 3),
                "volume_rule_non_front": round(float((x["rank_volume_rule_gm"] > 1).mean()), 3),
                "disagree": round(float((x["main_ours"] != x["main_gm_continuous"]).mean()), 3),
            }
        ),
        include_groups=False,
    )
    summary = {
        "days": int(len(g)),
        "oi_rule_rank_counts": {
            int(k): int(v) for k, v in g["rank_oi_rule"].value_counts().sort_index().items()
        },
        "volume_rule_rank_counts": {
            int(k): int(v) for k, v in g["rank_volume_rule_gm"].value_counts().sort_index().items()
        },
        "oi_rule_non_front_share": round(float((g["rank_oi_rule"] > 1).mean()), 3),
        "volume_rule_non_front_share": round(float((g["rank_volume_rule_gm"] > 1).mean()), 3),
        "disagreement_runs": int(len(runs)),
        "run_length_buckets": {
            str(k): int(v)
            for k, v in pd.cut(
                runs, [0, 1, 3, 5, 10, 20, 100], labels=["1", "2-3", "4-5", "6-10", "11-20", ">20"]
            )
            .value_counts()
            .sort_index()
            .items()
        },
        "disagreeing_days": int(dis.sum()),
        "disagreeing_days_in_runs_over_10": int(runs[runs > 10].sum()),
        "when_they_differ_volume_rule_is_nearer_expiry_share": round(
            float((g.loc[dis, "rank_volume_rule_gm"] < g.loc[dis, "rank_oi_rule"]).mean()), 3
        ),
        "by_year": yearly.to_dict("index"),
    }
    (d / "trackB_b3_ranks_summary.json").write_text(
        json.dumps(summary, indent=1, default=str), encoding="utf-8"
    )
    g.to_csv(d / "ic_main_contract_rank_compare.csv", index=False)
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
