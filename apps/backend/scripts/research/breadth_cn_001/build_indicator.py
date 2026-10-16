"""
BREADTH-CN-001 step 1 — build the breadth (情绪广度) indicator from the A-share store.

Outcome-blind: computes no forward return, signal outcome or P&L.  Fits the CN-P0 ground rules.

Usage (DuckDB store, e.g. myquant_free):
  python3 build_indicator.py --duckdb /path/to/myquant_free.duckdb \
      --sql "SELECT trade_date AS date, symbol AS code, close, adj_factor, sec_name, is_st, is_suspended
             FROM daily_bars JOIN history_symbol USING (symbol, trade_date)" \
      --out out/breadth_v1
Usage (CSV):
  python3 build_indicator.py --csv stocks.csv --out out/breadth_v1

Required columns after the query: date, code, close, adj_factor (a missing adj_factor aborts: unadjusted closes
would put ex-date gaps into the 5-period MA; pass --allow-unadjusted only for a deliberate diagnostic run)
Optional: sec_name, is_st, is_suspended, board (derived from the code prefix when absent; BSE is then only
detectable if the panel contains BSE codes - the census warns when it does not)
Exclusions (point-in-time, per row): is_st == 1; sec_name starting with ST / *ST / S*ST / N / C;
sec_name containing 退 (退市整理); is_suspended == 1 rows dropped (neither numerator nor denominator).

Outputs in --out:
  breadth_daily.csv / breadth_weekly.csv / breadth_monthly.csv   (n_above, n_eligible, ratio, pct, setup)
  breadth_daily.png / breadth_weekly.png / breadth_monthly.png / ratio_vs_count.png
  census.csv      per-year rows, eligible names, exclusions by reason, suspicious adjusted jumps
  manifest.json   query, row count, date span, config digest, file hashes
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
from pathlib import Path

import breadth_ic as B
import numpy as np
import pandas as pd

NAME_EXCL = re.compile(r"^(\*?S?\*?ST|N|C)")     # ST, *ST, S*ST, SST, N新股, C次新(注册制前5日)


def board_from_code(code: pd.Series) -> pd.Series:
    """Rule-based board from the exchange-listing code prefix (not a vendor historical-board panel: a
    stock that moved boards, e.g. SZ SME -> main in 2021, keeps one label here; it is only used for QA)."""
    c = code.astype(str).str.extract(r"(\d{6})")[0].fillna("")
    out = pd.Series("OTHER", index=code.index)
    out[c.str.match(r"^60[0-9]")] = "SH_MAIN"
    out[c.str.match(r"^688|^689")] = "STAR"
    out[c.str.match(r"^(000|001|002|003)")] = "SZ_MAIN"
    out[c.str.match(r"^(300|301)")] = "CHINEXT"
    out[c.str.match(r"^(4|8|920)")] = "BSE"
    return out


def load(args) -> tuple[pd.DataFrame, str]:
    if args.duckdb:
        import duckdb
        con = duckdb.connect(args.duckdb, read_only=True)
        df = con.execute(args.sql).df()
        src = f"duckdb:{args.duckdb} :: {args.sql}"
    else:
        df = pd.read_csv(args.csv, dtype={"code": str})
        src = f"csv:{args.csv}"
    missing = {"date", "code", "close"} - set(df.columns)
    if missing:
        raise SystemExit(f"query result lacks required columns: {sorted(missing)}")
    return df, src


args_allow_unadjusted = False   # set from --allow-unadjusted in main()


def _flag(df: pd.DataFrame, col: str) -> pd.Series:
    """Nullable 0/1 flag -> Int64 with NA kept. A value outside {0,1} aborts: it is a data defect, not 'false'."""
    v = pd.to_numeric(df[col], errors="coerce")
    bad = v.notna() & ~v.isin([0, 1])
    if bad.any():
        raise SystemExit(f"column {col} holds values outside 0/1 ({int(bad.sum())} rows)")
    return v.astype("Int64")


def prepare(df: pd.DataFrame, start: str):
    """Returns (tradable rows, census, jumps, unknown-share by date).  Rows BEFORE `start` are deliberately kept for
    the factor carry-forward and the MA warm-up only.  They do NOT enter the percentile history: main() trims each
    breadth series to `start` before percentiles and setups are computed (SPEC C3; test_build_invariance.py)."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    if df.duplicated(["date", "code"]).any():
        raise SystemExit("duplicate (date, code) rows — fix the join before building the indicator")
    missing = {"is_st", "is_suspended"} - set(df.columns)
    if missing:
        raise SystemExit(f"required status columns missing: {sorted(missing)} (no default to 'false': unknown is not eligible)")
    if "sec_name" not in df and not {"is_new_listing_nc", "is_delisting_period"} <= set(df.columns):
        raise SystemExit("need point-in-time sec_name, or explicit is_new_listing_nc AND is_delisting_period columns "
                         "(1/0, NULL = unknown; from date-effective listing rules or verified announcements)")
    if "adj_factor" not in df:
        if not args_allow_unadjusted:
            raise SystemExit("no adj_factor column - refusing to build on unadjusted closes (see --allow-unadjusted)")
        df["adj_factor"] = 1.0
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["adj_factor"] = pd.to_numeric(df["adj_factor"], errors="coerce")
    for c in ("close", "adj_factor"):
        if np.isinf(df[c]).any():
            raise SystemExit(f"non-finite (inf) values in {c}")
    df = df.sort_values(["code", "date"])
    # factors are event-based in several sources: carry the latest VERIFIED factor forward within a stock,
    # across the start date; rows before the first known factor stay NaN -> 'no_adj_factor' (excluded, counted)
    df["adj_factor"] = df.groupby("code")["adj_factor"].ffill()
    if "board" not in df:
        df["board"] = board_from_code(df["code"])

    st, susp = _flag(df, "is_st"), _flag(df, "is_suspended")
    name = df["sec_name"].astype("string").str.strip() if "sec_name" in df else pd.Series(pd.NA, index=df.index, dtype="string")
    has_name = (name.notna() & (name != "")).fillna(False).astype(bool)
    nc_name = name.str.match(r"^(N|C)").astype("boolean").where(has_name)
    del_name = name.str.contains("退").astype("boolean").where(has_name)
    st_name = (name.str.match(NAME_EXCL) & ~name.str.match(r"^(N|C)")).astype("boolean").where(has_name)

    def known(explicit: str, from_name: pd.Series) -> pd.Series:
        """explicit column wins; else the point-in-time name; else UNKNOWN (NA) - never 'false'."""
        e = _flag(df, explicit).astype("boolean") if explicit in df else pd.Series(pd.NA, index=df.index, dtype="boolean")
        return e.fillna(from_name)

    nc, dl = known("is_new_listing_nc", nc_name), known("is_delisting_period", del_name)
    close_ok = df["close"].notna() & (df["close"] > 0)
    fac_ok = df["adj_factor"].notna() & (df["adj_factor"] > 0)
    reasons = pd.DataFrame({
        "st_flag": st.eq(1).fillna(False).astype(bool),
        "st_name": st_name.fillna(False).astype(bool),
        "new_NC": nc.fillna(False).astype(bool),
        "delisting": dl.fillna(False).astype(bool),
        "suspended": susp.eq(1).fillna(False).astype(bool),
        "bad_price": ~close_ok,
        "no_adj_factor": ~fac_ok,
        # unknown eligibility inputs: never silently eligible; reported per year
        "unknown_st": st.isna(), "unknown_suspended": susp.isna(),
        "unknown_nc": nc.isna(), "unknown_delisting": dl.isna(),
    }, index=df.index)
    unknown_any = reasons[["unknown_st", "unknown_suspended", "unknown_nc", "unknown_delisting"]].any(axis=1)
    df["is_excluded"] = reasons[["st_flag", "st_name", "new_NC", "delisting"]].any(axis=1) | unknown_any
    # suspended rows are neither numerator nor denominator; unknown suspension cannot be assumed 'trading'
    keep = ~(reasons["suspended"] | reasons["unknown_suspended"] | reasons["bad_price"] | reasons["no_adj_factor"])
    df["close_adj"] = df["close"] * df["adj_factor"]

    # census (data QA only - not an outcome); trimmed to >= start's year
    d = df.sort_values(["code", "date"])
    r = d.groupby("code")["close_adj"].pct_change(fill_method=None).abs()
    board = d["board"].astype(str)
    yr = d["date"].dt.year
    reasons = reasons.loc[d.index]
    census = pd.DataFrame({
        "rows": yr.groupby(yr).size(),
        "codes": d.groupby(yr)["code"].nunique(),
        "eligible_codes": d[keep.loc[d.index] & ~d["is_excluded"]].groupby(yr)["code"].nunique(),
        **{f"excl_{c}": reasons[c].groupby(yr).sum() for c in reasons},
        # adjusted daily move > 25% (> any non-IPO A-share limit outside BSE's 30%): adjustment or data defect suspects
        "adj_jump_gt25pct": (r > 0.25).groupby(yr).sum(),
        "adj_jump_gt25pct_bse_excluded": ((r > 0.25) & ~board.str.contains("BSE|北交|BJ", case=False)).groupby(yr).sum(),
        "codes_bse": d[board.str.contains("BSE", case=False)].groupby(yr)["code"].nunique(),
        "codes_star": d[board.str.contains("STAR")].groupby(yr)["code"].nunique(),
    }).fillna(0).astype({"codes_bse": int, "codes_star": int})
    census = census[census.index >= pd.Timestamp(start).year]
    big = d.assign(move=r)[(r > 0.25) & ~board.str.contains("BSE|北交|BJ", case=False) & (d["date"] >= pd.Timestamp(start))]
    jumps = big.nlargest(20, "move")[["code", "date", "move"]]
    # per-date share of present rows excluded ONLY because a status is unknown (gate input; see main)
    present = df.index[~(reasons["bad_price"] | reasons["no_adj_factor"]).loc[df.index]]
    unk = pd.DataFrame({"date": df.loc[present, "date"], "unknown": unknown_any.loc[present].astype(bool)})
    unk = unk[unk["date"] >= pd.Timestamp(start)].groupby("date")["unknown"].agg(["sum", "size"])
    unk["share"] = unk["sum"] / unk["size"]
    return df.loc[keep, ["date", "code", "close_adj", "is_excluded"]], census, jumps, unk


