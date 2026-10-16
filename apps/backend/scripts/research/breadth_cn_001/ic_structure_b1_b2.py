"""BREADTH-CN-001 Track B1/B2: IC contract master and daily open-interest panel (structure only).

No return, trade outcome or equity curve is computed.  Prices are not stored; only open interest, volume and
the session-record fields that define the contract (multiplier, margin ratio).  Source: 掘金 free daily access
(terminal must be open).  Output folder: <out> (outside Git).

  contract master  -> ic_contract_master.csv   (one row per IC contract, source columns per field)
  daily OI panel   -> ic_daily_oi.csv          (date, contract, oi, expiry, volume; two OI sources side by side)
  coverage table   -> ic_oi_coverage.csv       (contract-days against the CFFEX calendar)
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd
from gm.api import get_history_symbol, get_symbol_infos, get_trading_dates, history, set_token

SERIES_START = "2016-07-01"  # SPEC B2: every contract and session from 2016-07 on


def third_friday(year: int, month: int, sessions: set[pd.Timestamp]) -> pd.Timestamp | None:
    """Third Friday of the month; a holiday defers to the next trading day.  None if the calendar does not
    reach that month (future contracts)."""
    d = pd.Timestamp(year, month, 1)
    d += pd.Timedelta(days=(4 - d.weekday()) % 7 + 14)
    for _ in range(10):
        if d in sessions:
            return d
        d += pd.Timedelta(days=1)
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--end", default="2026-10-16")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    set_token(Path(a.token_file).read_text().strip())

    inf = pd.DataFrame(
        get_symbol_infos(sec_type1=1040, sec_type2=104001, exchanges=["CFFEX"], df=True)
    )
    ic = inf[inf["symbol"].str.match(r"^CFFEX\.IC\d{4}$")].copy()
    for c in ("listed_date", "delisted_date"):
        ic[c] = pd.to_datetime(ic[c]).dt.tz_localize(None).dt.normalize()
    cal = pd.DatetimeIndex(
        pd.to_datetime(get_trading_dates("CFFEX", "2015-01-01", "2027-12-31"))
    ).tz_localize(None)
    sessions = set(cal.normalize())
    cal_through = pd.Timestamp(a.end)

    master, oi_rows, cov = [], [], []
    for r in ic.sort_values("symbol").itertuples(index=False):
        ym = r.symbol[-4:]
        year, month = 2000 + int(ym[:2]), int(ym[2:])
        rule = third_friday(year, month, sessions)
        row = {
            "contract": r.symbol,
            "listed_date": r.listed_date.date(),
            "last_trading_day_vendor": r.delisted_date.date(),
            "last_trading_day_third_friday_rule": rule.date() if rule is not None else None,
            "vendor_matches_rule": bool(r.delisted_date == rule) if rule is not None else None,
            "scheduled_future_listing": bool(r.listed_date > cal_through),
            "price_tick": r.price_tick,
            "underlying": r.underlying_symbol,
            "source_contract_fields": "gm get_symbol_infos(CFFEX stock-index futures)",
            "source_rule": "third Friday of the contract month, deferred to next CFFEX trading day (calendar: gm get_trading_dates CFFEX)",
        }
        lo = max(r.listed_date, pd.Timestamp(SERIES_START))
        hi = min(r.delisted_date, cal_through)
        if hi >= lo:
            sess = pd.DataFrame(
                get_history_symbol(
                    symbol=r.symbol,
                    start_date=lo.strftime("%Y-%m-%d"),
                    end_date=hi.strftime("%Y-%m-%d"),
                    df=True,
                )
            )
            time.sleep(0.2)
            hist = pd.DataFrame(
                history(
                    symbol=r.symbol,
                    frequency="1d",
                    start_time=lo.strftime("%Y-%m-%d") + " 09:00:00",
                    end_time=hi.strftime("%Y-%m-%d") + " 16:00:00",
                    fields="eob,volume,position",
                    df=True,
                    adjust=0,
                )
            )
            time.sleep(0.2)
            if len(sess):
                sess["date"] = (
                    pd.to_datetime(sess["trade_date"]).dt.tz_localize(None).dt.normalize()
                )
                row["multiplier"] = (
                    sorted(set(sess["multiplier"].dropna().astype(float)))[0]
                    if sess["multiplier"].notna().any()
                    else None
                )
                row["multiplier_distinct"] = sorted(set(sess["multiplier"].dropna().astype(float)))
                row["source_multiplier"] = "gm get_history_symbol session record"
            if len(hist):
                hist["date"] = pd.to_datetime(hist["eob"]).dt.tz_localize(None).dt.normalize()
            s = sess.set_index("date")["position"] if len(sess) else pd.Series(dtype=float)
            h = (
                hist.set_index("date")[["position", "volume"]]
                if len(hist)
                else pd.DataFrame(columns=["position", "volume"])
            )
            exp = [d for d in cal if lo <= d <= hi]
            days = sorted(set(exp) | set(s.index) | set(h.index))
            for d in days:
                oi_rows.append(
                    {
                        "date": d.date(),
                        "contract": r.symbol,
                        "oi_history": h["position"].get(d),
                        "oi_session": s.get(d),
                        "volume": h["volume"].get(d),
                        "expiry": r.delisted_date.date(),
                        "in_cffex_calendar": d in sessions,
                    }
                )
            got = set(h.index) | set(s.index)
            miss = [d for d in exp if d not in got]
            both = [d for d in exp if d in h.index and d in s.index]
            disagree = [
                d
                for d in both
                if pd.notna(h["position"].get(d))
                and pd.notna(s.get(d))
                and float(h["position"][d]) != float(s[d])
            ]
            zero = [
                d
                for d in exp
                if d in h.index and (pd.isna(h["position"].get(d)) or float(h["position"][d]) <= 0)
            ]
            cov.append(
                {
                    "contract": r.symbol,
                    "window": f"{lo.date()}..{hi.date()}",
                    "expected_days": len(exp),
                    "retrieved_days": len(got & set(exp)),
                    "missing_days": len(miss),
                    "missing_list": ";".join(str(d.date()) for d in miss[:10]),
                    "unexpected_days": len(got - set(exp)),
                    "oi_nonpositive_days": len(zero),
                    "oi_sources_disagree_days": len(disagree),
                }
            )
        master.append(row)
        print(r.symbol, row.get("multiplier"), flush=True)
    pd.DataFrame(master).to_csv(out / "ic_contract_master.csv", index=False)
    pd.DataFrame(oi_rows).to_csv(out / "ic_daily_oi.csv", index=False)
    cv = pd.DataFrame(cov)
    cv.to_csv(out / "ic_oi_coverage.csv", index=False)
    m = pd.DataFrame(master)
    summary = {
        "contracts": int(len(m)),
        "vendor_matches_third_friday_rule": int((m["vendor_matches_rule"] == True).sum()),  # noqa: E712
        "vendor_differs_from_rule": m.loc[m["vendor_matches_rule"] == False, "contract"].tolist(),  # noqa: E712
        "rule_not_checkable_calendar_ends": m.loc[
            m["vendor_matches_rule"].isna(), "contract"
        ].tolist(),
        "multiplier_values": sorted(
            {x for v in m.get("multiplier_distinct", pd.Series(dtype=object)).dropna() for x in v}
        ),
        "contracts_in_oi_panel": int(len(cv)),
        "expected_contract_days": int(cv["expected_days"].sum()),
        "retrieved_contract_days": int(cv["retrieved_days"].sum()),
        "missing_contract_days": int(cv["missing_days"].sum()),
        "unexpected_contract_days": int(cv["unexpected_days"].sum()),
        "oi_nonpositive_days": int(cv["oi_nonpositive_days"].sum()),
        "oi_sources_disagree_days": int(cv["oi_sources_disagree_days"].sum()),
        "series_start": SERIES_START,
        "through": a.end,
    }
    (out / "trackB_b1_b2_summary.json").write_text(
        json.dumps(summary, indent=1, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
