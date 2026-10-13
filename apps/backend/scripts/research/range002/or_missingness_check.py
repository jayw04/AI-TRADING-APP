"""READ-ONLY missingness investigation over the ALREADY STORED attempt-4 minute bars.

No network, no fetch, no write to the store, no new run, no registry row. Aggregates only.
Distinguishes (as far as stored evidence allows): no eligible prints (illiquidity), trade-condition
filtering (volume reconciliation vs the vendor daily volume), halts (not observable here) and
missing delivery (market-wide clustering by date / minute, DST, page boundaries).
"""

import json
import sys
from typing import Any

import duckdb
import pandas as pd

sys.path.insert(0, "/work/apps/backend")
from app.research.range002.data.store_adapter import open_snapshot  # noqa: E402

STORE = "/app/data/research/range002_run/minute_bars_2016q1_a4.duckdb"
SNAP = "/app/data/research/range002_s1/sharadar-2016q1-20261013"

con = duckdb.connect(STORE, read_only=True)
df = con.execute("select symbol, ts, open, high, low, close, volume from minute_bars").df()
con.close()
df["et"] = df["ts"].dt.tz_localize("UTC").dt.tz_convert("America/New_York").dt.tz_localize(None)
df["day"] = df["et"].dt.date
df["mod"] = df["et"].dt.hour * 60 + df["et"].dt.minute
reg = df[(df["mod"] >= 570) & (df["mod"] <= 959)]
loaded = reg.groupby(["symbol", "day"]).size().rename("n").reset_index()
n_loaded = len(loaded)
per_day_loaded = loaded.groupby("day").size()

present = reg.groupby(["symbol", "day"])["mod"].apply(set)


def missing_in(mset, lo, hi):
    return [m for m in range(lo, hi + 1) if m not in mset]


or_missing = present.apply(lambda s: missing_in(s, 570, 599))
n_or_missing = or_missing.apply(len)
inc = n_or_missing[n_or_missing > 0]
out: dict[str, Any] = {
    "store_regular_symbol_days": n_loaded,
    "or_incomplete_symbol_days": int(len(inc)),
    "or_missing_first_minute": int(or_missing.apply(lambda m: 570 in m).sum()),
    "extended_hours_bars_present": bool((df["mod"] < 570).any()),
}

# 1. clustering by date (market-wide delivery problems would cluster) and DST
inc_days = pd.Series([d for (_, d) in inc.index]).value_counts()
share = (inc_days / per_day_loaded.reindex(inc_days.index)).sort_values(ascending=False)
out["by_date_top"] = [
    {
        "day": str(d),
        "incomplete": int(inc_days[d]),
        "loaded": int(per_day_loaded[d]),
        "share": round(float(s), 3),
    }
    for d, s in share.head(8).items()
]
dst = pd.Timestamp("2016-03-13").date()
before = [(s, d) for (s, d) in inc.index if d < dst]
after = [(s, d) for (s, d) in inc.index if d >= dst]
lb = int(per_day_loaded[[d for d in per_day_loaded.index if d < dst]].sum())
la = int(per_day_loaded[[d for d in per_day_loaded.index if d >= dst]].sum())
out["dst_split"] = {
    "before_2016-03-13": {
        "incomplete": len(before),
        "loaded": lb,
        "rate": round(len(before) / lb, 4),
    },
    "from_2016-03-13": {"incomplete": len(after), "loaded": la, "rate": round(len(after) / la, 4)},
}
out["dates_with_incomplete_share_ge_10pct"] = int((share >= 0.10).sum())
out["distinct_dates_loaded"] = int(len(per_day_loaded))