def _key6(code: pd.Series) -> pd.Series:
    """Join key: the 6-digit A-share code, whatever the vendor decoration (600000.SH, SHSE.600000, sh.600000)."""
    return code.astype(str).str.extract(r"(\d{6})")[0]


def _unexpected_reason(extra, cal, start, last_trade, delist) -> np.ndarray:
    """Why a retrieved date is outside the expected set (first matching reason wins)."""
    ts = lambda v: np.datetime64(v, "ns") if pd.notna(v) else None     # noqa: E731
    start, last_trade, delist = ts(start), ts(last_trade), ts(delist)
    out = np.full(len(extra), "other", dtype=object)
    for i, d in enumerate(extra):
        if d not in cal_set(cal):
            out[i] = "not_in_calendar"
        elif start is not None and d < start:
            out[i] = "before_listing"
        elif last_trade is not None and d > last_trade and (delist is None or d < delist):
            out[i] = "after_last_trade_before_delisting"
        elif delist is not None and d >= delist:
            out[i] = "on_or_after_delisting"
    return out


_CAL_CACHE: dict = {}


def cal_set(cal) -> set:
    k = id(cal)
    if k not in _CAL_CACHE:
        _CAL_CACHE.clear()
        _CAL_CACHE[k] = set(cal)
    return _CAL_CACHE[k]


