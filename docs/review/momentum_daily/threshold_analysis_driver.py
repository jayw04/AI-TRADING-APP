import os, sys, json
from pathlib import Path
from datetime import date
WT = "C:/LLM-RAG-APP/momentum-daily-coldstart/apps/backend"
os.environ["WORKBENCH_FACTOR_DATA_DB_PATH"] = "C:/LLM-RAG-APP/ai-trading-app/apps/backend/data/factor_data_full.duckdb"
for p in (WT, WT + "/scripts"):
    if p not in sys.path: sys.path.insert(0, p)
import pandas as pd
from backtest_momentum_stage4 import build_market_proxy, gross_series, C_GROSS, C_BAND, MA_DAYS
from app.factor_data.store import FactorDataStore

start, end = date(2005,1,1), date(2026,6,13)
store = FactorDataStore(read_only=True)
tdays = store.trading_days(start, end)
print(f"[a] window {tdays[0]}..{tdays[-1]} {len(tdays)} days", flush=True)
proxy = build_market_proxy(store, tdays, os.environ["WORKBENCH_FACTOR_DATA_DB_PATH"])
print(f"[a] proxy built; 200d-MA days={int(proxy['ma'].notna().sum())}", flush=True)
g = gross_series(proxy, "C")   # graduated regime, the deployed variant
days = list(proxy.index)
idx = proxy["idx"]
gvals = [g[d] for d in days]
# save regime series for reuse
pd.DataFrame({"date": days, "gross": gvals, "idx": [float(idx.loc[d]) for d in days]}).to_csv("C:/Users/jayw0_ithkvux/AppData/Local/Temp/regime_series.csv", index=False)
print("[a] regime series saved", flush=True)

# ---- state distribution (exclude warm-up 1.0 = pre-MA) ----
from collections import Counter
valid = [(d,v) for d,v in zip(days,gvals) if abs(v-1.0)>1e-9]  # drop fail-open warmup
warm = len(gvals) - len(valid)
c = Counter(round(v,2) for _,v in valid)
tot = len(valid)
print(f"\n=== STATE DISTRIBUTION (graduated C), n={tot} post-warmup days (warmup 1.0 days dropped: {warm}) ===")
for lv in (0.98,0.60,0.15):
    print(f"  gross {lv}: {c[lv]:5d}  {100*c[lv]/tot:5.1f}%")

# helper: forward proxy return and maxDD over horizon h (sessions), from position i
lvls = [float(idx.loc[d]) for d in days]
def fwd_ret(i,h):
    j=min(i+h,len(lvls)-1)
    return lvls[j]/lvls[i]-1.0 if lvls[i]>0 else float('nan')
def fwd_maxdd(i,h):
    j=min(i+h,len(lvls)-1); peak=lvls[i]; mdd=0.0
    for k in range(i,j+1):
        peak=max(peak,lvls[k]); mdd=min(mdd, lvls[k]/peak-1.0)
    return mdd

# index by position for state transitions
gv = gvals
# ---- 0.60 ENTRIES (transition into mid from a different state) ----
entries=[]  # (i, prior_state)
for i in range(1,len(gv)):
    if abs(gv[i]-0.60)<1e-9 and abs(gv[i-1]-0.60)>1e-9:
        entries.append((i, gv[i-1]))
def within(i, target, h):
    for k in range(i+1, min(i+1+h, len(gv))):
        if abs(gv[k]-target)<1e-9: return True
    return False
def dwell(i):
    k=i
    while k<len(gv) and abs(gv[k]-0.60)<1e-9: k+=1
    return k-i, (gv[k] if k<len(gv) else None)  # dwell length, exit state