# 2. missing rate by time-of-day bin (slots over loaded symbol-days)
bins = [
    ("09:30", 570, 570),
    ("09:31", 571, 571),
    ("09:32-09:34", 572, 574),
    ("09:35-09:59", 575, 599),
    ("10:00-10:29", 600, 629),
    ("11:00-11:59", 660, 719),
    ("12:00-14:59", 720, 899),
    ("15:00-15:58", 900, 958),
    ("15:59", 959, 959),
]
rows = []
for item in bins:
    name, lo, hi = item
    miss = 0
    for s in present:
        miss += sum(1 for m in range(lo, hi + 1) if m not in s)
    slots = n_loaded * (hi - lo + 1)
    rows.append(
        {"bin": name, "missing_rate": round(miss / slots, 5), "missing": miss, "slots": slots}
    )
out["missing_rate_by_time_bin"] = rows

# 3. per-symbol liquidity vs first-minute missing
dv = reg.groupby(["symbol", "day"])["volume"].sum().rename("dvol").reset_index()
sym_med = dv.groupby("symbol")["dvol"].median().rename("median_regular_volume")
first_missing = or_missing.apply(lambda m: 570 in m).rename("m0930").reset_index()
sym_rate = first_missing.groupby("symbol")["m0930"].mean().rename("rate_0930_missing")
sym = pd.concat([sym_med, sym_rate], axis=1)
out["spearman_rate0930_vs_median_volume"] = round(float(sym.corr(method="spearman").iloc[0, 1]), 3)
out["symbols_with_any_0930_missing"] = int((sym["rate_0930_missing"] > 0).sum())
hi_liq = sym.sort_values("median_regular_volume", ascending=False).head(25)
out["top25_liquid_symbols_rate0930"] = round(float(hi_liq["rate_0930_missing"].mean()), 4)
out["bottom25_liquid_symbols_rate0930"] = round(
    float(sym.sort_values("median_regular_volume").head(25)["rate_0930_missing"].mean()), 4
)

# 4. neighbours of a missing 09:30 minute
fm = first_missing[first_missing["m0930"]]
idx = set(zip(fm["symbol"], fm["day"]))
pm = df[(df["mod"] < 570) & (df["mod"] >= 540)]
pre = pm.groupby(["symbol", "day"])["volume"].sum()
b31 = reg[reg["mod"] == 571].set_index(["symbol", "day"])["volume"]
b30_med = reg[reg["mod"] == 570].groupby("symbol")["volume"].median()
b31_med = reg[reg["mod"] == 571].groupby("symbol")["volume"].median()
ratios = []
for s, d in idx:
    if (s, d) in b31.index and s in b31_med.index and b31_med[s] > 0:
        ratios.append(float(b31[(s, d)]) / float(b31_med[s]))
out["on_days_0930_missing"] = {
    "n": len(idx),
    "bar_0931_present": int(sum(1 for k in idx if k in b31.index)),
    "median_0931_volume_vs_symbol_median": round(float(pd.Series(ratios).median()), 3)
    if ratios
    else None,
    "premarket_0900_0929_volume_present": int(sum(1 for k in idx if k in pre.index and pre[k] > 0)),
    "median_0930_volume_when_present_over_all_symbols": float(
        reg[reg["mod"] == 570]["volume"].median()
    ),
}

# 5. volume reconciliation vs the vendor's daily volume
snap = open_snapshot(__import__("pathlib").Path(SNAP))
sep = snap.execute("select ticker, date, volume from sep").df()
sep["day"] = pd.to_datetime(sep["date"]).dt.date
m = dv.merge(
    sep[["ticker", "day", "volume"]], left_on=["symbol", "day"], right_on=["ticker", "day"]
)
m = m[m["volume"] > 0]
m["ratio"] = m["dvol"] / m["volume"]
inc_set = set(inc.index)
m["incomplete"] = [(s, d) in inc_set for s, d in zip(m["symbol"], m["day"])]
m["first_missing"] = [(s, d) in idx for s, d in zip(m["symbol"], m["day"])]


def q(x):
    return {
        k: round(float(x.quantile(p)), 3) for k, p in (("p10", 0.1), ("p50", 0.5), ("p90", 0.9))
    }


