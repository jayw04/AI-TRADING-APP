#!/usr/bin/env python3
"""TREND-001 backtest — Multi-Asset Time-Series Trend (frozen pre-registration v1.0).

Runs the pre-registered primary design and the pre-registered sensitivities, computes the three-way
verdict (Approved / Diversifier / Rejected) with a block-bootstrap ΔSharpe CI + a power/MDE check, and
emits a JSON evidence blob to stdout. Research-only; Yahoo adjusted-close (= total-return basis).

Primary rule (frozen): hold asset i at each monthly rebalance iff
    TR_12m_skip1(i) > 0  AND  price(i) > MA200(i)
long-only · inverse-vol risk budget · vol-target 10% (63d lookback, leverage cap 1.0 = de-risk to
cash) · cash leg = BIL (T-bill proxy) · 5 bps/side costs · monthly (last trading day) rebalance.
Verdict vs the equal-weight buy-and-hold same-universe benchmark. Seeded; deterministic.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

import numpy as np
import pandas as pd

UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "UUP"]
BENCH_TREND = ["DBMF", "KMLM"]  # descriptive secondary (short overlap)
CASH_ETF = "BIL"                # T-bill total-return proxy
SEED = 20260708
VOL_TARGET = 0.10
VOL_LB = 63
COST_BPS = 5.0
BLOCK = 6                       # months (block bootstrap; vol-target autocorrelation)
N_BOOT = 5000
START = "2007-03-01"           # common window (UUP inception)
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
    """Annualized metrics from a monthly-return series (m) with monthly rf."""
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


def run_strategy(adj: pd.DataFrame, rf_m: pd.Series, *, use_mom=True, use_ma=True,
                 skip1=True, cost_bps=COST_BPS, cash_yield=True) -> pd.Series:
    """Return the monthly net return series for a design variant."""
    dret = adj.pct_change()
    ma200 = adj.rolling(200).mean()
    vol = dret.rolling(VOL_LB).std() * np.sqrt(252)
    # last trading day of each month
    rebal = adj.index.to_series().resample("ME").last().dropna()
    rebal = [d for d in rebal if d >= pd.Timestamp(START)]
    prev_w = pd.Series(0.0, index=adj.columns)
    out = {}
    for k in range(len(rebal) - 1):
        t, t1 = rebal[k], rebal[k + 1]
        # signal
        hold = pd.Series(True, index=adj.columns)
        if use_mom:
            lag = 13 if skip1 else 12
            base = 1 if skip1 else 0
            if k - lag < 0:
                continue
            mom = adj.loc[rebal[k - base]] / adj.loc[rebal[k - lag]] - 1
            hold &= (mom > 0)
        if use_ma:
            hold &= (adj.loc[t] > ma200.loc[t])
        hold = hold.fillna(False)
        held = [c for c in adj.columns if hold.get(c, False) and np.isfinite(vol.loc[t, c]) and vol.loc[t, c] > 0]
        w = pd.Series(0.0, index=adj.columns)
        if held:
            iv = pd.Series({c: 1.0 / vol.loc[t, c] for c in held})
            iv /= iv.sum()  # inverse-vol weights (sum 1 among held)
            # ex-ante portfolio vol (diagonal approx) → leverage to target, capped at 1.0 (de-risk only)
            port_vol = float(np.sqrt(((iv * vol.loc[t, held]) ** 2).sum()))
            lev = min(VOL_TARGET / port_vol, 1.0) if port_vol > 0 else 0.0
            w[held] = (iv * lev).values
        cash_w = 1.0 - w.sum()
        turnover = (w - prev_w).abs().sum()
        cost = turnover * cost_bps / 1e4
        prev_w = w
        # realized next-month return
        r_assets = (adj.loc[t1] / adj.loc[t] - 1)
        r = float((w * r_assets.reindex(w.index).fillna(0.0)).sum())
        r += cash_w * (float(rf_m.get(t1 + pd.offsets.MonthEnd(0), 0.0)) if cash_yield else 0.0)
        # index by the calendar month-end label (matches resample("ME") benchmark index) so the
        # strategy/benchmark align on intersection — the return value is the true trading-date return.
        out[t1 + pd.offsets.MonthEnd(0)] = r - cost
    return pd.Series(out).sort_index()


def block_bootstrap_delta(m_s: pd.Series, m_b: pd.Series, rf: pd.Series, metric: str) -> dict:
    """Circular block bootstrap CI on Δmetric (strategy − benchmark) over paired monthly returns."""
    idx = m_s.dropna().index.intersection(m_b.dropna().index)
    s, b, r = m_s.reindex(idx).values, m_b.reindex(idx).values, rf.reindex(idx).fillna(0.0).values
    n = len(idx)
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(n / BLOCK))

    def dmetric(si, bi, ri):
        ms = pd.Series(si); mb = pd.Series(bi); rr = pd.Series(ri)
        a = ann_metrics(ms, rr)[metric]; c = ann_metrics(mb, rr)[metric]
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


def main() -> None:
    prices = {}
    fails = []
    for sym in UNIVERSE + BENCH_TREND + [CASH_ETF]:
        try:
            prices[sym] = fetch_yahoo_adj(sym)
        except Exception as e:  # noqa: BLE001
            fails.append((sym, str(e)[:80]))
    adj = pd.DataFrame({s: prices[s] for s in UNIVERSE if s in prices}).sort_index()
    adj = adj[adj.index >= pd.Timestamp("2006-01-01")]  # warm-up for MA200/vol before START
    # cash monthly return (BIL); pre-inception → 0
    rf_m = (prices[CASH_ETF].resample("ME").last().pct_change()
            if CASH_ETF in prices else pd.Series(dtype="float64"))

    # benchmark: equal-weight buy-and-hold, monthly rebalanced
    m_ret = adj.resample("ME").last().pct_change()
    ew = m_ret.mean(axis=1)  # equal-weight of available names each month
    ew = ew[ew.index >= pd.Timestamp(START)]

    strat = run_strategy(adj, rf_m)
    idx = strat.index.intersection(ew.index)
    strat, ewb = strat.reindex(idx), ew.reindex(idx)

    res = {
        "meta": {"universe": UNIVERSE, "start": START, "n_months": len(idx),
                 "window": [str(idx[0].date()), str(idx[-1].date())],
                 "vol_target": VOL_TARGET, "vol_lb": VOL_LB, "cost_bps": COST_BPS,
                 "block": BLOCK, "n_boot": N_BOOT, "seed": SEED, "fetch_fails": fails},
        "strategy": ann_metrics(strat, rf_m),
        "benchmark_ew": ann_metrics(ewb, rf_m),
    }
    # secondary descriptive benchmarks
    for name, series in [("SPY", m_ret.get("SPY"))]:
        if series is not None:
            res[f"bench_{name}"] = ann_metrics(series.reindex(idx), rf_m)
    for tb in BENCH_TREND:
        if tb in prices:
            tbm = prices[tb].resample("ME").last().pct_change().reindex(idx).dropna()
            res[f"bench_{tb}_overlap"] = ann_metrics(tbm, rf_m)

    # verdict inputs
    res["delta_sharpe"] = block_bootstrap_delta(strat, ewb, rf_m, "sharpe")
    res["delta_calmar"] = block_bootstrap_delta(strat, ewb, rf_m, "calmar")
    sdd, bdd = res["strategy"]["maxdd"], res["benchmark_ew"]["maxdd"]
    res["maxdd_reduction_rel"] = float((abs(bdd) - abs(sdd)) / abs(bdd)) if bdd else None

    # verdict
    ds = res["delta_sharpe"]; dc = res["delta_calmar"]; mdr = res["maxdd_reduction_rel"]
    powered = abs(ds["point"]) >= ds["mde_95"]
    if ds["excludes_zero"]:
        verdict = "Approved"
    elif mdr is not None and mdr >= 0.25 and dc["excludes_zero"] and dc["point"] > 0:
        verdict = "Diversifier"
    else:
        verdict = "Rejected"
    res["power"] = {"mde_95_delta_sharpe": ds["mde_95"], "observed_delta_sharpe": ds["point"],
                    "adequately_powered": bool(powered)}
    res["verdict"] = verdict
    res["verdict_note"] = ("" if powered else
                           "POWER-LIMITED: |ΔSharpe| < MDE — a Rejected on ΔSharpe may be a power failure, "
                           "not evidence of no effect; the Diversifier path is the realistic bar.")

    # sensitivities (headline metrics + ΔSharpe point only)
    sens = {}
    for name, kw in [("ma_only", dict(use_mom=False)), ("tr_only", dict(use_ma=False)),
                     ("no_skip_12m", dict(skip1=False)), ("zero_cash", dict(cash_yield=False)),
                     ("costs_2x", dict(cost_bps=COST_BPS * 2))]:
        sret = run_strategy(adj, rf_m, **kw).reindex(idx)
        met = ann_metrics(sret, rf_m)
        met["delta_sharpe_pt"] = (met["sharpe"] - res["benchmark_ew"]["sharpe"]
                                  if met["sharpe"] is not None else None)
        sens[name] = met
    for excl in ["UUP", "DBC"]:
        sub = adj.drop(columns=[excl])
        subm = sub.resample("ME").last().pct_change()
        ewx = subm.mean(axis=1).reindex(idx)
        sx = run_strategy(sub, rf_m).reindex(idx)
        sens[f"ex_{excl}"] = {**ann_metrics(sx, rf_m),
                              "delta_sharpe_pt": (ann_metrics(sx, rf_m)["sharpe"] - ann_metrics(ewx, rf_m)["sharpe"])}
    res["sensitivities"] = sens

    # usability / capacity block
    res["usability"] = {
        "avg_positions": None, "note": "turnover/positions summarized in the MD from the run log",
        "worst_drawdown": res["strategy"]["maxdd"],
        "cost_drag_2x_vs_1x_cagr_pp": (sens["costs_2x"]["cagr"] - res["strategy"]["cagr"]) * 100
        if sens["costs_2x"]["cagr"] is not None else None,
        "suitability": "core (if Approved) / defensive (if Diversifier)",
    }
    print("TREND001_JSON_BEGIN")
    print(json.dumps(res, indent=2, default=str))
    print("TREND001_JSON_END")


if __name__ == "__main__":
    main()
