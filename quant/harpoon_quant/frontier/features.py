"""Causal optional oscillator context, separate from the registered baseline16.

Engineering adapter only: adding features does not establish predictive value.
It reuses the existing MACD12/30/9, WilderRSI14, stochastic14/3/3 implementation.
"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

import numpy as np

from ..core import timestamp
from ..macd30 import indicators
from .contracts import require


def oscillator_context(
    daily: dict[str, list[dict[str, Any]]], symbols: list[str], asof: str
) -> dict[str, Any]:
    require(
        1 <= len(symbols) <= 4 and len(set(symbols)) == len(symbols),
        "OSCILLATOR24_SYMBOL_BUDGET",
    )
    now = timestamp(asof)
    features: list[float] = []
    names = []
    latest = []
    for symbol in symbols:
        rows = [r for r in daily[symbol] if r["known"] < now]
        require(len(rows) >= 150, "OSCILLATOR150_COMPLETED_DAYS")
        require(
            all(a["known"] < b["known"] for a, b in pairwise(rows)),
            "OSCILLATOR_CHRONOLOGY",
        )
        close = np.asarray([r["close"] for r in rows[-22:]], dtype=float)
        returns = np.diff(np.log(close))
        require(
            bool(np.isfinite(returns).all()) and float(np.max(np.abs(returns))) < 0.20,
            "OSCILLATOR_UNADJUSTED_DISCONTINUITY",
        )
        vol = max(float(np.std(returns, ddof=1)), 1e-8)
        x = indicators(rows)
        scale = float(close[-1]) * vol
        features.extend(
            [
                vol,
                float((close[-1] / close[-20:].mean() - 1) / vol),
                float(x["hist"][-1] / scale),
                float((x["hist"][-1] - x["hist"][-2]) / scale),
                float((x["rsi"][-1] - 50) / 50),
                float((x["k"] - x["d"]) / 100),
            ]
        )
        names.extend(
            [
                symbol.replace("/", "_") + "_" + field
                for field in (
                    "vol21",
                    "trend20_z",
                    "macd12_30_9_hist_z",
                    "macd_hist_change_z",
                    "rsi14_centered",
                    "stochastic14_3_3_diff",
                )
            ]
        )
        latest.append(rows[-1]["known"])
    return {
        "features": features,
        "feature_names": names,
        "features_known_at": max(latest).isoformat(),
        "recipe": "OSCILLATORS24_ENGINEERING_NOT_THE_REGISTERED_BASELINE16",
        "predictive_improvement_accredited": False,
        "execution_allowed": False,
    }