out["volume_reconciliation_bars_vs_vendor_daily"] = {
    "compared_symbol_days": int(len(m)),
    "all": q(m["ratio"]),
    "complete_or_days": q(m[~m["incomplete"]]["ratio"]),
    "or_incomplete_days": q(m[m["incomplete"]]["ratio"]),
    "first_minute_missing_days": q(m[m["first_missing"]]["ratio"])
    if m["first_missing"].any()
    else None,
    "note": "ratio of summed regular-session SIP minute-bar volume to Sharadar daily volume",
}

# 6. weekly trend of first-minute / any-OR missingness, and low-volume-ratio days
fm_idx = set(zip(fm["symbol"], fm["day"]))
wk: dict[str, list[int]] = {}
for sname, d in present.index:
    w = pd.Timestamp(d).strftime("%G-W%V")
    r = wk.setdefault(w, [0, 0, 0])
    r[0] += 1
    r[1] += (sname, d) in fm_idx
    r[2] += (sname, d) in inc_set
out["weekly"] = {
    w: {
        "loaded": a,
        "first_min_missing_rate": round(b / a, 3),
        "any_or_missing_rate": round(c / a, 3),
    }
    for w, (a, b, c) in sorted(wk.items())
}
low = m[m["ratio"] < 0.5]
tot_missing = present.apply(lambda x: len([k for k in range(570, 960) if k not in x]))
out["low_ratio_days"] = {
    "n_ratio_lt_0.5": int(len(low)),
    "distinct_symbols": int(low["symbol"].nunique()),
    "top_symbols": low["symbol"].value_counts().head(8).to_dict(),
    "median_missing_regular_minutes_on_those_days": float(
        tot_missing.reindex(list(zip(low["symbol"], low["day"]))).median()
    ),
    "median_missing_regular_minutes_on_other_days": float(
        tot_missing.reindex(
            list(zip(m[m["ratio"] >= 0.5]["symbol"], m[m["ratio"] >= 0.5]["day"]))
        ).median()
    ),
}

med_ratio = m.groupby("symbol")["ratio"].median()
adj = sorted(med_ratio[(med_ratio < 0.5) | (med_ratio > 1.5)].index)
mm = m[~m["symbol"].isin(adj)]
out["vendor_volume_basis_mismatch_symbols"] = adj
out["reconciliation_excluding_basis_mismatch"] = {
    "compared_symbol_days": int(len(mm)),
    "all": q(mm["ratio"]),
    "complete_or_days": q(mm[~mm["incomplete"]]["ratio"]),
    "or_incomplete_days": q(mm[mm["incomplete"]]["ratio"]),
    "first_minute_missing_days": q(mm[mm["first_missing"]]["ratio"]),
    "share_days_ratio_lt_0.8": round(float((mm["ratio"] < 0.8).mean()), 3),
}
wm: dict[str, list[int]] = {}
for (_sname, d), st in present.items():
    w = pd.Timestamp(d).strftime("%G-W%V")
    r = wm.setdefault(w, [0, 0])
    r[0] += 60
    r[1] += sum(1 for k in range(660, 720) if k not in st)
out["weekly_midday_missing_rate_1100_1159"] = {
    w: round(b / a, 4) for w, (a, b) in sorted(wm.items())
}

dd: dict[str, list[int]] = {}
for (_sname, d), st in present.items():
    r = dd.setdefault(str(d), [0, 0, 0])
    r[0] += 390
    r[1] += sum(1 for k in range(570, 960) if k not in st)
    r[2] += 1
top = sorted(((v[1] / v[0], k, v[2]) for k, v in dd.items()), reverse=True)[:6]
out["worst_dates_missing_regular_minutes_rate"] = [
    {"day": k, "rate": round(r, 4), "symbols": n} for r, k, n in top
]
out["median_date_missing_regular_minutes_rate"] = round(
    float(pd.Series([v[1] / v[0] for v in dd.values()]).median()), 4
)

print(json.dumps(out, default=str))
