import os, sys, statistics as st
from datetime import date
WT = "C:/LLM-RAG-APP/momentum-daily-coldstart/apps/backend"
os.environ["WORKBENCH_FACTOR_DATA_DB_PATH"] = "C:/LLM-RAG-APP/ai-trading-app/apps/backend/data/factor_data_full.duckdb"
for p in (WT, WT + "/scripts"):
    if p not in sys.path:
        sys.path.insert(0, p)
import pandas as pd
import time as _t
from backtest_momentum_stage2 import BACKSTOP_DAYS, INITIAL_EQUITY, TURNOVER_COST_BPS, WEIGHT_DRIFT_PCT, compute_day
from backtest_momentum_stage3 import select_n, weigh
from backtest_momentum_stage4 import build_market_proxy, gross_series, N, SIZING, CAP_ON
from app.factor_data.backtest import _CachedPriceStore
from app.factor_data.store import FactorDataStore

t0 = _t.perf_counter()
store = FactorDataStore(read_only=True)
tdays = store.trading_days(date(2005, 1, 1), date(2026, 6, 13))
cached = _CachedPriceStore(store)
proxy = build_market_proxy(store, tdays, os.environ["WORKBENCH_FACTOR_DATA_DB_PATH"])
g = gross_series(proxy, "C")
gv = [g[d] for d in tdays]
print("[5B] proxy+gross ready %.1fm" % ((_t.perf_counter() - t0) / 60), flush=True)

day_scores = {}
for i, d in enumerate(tdays):
    ds = compute_day(cached, d)
    if ds is not None:
        day_scores[d] = ds
    if (i + 1) % 1000 == 0:
        print("[5B] scored %d/%d %.1fm" % (i + 1, len(tdays), (_t.perf_counter() - t0) / 60), flush=True)
all_tk = sorted({t for ds in day_scores.values() for t in ds.ranked})
sectors = store.get_sectors(all_tk)
print("[5B] scoring done %d usable %.1fm" % (len(day_scores), (_t.perf_counter() - t0) / 60), flush=True)

pxc = {}
def pxmap(t):
    if t not in pxc:
        df = store.get_prices(t, tdays[0], tdays[-1], adjusted=True)
        pxc[t] = {dt.date(): float(c) for dt, c in zip(df["date"], df["close"]) if c is not None and float(c) > 0}
    return pxc[t]

HZ = 63
def sim_forward(i0, policy):
    equity = INITIAL_EQUITY
    sleeves = {}
    cash = 0.0
    target_w = {}
    last_px = {}
    held = set()
    curve = []
    total_turn = 0.0
    trades = 0
    since = 0
    prev_rank = None
    applied = 1.0
    active = False
    deploy_i = None
    first_names = None
    end = min(i0 + HZ, len(tdays) - 1)
    for k in range(i0, end + 1):
        d = tdays[k]
        gg = gv[k]
        if held:
            for tk in list(held):
                p = pxmap(tk).get(d)
                if p is not None:
                    lp = last_px.get(tk, 0.0)
                    if lp > 0:
                        sleeves[tk] *= 1.0 + (p / lp - 1.0)
                    last_px[tk] = p
            equity = sum(sleeves.values()) + cash
        curve.append(equity)
        if not active:
            ok = (gg >= 0.60 - 1e-9) if policy == "M" else (abs(gg - 0.98) < 1e-9)
            if not ok:
                continue
            active = True
        ds = day_scores.get(d)
        if ds is None:
            since += 1
            continue
        target = select_n(ds, held, prev_rank, N, sectors, CAP_ON)
        prev_rank = ds.rank
        changed = set(target) != held
        regime_flip = abs(gg - applied) > 1e-9
        drift = False
        if held and equity > 0 and target_w:
            drift = max(abs(sleeves.get(tk, 0.0) / equity - target_w.get(tk, 0.0)) for tk in held) > WEIGHT_DRIFT_PCT
        if not (changed or regime_flip or drift or since >= BACKSTOP_DAYS):
            since += 1
            continue
        if gg <= 0.0 or not target:
            neww = {}
        else:
            base = weigh(store, target, d, sizing=SIZING, n=N, cap_on=CAP_ON, sectors=sectors)
            neww = {tk: w * gg for tk, w in base.items()}
        cash_w = 1.0 - sum(neww.values())
        curw = {tk: (sleeves.get(tk, 0.0) / equity if equity > 0 else 0.0) for tk in set(sleeves) | set(neww)}
        cur_cash = cash / equity if equity > 0 else 0.0
        turn = 0.5 * (sum(abs(neww.get(x, 0.0) - curw.get(x, 0.0)) for x in set(neww) | set(curw)) + abs(cash_w - cur_cash))
        total_turn += turn
        if deploy_i is None:
            deploy_i = k
            first_names = tuple(sorted(neww))
        equity *= 1.0 - (TURNOVER_COST_BPS / 1e4) * turn
        sleeves = {tk: w * equity for tk, w in neww.items()}
        cash = cash_w * equity
        last_px = {tk: (pxmap(tk).get(d) or 0.0) for tk in neww}
        target_w = dict(neww)
        held = set(neww)
        applied = gg
        trades += 1
        since = 0
    peak = curve[0]
    mdd = 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return {"curve": curve, "turn": total_turn, "trades": trades, "deploy_i": deploy_i, "first_names": first_names, "maxdd": mdd, "final": curve[-1]}

