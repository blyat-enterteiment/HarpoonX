"""EX71 research-only directional ETF allocation. No broker interface."""
from math import isfinite, log
from dataclasses import dataclass
from datetime import datetime

PAIRS = (("TQQQ","SQQQ"),("SPXL","SPXS"),("HIBL","HIBS"),("TMF","TMV"))
UNIVERSE = frozenset(s for pair in PAIRS for s in pair) | {"HCMT"}
CAP = 1/3

def ema(xs: list[float], n: int) -> list[float]:
    out = [xs[0]]
    for x in xs[1:]:
        out.append(out[-1] + 2/(n+1)*(x-out[-1]))
    return out

def histogram(prices: list[float]) -> list[float]:
    if len(prices)<60 or any(not isfinite(x) or x<=0 for x in prices):
        raise ValueError("invalid adjusted price history")
    p = [log(x) for x in prices]
    m = [a-b for a,b in zip(ema(p,12),ema(p,30))]
    return [a-b for a,b in zip(m,ema(m,9))]

@dataclass(frozen=True)
class Candidate:
    symbol: str
    known_at: datetime
    lower_net_edge: float
    adjusted_prices: tuple[float,...]

def allocate(candidates: list[Candidate], decision_at: datetime, cap: float=CAP) -> dict[str,float]:
    """Target weights only; lower_net_edge must come from independent causal calibration."""
    if decision_at.utcoffset() is None or not isfinite(cap) or not 0<=cap<=CAP:
        raise ValueError("invalid decision or cap")
    seen = set()
    eligible = []
    for c in candidates:
        if c.symbol not in UNIVERSE or c.symbol in seen:
            raise ValueError("invalid or duplicate symbol")
        seen.add(c.symbol)
        if c.known_at.utcoffset() is None or c.known_at>decision_at or not isfinite(c.lower_net_edge):
            raise ValueError("invalid causal evidence")
        h = histogram(list(c.adjusted_prices))
        if h[-1]<0 and h[-1]>h[-2] and h[-2]<=h[-3] and c.lower_net_edge>0:
            eligible.append(c)
    # Conservative single winner avoids correlated simultaneous admissions.
    if not eligible or cap==0:
        return {}
    winner = sorted(eligible,key=lambda c:(-c.lower_net_edge,c.symbol))[0]
    return {winner.symbol:cap}
