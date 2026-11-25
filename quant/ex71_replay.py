"""Offline EX71 daily replay. Research only; no broker calls.
Input prices must be raw, with verified split factors and dividend events.
Daily open is a proxy, not a SIP fill.
"""
from dataclasses import dataclass
from datetime import date
from math import isfinite, log, sqrt, exp
from statistics import mean, stdev
from ex71_directional import UNIVERSE, histogram

@dataclass(frozen=True)
class Bar:
    day: date
    open: float
    close: float
    split: float = 1.0
    dividend: float = 0.0
    payable: date | None = None

@dataclass(frozen=True)
class Episode:
    symbol: str
    known: date
    mature: date
    net_log: float

def lower_edge(episodes: list[Episode], symbol: str, day: date,
               minimum: int = 20) -> float:
    # Nonoverlapping same-symbol episodes; heuristic uncertainty penalty,
    # not a certified confidence interval under serial dependence.
    xs = sorted((e for e in episodes if e.symbol == symbol and e.mature < day),
                key=lambda e: (e.known,e.mature))
    values = []
    last = None
    for e in xs:
        if e.known >= e.mature or not isfinite(e.net_log):
            raise ValueError("invalid episode")
        if last is None or e.known > last:
            values.append(e.net_log)
            last = e.mature
    if len(values) < minimum:
        return float("-inf")
    return mean(values)-2*stdev(values)/sqrt(len(values))

def replay(data: dict[str,list[Bar]], cap: float, fee: float,
           policy: str = "calibrated") -> dict:
    if set(data)!=UNIVERSE or cap not in (.2,1/3) or fee not in (.002,.004):
        raise ValueError("invalid universe or experiment")
    if policy not in ("calibrated","inflection","cross","cash","bull","kelly","gain","kelly_gain"):
        raise ValueError("invalid policy")
    days=[b.day for b in data["TQQQ"]]
    if len(days)<62 or days!=sorted(set(days)) or days[-1]>=date(2026,11,1):
        raise ValueError("invalid calendar or sealed holdout")
    hs={}
    for s,bars in data.items():
        if [b.day for b in bars]!=days:
            raise ValueError("calendar mismatch")
        f=1.; prices=[]
        for b in bars:
            if any(not isfinite(v) for v in (b.open,b.close,b.split,b.dividend)) or min(b.open,b.close,b.split)<=0 or b.dividend<0:
                raise ValueError("invalid bar")
            if b.dividend and (b.payable is None or b.payable<b.day):
                raise ValueError("invalid dividend")
            f*=b.split
            prices.append(b.close*f)
        hs[s]=histogram(prices)
    from ex71_advanced import robust_kelly, gain_exit
    advanced = policy in ("gain","kelly_gain")
    sizing = policy in ("kelly","kelly_gain")
    def signal(s,i):
        h=hs[s]
        return h[i]<0 and h[i]>h[i-1] and h[i-1]<=h[i-2]
    def exit_signal(s,i,age):
        h=hs[s]
        return age>=20 or h[i]<h[i-1]<h[i-2]
    # Counterfactual labels are generated for every inflection, regardless of admission.
    episodes=[]
    for s in sorted(data):
        b=data[s]
        for i in range(59,len(days)-2):
            if not signal(s,i): continue
            k=i+1; j=k+1
            marks=[]; units=1.; dividends=0.
            while j<len(days):
                t=j-1
                if t>k:
                    units*=b[t].split; dividends+=units*b[t].dividend
                marks.append((units*b[t].close+dividends)/b[k].open)
                stop=gain_exit(marks,hs[s][:j],j-k) if advanced else exit_signal(s,t,j-k)
                if stop: break
                j+=1
            if j>=len(days): continue
            q=1.; div=0.
            for t in range(k+1,j+1):
                q*=b[t].split
                div+=q*b[t].dividend
            r=(q*b[j].open*(1-fee)+div)/(b[k].open*(1+fee))
            episodes.append(Episode(s,days[i],days[j],log(r)))
    cash=20000.; q=0.; symbol=None; entry=0; receivables=[]
    peak=cash; dd=0.; fees=0.; entries=0; nav=cash; curve=[]
    marks=[]; basis=0.; campaign_div=0.
    for i in range(60,len(days)):
        day=days[i]
        if symbol:
            b=data[symbol][i]; q*=b.split
            if b.dividend:
                receivables.append((b.payable,q*b.dividend)); campaign_div+=q*b.dividend
        cash+=sum(v for d,v in receivables if d<=day)
        receivables=[(d,v) for d,v in receivables if d>day]
        owed=sum(v for d,v in receivables)
        if symbol and policy!="bull" and (gain_exit(marks,hs[symbol][:i],i-entry) if advanced else exit_signal(symbol,i-1,i-entry)):
            proceeds=q*data[symbol][i].open
            cash+=proceeds*(1-fee); fees+=proceeds*fee
            symbol=None; q=0.
        if not symbol and policy!="cash":
            eligible=[]
            for s in sorted(data):
                h=hs[s]
                if policy=="bull": ok=s=="TQQQ"
                elif policy=="cross": ok=h[i-1]>0>=h[i-2]
                else: ok=signal(s,i-1)
                if not ok: continue
                weight,edge=robust_kelly(episodes,s,day,cap) if sizing else (cap,lower_edge(episodes,s,day) if policy=="calibrated" else h[i-1]-h[i-2])
                if (not sizing and policy!="calibrated") or (edge>0 and weight>0): eligible.append((edge,s,weight))
            if eligible:
                _,symbol,weight=max(eligible)
                amount=min(cash/(1+fee),weight*(cash+owed)/(1+weight*fee))
                q=amount/data[symbol][i].open
                cash-=amount*(1+fee); fees+=amount*fee; entry=i; entries+=1
                marks=[]; basis=amount; campaign_div=0.
        value=q*data[symbol][i].close if symbol else 0.
        if symbol: marks.append((value+campaign_div)/basis)
        nav=cash+owed+value*(1-fee) # liquidation mark, no invented terminal fill
        if cash < -1e-7 or nav<=0: raise ArithmeticError("funding")
        peak=max(peak,nav); dd=max(dd,1-nav/peak); curve.append(nav)
    n=len(curve)
    return dict(final=nav,ret=nav/20000-1,annual=(nav/20000)**(252/n)-1,
                log_bp=10000*log(nav/20000)/n,drawdown=dd,fees=fees,
                entries=entries,sessions=n,episodes=len(episodes),curve=curve)

def compare(data: dict[str,list[Bar]]) -> list[dict]:
    return [dict(cap=cap,fee=fee,policy=p,**replay(data,cap,fee,p))
            for cap in (.2,1/3) for fee in (.002,.004)
            for p in ("cash","bull","cross","inflection","calibrated","kelly","gain","kelly_gain")]
