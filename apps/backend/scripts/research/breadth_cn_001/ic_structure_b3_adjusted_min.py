"""BREADTH-CN-001 Track B3 supplement: scale and minimum of the difference-adjusted IC continuous series (daily proxy).

Structure only: no return, trade outcome or equity curve is computed.  For each main-contract rule (SPEC: previous-day
highest open interest; 掘金 mapping: previous-day highest volume) the series is stitched exactly as
breadth_ic.build_main_series does, but on DAILY closes (the 30-minute history needed for the real series is not
available before the last 180 days): the roll gap at a switch is close(new) - close(old) on the last day before the
switch, and history is shifted by the sum of all later gaps so the newest contract is unadjusted.

Reports the minimum / maximum of the adjusted series, the total cumulative adjustment, and whether the adjusted
level ever falls to or below zero.  Only these summary numbers are written.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from gm.api import history, set_token


def stitched(main: pd.Series, close: pd.DataFrame) -> pd.DataFrame:
    """main: date -> contract (the contract traded on that date).  close: date x contract."""
    d = pd.DataFrame({"contract": main})
    d["close"] = [close.at[t, c] for t, c in zip(d.index, d["contract"], strict=True)]
    roll = d["contract"] != d["contract"].shift()
    gap = pd.Series(0.0, index=d.index)
    prev_day = d.index.to_series().shift()
    for t in d.index[roll]:
        p = prev_day[t]
        if pd.isna(p):
            continue
        old, new = d.at[p, "contract"], d.at[t, "contract"]
        o, n = close.at[p, old], close.at[p, new]
        if pd.notna(o) and pd.notna(n):
            gap[t] = n - o
    future = gap[::-1].cumsum()[::-1].shift(-1).fillna(0.0)
    d["adjusted"] = d["close"] + future
    d["gap"] = gap
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--b-dir", required=True)
    a = ap.parse_args()
    b = Path(a.b_dir)
    set_token(Path(a.token_file).read_text().strip())
    tab = pd.read_csv(b / "ic_main_contract_table.csv", parse_dates=["date"]).set_index("date")
    oi = pd.read_csv(b / "ic_daily_oi.csv", parse_dates=["date"])
    closes = {}
    for c in sorted(oi["contract"].unique()):
        lo, hi = oi.loc[oi["contract"] == c, "date"].agg(["min", "max"])
        h = pd.DataFrame(
            history(
                symbol=c,
                frequency="1d",
                start_time=f"{lo.date()} 09:00:00",
                end_time=f"{hi.date()} 16:00:00",
                fields="eob,close",
                df=True,
                adjust=0,
            )
        )
        h["date"] = pd.to_datetime(h["eob"]).dt.tz_localize(None).dt.normalize()
        closes[c] = h.set_index("date")["close"]
    close = pd.DataFrame(closes)
    out = {}
    for name, col in (
        ("spec_rule_prev_day_max_open_interest", "main_ours"),
        ("vendor_rule_prev_day_max_volume", "main_gm_continuous"),
    ):
        main_s = tab[col].dropna()
        s = stitched(main_s, close)
        s = s.dropna(subset=["adjusted"])
        out[name] = {
            "days": int(len(s)),
            "rolls": int((s["gap"] != 0).sum()),
            "actual_close_min": round(float(s["close"].min()), 1),
            "actual_close_max": round(float(s["close"].max()), 1),
            "adjusted_min": round(float(s["adjusted"].min()), 1),
            "adjusted_min_date": str(s["adjusted"].idxmin().date()),
            "adjusted_max": round(float(s["adjusted"].max()), 1),
            "total_cumulative_adjustment_points": round(float(s["gap"].sum()), 1),
            "oldest_day_adjustment_points": round(
                float(s["adjusted"].iloc[0] - s["close"].iloc[0]), 1
            ),
            "adjusted_ever_le_zero": bool((s["adjusted"] <= 0).any()),
        }
    (b / "trackB_b3_adjusted_series_summary.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8"
    )
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
