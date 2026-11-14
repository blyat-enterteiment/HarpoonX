"""C51 dual-clock decision engine. Read-only causal signal generation.

A is an early price crossing known after a completed bar; B is late
screener confirmation. B can never authorize or backdate A.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite


@dataclass(frozen=True)
class Bar:
    at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Signal:
    symbol: str
    known_at: datetime
    early: bool
    late: bool
    early_first_at: datetime | None
    late_first_at: datetime | None
    admissible_now: bool
    reason: str


@dataclass
class ClockState:
    last_at: datetime | None = None
    first_early_at: datetime | None = None
    first_late_at: datetime | None = None
    halted: bool = False


def update(
    symbol: str, state: ClockState, bar: Bar, *,
    official_prior_close: float, session_open: float,
    historical_same_clock_expected_volume: float | None,
    completed_bar_minutes: int = 5,
) -> Signal:
    """No fills. Volume expected from earlier sessions, not future bars."""
    if completed_bar_minutes not in (1, 5):
        raise ValueError("C51_UNREGISTERED_TIMEFRAME")
    if (not symbol or bar.at.utcoffset() is None
            or not all(isfinite(x) and x > 0 for x in
                       (bar.open, bar.high, bar.low, bar.close,
                        official_prior_close, session_open))
            or not isfinite(bar.volume) or bar.volume < 0
            or not bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high):
        raise ValueError("C51_INVALID_CAUSAL_INPUT")
    known_at = bar.at + timedelta(minutes=completed_bar_minutes)
    if state.last_at is not None and bar.at <= state.last_at:
        raise ValueError("C51_REPLAY_OR_CLOCK_REVERSAL")
    if state.last_at is not None and bar.at - state.last_at != timedelta(minutes=completed_bar_minutes):
        state.halted = True
    state.last_at = bar.at
    if state.halted:
        return Signal(symbol, known_at, False, False, state.first_early_at,
                      state.first_late_at, False, "SOURCE_GAP_FAIL_CLOSED")
    # A completed close, not the unsequenced intrabar HIGH, triggers
    # the earliest provably causal bar-close signal.
    early = bar.close >= official_prior_close * 1.05
    if early and state.first_early_at is None:
        state.first_early_at = known_at
    rvol_valid = (historical_same_clock_expected_volume is not None
                  and isfinite(historical_same_clock_expected_volume)
                  and historical_same_clock_expected_volume > 0)
    late = (rvol_valid and bar.close >= session_open * 1.10
            and bar.volume / historical_same_clock_expected_volume > 5)
    if late and state.first_late_at is None:
        state.first_late_at = known_at
    return Signal(symbol, known_at, early, late, state.first_early_at,
                  state.first_late_at, bool(early),
                  "EARLY_INDEPENDENT_OF_LATE" if early else "NO_EARLY_SIGNAL")
