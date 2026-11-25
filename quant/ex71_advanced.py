"""EX71 robust sizing and causal close-based trailing exit; research only."""
from math import isfinite, log1p, expm1, sqrt
from statistics import mean, stdev
from datetime import date
from ex71_replay import Episode

def robust_kelly(episodes: list[Episode], symbol: str, day: date,
                 cap: float, minimum: int=20) -> tuple[float,float]:
    """Half Kelly on stressed empirical returns. Score is worst-case grid utility,
    not a statistical confidence bound. Returns weight and score."""
    if not isfinite(cap) or not 0<=cap<=1/3 or minimum<2:
        raise ValueError("invalid sizing parameters")
    values=[]; last=None
    for e in sorted(episodes,key=lambda e:(e.known,e.mature)):
        if e.symbol!=symbol or e.mature>=day: continue
        if e.known>=e.mature or not isfinite(e.net_log):
            raise ValueError("invalid episode")
        if last is None or e.known>last:
            values.append(expm1(e.net_log)); last=e.mature
    if len(values)<minimum or cap==0: return 0.,0.
    penalty=2*stdev(values)/sqrt(len(values))
    stressed=[max(-1.,r-penalty) for r in values]+[-.35]
    def utility(f):
        return mean(log1p(f*r) for r in stressed)
    best=max(range(101),key=lambda k:utility(cap*k/100))
    weight=cap*best/200
    score=utility(weight)
    return (weight,score) if score>0 else (0.,0.)

def gain_exit(marks: list[float], hist: list[float], age: int) -> str | None:
    """Marks are split/dividend-aware campaign wealth ratios, through known close.
    Exit at next open, not at the trigger price. No intraday stop guarantee."""
    if not marks or len(hist)<3 or age<0 or any(not isfinite(x) or x<=0 for x in marks) or any(not isfinite(x) for x in hist[-3:]):
        raise ValueError("invalid campaign history")
    current=marks[-1]; peak=max(1.,max(marks))
    if current<=.94: return "loss_guard"
    if peak>=1.05 and current<=peak*(.95 if peak>=1.15 else .97):
        return "gain_trail"
    if age>=20: return "time"
    if hist[-1]<hist[-2]<hist[-3]: return "momentum"
    return None
