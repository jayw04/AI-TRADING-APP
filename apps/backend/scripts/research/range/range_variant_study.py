import pathlib
from datetime import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.config import get_settings

ET=ZoneInfo("America/New_York"); root=pathlib.Path(get_settings().bars_cache_root)
UNI=['MSFT','NVDA','AMD','TSLA','GOOGL','AMZN','META','NFLX','INTC','MU','F','KO','DIS','BAC','XOM','WMT','SPY','QQQ']
OR_END=time(10,0);OPEN_T=time(9,30);RTH_END=time(16,0);FLAT_T=time(15,55)
STOP_BUF=0.005;COST=2*5.0/1e4
def load(sym):
    d=root/sym/'5Min'
    if not d.exists(): return None
    df=pd.concat([pd.read_parquet(f) for f in d.glob('*.parquet')]).drop_duplicates('t').sort_values('t')
    df['et']=df['t'].dt.tz_convert(ET); df['day']=df['et'].dt.date; df['tod']=df['et'].dt.time
    return df
data={s:load(s) for s in UNI}; data={s:d for s,d in data.items() if d is not None}
daily={}
for s,df in data.items():
    r=df[(df['tod']>=OPEN_T)&(df['tod']<RTH_END)].groupby('day').agg(c=('c','last'),h=('h','max'),l=('l','min'))
    daily[s]=r.reset_index()
def score(s,day):
    d=daily[s]; d=d[d['day']<day].tail(21)
    if len(d)<21: return None
    c=d['c'].values;h=d['h'].values;l=d['l'].values
    tr=np.maximum(h[1:]-l[1:],np.maximum(abs(h[1:]-c[:-1]),abs(l[1:]-c[:-1])))
    atrp=tr[-14:].mean()/c[-1]
    net=abs(c[-1]-c[-21]);path=np.abs(np.diff(c[-21:])).sum();er=net/path if path>0 else 0
    if atrp<0.03: return None
    w=1.0 if er<0.3 else (0.1 if er>0.5 else 0.5)
    return atrp*(1-er)*w
days=sorted(set().union(*[set(df['day'].unique()) for df in data.values()]))
selected={}
for day in days:
    sc=[(s,score(s,day)) for s in data]; sc=[(s,v) for s,v in sc if v is not None]
    selected[day]=set(s for s,_ in sorted(sc,key=lambda x:-x[1])[:5])
spy=data['SPY']; regime={}; spy_ok={}
for day,g in spy.groupby('day'):
    rt=g[(g['tod']>=OPEN_T)&(g['tod']<RTH_END)].sort_values('et')
    if len(rt)<3: continue
    rr=rt['c'].iloc[-1]/rt['o'].iloc[0]-1; regime[day]='up' if rr>0.003 else('down' if rr<-0.003 else 'chop')
    tp=(rt['h']+rt['l']+rt['c'])/3; vw=((tp*rt['v']).cumsum()/rt['v'].cumsum()).values
    for (_,row),v in zip(rt.iterrows(),vw): spy_ok[(day,row['tod'])]=bool(row['c']>=v)

def replay(rth, ol, oh, mode):
    rth=rth.sort_values('et').reset_index(drop=True)
    tp=(rth['h']+rth['l']+rth['c'])/3; vwap=((tp*rth['v']).cumsum()/rth['v'].cumsum()).values
    mid=ol+0.5*(oh-ol); stop=ol*(1-STOP_BUF)
    idx=[i for i in range(len(rth)) if OR_END<=rth['tod'][i]<=FLAT_T]
    if len(idx)<3: return (False,'no_entry',None)
    if mode=='A':
        ei=None
        for i in idx:
            if rth['l'][i]<=ol: ei=i; epx=ol; break
            if rth['h'][i]>=oh: return (False,'tbe',None)
        if ei is None: return (False,'no_entry',None); 
        walk=[i for i in idx if i>=ei]
    else:
        armed=False; ei=None; epx=None
        for i in idx:
            if not armed and rth['l'][i]<=ol: armed=True
            if armed:
                conf = rth['c'][i]>=mid if mode=='mid' else rth['c'][i]>=vwap[i]
                if conf:
                    if mode=='vwap_gate' and not spy_ok.get((rth['day'][i],rth['tod'][i]),True): continue
                    ei=i; epx=rth['c'][i]; break
        if ei is None: return (False,'no_entry',None)
        walk=[i for i in idx if i>ei]
    res=None
    for i in walk:
        if rth['l'][i]<=stop: res=('loss_stop',stop); break
        if rth['h'][i]>=oh: res=('win_target',oh); break
    if res is None: res=('eod_exit', rth['c'][walk[-1]] if walk else epx)
    oc,px=res; return (True,oc,(px-epx)/epx-COST)

rows=[]
for s,df in data.items():
    for day,g in df.groupby('day'):
        rth=g[(g['tod']>=OPEN_T)&(g['tod']<RTH_END)]
        orb=rth[rth['tod']<OR_END]
        if len(orb)<3 or len(rth[rth['tod']>=OR_END])<3: continue
        ol=orb['l'].min(); oh=orb['h'].max()
        if oh<=ol: continue
        rec=dict(day=day,regime=regime.get(day,'?'),sel=s in selected.get(day,set()))
        for v in ('A','mid','vwap','vwap_gate'): rec[v]=replay(rth[['et','o','h','l','c','v','tod','day']],ol,oh,v)
        rows.append(rec)
R=pd.DataFrame(rows)
def summ(sub,label):
    print(f'\n=== {label} (n={len(sub)}) ===')
    print(f'{"variant":11}{"fill%":>7}{"win%":>7}{"stop%":>7}{"avgPnL":>8}{"total":>8}{"PF":>6} | {"up":>7}{"down":>8}{"chop":>8}')
    for v,nm in [('A','A base'),('mid','E-mid'),('vwap','E-vwap'),('vwap_gate','E-vwap+gate')]:
        ent=[r for r in sub[v] if r[0]]; n=len(sub); f=len(ent)
        w=sum(1 for e in ent if e[1]=='win_target'); st=sum(1 for e in ent if e[1]=='loss_stop')
        pn=[e[2] for e in ent if e[2] is not None]; avg=np.mean(pn) if pn else 0; tot=np.sum(pn) if pn else 0
        g=sum(p for p in pn if p>0); ls=-sum(p for p in pn if p<0); pf=g/ls if ls>0 else 9.99
        rg={}
        for reg in ('up','down','chop'):
            rp=[sub[v].iloc[i][2] for i in range(len(sub)) if sub.iloc[i]['regime']==reg and sub[v].iloc[i][0] and sub[v].iloc[i][2] is not None]
            rg[reg]=np.mean(rp)*100 if rp else float('nan')
        print(f'{nm:11}{100*f/n:7.1f}{100*w/f if f else 0:7.1f}{100*st/f if f else 0:7.1f}{avg*100:8.3f}{tot*100:8.1f}{pf:6.2f} | {rg["up"]:+7.3f}{rg["down"]:+8.3f}{rg["chop"]:+8.3f}')
summ(R[R['sel']].reset_index(drop=True),'SELECTED TOP-5/day')
sel=R[R['sel']].reset_index(drop=True)
ud=sorted(sel['day'].unique()); med=ud[len(ud)//2]
print(f'\n[train=before {med}, test={med} onward]')
summ(sel[sel['day']<med].reset_index(drop=True),'TRAIN half (early ~3mo)')
summ(sel[sel['day']>=med].reset_index(drop=True),'TEST half (late ~3mo, out-of-sample)')
