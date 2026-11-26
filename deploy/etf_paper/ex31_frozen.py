"""ASTRA EX31 funded hysteresis economic ledger. Research only, no broker actions."""
from dataclasses import dataclass
import csv,math,random
@dataclass(frozen=True)
class Bar:
    date:str
    underlying_close:float
    bull_open:float
    bull_close:float
    bear_open:float
    bear_close:float
def load(path):
    with open(path,newline="") as f:
        rows=[Bar(r["date"],*(float(r[k]) for k in ("underlying_close","bull_open","bull_close","bear_open","bear_close"))) for r in csv.DictReader(f)]
    if len(rows)<61 or any(rows[i].date>=rows[i+1].date for i in range(len(rows)-1)):raise ValueError("Require >=61 unique ordered bars")
    if any(min(x.underlying_close,x.bull_open,x.bull_close,x.bear_open,x.bear_close)<=0 for x in rows):raise ValueError("Invalid price")
    return rows
def ema(a,n):
    v=a[0];k=2/(n+1);out=[]
    for x in a:v+=k*(x-v);out.append(v)
    return out
def features(rows):
    c=[x.underlying_close for x in rows]
    e12,e30=ema(c,12),ema(c,30)
    macd=[x-y for x,y in zip(e12,e30)]
    signal=ema(macd,9)
    gain=loss=0.;rsi=[]
    for i,x in enumerate(c):
        d=x-c[i-1] if i else 0.
        gain=(gain*13+max(d,0))/14 if i>14 else gain+max(d,0)/14
        loss=(loss*13+max(-d,0))/14 if i>14 else loss+max(-d,0)/14
        rsi.append(50. if i<14 else 100-100/(1+gain/max(loss,1e-12)))
    # dimensionless MACD histogram, EMA gap and RSI center; scale deliberately fixed
    score=[.45*((m-s)/max(x*.005,1e-9))+.30*((x-e)/max(x*.02,1e-9))+.25*((r-50)/10)
           for x,m,s,e,r in zip(c,macd,signal,e30,rsi)]
    return score
def decision(policy,prev,s,entry=.60,exit_ratio=.4):
    if policy=="cash":return 0
    if policy=="l50":return 1 if s>0 else -1 if s<0 else 0
    if policy=="hyst":
        if prev==0:return 1 if s>=entry else -1 if s<=-entry else 0
        if prev==1:return -1 if s<=-entry else 0 if s<entry*exit_ratio else 1
        return 1 if s>=entry else 0 if s>-entry*exit_ratio else -1
    raise ValueError("Unknown policy")
def run(rows,policy,fee=.002,entry=.60,exit_ratio=.4,capital=20000.,gross=.2):
    if not 0<=fee<.1 or not 0<=gross<=1 or entry<=0 or not 0<=exit_ratio<1:raise ValueError("Invalid config")
    sc=features(rows);cash=capital;qb=qs=0.;state=0;costs=turnover=0.;navs=[];transitions=0
    for i in range(60,len(rows)):
        # only yesterday's signal can be used at today's open
        new=decision(policy,state,sc[i-1],entry,exit_ratio)
        if new!=state:transitions+=1
        state=new
        b=rows[i];open_nav=cash+qb*b.bull_open+qs*b.bear_open
        wb,ws=(gross,0.) if state==1 else (0.,gross) if state==-1 else (0.,0.)
        budget=open_nav
        for _ in range(100):
            nb=budget*wb/b.bull_open;ns=budget*ws/b.bear_open
            n=abs(nb-qb)*b.bull_open+abs(ns-qs)*b.bear_open
            updated=open_nav-fee*n
            if abs(updated-budget)<1e-9:budget=updated;break
            budget=updated
        nb=budget*wb/b.bull_open;ns=budget*ws/b.bear_open
        traded=abs(nb-qb)*b.bull_open+abs(ns-qs)*b.bear_open
        cost=fee*traded
        cash=open_nav-nb*b.bull_open-ns*b.bear_open-cost
        if cash < -1e-7:raise AssertionError("Negative cash")
        costs+=cost;turnover+=traded;qb,qs=nb,ns
        nav=cash+qb*b.bull_close+qs*b.bear_close
        if nav<=0:raise AssertionError("Nonpositive NAV")
        navs.append(nav)
    final=rows[-1]
    notional=qb*final.bull_close+qs*final.bear_close
    cash+=notional*(1-fee);costs+=fee*notional;turnover+=notional
    navs[-1]=cash
    peak=capital;dd=0.;prev=capital;logret=[]
    for nav in navs:
        logret.append(math.log(nav/prev));prev=nav
        peak=max(peak,nav);dd=max(dd,1-nav/peak)
    return dict(policy=policy,final_usd=round(cash,2),return_pct=round(100*(cash/capital-1),4),
                max_dd_pct=round(100*dd,4),costs_usd=round(costs,2),
                turnover_usd=round(turnover,2),transitions=transitions,
                daily_log_returns=logret)
def bootstrap(a,b,rep=2000,block=10,seed=31):
    x=[u-v for u,v in zip(a["daily_log_returns"],b["daily_log_returns"])]
    rng=random.Random(seed);n=len(x);samples=[]
    for _ in range(rep):
        z=[]
        while len(z)<n:
            start=rng.randrange(n)
            z.extend(x[(start+k)%n] for k in range(block))
        samples.append(sum(z[:n]))
    samples.sort()
    return dict(observed_log_advantage=sum(x),ci95=[samples[int(.025*rep)],samples[int(.975*rep)]],
                p_nonpositive=sum(y<=0 for y in samples)/rep)
def compare(rows,fee=.002):
    policies={k:run(rows,k,fee) for k in ("cash","l50","hyst")}
    result={"policies":{k:{a:b for a,b in v.items() if a!="daily_log_returns"} for k,v in policies.items()},
            "bootstrap_hyst_vs_l50":bootstrap(policies["hyst"],policies["l50"]),
            "data_kind":"user supplied authentic OHLC or clearly labeled synthetic; no live orders"}
    return result
if __name__=="__main__":
    import argparse,json
    a=argparse.ArgumentParser();a.add_argument("csv");a.add_argument("--fee",type=float,default=.002);z=a.parse_args()
    print(json.dumps(compare(load(z.csv),z.fee),indent=2))
