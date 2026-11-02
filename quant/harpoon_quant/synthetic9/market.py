"""Registered toy worlds, known only through past features at each core call."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import numpy as np

from ..core import digest, timestamp
from ..frontier.contracts import require
from . import ORIGIN

SYMBOLS = ["AAPL", "MSFT", "BTC/USD", "ETH/USD"]
LOTS = [1.0, 1.0, 0.02, 0.2]
WORLDS = ["NULL", "TREND_BREAK", "LIQUIDITY_SHOCK"]
FEATURES = [s + "_" + f for s in SYMBOLS for f in ("PREVIOUS_RETURN", "PREVIOUS8_VOL")]


def ms(value: str) -> int:
    return round(timestamp(value).timestamp() * 1000)


def schedule(index: int) -> list[bool]:
    return [True] * 72 if index >= 2 else [h % 24 < 7 for h in range(72)]


def world(seed: int, name: str, protocol: dict[str, Any]) -> dict[str, Any]:
    require(type(seed) is int and seed >= 0 and name in WORLDS, "WORLD_CONFIG")
    require(protocol["origin"] == ORIGIN, "PROTOCOL_ORIGIN")
    rng = np.random.default_rng(np.random.SeedSequence([seed, WORLDS.index(name), 707]))
    warmup, forward = protocol["warmup_weeks"], protocol["evaluation_weeks"]
    require(24 <= warmup <= 100 and 1 <= forward <= 16, "WORLD_BUDGET")
    previous = rng.normal(0, 0.01, size=(8, 4)).tolist()
    prices = np.array([200.0, 400.0, 60000.0, 3000.0])
    cases = []
    began = timestamp(protocol["first_warmup_start_utc"])
    sigma = np.array([0.001, 0.0012, 0.0017, 0.002])
    for week in range(warmup + forward):
        start = began + timedelta(days=7 * week)
        history = np.asarray(previous[-8:])
        features = (
            np.column_stack(
                (history[-1], np.maximum(history.std(axis=0, ddof=1), 1e-5))
            )
            .ravel()
            .tolist()
        )
        paths: list[list[list[float]]] = [[] for _ in SYMBOLS]
        base = prices.copy()
        for h in range(72):
            common = rng.normal()
            shocks = 0.5 * common + np.sqrt(0.75) * rng.normal(size=4)
            for j in range(4):
                if not schedule(j)[h]:
                    values = [float(prices[j])] * 4
                else:
                    opening = prices[j]
                    if j < 2 and h > 0 and h % 24 == 0:
                        opening *= np.exp(rng.normal(0, 0.003))
                    drift = 0.0
                    if name == "TREND_BREAK":
                        drift = 0.0007 if week < warmup + forward // 2 else -0.0007
                    if name == "LIQUIDITY_SHOCK" and week >= warmup and h == 24:
                        opening *= 0.96
                    change = drift - sigma[j] ** 2 / 2 + sigma[j] * shocks[j]
                    closing = opening * np.exp(change)
                    wick = abs(rng.normal()) * sigma[j] * 0.35
                    values = [
                        float(opening),
                        float(max(opening, closing) * (1 + wick)),
                        float(min(opening, closing) / (1 + wick)),
                        float(closing),
                    ]
                    prices[j] = closing
                paths[j].append([float(v / base[j]) for v in values])
        previous.append(np.log(prices / base).tolist())
        cases.append(
            {
                "id": f"SYN9-{name}-{seed}-{week}",
                "start_at": start.isoformat(),
                "features_known_at": (start - timedelta(seconds=1)).isoformat(),
                "label_end": (start + timedelta(hours=72)).isoformat(),
                "known_at": (start + timedelta(hours=72, seconds=1)).isoformat(),
                "features": features,
                "ohlc": paths,
                "dividend_cash": np.zeros((4, 72)).tolist(),
                "schedule": [schedule(j) for j in range(4)],
                "source_hash": digest(
                    {"synthetic_world": name, "seed": seed, "week": week}
                ),
                "entry_prices": base.tolist(),
            }
        )
    return {
        "schema": "HARPOON_JOINT_PATH_DATASET_1",
        "origin": ORIGIN,
        "symbols": SYMBOLS,
        "feature_names": FEATURES,
        "price_basis": "SPLIT_ADJUSTED_TO_SAMPLE_ENTRY_SHARE_UNIT",
        "dividend_basis": "FRACTION_OF_ENTRY_PRICE_PER_ENTRY_SHARE",
        "corporate_actions_covered": True,
        "corporate_action_scope": "SYNTHETIC_NONE_GENERATED_NOT_PROVIDER_CERTIFICATION",
        "samples": cases,
    }


def quotes(
    case: dict[str, Any], hour: int, *, multiplier: float = 1.0
) -> dict[str, Any]:
    require(type(hour) is int and 0 <= hour <= 72, "HOUR_DOMAIN")
    at = ms(case["start_at"]) + hour * 3_600_000
    result = {}
    for j, symbol in enumerate(SYMBOLS):
        relative = (
            1.0
            if hour == 0
            else case["ohlc"][j][hour][0]
            if hour < 72 and schedule(j)[hour]
            else case["ohlc"][j][hour - 1][3]
        )
        mid = case["entry_prices"][j] * relative
        spread_bps = (2 if j < 2 else 6) * multiplier
        result[symbol] = {
            "bid": mid * (1 - spread_bps / 20000),
            "ask": mid * (1 + spread_bps / 20000),
            "quote_at": at,
            "received_at": at,
        }
    return result


def available(name: str, week: int, warmup: int, hour: int, index: int) -> bool:
    if name == "LIQUIDITY_SHOCK" and week >= warmup and 48 <= hour <= 60:
        return False
    return index >= 2 or hour % 24 < 7