epis = []
for k in range(1, len(tdays)):
    if abs(gv[k] - 0.60) < 1e-9 and abs(gv[k - 1] - 0.60) > 1e-9 and gv[k - 1] != 1.0:
        epis.append(k)
print("[5B] %d inception episodes; running M vs H ..." % len(epis), flush=True)

def eq_at(res, h):
    c = res["curve"]
    return c[min(h, len(c) - 1)]

rows = []
for n, i0 in enumerate(epis):
    M = sim_forward(i0, "M")
    H = sim_forward(i0, "H")
    th = None
    for k in range(i0, min(i0 + HZ, len(tdays) - 1) + 1):
        if abs(gv[k] - 0.98) < 1e-9:
            th = k
            break
    wait = (th - i0) if th is not None else None
    row = {"i0": i0, "date": str(tdays[i0]), "wait": wait,
           "M_final": M["final"], "H_final": H["final"], "M_dd": M["maxdd"], "H_dd": H["maxdd"],
           "M_turn": M["turn"], "H_turn": H["turn"],
           "M_ret_wait": (eq_at(M, wait) / INITIAL_EQUITY - 1.0) if wait is not None else (M["final"] / INITIAL_EQUITY - 1.0)}
    for h in (10, 21, 42, 63):
        row["pnl_diff_%d" % h] = (eq_at(M, h) - eq_at(H, h)) / INITIAL_EQUITY
    if M["first_names"] and H["first_names"]:
        a, b = set(M["first_names"]), set(H["first_names"])
        row["name_overlap"] = len(a & b) / max(len(a | b), 1)
    else:
        row["name_overlap"] = None
    rows.append(row)
    if (n + 1) % 25 == 0:
        print("[5B] %d/%d %.1fm" % (n + 1, len(epis), (_t.perf_counter() - t0) / 60), flush=True)

df = pd.DataFrame(rows)
df.to_csv("C:/Users/jayw0_ithkvux/AppData/Local/Temp/actualbook_5B.csv", index=False)

def pct(s, p):
    x = sorted([v for v in s if pd.notna(v)])
    return x[int(p * (len(x) - 1))] if x else float("nan")

print("\n===== STEP 5B ACTUAL-BOOK RESULTS (n=%d, horizon=%dd) =====" % (len(df), HZ))
for h in (10, 21, 42, 63):
    s = df["pnl_diff_%d" % h] * 100
    print(" PnL diff (M-H) @%2dd (%% equity): median %+5.2f  mean %+5.2f  p5 %+5.2f  p95 %+5.2f"
          % (h, s.median(), s.mean(), pct(df["pnl_diff_%d" % h], 0.05) * 100, pct(df["pnl_diff_%d" % h], 0.95) * 100))
print(" maxDD: M median %.2f%%  H median %.2f%%  (M-H) median %+.2f  p5 %+.2f"
      % (100 * df["M_dd"].median(), 100 * df["H_dd"].median(), 100 * (df["M_dd"] - df["H_dd"]).median(), 100 * pct(df["M_dd"] - df["H_dd"], 0.05)))
print(" turnover over %dd: M median %.2f  H median %.2f  (M-H) median %+.2f"
      % (HZ, df["M_turn"].median(), df["H_turn"].median(), (df["M_turn"] - df["H_turn"]).median()))
mw = df["M_ret_wait"] * 100
print(" M book return during H wait (+=missed upside, -=avoided loss): median %+5.2f%%  mean %+5.2f%%  p5 %+5.2f%%  p95 %+5.2f%%  neg-share %.0f%%"
      % (mw.median(), mw.mean(), pct(df["M_ret_wait"], 0.05) * 100, pct(df["M_ret_wait"], 0.95) * 100, 100 * (mw < 0).mean()))
for h in (10, 21, 42, 63):
    nd = 100 * (df["wait"].isna() | (df["wait"] > h)).mean()
    print(" H NOT deployed within %2dd: %.0f%%" % (h, nd))
w = df["wait"].dropna()
print(" H wait (when deployed <=%dd): median %.0f  mean %.1f  max %.0f" % (HZ, w.median(), w.mean(), w.max()))
print(" first-portfolio overlap M vs H (Jaccard) median: %.2f" % df["name_overlap"].median())
df["yr"] = df["date"].str[:4].astype(int)
for lo, hi, lbl in [(2005, 2012, "2005-12"), (2013, 2019, "2013-19"), (2020, 2026, "2020-26")]:
    sub = df[(df["yr"] >= lo) & (df["yr"] <= hi)]
    if len(sub):
        print("  [%s] n=%d  PnLdiff@21d med %+.2f%%  ddDiff(M-H) med %+.2f%%  Mret_wait med %+.2f%%"
              % (lbl, len(sub), 100 * sub["pnl_diff_21"].median(), 100 * (sub["M_dd"] - sub["H_dd"]).median(), 100 * sub["M_ret_wait"].median()))
print("\n[5B DONE]", flush=True)
