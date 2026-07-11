"""MR-002 pre-freeze data verifications V1-V4 (pre-reg v0.3 §8).

Host-venv, read-only, no stack. Interrogates the actual vendor holdings
(Sharadar via Nasdaq Data Link + FMP probe) to answer the four freeze blockers:

  V1  PIT earnings schedule    - forward calendar with known-at timestamps?
  V2  PIT sector history       - effective-dated sector/industry classifications?
  V3  price-series consistency - can SEP/ACTIONS deliver the four registered series?
  V4  historical borrow / HTB  - any PIT borrow-availability source?

Run:
    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
        apps/backend/scripts/mr002_verify_v1_v4.py

Writes JSON evidence to Docs/implementation/evidence/mr_002/. Exit code is
always 0 unless the vendor is unreachable: these are *findings*, not gates -
the verdicts feed the owner's freeze decision.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import truststore  # ADR 0017 - OS trust store before any HTTPS (Norton)

truststore.inject_into_ssl()

import httpx  # noqa: E402
import pandas as pd  # noqa: E402

try:
    from dotenv import load_dotenv  # noqa: E402

    _root = Path(__file__).resolve().parents[3]
    for env in (_root / ".env", _root / "apps" / "backend" / ".env"):
        if env.exists():
            load_dotenv(env, override=False)
except Exception:
    pass

NDL_KEY = os.environ.get("NASDAQ_DATA_LINK_API_KEY", "")
FMP_KEY = os.environ.get("FMP_API_KEY", "")
NDL_BASE = "https://data.nasdaq.com/api/v3/datatables/SHARADAR"
OUT_DIR = Path(__file__).resolve().parents[3] / "Docs" / "implementation" / "evidence" / "mr_002"

findings: dict[str, dict] = {}


def ndl_table(client: httpx.Client, dataset: str, max_pages: int = 10, **params) -> pd.DataFrame:
    params["api_key"] = NDL_KEY
    frames, cursor, pages = [], None, 0
    while pages < max_pages:
        q = dict(params)
        if cursor:
            q["qopts.cursor_id"] = cursor
        r = client.get(f"{NDL_BASE}/{dataset}.json", params=q, timeout=60)
        r.raise_for_status()
        dt = r.json()["datatable"]
        cols = [c["name"] for c in dt["columns"]]
        frames.append(pd.DataFrame(dt["data"], columns=cols))
        cursor = r.json().get("meta", {}).get("next_cursor_id")
        pages += 1
        if not cursor:
            break
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def note(section: str, key: str, value) -> None:
    findings.setdefault(section, {})[key] = value
    print(f"  [{section}] {key}: {value}")


def main() -> int:
    print(f"key lengths: NDL={len(NDL_KEY)} FMP={len(FMP_KEY)}; today={date.today()}")
    if not NDL_KEY:
        print("FATAL: NASDAQ_DATA_LINK_API_KEY missing")
        return 1
    client = httpx.Client(follow_redirects=True)

    # ---------------- V1 - PIT earnings schedule ----------------
    print("\nV1 - PIT earnings schedule")
    try:
        ev = ndl_table(client, "EVENTS", ticker="AAPL", max_pages=6)
        note("V1", "sharadar_events_columns", sorted(ev.columns.tolist()))
        note("V1", "sharadar_events_rows_aapl", len(ev))
        if not ev.empty:
            note("V1", "sharadar_events_date_range", f"{ev['date'].min()} .. {ev['date'].max()}")
            codes = set()
            for c in ev.get("eventcodes", pd.Series(dtype=str)).dropna().astype(str):
                codes.update(x.strip() for x in c.split("|"))
            note("V1", "sharadar_events_distinct_codes_sample", sorted(codes)[:30])
        # any FUTURE-dated rows anywhere? (forward calendar test)
        fut = ndl_table(client, "EVENTS", max_pages=1, **{"date.gte": str(date.today())})
        note("V1", "sharadar_events_future_rows", len(fut))
    except Exception as e:
        note("V1", "sharadar_events_error", repr(e)[:200])

    if FMP_KEY:
        try:
            r = client.get(
                "https://financialmodelingprep.com/api/v3/historical/earning_calendar/AAPL",
                params={"apikey": FMP_KEY, "limit": 20},
                timeout=30,
            )
            body = r.json() if r.status_code == 200 else None
            note("V1", "fmp_hist_earning_calendar_status", r.status_code)
            if isinstance(body, list) and body:
                note("V1", "fmp_hist_earning_calendar_fields", sorted(body[0].keys()))
                note("V1", "fmp_time_field_sample", [row.get("time") for row in body[:6]])
                note(
                    "V1",
                    "fmp_updatedFromDate_sample",
                    [row.get("updatedFromDate") for row in body[:6]],
                )
        except Exception as e:
            note("V1", "fmp_error", repr(e)[:160])

    # ---------------- V2 - PIT sector history ----------------
    print("\nV2 - PIT sector history")
    try:
        tk = ndl_table(client, "TICKERS", max_pages=1, table="SEP", ticker="AAPL")
        note("V2", "tickers_columns", sorted(tk.columns.tolist()))
        note("V2", "tickers_rows_for_aapl", len(tk))
        if not tk.empty:
            row = tk.iloc[0]
            note(
                "V2",
                "aapl_classification",
                {
                    k: str(row.get(k))
                    for k in ("sector", "industry", "sicsector", "siccode", "famaindustry")
                    if k in tk.columns
                },
            )
        # does TICKERS keep >1 row per ticker (history) across table variants?
        tk_all = ndl_table(client, "TICKERS", max_pages=1, ticker="AAPL")
        per_table = tk_all.groupby("table").size().to_dict() if "table" in tk_all.columns else {}
        note("V2", "aapl_rows_per_table_param", per_table)
        has_effective_dates = any(
            c in tk_all.columns for c in ("effectivedate", "startdate", "enddate", "asof")
        )
        note("V2", "tickers_has_effective_date_fields", has_effective_dates)
    except Exception as e:
        note("V2", "tickers_error", repr(e)[:200])

    # a reclassification example: META moved Tech->Communication Services (GICS 2018)
    try:
        meta = ndl_table(client, "TICKERS", max_pages=1, table="SEP", ticker="META")
        if not meta.empty:
            note(
                "V2",
                "meta_current_classification",
                {
                    k: str(meta.iloc[0].get(k))
                    for k in ("sector", "industry", "siccode")
                    if k in meta.columns
                },
            )
    except Exception as e:
        note("V2", "meta_error", repr(e)[:160])

    # ---------------- V3 - price series consistency ----------------
    print("\nV3 - price-series consistency (AAPL 4:1 split 2020-08-31 + Aug-2020 dividend)")
    try:
        sep = ndl_table(
            client, "SEP", ticker="AAPL", **{"date.gte": "2020-08-01", "date.lte": "2020-09-15"}
        )
        sep = sep.sort_values("date").reset_index(drop=True)
        note("V3", "sep_columns", sorted(sep.columns.tolist()))
        pre = sep[sep["date"] < "2020-08-31"].iloc[-1]
        post = sep[sep["date"] >= "2020-08-31"].iloc[0]
        note("V3", "pre_split_close_vs_closeunadj", round(float(pre["closeunadj"]) / float(pre["close"]), 3))
        note("V3", "post_split_close_vs_closeunadj", round(float(post["closeunadj"]) / float(post["close"]), 3))
        # volume basis: split-adjusted volume shows NO 4x level shift across the split
        v_pre = sep[sep["date"] < "2020-08-31"]["volume"].astype(float).median()
        v_post = sep[sep["date"] >= "2020-08-31"]["volume"].astype(float).median()
        note("V3", "median_volume_pre_vs_post_split_ratio", round(v_post / v_pre, 2))
        # dividend basis: ex-div 2020-08-07 - closeadj/close ratio steps, close/closeunadj does not
        ex = "2020-08-07"
        d0 = sep[sep["date"] < ex].iloc[-1]
        d1 = sep[sep["date"] >= ex].iloc[0]
        r_adj_0 = float(d0["closeadj"]) / float(d0["close"])
        r_adj_1 = float(d1["closeadj"]) / float(d1["close"])
        note("V3", "closeadj_over_close_before_exdiv", round(r_adj_0, 5))
        note("V3", "closeadj_over_close_after_exdiv", round(r_adj_1, 5))
        note("V3", "dividend_step_in_closeadj_ratio", abs(r_adj_1 - r_adj_0) > 1e-4)
    except Exception as e:
        note("V3", "sep_error", repr(e)[:200])

    try:
        act = ndl_table(client, "ACTIONS", ticker="AAPL", max_pages=4)
        note("V3", "actions_columns", sorted(act.columns.tolist()))
        note("V3", "actions_types_aapl", sorted(set(act["action"])) if "action" in act else [])
        div = act[act["action"] == "dividend"] if "action" in act else pd.DataFrame()
        note("V3", "dividend_rows_have_value", bool(len(div)) and div["value"].notna().all())
    except Exception as e:
        note("V3", "actions_error", repr(e)[:200])

    # delisting: does ACTIONS mark it, and does SEP carry prices to the end? (TWTR 2022-10)
    try:
        act_t = ndl_table(client, "ACTIONS", ticker="TWTR", max_pages=2)
        note("V3", "twtr_action_types", sorted(set(act_t["action"])) if "action" in act_t else [])
        sep_t = ndl_table(client, "SEP", ticker="TWTR", **{"date.gte": "2022-10-01"})
        note("V3", "twtr_last_sep_date", str(sep_t["date"].max()) if not sep_t.empty else "none")
        note("V3", "vendor_delisting_return_field", "none in SEP/ACTIONS schema (priority-1 unavailable)")
    except Exception as e:
        note("V3", "delisting_error", repr(e)[:200])

    # ---------------- V4 - historical borrow / HTB ----------------
    print("\nV4 - historical borrow / hard-to-borrow source")
    note(
        "V4",
        "sharadar_bundle",
        "Core US Equities Bundle (SEP/SF1/DAILY/METRICS/TICKERS/ACTIONS/EVENTS/INDICATORS/SP500 "
        "+ SF3/SF3A); NO SF2, no borrow/short-interest table with PIT availability",
    )
    if FMP_KEY:
        try:
            r = client.get(
                "https://financialmodelingprep.com/api/v4/short-interest",
                params={"symbol": "AAPL", "apikey": FMP_KEY},
                timeout=30,
            )
            note("V4", "fmp_short_interest_status", r.status_code)
        except Exception as e:
            note("V4", "fmp_short_interest_error", repr(e)[:120])
    note("V4", "alpaca_easy_to_borrow", "current-snapshot only (asset.easy_to_borrow); not historical/PIT")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "V1_V4_raw_findings.json"
    out.write_text(json.dumps(findings, indent=2, default=str))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
