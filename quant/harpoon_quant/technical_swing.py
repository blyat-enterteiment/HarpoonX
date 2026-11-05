"""Price/volume-only opening-range decisions on a completed five-minute grid."""

from __future__ import annotations

import math
from bisect import bisect_left
from itertools import pairwise
from statistics import median
from typing import Any

from .core import finite

BAR = 300_000
OPENING_BARS = 12
LOOKBACK = 20
RECIPES = ("CONFIRMED", "SIMPLE", "CASH")


class TechnicalSwing:
    """Index raw market bars once. Each decision reads only timestamped prefixes."""

    def __init__(
        self, dataset: dict[str, Any], symbols: list[str], benchmark: str
    ) -> None:
        if dataset.get("schema") != "HARPOON-ULTIMATE-DATA-1":
            raise ValueError("TECHNICAL_DATASET_SCHEMA")
        if not symbols or len(set(symbols)) != len(symbols) or benchmark in symbols:
            raise ValueError("TECHNICAL_UNIVERSE")
        self.symbols = sorted(symbols)
        self.benchmark = benchmark
        self.sessions = dataset["sessions"]
        self.opens = [s["open"] for s in self.sessions]
        if any(
            a["close"] >= b["open"] for a, b in pairwise(self.sessions)
        ):
            raise ValueError("OVERLAPPING_SESSIONS")
        self.bars: dict[str, dict[int, dict[str, Any]]] = {}
        for series in dataset["series"]:
            symbol = series["symbol"]
            if symbol not in {*symbols, benchmark}:
                continue
            raw = series["bars"]
            by_time = {b["t"]: b for b in raw}
            if symbol in self.bars or len(raw) != len(by_time):
                raise ValueError("DUPLICATE_MARKET_DATA")
            self.bars[symbol] = by_time
        if set(self.bars) != {*symbols, benchmark}:
            raise ValueError("TECHNICAL_SERIES_REQUIRED")
        self.splits = [(e["symbol"], e["at"]) for e in dataset.get("splitEvents", [])]

    def _window(
        self, symbol: str, opening: int, start: int, end: int, asof: int
    ) -> list[dict[str, Any]]:
        result = []
        for i in range(start, end):
            at = opening + i * BAR
            bar = self.bars[symbol].get(at)
            if (
                bar is None
                or bar["end"] != at + BAR
                or not at + BAR <= bar["availableAt"] <= asof
            ):
                raise ValueError("INCOMPLETE_OR_UNAVAILABLE_BARS")
            op, high, low, close = (
                finite(bar[k], k, True) for k in ("o", "h", "l", "c")
            )
            if (
                not low <= min(op, close) <= max(op, close) <= high
                or finite(bar["v"], "VOLUME") < 0
            ):
                raise ValueError("INVALID_OHLCV")
            result.append(bar)
        return result

    def decision(self, asof: int) -> dict[str, Any]:
        if type(asof) is not int:
            raise ValueError("DECISION_TIMESTAMP_MS")
        opening = asof - OPENING_BARS * BAR - 1000
        i = bisect_left(self.opens, opening)
        if (
            i >= len(self.opens)
            or self.opens[i] != opening
            or asof + BAR >= self.sessions[i]["close"]
        ):
            raise ValueError("DECISION_MUST_BE_OPEN_PLUS_60_MINUTES_AND_ONE_SECOND")
        rows: list[dict[str, Any]] = []
        refusals: dict[str, str] = {}
        for symbol in self.symbols:
            try:
                if i < LOOKBACK:
                    raise ValueError("VOLUME_WARMUP")
                if any(
                    s == symbol and self.opens[i - LOOKBACK] <= t <= asof
                    for s, t in self.splits
                ):
                    raise ValueError("SPLIT_ACROSS_VOLUME_LOOKBACK")
                stock = self._window(symbol, opening, 0, OPENING_BARS, asof)
                sector = self._window(self.benchmark, opening, 0, OPENING_BARS, asof)
                previous = []
                for prior in self.opens[i - LOOKBACK : i]:
                    previous.append(
                        sum(b["v"] for b in self._window(symbol, prior, 10, 12, asof))
                    )
                baseline = median(previous)
                if baseline <= 0:
                    raise ValueError("NO_COMPARABLE_VOLUME")
                level = max(b["h"] for b in stock[:6])
                floor = min(b["l"] for b in stock[:6])
                price = stock[-1]["c"]
                relative = math.log(price / stock[0]["o"]) - math.log(
                    sector[-1]["c"] / sector[0]["o"]
                )
                rvol = sum(b["v"] for b in stock[-2:]) / baseline
                if price <= level:
                    raise ValueError("NO_BREAKOUT")
                rows.append(
                    {
                        "symbol": symbol,
                        "relative": relative,
                        "rvol": rvol,
                        "level": level,
                        "price": price,
                        "stop_distance": price - floor,
                        "confirmed": stock[-2]["c"] > level
                        and relative > 0
                        and rvol > 1,
                    }
                )
            except ValueError as exc:
                refusals[symbol] = str(exc)
        ranked = sorted(rows, key=lambda r: (-r["relative"], r["symbol"]))
        return {
            "schema": "HARPOON_TECHNICAL_OPENING_RANGE_1",
            "decision_at": asof,
            "planned_entry_at": opening + (OPENING_BARS + 1) * BAR,
            "ranked": ranked,
            "refusals": refusals,
            "simple": next(iter(ranked), None),
            "confirmed": next((row for row in ranked if row["confirmed"]), None),
            "execution_allowed": False,
        }
