# SYNTHETIC-ONLY illustration for RANGE-002 data-feasibility report v0.1 (section 6). ILLUSTRATIVE, not validator-calibrated.
# No file or network I/O; imports only numpy and scipy.stats.norm. No market data. All assumptions are in the code and report 6.5.
# Versions used for reproduction: Python 3.12.10, numpy 2.2.6, scipy 1.18.1.
# Command: apps/backend/.venv python -I range002_synthetic_power_illustration.py   (no arguments; runtime ~40 s)
# All sections share ONE RNG (default_rng(20261010)); figures reproduce only from a full top-to-bottom run.
import numpy as np
from scipy.stats import norm
rng=np.random.default_rng(20261010)
z=norm.ppf
def mde(n,sd,deff,alpha,power=0.8):
    return (z(1-alpha)+z(power))*sd*np.sqrt(deff/n)
def pw(m,n,sd,deff,alpha):
    se=sd*np.sqrt(deff/n); return 1-norm.cdf(z(1-alpha)-m/se)
print("MDE (R) for 80% power, one-sided; sd=1.3, deff=1.2")
for n in (150,300,600,1200):
    print(n, [round(mde(n,1.3,1.2,a),3) for a in (0.05,0.025,0.0125)])
print("Power at true mean m; n, alpha=.05 / .025; sd1.3 deff1.2")
for n in (150,300,600):
    for m in (0.05,0.10,0.15,0.20):
        print(n,m,round(pw(m,n,1.3,1.2,0.05),2),round(pw(m,n,1.3,1.2,0.025),2))
# Holm over {G4,G5}: both required. G4 z4 ~ N(m/se,1); G5 diff has var ~ 2x (indep baseline) -> se*sqrt(2) ; corr between z4,z5 = 1/sqrt2
def holm_power(m4,m5,n,sd,deff,reps=400000):
    se4=sd*np.sqrt(deff/n); se5=se4*np.sqrt(2)
    rho=1/np.sqrt(2)
    e=rng.standard_normal((reps,2))
    z4=m4/se4+e[:,0]; z5=m5/se5+rho*e[:,0]+np.sqrt(1-rho**2)*e[:,1]
    p=np.stack([1-norm.cdf(z4),1-norm.cdf(z5)],1)
    lo=p.min(1); hi=p.max(1)
    holm=(lo<=0.025)&(hi<=0.05)
    sep=(p[:,0]<=0.05)&(p[:,1]<=0.05)
    return holm.mean(), sep.mean()
print("P4 pass prob for G4&G5 (Holm m=2 vs separate .05 each); baseline mean R=-0.03 so diff=m+0.03")
for n in (300,600):
  for m in (0.05,0.10,0.15,0.20):
    print(n,m,[round(x,2) for x in holm_power(m,m+0.03,n,1.3,1.2)])
# max-stat critical value K=7
print("max-stat 95% critical value (one-sided) K=7, equicorr rho")
for rho in (0.3,0.6,0.8,0.9,0.95):
    C=np.full((7,7),rho); np.fill_diagonal(C,1)
    L=np.linalg.cholesky(C); x=rng.standard_normal((400000,7))@L.T
    print(rho, round(np.quantile(x.max(1),0.95),3), "single:",round(z(.95),3))
# type-I of day-clustered percentile (recentered-null) bootstrap under skewed null
def trade_R(size):
    # skewed: stop -1 (p .55), small win 0.5 (p .2), big win +3 (p .25)? make mean zero by solving
    return None
def skew_null(nd,tpd_lambda=0.5,reps=3000,B=1000):
    # days with Poisson trades; R: -1 w.p. .6, +1.5 w.p. .4 -> mean 0 ; add 'cost' none
    rej=0
    for _ in range(reps):
        k=rng.poisson(tpd_lambda,nd)
        tot=k.sum()
        if tot<5: continue
        R=np.where(rng.random(tot)<0.4,1.5,-1.0)
        day_id=np.repeat(np.arange(nd),k)
        s=np.bincount(day_id,weights=R,minlength=nd); c=k.astype(float)
        obs=s.sum()/c.sum()
        idx=rng.integers(0,nd,(B,nd))
        bm=s[idx].sum(1)/np.maximum(c[idx].sum(1),1)
        # recentered null: p = share of (bm - obs) >= obs
        p=np.mean((bm-obs)>=obs)
        rej+= p<=0.05
    return rej/reps
for nd,lam in ((500,0.3),(1000,0.3),(1000,0.6)):
    print("type-I skewed null days",nd,"trades/day",lam,"expected trades",int(nd*lam),round(skew_null(nd,lam,reps=1500),3))
# chain power (G4-type tests only): P3a max-stat (crit 2.0 corresponds to rho ~0.9: rho 0.8 gives 2.155, rho 0.9 gives 2.023; the winner's-curse section below uses rho 0.8), P3b alpha .05 on shrunk effect, P4 holm
print("chain: P3a selection-aware test, P3b, P4 (G4 only holm .025) probability all pass; sd1.3 deff1.2; winner's-curse shrink 0.7 for P3b")
for m in (0.05,0.10,0.15,0.20):
    out=[]
    for n3a,n3b,n4 in ((300,150,300),(600,300,600)):
        se=lambda n:1.3*np.sqrt(1.2/n)
        p3a=1-norm.cdf(2.0-m/se(n3a))
        p3b=pw(m*0.7,n3b,1.3,1.2,0.05)  # conservative: selected exit's true effect shrunk
        p4=pw(m*0.7,n4,1.3,1.2,0.025)
        out.append((round(p3a,2),round(p3b,2),round(p4,2),round(p3a*p3b*p4,3)))
    print(m,out)
# winner's curse: K=7 candidates all true mean m, corr .8, se for n=300 trades; expected max observed
for m in (0.0,0.05):
    C=np.full((7,7),0.8); np.fill_diagonal(C,1); L=np.linalg.cholesky(C)
    se=1.3*np.sqrt(1.2/300)
    x=m+se*(rng.standard_normal((200000,7))@L.T)
    print("winner curse m",m,"E[max obs]",round(x.max(1).mean(),3),"bias",round(x.max(1).mean()-m,3),"se",round(se,3))
# control false alarms
for a in (0.05,0.01,0.001):
    print("alpha",a,"P(any of 2 independent negative-control tests fire in a correct engine)",round(1-(1-a)**2,4))
# PF vs mean R
print("PF/mean R: p=win rate, b=avg win/avg loss (R units, loss=1R)")
for p in (0.35,0.40,0.45,0.50):
    b=1.3*(1-p)/p
    print(p,"b for PF1.3 =",round(b,2),"mean R =",round(p*b-(1-p),3))
# trades per day implied
print("300 trades / 1004 days =",round(300/1004,3),"; 150/505=",round(150/505,3))
