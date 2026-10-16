"""BREADTH-CN-001 Track B4: 1-minute -> 30-minute aggregator for IC bars (structure and completeness only).

Conventions (declared, as the instruction requires)
  * Sessions: 09:30-11:30 and 13:00-15:00 (CFFEX stock-index futures, since 2016-01-01; earlier hours differ and
    must be taken from CFFEX notices before any pre-2016 use - this module refuses dates before 2016-01-01).
  * Labels: a bar is labelled at its CLOSE.  A 1-minute bar's `eob` is its end time (first bar of the day 09:31,
    last 15:00), so the 30-minute bars end at 10:00, 10:30, 11:00, 11:30, 13:30, 14:00, 14:30, 15:00 and
    cover 1-minute bars with eob in (end-30min, end].
  * Call auction: no separate auction bar exists in the 1-minute series; whatever the vendor folds into the
    09:31 bar (the opening print) becomes part of the first 30-minute bar's open.  Nothing is added or inferred.
  * Completeness: a 30-minute bar built from fewer than 30 one-minute bars is FLAGGED (`complete` = False), never
    filled or interpolated.  The report is a completeness table; no prices are written out and no return is computed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

SESSION_ENDS = ["10:00", "10:30", "11:00", "11:30", "13:30", "14:00", "14:30", "15:00"]
FIRST_SUPPORTED = pd.Timestamp("2016-01-01")


def aggregate_30m(m1: pd.DataFrame) -> pd.DataFrame:
    """m1: columns eob (tz-naive datetime, bar END), open, high, low, close, volume.  Returns one row per 30-minute
    bar actually present: label (bar end), n_1m, complete, open, high, low, close, volume."""
    d = m1.copy()
    d["eob"] = pd.to_datetime(d["eob"])
    if (d["eob"] < FIRST_SUPPORTED).any():
        raise ValueError(
            "pre-2016-01-01 bars use different trading hours; verify against CFFEX notices first"
        )
    d = d.sort_values("eob")
    mins = d["eob"].dt.hour * 60 + d["eob"].dt.minute
    ends = [int(s[:2]) * 60 + int(s[3:]) for s in SESSION_ENDS]
    label_min = pd.Series(pd.NA, index=d.index, dtype="Int64")
    for e in ends:
        label_min[(mins > e - 30) & (mins <= e)] = e
    d = d[
        label_min.notna()
    ].copy()  # minutes outside the two sessions are dropped (reported by the caller)
    d["label"] = d["eob"].dt.normalize() + pd.to_timedelta(
        label_min[label_min.notna()].astype(int), unit="m"
    )
    g = d.groupby("label", sort=True)
    out = g.agg(
        n_1m=("close", "size"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).reset_index()
    out["complete"] = out["n_1m"] == 30
    return out


def expected_labels(dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(
        [
            d + pd.Timedelta(hours=int(s[:2]), minutes=int(s[3:]))
            for d in dates
            for s in SESSION_ENDS
        ]
    )


def completeness(m1: pd.DataFrame, sessions: pd.DatetimeIndex) -> dict:
    """Completeness of the 30-minute bars implied by `m1` over the given trading sessions."""
    bars = aggregate_30m(m1)
    exp = expected_labels(sessions)
    have = set(bars["label"])
    outside = int((~pd.to_datetime(m1["eob"]).dt.strftime("%H:%M").between("09:31", "15:00")).sum())
    missing = [t for t in exp if t not in have]
    partial = bars[~bars["complete"]]
    return {
        "sessions": int(len(sessions)),
        "expected_30m_bars": int(len(exp)),
        "present_30m_bars": int(len(have & set(exp))),
        "complete_30m_bars": int(bars.loc[bars["label"].isin(exp), "complete"].sum()),
        "bars_with_fewer_than_30_minutes": int(len(partial)),
        "missing_30m_bars": int(len(missing)),
        "unexpected_30m_labels": int(len(have - set(exp))),
        "one_minute_bars_outside_sessions": outside,
        "partial_examples": [
            {"label": str(r.label), "n_1m": int(r.n_1m)} for r in partial.head(10).itertuples()
        ],
        "missing_examples": [str(t) for t in missing[:10]],
        "complete_share": round(
            float(bars.loc[bars["label"].isin(exp), "complete"].sum() / max(len(exp), 1)), 4
        ),
    }


def main() -> None:
    from gm.api import get_trading_dates, history, set_token

    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--contracts", default="CFFEX.IC2606,CFFEX.IC2609,CFFEX.IC2612")
    ap.add_argument("--start", default="2026-04-21")
    ap.add_argument("--end", default="2026-10-15")
    a = ap.parse_args()
    set_token(Path(a.token_file).read_text().strip())
    cal = (
        pd.DatetimeIndex(pd.to_datetime(get_trading_dates("CFFEX", a.start, a.end)))
        .tz_localize(None)
        .normalize()
    )
    res = {}
    for c in a.contracts.split(","):
        raw = pd.DataFrame(
            history(
                symbol=c,
                frequency="60s",
                start_time=f"{a.start} 09:00:00",
                end_time=f"{a.end} 16:00:00",
                fields="eob,open,high,low,close,volume",
                df=True,
                adjust=0,
            )
        )
        raw["eob"] = pd.to_datetime(raw["eob"]).dt.tz_localize(None)
        days = pd.DatetimeIndex(
            sorted(set(raw["eob"].dt.normalize()) & set(cal))
        )  # sessions on which the contract traded
        res[c] = {
            "first_session": str(days.min().date()),
            "last_session": str(days.max().date()),
            **completeness(raw, days),
        }
        print(c, {k: v for k, v in res[c].items() if not k.endswith("examples")}, flush=True)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / "trackB_b4_completeness.json").write_text(
        json.dumps(res, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