def coverage_by_date(panel: pd.DataFrame, master_csv: str, calendar_csv: str, out: Path,
                     period_start, period_end) -> pd.DataFrame:
    """Expected vs retrieved SYMBOL SETS per trading date and board, against an independently sourced calendar and
    an EXPLICIT requested period [period_start, period_end] (never the panel's own observed min/max, which would
    let a wholly missing opening or closing period pass unnoticed).

    Why sets, not counts: subtracting counts lets an unexpected symbol offset a missing one.  Missing and
    unexpected symbols are therefore listed separately.
      master CSV  : code, list_date, delist_date (blank or year >= 2037 = still listed)[, board]
                    optional trading-boundary columns: first_trade_date, first_trade_basis, first_trade_confirmed,
                    last_trade_date, last_trade_basis, last_trade_confirmed
      calendar CSV: one column 'date' - sessions from a source independent of the bar vendor (e.g. Tushare trade_cal)
    Three intervals are kept apart: LISTED (list_date .. delist_date), TRADING (first/last real session) and
    ELIGIBLE (decided later by the status flags).  A symbol is EXPECTED on the TRADING interval only when the
    boundary is CONFIRMED (confirmed == 1, a stated basis such as 'exchange_notice', and basis != 'panel_derived').
    A boundary read off the very download being checked (first/last tradestatus = 1) is only a candidate: letting it
    define the expected interval would hide missing leading or trailing bars, so unconfirmed boundaries are ignored
    for expectation and listed in coverage_boundaries.csv with the reason.  Fallback: list_date <= d < delist_date
    (the delist_date is the exchange termination date, not a session).  Rows between a confirmed last trade and the
    delisting date are 'unexpected: after_last_trade_before_delisting'; rows on or after the delisting date are
    'on_or_after_delisting'; neither is ever 'missing'.
    Missing kinds: leading (before the symbol's first retrieved date), trailing (after its last), interior (a hole
    inside the retrieved span), whole_symbol (never retrieved).
    Writes coverage_by_date.csv (union of expected and unexpected date/board groups, so an unexpected-only date such
    as a weekend, or an unexpected-only board, still appears), coverage_missing_symbols.csv,
    coverage_unexpected_symbols.csv, coverage_boundaries.csv and coverage_period.json."""
    import json as _json
    cal = np.sort(pd.to_datetime(pd.read_csv(calendar_csv)["date"].astype(str)).dt.normalize().unique()).astype("datetime64[ns]")
    pmin, pmax = np.datetime64(pd.Timestamp(period_start), "ns"), np.datetime64(pd.Timestamp(period_end), "ns")
    if pmin > pmax:
        raise SystemExit("period_start is after period_end")
    m = pd.read_csv(master_csv, dtype={"code": str}, parse_dates=["list_date", "delist_date"])
    for c in ("first_trade_date", "last_trade_date"):
        m[c] = pd.to_datetime(m[c]) if c in m else pd.NaT
        m[c.replace("_date", "_basis")] = m[c.replace("_date", "_basis")].astype("string") if c.replace("_date", "_basis") in m else pd.Series(pd.NA, index=m.index, dtype="string")
        m[c.replace("_date", "_confirmed")] = pd.to_numeric(m[c.replace("_date", "_confirmed")], errors="coerce") if c.replace("_date", "_confirmed") in m else np.nan
    m["key"] = _key6(m["code"])
    m["delist_date"] = m["delist_date"].where(m["delist_date"].dt.year < 2037, pd.NaT)
    if "board" not in m:
        m["board"] = board_from_code(m["code"])

    def usable(date, basis, confirmed):
        if pd.isna(date):
            return False, "no_boundary"
        if pd.isna(basis) or str(basis).strip() == "":
            return False, "no_basis_recorded"
        if str(basis).strip() == "panel_derived":
            return False, "derived_from_the_panel_itself"
        if confirmed != 1:
            return False, "not_confirmed"
        return True, ""

    p = panel[["date", "code"] + (["board"] if "board" in panel else [])].copy()
    p["date"] = pd.to_datetime(p["date"]).dt.normalize()
    p["key"] = _key6(p["code"])
    obs_min, obs_max = p["date"].min(), p["date"].max()
    got_by = {k: np.sort(g["date"].values.astype("datetime64[ns]")) for k, g in p.groupby("key")}
    board_of = dict(zip(m["key"], m["board"].astype(str)))
    if "board" in p:
        for k, b in zip(p["key"], p["board"].astype(str)):
            board_of.setdefault(k, b)
    miss, unexp, exp_rows, bnd = [], [], [], []
    for r in m.itertuples(index=False):
        f_ok, f_why = usable(r.first_trade_date, r.first_trade_basis, r.first_trade_confirmed)
        l_ok, l_why = usable(r.last_trade_date, r.last_trade_basis, r.last_trade_confirmed)
        first_used = r.first_trade_date if f_ok else pd.NaT
        last_used = r.last_trade_date if l_ok else pd.NaT
        if pd.notna(r.first_trade_date) or pd.notna(r.last_trade_date):
            bnd.append({"key": r.key, "first_trade_date": r.first_trade_date, "first_basis": r.first_trade_basis, "first_used": f_ok,
                        "first_ignored_because": "" if f_ok else f_why, "last_trade_date": r.last_trade_date, "last_basis": r.last_trade_basis,
                        "last_used": l_ok, "last_ignored_because": "" if l_ok else l_why})
        start = first_used if pd.notna(first_used) else r.list_date
        lo = np.searchsorted(cal, max(np.datetime64(start, "ns"), pmin) if pd.notna(start) else pmin, side="left")
        if pd.notna(last_used):
            hi = np.searchsorted(cal, np.datetime64(last_used, "ns"), side="right")
        elif pd.notna(r.delist_date):
            hi = np.searchsorted(cal, np.datetime64(r.delist_date, "ns"), side="left")
        else:
            hi = len(cal)
        hi = min(hi, np.searchsorted(cal, pmax, side="right"))
        exp = cal[lo:hi] if hi > lo else cal[:0]
        got = got_by.get(r.key, cal[:0])
        exp_rows.append((str(r.board), exp))
        mis = np.setdiff1d(exp, got)
        if len(mis):
            kinds = np.array(["whole_symbol"] * len(mis)) if len(got) == 0 else \
                np.where(mis < got[0], "leading", np.where(mis > got[-1], "trailing", "interior"))
            miss.append(pd.DataFrame({"key": r.key, "board": str(r.board), "date": mis, "kind": kinds}))
        extra = np.setdiff1d(got, exp)
        if len(extra):
            reason = _unexpected_reason(extra, cal, start, last_used, r.delist_date)
            unexp.append(pd.DataFrame({"key": r.key, "board": str(r.board), "date": extra, "reason": reason}))
    in_master = set(m["key"])
    for k, got in got_by.items():            # retrieved symbols the master does not know at all
        if k not in in_master:
            unexp.append(pd.DataFrame({"key": k, "board": board_of.get(k) or board_from_code(pd.Series([k])).iloc[0], "date": got, "reason": "not_in_master"}))
    miss_df = pd.concat(miss, ignore_index=True) if miss else pd.DataFrame(columns=["key", "board", "date", "kind"])
    unexp_df = pd.concat(unexp, ignore_index=True) if unexp else pd.DataFrame(columns=["key", "board", "date", "reason"])
    exp_parts = [pd.DataFrame({"board": b, "date": e}) for b, e in exp_rows if len(e)]
    exp_n = pd.concat(exp_parts, ignore_index=True) if exp_parts else pd.DataFrame(columns=["board", "date"])
    def cnt(df, name):
        if not len(df):
            return pd.DataFrame({"date": pd.Series(dtype="datetime64[ns]"), "board": pd.Series(dtype=object), name: pd.Series(dtype=int)})
        return df.assign(date=pd.to_datetime(df["date"])).groupby(["date", "board"]).size().rename(name).reset_index()

    summ = cnt(exp_n, "expected")
    for part in (cnt(miss_df, "missing"), cnt(unexp_df, "unexpected")):
        summ = summ.merge(part, on=["date", "board"], how="outer")
    for c in ("expected", "missing", "unexpected"):
        summ[c] = summ[c].fillna(0).astype(int)
    summ["retrieved_expected"] = summ["expected"] - summ["missing"]
    summ = summ.sort_values(["date", "board"]).reset_index(drop=True)
    summ.to_csv(out / "coverage_by_date.csv", index=False)
    miss_df.to_csv(out / "coverage_missing_symbols.csv", index=False)
    unexp_df.to_csv(out / "coverage_unexpected_symbols.csv", index=False)
    pd.DataFrame(bnd).to_csv(out / "coverage_boundaries.csv", index=False)
    in_req = cal[(cal >= pmin) & (cal <= pmax)]
    (out / "coverage_period.json").write_text(_json.dumps({
        "requested_start": str(pd.Timestamp(period_start).date()), "requested_end": str(pd.Timestamp(period_end).date()),
        "observed_min": str(obs_min.date()), "observed_max": str(obs_max.date()),
        "requested_sessions": int(len(in_req)),
        "requested_sessions_with_no_rows": int(len(set(in_req) - set(p["date"].values.astype("datetime64[ns]"))))}, indent=1))
    return summ


