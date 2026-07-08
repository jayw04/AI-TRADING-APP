#!/usr/bin/env python3
"""TREND-001 backtest — Multi-Asset Time-Series Trend (frozen pre-registration v1.0).

Runs the pre-registered primary design and sensitivities, computes the three-way verdict
(Approved / Diversifier / Rejected) with a block-bootstrap ΔSharpe CI + a power/MDE check, and emits a
JSON evidence blob to stdout. Research-only; Yahoo adjusted-close (= total-return basis).

Primary rule (frozen): hold asset i at each monthly rebalance iff
    TR_12m_skip1(i) > 0  AND  price(i) > MA200(i)
long-only · inverse-vol risk budget · vol-target 10% (63d lookback, leverage cap 1.0 = de-risk to
cash) · cash leg = BIL (T-bill proxy) · 5 bps/side costs · **monthly, FIRST trading day** rebalance
(matches the frozen pre-registration §6). Verdict vs the equal-weight buy-and-hold same-universe
benchmark, on the same first-trading-day grid. Seeded; deterministic.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

import numpy as np
import pandas as pd

UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "UUP"]
BENCH_TREND = ["DBMF", "KMLM"]
CASH_ETF = "BIL"
SEED = 20260708
VOL_TARGET = 0.10
VOL_LB = 63
COST_BPS = 5.0
BLOCK = 6
N_BOOT = 5000
START = "2007-03-01"
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


def first_trading_days(idx: pd.DatetimeIndex, start: str) -> list:
    """First trading day of each calendar month (the frozen §6 rebalance cadence)."""
    s = idx.to_series()
    ftd = s.groupby([idx.year, idx.month]).first()
    return [pd.Timestamp(d) for d in ftd.values]  # full history; warm-up handled by the lookback skip


def run_strategy(adj: pd.DataFrame, rebal: list, rf_by_date: pd.Series, start: str, *,
                 use_mom=True, use_ma=True, skip1=True, cost_bps=COST_BPS, cash_yield=True,
                 collect_diag=False):
    dret = adj.pct_change()
    ma200 = adj.rolling(200).mean()
    vol = dret.rolling(VOL_LB).std() * np.sqrt(252)
    prev_w = pd.Series(0.0, index=adj.columns)
    out, positions, cashw, turns = {}, [], [], []
    lag = 13 if skip1 else 12
    base = 1 if skip1 else 0
    for k in range(len(rebal) - 1):
        t, t1 = rebal[k], rebal[k + 1]
        if t1 < pd.Timestamp(start) or k - lag < 0:
            continue
        hold = pd.Series(True, index=adj.columns)
        if use_mom:
            mom = adj.loc[rebal[k - base]] / adj.loc[rebal[k - lag]] - 1
            hold &= (mom > 0)
        if use_ma:
            hold &= (adj.loc[t] > ma200.loc[t])
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
        diag = {"avg_positions": float(np.mean(positions)),
                "median_positions": float(np.median(positions)),
                "avg_cash_weight": float(np.mean(cashw)),
                "annual_turnover": float(np.mean(turns) * 12),
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


def monthly_on_grid(price: pd.Series, rebal: list) -> pd.Series:
    """Return series on the rebalance grid using as-of prices (for assets outside `adj`)."""
    out = {}
    for k in range(len(rebal) - 1):
        t, t1 = rebal[k], rebal[k + 1]
        p0, p1 = price.asof(t), price.asof(t1)
        if pd.notna(p0) and pd.notna(p1) and p0 > 0:
            out[t1] = p1 / p0 - 1
    return pd.Series(out).sort_index()


def main() -> None:
    prices, fails = {}, []
    for sym in UNIVERSE + BENCH_TREND + [CASH_ETF]:
        try:
            prices[sym] = fetch_yahoo_adj(sym)
        except Exception as e:  # noqa: BLE001
            fails.append((sym, str(e)[:80]))
    adj = pd.DataFrame({s: prices[s] for s in UNIVERSE if s in prices}).sort_index()
    adj = adj[adj.index >= pd.Timestamp("2005-06-01")]  # warm-up for MA200/12-1 before START

    rebal = first_trading_days(adj.index, START)
    rf_by_date = monthly_on_grid(prices[CASH_ETF], rebal) if CASH_ETF in prices else pd.Series(dtype="float64")

    # equal-weight buy-and-hold, monthly rebalanced, on the SAME first-trading-day grid
    ew_out = {}
    for k in range(len(rebal) - 1):
        t, t1 = rebal[k], rebal[k + 1]
        if t1 < pd.Timestamp(START):
            continue
        ew_out[t1] = float((adj.loc[t1] / adj.loc[t] - 1).mean())
    ew = pd.Series(ew_out).sort_index()

    strat, diag = run_strategy(adj, rebal, rf_by_date, START, collect_diag=True)
    idx = strat.index.intersection(ew.index)
    strat, ewb = strat.reindex(idx), ew.reindex(idx)

    res = {
        "meta": {"universe": UNIVERSE, "cadence": "monthly_first_trading_day", "start": START,
                 "n_months": len(idx), "window": [str(idx[0].date()), str(idx[-1].date())],
                 "vol_target": VOL_TARGET, "vol_lb": VOL_LB, "cost_bps": COST_BPS, "block": BLOCK,
                 "n_boot": N_BOOT, "seed": SEED, "fetch_fails": fails},
        "strategy": ann_metrics(strat, rf_by_date),
        "benchmark_ew": ann_metrics(ewb, rf_by_date),
        "bench_SPY": ann_metrics(monthly_on_grid(adj["SPY"], rebal).reindex(idx), rf_by_date),
    }
    res["delta_sharpe"] = block_bootstrap_delta(strat, ewb, rf_by_date, "sharpe")
    res["delta_calmar"] = block_bootstrap_delta(strat, ewb, rf_by_date, "calmar")
    sdd, bdd = res["strategy"]["maxdd"], res["benchmark_ew"]["maxdd"]
    res["maxdd_reduction_rel"] = float((abs(bdd) - abs(sdd)) / abs(bdd)) if bdd else None

    ds, dc, mdr = res["delta_sharpe"], res["delta_calmar"], res["maxdd_reduction_rel"]
    powered = abs(ds["point"]) >= ds["mde_95"]
    if ds["excludes_zero"]:
        verdict, status = "Approved", "Completed · Approved"
    elif mdr is not None and mdr >= 0.25 and dc["excludes_zero"] and dc["point"] > 0:
        verdict, status = "Diversifier", "Completed · Diversifier"
    elif not powered:
        verdict, status = "Inconclusive", "Completed · Power-Limited · Inconclusive"
    else:
        verdict, status = "Rejected", "Completed · Rejected"
    res["power"] = {"mde_95_delta_sharpe": ds["mde_95"], "observed_delta_sharpe": ds["point"],
                    "adequately_powered": bool(powered)}
    res["verdict"] = verdict
    res["status_label"] = status
    res["secondary_label"] = ("Diversifier Candidate"
                              if (mdr is not None and mdr >= 0.25 and dc["point"] > 0) else "")

    # same-overlap comparison vs the trend ETFs (grounds "buy the ETF vs use our strategy")
    overlaps = {}
    for tb in BENCH_TREND:
        if tb in prices:
            tbm = monthly_on_grid(prices[tb], rebal)
            ov = strat.index.intersection(tbm.dropna().index)
            if len(ov) >= 6:
                overlaps[tb] = {"window": [str(ov[0].date()), str(ov[-1].date())], "n": len(ov),
                                "trend_001": ann_metrics(strat.reindex(ov), rf_by_date),
                                tb: ann_metrics(tbm.reindex(ov), rf_by_date)}
    res["same_overlap_vs_trend_etfs"] = overlaps

    # sensitivities
    sens = {}
    for name, kw in [("ma_only", dict(use_mom=False)), ("tr_only", dict(use_ma=False)),
                     ("no_skip_12m", dict(skip1=False)), ("zero_cash", dict(cash_yield=False)),
                     ("costs_2x", dict(cost_bps=COST_BPS * 2))]:
        sret, _ = run_strategy(adj, rebal, rf_by_date, START, **kw)
        sret = sret.reindex(idx)
        met = ann_metrics(sret, rf_by_date)
        met["delta_sharpe_pt"] = (met["sharpe"] - res["benchmark_ew"]["sharpe"]
                                  if met["sharpe"] is not None else None)
        sens[name] = met
    for excl in ["UUP", "DBC"]:
        sub = adj.drop(columns=[excl])
        sx, _ = run_strategy(sub, rebal, rf_by_date, START)
        sx = sx.reindex(idx)
        ewx_out = {t1: float((sub.loc[t1] / sub.loc[rebal[k]] - 1).mean())
                   for k, t1 in enumerate(rebal[1:], 0) if t1 in idx}
        ewx = pd.Series(ewx_out).reindex(idx)
        sens[f"ex_{excl}"] = {**ann_metrics(sx, rf_by_date),
                              "delta_sharpe_pt": ann_metrics(sx, rf_by_date)["sharpe"]
                              - ann_metrics(ewx, rf_by_date)["sharpe"]}
    res["sensitivities"] = sens

    # usability / capacity block (owner correction #4 — fully populated)
    res["usability"] = {
        **diag,
        "cost_drag_2x_vs_1x_cagr_pp": (sens["costs_2x"]["cagr"] - res["strategy"]["cagr"]) * 100
        if sens["costs_2x"]["cagr"] is not None else None,
        "suggested_role": "defensive / all-weather sleeve — NOT a core return engine",
        "account_size": "unbounded for an individual (≤10 mega-cap ETFs; monthly, low turnover)",
    }
    print("TREND001_JSON_BEGIN")
    print(json.dumps(res, indent=2, default=str))
    print("TREND001_JSON_END")


if __name__ == "__main__":
    main()
