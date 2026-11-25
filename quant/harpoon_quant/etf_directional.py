"""EX71 isolated shadow-only ETF signal layer. No broker or order interface."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from math import isfinite, log
from typing import Mapping, Sequence

PAIRS = (("TQQQ", "SQQQ"), ("SPXL", "SPXS"), ("TMF", "TMV"))
UNIVERSE = frozenset(s for pair in PAIRS for s in pair)
MAX_GROSS = 1 / 3

@dataclass(frozen=True)
class Bar:
    known_at: datetime
    adjusted_close: float

def ema(values: Sequence[float], span: int) -> list[float]:
    result = [values[0]]
    for value in values[1:]:
        result.append(result[-1] + 2 / (span + 1) * (value - result[-1]))
    return result

def histogram(bars: Sequence[Bar], decision_at: datetime) -> list[float]:
    if decision_at.utcoffset() is None or len(bars) < 60:
        raise ValueError("timezone and 60 completed bars required")
    if any(b.known_at.utcoffset() is None or b.known_at > decision_at
           or not isfinite(b.adjusted_close) or b.adjusted_close <= 0 for b in bars):
        raise ValueError("invalid or future observation")
    if any(a.known_at >= b.known_at for a, b in zip(bars, bars[1:])):
        raise ValueError("unordered or duplicate observations")
    prices = [log(b.adjusted_close) for b in bars]
    macd = [a-b for a,b in zip(ema(prices,12), ema(prices,30))]
    return [a-b for a,b in zip(macd,ema(macd,9))]

def shadow_targets(panel: Mapping[str, Sequence[Bar]], decision_at: datetime,
                   held_sessions: Mapping[str, int], gross: float = MAX_GROSS,
                   mode: str = "inflection") -> dict[str, float]:
    """Equal family sleeves; no capital reservation or execution implied."""
    if set(panel) != UNIVERSE or not set(held_sessions) <= UNIVERSE:
        raise ValueError("ETF universe mismatch")
    if not isfinite(gross) or not 0 <= gross <= MAX_GROSS:
        raise ValueError("gross outside research cap")
    if mode not in ("inflection", "cross"):
        raise ValueError("unknown mode")
    if any(type(n) is not int or n < 1 for n in held_sessions.values()):
        raise ValueError("invalid holding age")
    clocks = [tuple(b.known_at for b in panel[s]) for s in sorted(UNIVERSE)]
    if any(c != clocks[0] for c in clocks[1:]):
        raise ValueError("unaligned panel")
    h = {s: histogram(panel[s], decision_at) for s in UNIVERSE}
    targets = dict.fromkeys(sorted(UNIVERSE), 0.0)
    for pair in PAIRS:
        held = [s for s in pair if s in held_sessions]
        if len(held) > 1:
            raise ValueError("opposite holdings in one family")
        if held:
            s = held[0]
            a,b,c = h[s][-3:]
            if held_sessions[s] < 20 and not (c < b < a):
                targets[s] = gross / 3
                continue
        candidates = []
        for s in pair:
            if s in held:
                continue
            a,b,c = h[s][-3:]
            signal = (c < 0 and c > b and b <= a) if mode == "inflection" else (b <= 0 < c)
            if signal:
                candidates.append((c-b,s))
        if candidates:
            targets[max(candidates)[1]] = gross / 3
    return targets
