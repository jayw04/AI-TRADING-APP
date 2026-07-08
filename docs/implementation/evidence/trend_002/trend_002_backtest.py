#!/usr/bin/env python3
"""TREND-002 backtest — Long-History Core Trend (frozen pre-registration v1.0).

Same frozen design as TREND-001 (signal `TR_12m_skip1>0 AND price>MA200`, monthly first-trading-day,
long-only inverse-vol vol-target 10%/63d cap 1.0, 5 bps/side, three-way verdict + power check), on a
LONGER core equity+bond universe (SPY/QQQ/IWM/EFA/TLT/IEF, ~2002+) to attack TREND-001's power limit.
Cash leg = SHY (2002+ short-Treasury proxy); BIL-overlap + zero-yield are sensitivities. Adds a
cash-leg attribution block. Research-only; Yahoo adjusted-close. Seeded; deterministic.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

import numpy as np
import pandas as pd

UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "TLT", "IEF"]      # core-6 (primary)
SENS_ADDS = ["EEM", "GLD", "DBC"]                           # pre-declared universe-expansion sensitivities
CASH_PRIMARY = "SHY"
CASH_BIL = "BIL"
BENCH_TREND = ["DBMF", "KMLM"]
SEED = 20260708
VOL_TARGET = 0.10
VOL_LB = 63
COST_BPS = 5.0
BLOCK = 6
N_BOOT = 5000
START = "2002-07-01"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36"}


def fetch_yahoo_adj(sym: str) -> pd.Series:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?period1=0&period2=9999999999&interval=1d")
    j = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=45))
    res = j["chart"]["result"][0]
    ts = res["timestamp"]
    adj = res["indicators"]["adjclose"][0]["adjclose"]
    idx = pd.to_datetime([datetime.fromtimestamp(t, tz=timezone.utc).date() for t in ts])
    s = pd.Series(adj, index=idx, dtype="float64")
    return s[~s.index.duplicated(keep="last")].dropna().sort_index()


def ann_metrics(m: pd.Series, rf: pd.Series) -> dict:
    m = m.dropna()
    if len(m) < 6:
        return {"cagr": None, "vol": None, "sharpe": None, "maxdd": None, "calmar": None, "n": len(m)}
    exc = m - rf.reindex(m.index).fillna(0.0)
    cum = (1 + m).cumprod()
    n = len(m)
    cagr = cum.iloc[-1] ** (12 / n) - 1
    vol = m.std(ddof=1) * np.sqrt(12)
    sharpe = (exc.mean() * 12) / vol if vol > 0 else 0.0
    maxdd = float((cum / cum.cummax() - 1).min())
    calmar = cagr / abs(maxdd) if maxdd < 0 else None
    return {"cagr": float(cagr), "vol": float(vol), "sharpe": float(sharpe),
            "maxdd": maxdd, "calmar": (float(calmar) if calmar is not None else None), "n": n}


def first_trading_days(idx: pd.DatetimeIndex) -> list:
    s = idx.to_series()
    ftd = s.groupby([idx.year, idx.month]).first()
    return [pd.Timestamp(d) for d in ftd.values]


def run_strategy(adj, rebal, rf_by_date, start, *, cost_bps=COST_BPS, cash_yield=True, collect_diag=False):
    dret = adj.pct_change()
    ma200 = adj.rolling(200).mean()
    vol = dret.rolling(VOL_LB).std() * np.sqrt(252)
    prev_w = pd.Series(0.0, index=adj.columns)
    out, positions, cashw, turns = {}, [], [], []
    for k in range(len(rebal) - 1):
        t, t1 = rebal[k], rebal[k + 1]
        if t1 < pd.Timestamp(start) or k - 13 < 0:
            continue
        mom = adj.loc[rebal[k - 1]] / adj.loc[rebal[k - 13]] - 1
        hold = (mom > 0) & (adj.loc[t] > ma200.loc[t])
        hold = hold.fillna(False)
        held = [c for c in adj.columns
                if hold.get(c, False) and np.isfinite(vol.loc[t, c]) and vol.loc[t, c] > 0]
        w = pd.Series(0.0, index=adj.columns)
        if held:
            iv = pd.Series({c: 1.0 / vol.loc[t, c] for c in held})
            iv /= iv.sum()
            port_vol = float(np.sqrt(((iv * vol.loc[t, held]) ** 2).sum()))
            lev = min(VOL_TARGET / port_vol, 1.0) if port_vol > 0 else 0.0
            w[held] = (iv * lev).values
        cash_w = 1.0 - w.sum()
        turnover = (w - prev_w).abs().sum()
        cost = turnover * cost_bps / 1e4
        prev_w = w
        r_assets = adj.loc[t1] / adj.loc[t] - 1
        r = float((w * r_assets.reindex(w.index).fillna(0.0)).sum())
        r += cash_w * (float(rf_by_date.get(t1, 0.0)) if cash_yield else 0.0)
        out[t1] = r - cost
        if collect_diag:
            positions.append(len(held)); cashw.append(cash_w); turns.append(turnover)
    series = pd.Series(out).sort_index()
    diag = {}
    if collect_diag and positions:
        diag = {"avg_positions": float(np.mean(positions)), "median_positions": float(np.median(positions)),
                "avg_cash_weight": float(np.mean(cashw)), "annual_turnover": float(np.mean(turns) * 12),
                "worst_month": float(series.min())}
    return series, diag


def block_bootstrap_delta(m_s, m_b, rf, metric):
    idx = m_s.dropna().index.intersection(m_b.dropna().index)
    s, b, r = m_s.reindex(idx).values, m_b.reindex(idx).values, rf.reindex(idx).fillna(0.0).values
    n = len(idx)
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(n / BLOCK))

    def dmetric(si, bi, ri):
        a = ann_metrics(pd.Series(si), pd.Series(ri))[metric]
        c = ann_metrics(pd.Series(bi), pd.Series(ri))[metric]
        return (a - c) if (a is not None and c is not None) else np.nan

    point = dmetric(s, b, r)
    draws = []
    for _ in range(N_BOOT):
        starts = rng.integers(0, n, size=nb)
        idxs = np.concatenate([(np.arange(st, st + BLOCK) % n) for st in starts])[:n]
        draws.append(dmetric(s[idxs], b[idxs], r[idxs]))
    draws = np.array([d for d in draws if np.isfinite(d)])
    lo, hi = np.percentile(draws, [2.5, 97.5])
    se = float(draws.std(ddof=1))
    return {"point": float(point), "ci_lo": float(lo), "ci_hi": float(hi),
            "excludes_zero": bool(lo > 0 or hi < 0), "se": se, "mde_95": float(1.96 * se)}


def monthly_on_grid(price, rebal):
    out = {}
    for k in range(len(rebal) - 1):
        t, t1 = rebal[k], rebal[k + 1]
        p0, p1 = price.asof(t), price.asof(t1)
        if pd.notna(p0) and pd.notna(p1) and p0 > 0:
            out[t1] = p1 / p0 - 1
    return pd.Series(out).sort_index()


def classify(ds, dc, mdr, powered):
    if ds["excludes_zero"]:
        return "Approved"
    if mdr is not None and mdr >= 0.25 and dc["excludes_zero"] and dc["point"] > 0:
        return "Diversifier"
    return "Inconclusive" if not powered else "Rejected"


def evaluate(strat, ew, rf, with_calmar=True):
    idx = strat.index.intersection(ew.index)
    s, b = strat.reindex(idx), ew.reindex(idx)
    ds = block_bootstrap_delta(s, b, rf, "sharpe")
    dc = block_bootstrap_delta(s, b, rf, "calmar") if with_calmar else {"point": None, "excludes_zero": False}
    sm, bm = ann_metrics(s, rf), ann_metrics(b, rf)
    mdr = (abs(bm["maxdd"]) - abs(sm["maxdd"])) / abs(bm["maxdd"]) if bm["maxdd"] else None
    powered = abs(ds["point"]) >= ds["mde_95"]
    return {"verdict": classify(ds, dc, mdr, powered), "delta_sharpe": ds, "delta_calmar": dc,
            "maxdd_reduction_rel": mdr, "powered": powered, "strategy": sm, "benchmark_ew": bm}


def ew_on_grid(adj, rebal, start):
    out = {}
    for k in range(len(rebal) - 1):
        t, t1 = rebal[k], rebal[k + 1]
        if t1 < pd.Timestamp(start):
            continue
        out[t1] = float((adj.loc[t1] / adj.loc[t] - 1).mean())
    return pd.Series(out).sort_index()


def main() -> None:
    prices, fails = {}, []
    for sym in UNIVERSE + SENS_ADDS + BENCH_TREND + [CASH_PRIMARY, CASH_BIL]:
        try:
            prices[sym] = fetch_yahoo_adj(sym)
        except Exception as e:  # noqa: BLE001
            fails.append((sym, str(e)[:80]))
    adj = pd.DataFrame({s: prices[s] for s in UNIVERSE if s in prices}).sort_index()
    adj = adj[adj.index >= pd.Timestamp("2000-06-01")]
    rebal = first_trading_days(adj.index)
    rf_shy = monthly_on_grid(prices[CASH_PRIMARY], rebal)
    rf_bil = monthly_on_grid(prices[CASH_BIL], rebal)
    ew = ew_on_grid(adj, rebal, START)

    strat_shy, diag = run_strategy(adj, rebal, rf_shy, START, collect_diag=True)
    strat_zero, _ = run_strategy(adj, rebal, rf_shy, START, cash_yield=False)
    strat_bil, _ = run_strategy(adj, rebal, rf_bil, START)
    idx = strat_shy.index.intersection(ew.index)

    prim = evaluate(strat_shy, ew, rf_shy)
    res = {
        "meta": {"universe": UNIVERSE, "sensitivity_adds": SENS_ADDS, "cash_proxy": CASH_PRIMARY,
                 "cadence": "monthly_first_trading_day", "start": START, "n_months": len(idx),
                 "window": [str(idx[0].date()), str(idx[-1].date())], "vol_target": VOL_TARGET,
                 "cost_bps": COST_BPS, "block": BLOCK, "n_boot": N_BOOT, "seed": SEED, "fetch_fails": fails},
        "strategy": prim["strategy"], "benchmark_ew": prim["benchmark_ew"],
        "bench_SPY": ann_metrics(monthly_on_grid(adj["SPY"], rebal).reindex(idx), rf_shy),
        "delta_sharpe": prim["delta_sharpe"], "delta_calmar": prim["delta_calmar"],
        "maxdd_reduction_rel": prim["maxdd_reduction_rel"],
        "power": {"mde_95_delta_sharpe": prim["delta_sharpe"]["mde_95"],
                  "observed_delta_sharpe": prim["delta_sharpe"]["point"], "adequately_powered": prim["powered"]},
        "verdict": prim["verdict"],
        "status_label": {"Approved": "Completed · Approved", "Diversifier": "Completed · Diversifier",
                         "Inconclusive": "Completed · Power-Limited · Inconclusive",
                         "Rejected": "Completed · Rejected"}[prim["verdict"]],
        "secondary_label": ("Diversifier Candidate" if (prim["maxdd_reduction_rel"] or 0) >= 0.25
                            and prim["delta_calmar"]["point"] and prim["delta_calmar"]["point"] > 0 else ""),
    }

    # cash-leg attribution (owner-required)
    bil_win = [d for d in idx if pd.notna(rf_bil.get(d)) and d >= pd.Timestamp("2007-06-01")]
    eval_bil = evaluate(strat_bil, ew, rf_bil, with_calmar=False)
    eval_zero = evaluate(strat_zero, ew, rf_shy, with_calmar=False)
    res["cash_leg_attribution"] = {
        "cash_proxy": CASH_PRIMARY,
        "avg_cash_weight": diag.get("avg_cash_weight"),
        "worst_cash_proxy_month_shy": float(rf_shy.reindex(idx).min()),
        "cash_contribution_cagr_pp": (res["strategy"]["cagr"] - ann_metrics(strat_zero.reindex(idx), rf_shy)["cagr"]) * 100,
        "bil_overlap": {
            "window": [str(bil_win[0].date()), str(bil_win[-1].date())] if bil_win else None,
            "shy": ann_metrics(strat_shy.reindex(bil_win), rf_shy) if bil_win else None,
            "bil": ann_metrics(strat_bil.reindex(bil_win), rf_bil) if bil_win else None,
        },
        "zero_yield": ann_metrics(strat_zero.reindex(idx), rf_shy),
        "verdict_under": {"SHY": prim["verdict"], "BIL": eval_bil["verdict"], "zero": eval_zero["verdict"]},
        "verdict_depends_on_proxy": bool(len({prim["verdict"], eval_bil["verdict"], eval_zero["verdict"]}) > 1),
    }

    # universe-expansion sensitivities (add EEM/GLD/DBC; do NOT re-optimize)
    sens = {}
    for add in SENS_ADDS + ["ALL3"]:
        cols = UNIVERSE + (SENS_ADDS if add == "ALL3" else [add])
        cols = [c for c in cols if c in prices]
        sub = pd.DataFrame({c: prices[c] for c in cols}).sort_index()
        sub = sub[sub.index >= pd.Timestamp("2000-06-01")]
        reb = first_trading_days(sub.index)
        rf_s = monthly_on_grid(prices[CASH_PRIMARY], reb)
        sx, _ = run_strategy(sub, reb, rf_s, START)
        ewx = ew_on_grid(sub, reb, START)
        ix = sx.index.intersection(ewx.index)
        met = ann_metrics(sx.reindex(ix), rf_s)
        met["delta_sharpe_pt"] = met["sharpe"] - ann_metrics(ewx.reindex(ix), rf_s)["sharpe"]
        met["window"] = [str(ix[0].date()), str(ix[-1].date())]
        sens[f"add_{add}"] = met
    res["sensitivities"] = sens

    res["usability"] = {**diag,
                        "suggested_role": "defensive / all-weather sleeve — NOT a core return engine",
                        "account_size": "unbounded for an individual (≤6 mega-cap ETFs; monthly, low churn)"}
    print("TREND002_JSON_BEGIN")
    print(json.dumps(res, indent=2, default=str))
    print("TREND002_JSON_END")


if __name__ == "__main__":
    main()
