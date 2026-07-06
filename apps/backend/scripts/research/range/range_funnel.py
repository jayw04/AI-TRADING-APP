import pathlib
from datetime import time
from zoneinfo import ZoneInfo

import pandas as pd

from app.config import get_settings

ET = ZoneInfo("America/New_York")
root = pathlib.Path(get_settings().bars_cache_root)
UNI = ['MSFT','NVDA','AMD','TSLA','GOOGL','AMZN','META','NFLX','INTC','MU',
       'F','KO','DIS','BAC','XOM','WMT','SPY','QQQ']
OR_MIN_END = time(10,0); OPEN_T = time(9,30); RTH_END = time(16,0); FLAT_T = time(15,55)
STOP_BUF = 0.005; COST_BPS = 5.0   # per side

def load(sym):
    d = root/sym/'5Min'
    if not d.exists(): return None
    df = pd.concat([pd.read_parquet(f) for f in d.glob('*.parquet')]).drop_duplicates('t').sort_values('t')
    df['et'] = df['t'].dt.tz_convert(ET); df['day'] = df['et'].dt.date; df['tod'] = df['et'].dt.time
    return df

spy = load('SPY'); regime = {}
for day,g in spy.groupby('day'):
    rth=g[(g['tod']>=OPEN_T)&(g['tod']<=RTH_END)]
    if len(rth)>=2:
        r=rth['c'].iloc[-1]/rth['o'].iloc[0]-1
        regime[day]='up' if r>0.003 else ('down' if r<-0.003 else 'chop')

rows=[]
for sym in UNI:
    df=load(sym)
    if df is None: continue
    for day,g in df.groupby('day'):
        rth=g[(g['tod']>=OPEN_T)&(g['tod']<RTH_END)].sort_values('et')
        orb=rth[rth['tod']<OR_MIN_END]; post=rth[(rth['tod']>=OR_MIN_END)&(rth['tod']<=FLAT_T)]
        if len(orb)<3 or len(post)<3: continue
        or_low=orb['l'].min(); or_high=orb['h'].max()
        buy,sell,stop=or_low,or_high,or_low*(1-STOP_BUF)
        if sell<=buy: continue
        entry_i=None; tgt_before=False
        for i,(_,b) in enumerate(post.iterrows()):
            if b['l']<=buy: entry_i=i; break
            if b['h']>=sell: tgt_before=True; break
        if entry_i is None:
            outcome='target_before_entry' if tgt_before else 'no_reentry'; pnl=None
        else:
            after=post.iloc[entry_i:]; res=None
            for _,b in after.iterrows():
                hs=b['l']<=stop; ht=b['h']>=sell
                if hs: res=('stop',stop); break
                if ht: res=('target',sell); break
            if res is None: res=('eod',after['c'].iloc[-1])
            er,px=res; pnl=(px-buy)/buy - 2*COST_BPS/10000
            outcome={'target':'win_target','stop':'loss_stop','eod':'eod_exit'}[er]
        rows.append(dict(sym=sym,day=day,regime=regime.get(day,'?'),entry=entry_i is not None,outcome=outcome,pnl=pnl))

res=pd.DataFrame(rows); n=len(res); ent=res[res['entry']]; E=len(ent)
def pct(x): return f'{100*x/n:5.1f}%'
print(f'=== RANGE FUNNEL DIAGNOSTIC — {n} candidate-days (18 names x ~126 days) ===\n')
print('FUNNEL:')
print(f'  candidate-days                         {n}')
print(f'  buy touched before activation          {n}   (100%  — definitional: buy = OR-window low)')
print(f'  buy touched AFTER activation (=fill)    {E}   ({pct(E)})')
for k,lbl in [('win_target','   -> target after entry (WIN)'),('loss_stop','   -> stop after entry (reversal loss)'),('eod_exit','   -> no target, EOD flat exit')]:
    c=(res["outcome"]==k).sum(); print(f'  {lbl:38} {c}   ({pct(c)})')
print('  NO entry after activation:')
for k,lbl in [('target_before_entry','   -> target hit BEFORE entry'),('no_reentry','   -> never re-touched buy, no target')]:
    c=(res["outcome"]==k).sum(); print(f'  {lbl:38} {c}   ({pct(c)})')
print('\nBOTTLENECK CLASSIFICATION:')
print(f'  Entry-timing (no reentry/no target)  {pct((res["outcome"]=="no_reentry").sum())}')
print(f'  Path/sequence (target before entry)  {pct((res["outcome"]=="target_before_entry").sum())}')
print(f'  Order/exec (touched, no fill)          0.0%  (touch-to-fill model)')
print(f'  Exit/target (filled, no target->EOD) {pct((res["outcome"]=="eod_exit").sum())}')
print(f'  Signal-quality (filled -> reversal)  {pct((res["outcome"]=="loss_stop").sum())}')
print(f'  [SUCCESS: filled -> target]          {pct((res["outcome"]=="win_target").sum())}')
if E:
    w=(ent["outcome"]=="win_target").sum(); l=(ent["outcome"]=="loss_stop").sum()
    g=ent[ent.pnl>0].pnl.sum(); ls=-ent[ent.pnl<0].pnl.sum()
    print(f'\nENTERED-TRADE METRICS (net {COST_BPS}bps/side):')
    print(f'  fill rate {100*E/n:.1f}% | target-after-entry {100*w/E:.1f}% | reversal(stop) {100*l/E:.1f}%')
    print(f'  avg P&L/trade {ent.pnl.mean()*100:+.3f}% | total {ent.pnl.sum()*100:+.1f}% | profit factor {g/ls:.2f}' if ls>0 else '  PF inf')
print('\nREGIME SPLIT:')
for rg in ('up','down','chop'):
    s=res[res.regime==rg]; e=s[s.entry]
    if len(s):
        line=f'  {rg:4} {len(s):4d} cand | fill {100*s.entry.mean():4.0f}%'
        if len(e): line+=f' | win {100*(e.outcome=="win_target").mean():3.0f}% | stop {100*(e.outcome=="loss_stop").mean():3.0f}% | avgP&L {e.pnl.mean()*100:+.3f}%'
        print(line)