import statistics as st
asc = [e for e in entries if e[1] in (0.15,) or (e[1]!=0.98 and abs(e[1]-1.0)>1e-9)]  # from below/warmup-ish
desc= [e for e in entries if abs(e[1]-0.98)<1e-9]  # from above (deteriorating)
print(f"\n=== 0.60 (mid) INCEPTION EPISODES: {len(entries)} entries ({len(desc)} descending from 0.98, {len(entries)-len(desc)} ascending from 0.15/other) ===")
w5 = sum(within(i,0.15,5) for i,_ in entries); w10=sum(within(i,0.15,10) for i,_ in entries)
u5 = sum(within(i,0.98,5) for i,_ in entries); u10=sum(within(i,0.98,10) for i,_ in entries)
dwl=[dwell(i)[0] for i,_ in entries]
ex = Counter(dwell(i)[1] for i,_ in entries)
n=len(entries)
print(f"  P(-> 0.15 within 5 sessions):  {w5}/{n} = {100*w5/n:4.1f}%")
print(f"  P(-> 0.15 within 10 sessions): {w10}/{n} = {100*w10/n:4.1f}%")
print(f"  P(-> 0.98 within 5 sessions):  {u5}/{n} = {100*u5/n:4.1f}%")
print(f"  P(-> 0.98 within 10 sessions): {u10}/{n} = {100*u10/n:4.1f}%")
print(f"  dwell at 0.60 (sessions): median {st.median(dwl):.0f}  mean {st.mean(dwl):.1f}  p90 {sorted(dwl)[int(0.9*len(dwl))]:.0f}")
print(f"  exit resolution: -> up(0.98) {ex[0.98]} ({100*ex[0.98]/n:.0f}%) | -> down(0.15) {ex[0.15]} ({100*ex[0.15]/n:.0f}%)")

# ---- forward outcomes: seeding at 0.60 entries vs 0.98 entries ----
entries98=[]
for i in range(1,len(gv)):
    if abs(gv[i]-0.98)<1e-9 and abs(gv[i-1]-0.98)>1e-9:
        entries98.append(i)
def agg(idxs,h):
    rs=[fwd_ret(i,h) for i in idxs]; dds=[fwd_maxdd(i,h) for i in idxs]
    return st.mean(rs), st.median(rs), st.mean(dds)
print(f"\n=== FORWARD PROXY OUTCOMES after inception (mean ret / median ret / mean maxDD) ===")
for h in (10,21):
    m=agg([i for i,_ in entries],h); hh=agg(entries98,h)
    print(f"  h={h:2d}d  seed@0.60(n={len(entries)}): ret {100*m[0]:+5.2f}% / {100*m[1]:+5.2f}% med / DD {100*m[2]:5.2f}%   |   seed@0.98(n={len(entries98)}): ret {100*hh[0]:+5.2f}% / {100*hh[1]:+5.2f}% med / DD {100*hh[2]:5.2f}%")

# ---- Policy H waiting cost: from each 0.60 entry, time & proxy return until next 0.98 ----
waits=[]; missed=[]; nevr=0
for i,_ in entries:
    j=None
    for k in range(i, len(gv)):
        if abs(gv[k]-0.98)<1e-9: j=k; break
    if j is None: nevr+=1; continue
    waits.append(j-i); missed.append(lvls[j]/lvls[i]-1.0)
print(f"\n=== POLICY H (wait for 0.98) COST, measured from each 0.60 entry (n={len(entries)}) ===")
print(f"  sessions waited until next 0.98: median {st.median(waits):.0f}  mean {st.mean(waits):.1f}  (never reached before series end: {nevr})")
mg=[x for x in missed]
print(f"  proxy return during the wait (0.60->0.98): mean {100*st.mean(mg):+5.2f}%  median {100*st.median(mg):+5.2f}%  (positive = missed upside by waiting; negative = drawdown avoided)")
neg=sum(1 for x in mg if x<0)
print(f"  fraction of waits where the interim return was NEGATIVE (Policy H avoided a drawdown): {neg}/{len(mg)} = {100*neg/len(mg):.0f}%")
print("\n[DONE]")