def trim(obj: pd.DataFrame, start: str) -> pd.DataFrame:
    idx = obj.index.to_timestamp(how="end") if hasattr(obj.index, "to_timestamp") else obj.index
    return obj[idx >= pd.Timestamp(start)]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def ratio_vs_count(br: pd.DataFrame, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(3, 1, figsize=(13, 8), sharex=True)
    ax[0].plot(br.index, br["n_above"], lw=0.6, color="#3b6ea5"); ax[0].set_ylabel("count above MA5")
    ax[1].plot(br.index, br["n_eligible"], lw=0.9, color="#7f7f7f"); ax[1].set_ylabel("eligible names")
    ax[2].plot(br.index, br["ratio"], lw=0.6, color="#3b6ea5"); ax[2].set_ylabel("ratio above MA5")
    for a in ax:
        a.spines[["top", "right"]].set_visible(False)
    ax[0].set_title("Count vs ratio: the count inherits the growth in listed names (SPEC C2)")
    fig.tight_layout(); fig.savefig(path, dpi=120); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--duckdb"); src.add_argument("--csv")
    ap.add_argument("--sql", help="query returning date, code, close [, adj_factor, sec_name, is_st, is_suspended, board]")
    ap.add_argument("--start", default="2014-01-01")
    ap.add_argument("--master-csv", help="security master (code, list_date, delist_date[, board]) for coverage_by_date.csv")
    ap.add_argument("--pull-start", help="requested download start (explicit); coverage is judged against it")
    ap.add_argument("--pull-end", help="requested download end (explicit)")
    ap.add_argument("--calendar-csv", help="independent trading calendar (column 'date'), required with --master-csv")
    ap.add_argument("--allow-unadjusted", action="store_true", help="diagnostic only: build without adj_factor")
    ap.add_argument("--max-unknown-share", type=float, default=0.01,
                    help="abort if, on any output date, more than this share of present rows is excluded only for unknown status")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    global args_allow_unadjusted
    args_allow_unadjusted = args.allow_unadjusted
    if args.duckdb and not args.sql:
        ap.error("--duckdb needs --sql")

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    raw, source = load(args)
    stocks, census, jumps, unk = prepare(raw, args.start)
    census.to_csv(out / "census.csv")
    jumps.to_csv(out / "census_adj_jumps_top20.csv", index=False)
    unk.to_csv(out / "census_unknown_share_by_date.csv")
    # GATE: unknown status is excluded, never guessed - but if it is wide it silently removes whole groups
    # (e.g. every delisted stock if is_delisting_period is NULL over its whole life) = survivorship bias.
    worst = unk.nlargest(5, "share")
    if len(unk) and unk["share"].max() > args.max_unknown_share:
        raise SystemExit(
            f"GATE FAILED: rows excluded only for UNKNOWN status exceed {args.max_unknown_share:.1%} of present rows on "
            f"{int((unk['share'] > args.max_unknown_share).sum())} dates (worst {unk['share'].max():.1%}).\n"
            f"Set flags to 0 outside each rule's possible window (see brief) instead of NULL.\nWorst dates:\n{worst}")
    if (census["codes_bse"] == 0).all():
        print("WARNING: no BSE codes in the panel - the indicator covers SH/SZ/STAR/ChiNext only; "
              "state this in the report (the platform security master has no BSE records).")
    if (census["codes_star"] == 0).all():
        print("WARNING: no STAR (688) codes in the panel.")

    if args.master_csv:
        if not args.calendar_csv:
            ap.error("--master-csv needs --calendar-csv (an independently sourced calendar)")
        if not (args.pull_start and args.pull_end):
            ap.error("--master-csv needs --pull-start and --pull-end (the requested period, not the observed one)")
        cov = coverage_by_date(raw.assign(date=pd.to_datetime(raw["date"]).dt.normalize()), args.master_csv, args.calendar_csv, out,
                              args.pull_start, args.pull_end)
        worst = cov.assign(frac=(cov["missing"] + cov["unexpected"]) / cov["expected"].clip(lower=1)).nlargest(1, "frac")
        print("coverage: worst date/board by (missing+unexpected)/expected\n", worst.to_string(index=False))
    else:
        print("WARNING: no --master-csv/--calendar-csv - coverage by date and board was NOT measured; do not treat the panel as complete.")

    cfg = B.Config()
    spans = {"daily": (B.stock_breadth(stocks, cfg), cfg),
             "weekly": (B.period_breadth(stocks, cfg, "W"), dataclasses.replace(cfg, pct_warmup=100)),
             "monthly": (B.period_breadth(stocks, cfg, "M"), dataclasses.replace(cfg, pct_warmup=24))}
    summary = {}
    for name, (br, c) in spans.items():
        # SPEC C3: the percentile history starts at --start.  Rows before it serve ONLY the MA warm-up, so the
        # pull start (any date early enough for the 5-month MA) cannot change the indicator.
        br = trim(br, args.start)
        st = B.daily_setups(br, c)
        tbl = br.join(st[["pct", "setup"]])
        tbl.to_csv(out / f"breadth_{name}.csv", float_format="%.6f")
        B.plot_breadth(st, c, str(out / f"breadth_{name}.png"),
                       title=f"{name} breadth — share of eligible A-shares above their 5-period MA (PIT zones)")
        summary[name] = {"periods": int(len(tbl)), "first": str(tbl.index.min().date()),
                         "last": str(tbl.index.max().date()), "pct_warmup": c.pct_warmup,
                         "short_setups": int((tbl.setup == -1).sum()), "long_setups": int((tbl.setup == 1).sum()),
                         "ratio_min": round(float(tbl.ratio.min()), 4), "ratio_max": round(float(tbl.ratio.max()), 4)}
    ratio_vs_count(trim(B.stock_breadth(stocks, cfg), args.start), out / "ratio_vs_count.png")

    manifest = {"program": "BREADTH-CN-001", "step": "1-indicator", "outcome_blind": True, "source": source, "allow_unadjusted": args.allow_unadjusted,
                "rows_in": int(len(raw)), "rows_used": int(len(stocks)), "start": args.start,
                "config_digest": cfg.digest(), "config": dataclasses.asdict(cfg), "summary": summary,
                "max_unknown_share": args.max_unknown_share, "unknown_share_max_observed": float(unk["share"].max()) if len(unk) else 0.0,
                "files": {p.name: sha(p) for p in sorted(out.iterdir()) if p.name != "manifest.json"}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2))
    print("\ncensus (per year):\n", census.to_string())


if __name__ == "__main__":
    main()
